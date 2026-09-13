"""Calibration wrapper for any prediction model (Layer 1).

Wraps a base model with a :class:`BaseCalibrator`. During ``fit`` the base
model is trained on a chronological in-sample slice, its out-of-sample
predictions on the tail slice calibrate the mapping, then the base model is
refit on all data. ``predict`` applies the fitted calibration so the Value
Engine receives calibrated probabilities.

Leakage stays intact: the calibration slice is strictly after the training
slice, and refitting on the full history never touches future targets.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from quantbot.analysis.calibration import BaseCalibrator
from quantbot.features.extractor import OUTCOME_TO_LABEL
from quantbot.logging import get_logger
from quantbot.models.base import BaseModel, ModelPrediction
from quantbot.schemas import Match, Prediction

logger = get_logger(__name__)


class CalibratedModel(BaseModel):
    """Post-hoc probability calibration around a base model.

    Args:
        model: The wrapped base model.
        calibrator: A fitted-on-fit calibrator (e.g. Isotonic or Platt).
        val_fraction: Chronological tail fraction used to fit the calibrator.
    """

    def __init__(
        self,
        model: BaseModel,
        calibrator: BaseCalibrator,
        val_fraction: float = 0.3,
    ) -> None:
        super().__init__()
        if not 0.0 < val_fraction < 1.0:
            raise ValueError("val_fraction must be in (0, 1)")
        self.model = model
        self.calibrator = calibrator
        self.val_fraction = val_fraction
        self.name = f"{model.name}_calibrated"
        self._calibrated = False

    def fit(self, matches: Sequence[Match]) -> None:
        ordered = self._validate_training_matches(matches)
        split = int(len(ordered) * (1.0 - self.val_fraction))
        train, val = ordered[:split], ordered[split:]

        self._calibrated = False
        if train and val:
            try:
                self.model.fit(train)
                probs = np.array(
                    [
                        [p.prob_home, p.prob_draw, p.prob_away]
                        for p in (self.model.predict(m) for m in val)
                    ],
                    dtype=float,
                )
                labels = np.array(
                    [OUTCOME_TO_LABEL[m.result.outcome] for m in val], dtype=int  # type: ignore[union-attr]
                )
                self.calibrator.fit(probs, labels)
                self._calibrated = True
            except (ValueError, RuntimeError) as exc:
                logger.warning("Calibration disabled (%s); using raw probabilities.", exc)

        # Refit the base model on the full history regardless of calibration.
        self.model.fit(ordered)
        self._is_fitted = True

    def predict(self, match: Match) -> ModelPrediction:
        self._check_fitted()
        base = self.model.predict(match)
        if not self._calibrated:
            return base.model_copy(update={"model_name": self.name})

        raw = np.array([[base.prob_home, base.prob_draw, base.prob_away]], dtype=float)
        calibrated = self.calibrator.transform(raw)[0]
        return Prediction(
            match_id=match.match_id,
            model_name=self.name,
            prediction_timestamp=match.prediction_timestamp,
            prob_home=float(calibrated[0]),
            prob_draw=float(calibrated[1]),
            prob_away=float(calibrated[2]),
            confidence=base.confidence,
            score_matrix=base.score_matrix,
        )
