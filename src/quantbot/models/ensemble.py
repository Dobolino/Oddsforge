"""Ensemble layer: weighted combination of probabilistic models (Layer 1).

Combines any set of BaseModels (Poisson, Elo, ML) via a weighted average of
their outcome probabilities. Weights are either configured explicitly or fit
by minimizing the multiclass Brier score on a chronological validation slice,
which keeps weight selection leak-free.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy.optimize import minimize

from quantbot.features.extractor import OUTCOME_TO_LABEL
from quantbot.models.base import BaseModel, ModelPrediction
from quantbot.schemas import Match, Prediction


def multiclass_brier(probs: np.ndarray, labels: np.ndarray) -> float:
    """Mean Brier score for 3-class probabilities against integer labels."""

    onehot = np.zeros_like(probs)
    onehot[np.arange(len(labels)), labels] = 1.0
    return float(np.mean(np.sum((probs - onehot) ** 2, axis=1)))


class EnsembleModel(BaseModel):
    """Weighted ensemble of probabilistic sub-models.

    Args:
        models: Sub-models to combine.
        weights: Optional fixed weights (normalized to sum 1). Ignored when
            ``optimize_weights`` is True.
        optimize_weights: Fit weights by Brier minimization on a validation
            slice.
        val_fraction: Fraction of the chronological tail used for validation.
    """

    name = "ensemble"

    def __init__(
        self,
        models: Sequence[BaseModel],
        weights: Sequence[float] | None = None,
        optimize_weights: bool = False,
        val_fraction: float = 0.3,
    ) -> None:
        super().__init__()
        if not models:
            raise ValueError("ensemble requires at least one model")
        if weights is not None and len(weights) != len(models):
            raise ValueError("weights length must match number of models")
        if not 0.0 < val_fraction < 1.0:
            raise ValueError("val_fraction must be in (0, 1)")
        self.models = list(models)
        self.optimize_weights = optimize_weights
        self.val_fraction = val_fraction
        self._weights = self._normalize(weights) if weights is not None else self._uniform()

    @property
    def weights(self) -> list[float]:
        return list(self._weights)

    def _uniform(self) -> np.ndarray:
        n = len(self.models)
        return np.full(n, 1.0 / n)

    @staticmethod
    def _normalize(weights: Sequence[float]) -> np.ndarray:
        arr = np.asarray(weights, dtype=float)
        if np.any(arr < 0):
            raise ValueError("weights must be non-negative")
        total = arr.sum()
        if total <= 0:
            raise ValueError("weights must sum to a positive value")
        return arr / total

    # --- Fit ---

    def fit(self, matches: Sequence[Match]) -> None:
        ordered = self._validate_training_matches(matches)

        if self.optimize_weights:
            self._weights = self._fit_weights(ordered)

        # Final fit of every sub-model on the full training set.
        for model in self.models:
            model.fit(ordered)
        self._is_fitted = True

    def _fit_weights(self, ordered: list[Match]) -> np.ndarray:
        split = int(len(ordered) * (1.0 - self.val_fraction))
        train, val = ordered[:split], ordered[split:]
        if not train or not val:
            return self._uniform()

        # Fit each sub-model on the train slice and predict the validation slice.
        model_probs: list[np.ndarray] = []
        usable: list[int] = []
        for idx, model in enumerate(self.models):
            try:
                model.fit(train)
                preds = np.array(
                    [self._prediction_vector(model.predict(m)) for m in val], dtype=float
                )
            except (ValueError, RuntimeError):
                continue
            model_probs.append(preds)
            usable.append(idx)

        labels = np.array([OUTCOME_TO_LABEL[m.result.outcome] for m in val], dtype=int)  # type: ignore[union-attr]

        if len(usable) < 2:
            # Not enough comparable models; fall back to uniform.
            return self._uniform()

        stacked = np.stack(model_probs, axis=0)  # (n_usable, n_val, 3)

        def objective(w: np.ndarray) -> float:
            w = np.clip(w, 0.0, None)
            if w.sum() <= 0:
                return 1e9
            w = w / w.sum()
            blended = np.tensordot(w, stacked, axes=([0], [0]))  # (n_val, 3)
            blended = blended / blended.sum(axis=1, keepdims=True)
            return multiclass_brier(blended, labels)

        x0 = np.full(len(usable), 1.0 / len(usable))
        constraints = [{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}]
        bounds = [(0.0, 1.0)] * len(usable)
        result = minimize(
            objective, x0, method="SLSQP", bounds=bounds, constraints=constraints
        )
        fitted = np.clip(result.x, 0.0, None)
        fitted = fitted / fitted.sum()

        # Map optimized weights back onto the full model list (0 for unusable).
        full = np.zeros(len(self.models))
        for w, idx in zip(fitted, usable, strict=True):
            full[idx] = w
        if full.sum() <= 0:
            return self._uniform()
        return full / full.sum()

    # --- Predict ---

    @staticmethod
    def _prediction_vector(pred: Prediction) -> np.ndarray:
        return np.array([pred.prob_home, pred.prob_draw, pred.prob_away], dtype=float)

    def predict(self, match: Match) -> ModelPrediction:
        self._check_fitted()
        blended = np.zeros(3, dtype=float)
        for weight, model in zip(self._weights, self.models, strict=True):
            if weight <= 0.0:
                continue
            blended += weight * self._prediction_vector(model.predict(match))
        total = blended.sum()
        blended = blended / total if total > 0 else np.full(3, 1.0 / 3.0)

        confidence = 40.0 + 50.0 * float(blended.max())
        return Prediction(
            match_id=match.match_id,
            model_name=self.name,
            prediction_timestamp=match.prediction_timestamp,
            prob_home=float(blended[0]),
            prob_draw=float(blended[1]),
            prob_away=float(blended[2]),
            confidence=min(confidence, 95.0),
        )
