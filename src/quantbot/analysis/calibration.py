"""Probability calibration and scoring (Layer 3).

Scoring metrics: multiclass Brier score, log loss, and Expected Calibration
Error (ECE). Post-processors: isotonic regression and Platt scaling, each
fitted per class (one-vs-rest) then renormalized to a valid distribution.

Calibration must be fitted on out-of-sample predictions to be meaningful; the
walk-forward backtester (Step 09) supplies those.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

_EPS = 1e-12


def _as_2d(probs: np.ndarray) -> np.ndarray:
    arr = np.asarray(probs, dtype=float)
    if arr.ndim != 2 or arr.shape[1] < 2:
        raise ValueError("probs must be a 2D array with >= 2 columns")
    return arr


def brier_score(probs: np.ndarray, labels: np.ndarray) -> float:
    """Mean multiclass Brier score (lower is better)."""

    p = _as_2d(probs)
    y = np.asarray(labels, dtype=int)
    onehot = np.zeros_like(p)
    onehot[np.arange(len(y)), y] = 1.0
    return float(np.mean(np.sum((p - onehot) ** 2, axis=1)))


def log_loss(probs: np.ndarray, labels: np.ndarray) -> float:
    """Mean negative log-likelihood of the true class (lower is better)."""

    p = _as_2d(probs)
    y = np.asarray(labels, dtype=int)
    picked = p[np.arange(len(y)), y]
    return float(-np.mean(np.log(np.clip(picked, _EPS, 1.0))))


def expected_calibration_error(
    probs: np.ndarray, labels: np.ndarray, n_bins: int = 10
) -> float:
    """ECE over the predicted (argmax) class confidence, ``n_bins`` equal-width."""

    p = _as_2d(probs)
    y = np.asarray(labels, dtype=int)
    confidences = p.max(axis=1)
    predictions = p.argmax(axis=1)
    correct = (predictions == y).astype(float)

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(y)
    for lo, hi in zip(bins[:-1], bins[1:], strict=True):
        # Bins are lower-open, upper-closed; confidence == 1.0 lands in the last.
        in_bin = (confidences > lo) & (confidences <= hi)
        count = int(in_bin.sum())
        if count == 0:
            continue
        avg_conf = float(confidences[in_bin].mean())
        avg_acc = float(correct[in_bin].mean())
        ece += (count / n) * abs(avg_conf - avg_acc)
    return float(ece)


class BaseCalibrator(ABC):
    """Per-class one-vs-rest probability calibrator."""

    def __init__(self) -> None:
        self._models: list[object] = []
        self._n_classes: int = 0
        self._fitted = False

    @abstractmethod
    def _fit_one(self, x: np.ndarray, y: np.ndarray) -> object: ...

    @abstractmethod
    def _transform_one(self, model: object, x: np.ndarray) -> np.ndarray: ...

    def fit(self, probs: np.ndarray, labels: np.ndarray) -> BaseCalibrator:
        p = _as_2d(probs)
        y = np.asarray(labels, dtype=int)
        self._n_classes = p.shape[1]
        self._models = []
        for c in range(self._n_classes):
            target = (y == c).astype(float)
            self._models.append(self._fit_one(p[:, c], target))
        self._fitted = True
        return self

    def transform(self, probs: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("calibrator is not fitted")
        p = _as_2d(probs)
        if p.shape[1] != self._n_classes:
            raise ValueError("column count differs from training")
        cols = [self._transform_one(self._models[c], p[:, c]) for c in range(self._n_classes)]
        stacked = np.clip(np.column_stack(cols), 0.0, None)
        totals = stacked.sum(axis=1, keepdims=True)
        # Rows that collapse to all-zero fall back to uniform.
        uniform = np.full(self._n_classes, 1.0 / self._n_classes)
        safe = np.where(totals > 0.0, stacked / np.where(totals > 0.0, totals, 1.0), uniform)
        return safe

    def fit_transform(self, probs: np.ndarray, labels: np.ndarray) -> np.ndarray:
        return self.fit(probs, labels).transform(probs)


class IsotonicCalibrator(BaseCalibrator):
    """Non-parametric monotone calibration via isotonic regression."""

    def _fit_one(self, x: np.ndarray, y: np.ndarray) -> object:
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        iso.fit(x, y)
        return iso

    def _transform_one(self, model: object, x: np.ndarray) -> np.ndarray:
        return np.asarray(model.predict(x), dtype=float)  # type: ignore[attr-defined]


class PlattScaler(BaseCalibrator):
    """Parametric logistic (Platt) calibration."""

    def _fit_one(self, x: np.ndarray, y: np.ndarray) -> object:
        # A degenerate target (all one class) has nothing to scale.
        if len(np.unique(y)) < 2:
            return float(y.mean())
        clf = LogisticRegression()
        clf.fit(x.reshape(-1, 1), y.astype(int))
        return clf

    def _transform_one(self, model: object, x: np.ndarray) -> np.ndarray:
        if isinstance(model, float):
            return np.full(len(x), model, dtype=float)
        return np.asarray(model.predict_proba(x.reshape(-1, 1))[:, 1], dtype=float)  # type: ignore[attr-defined]
