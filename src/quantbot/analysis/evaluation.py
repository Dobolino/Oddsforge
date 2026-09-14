"""Out-of-sample evaluation: calibration curve and model comparison (Layer 3).

Walk-forward: for every match the model is fit only on earlier matches, then
predicts it. The resulting out-of-sample probabilities feed a reliability
curve (predicted confidence vs actual accuracy) and a per-model scorecard
(Brier, log loss, ECE). No random split, no leakage.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from quantbot.analysis.calibration import brier_score, expected_calibration_error, log_loss
from quantbot.data.base import BaseDataProvider
from quantbot.features.extractor import OUTCOME_TO_LABEL
from quantbot.logging import get_logger
from quantbot.models.base import BaseModel, NotFittedError
from quantbot.schemas import League, Match

logger = get_logger(__name__)


def walk_forward_probabilities(
    matches: Sequence[Match],
    model: BaseModel,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (probabilities Nx3, integer labels N) from a leak-free walk.

    Each match is predicted with the model fit only on strictly earlier
    matches. Matches the model cannot yet fit are skipped.
    """

    ordered = sorted(
        (m for m in matches if m.is_finished and m.result is not None),
        key=lambda m: m.kickoff,
    )
    probs: list[list[float]] = []
    labels: list[int] = []
    for match in ordered:
        try:
            model.fit_until(ordered, match.prediction_timestamp)
            pred = model.predict(match)
        except (ValueError, NotFittedError):
            continue
        probs.append([pred.prob_home, pred.prob_draw, pred.prob_away])
        labels.append(OUTCOME_TO_LABEL[match.result.outcome])  # type: ignore[union-attr]
    return np.array(probs, dtype=float), np.array(labels, dtype=int)


def reliability_curve(
    probs: np.ndarray, labels: np.ndarray, n_bins: int = 10
) -> list[dict[str, float]]:
    """Bin the predicted-class confidence and compare it to actual accuracy.

    A well-calibrated model has mean confidence close to accuracy in every bin.
    """

    if probs.size == 0:
        return []
    confidences = probs.max(axis=1)
    predictions = probs.argmax(axis=1)
    correct = (predictions == labels).astype(float)

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    out: list[dict[str, float]] = []
    for lo, hi in zip(bins[:-1], bins[1:], strict=True):
        in_bin = (confidences > lo) & (confidences <= hi)
        count = int(in_bin.sum())
        if count == 0:
            continue
        out.append(
            {
                "bin_lo": round(float(lo), 3),
                "bin_hi": round(float(hi), 3),
                "confidence": round(float(confidences[in_bin].mean()), 4),
                "accuracy": round(float(correct[in_bin].mean()), 4),
                "count": count,
            }
        )
    return out


def model_comparison(
    models: dict[str, BaseModel],
    matches: Sequence[Match],
) -> list[dict[str, object]]:
    """Per-model out-of-sample scorecard: Brier, log loss, ECE, sample size."""

    rows: list[dict[str, object]] = []
    for name, model in models.items():
        probs, labels = walk_forward_probabilities(matches, model)
        if probs.size == 0:
            rows.append({"model": name, "n": 0, "brier": None, "log_loss": None, "ece": None})
            continue
        rows.append(
            {
                "model": name,
                "n": int(len(labels)),
                "brier": round(brier_score(probs, labels), 4),
                "log_loss": round(log_loss(probs, labels), 4),
                "ece": round(expected_calibration_error(probs, labels), 4),
            }
        )
    rows.sort(key=lambda r: (r["brier"] is None, r["brier"] if r["brier"] is not None else 9.9))
    logger.info("Model comparison over %d models", len(rows))
    return rows


def calibration_report(
    matches: Sequence[Match],
    model: BaseModel,
    n_bins: int = 10,
) -> dict[str, object]:
    """Full calibration report for one model: curve plus summary metrics."""

    probs, labels = walk_forward_probabilities(matches, model)
    if probs.size == 0:
        return {"curve": [], "brier": None, "log_loss": None, "ece": None, "n": 0}
    return {
        "curve": reliability_curve(probs, labels, n_bins),
        "brier": round(brier_score(probs, labels), 4),
        "log_loss": round(log_loss(probs, labels), 4),
        "ece": round(expected_calibration_error(probs, labels), 4),
        "n": int(len(labels)),
    }


def league_universe(provider: BaseDataProvider, league: League, season: str) -> list[Match]:
    """Convenience: all finished matches for a league/season (for evaluation)."""

    from datetime import datetime, timezone

    far = datetime(2100, 1, 1, tzinfo=timezone.utc)
    return [m for m in provider.get_matches(league, season, far) if m.is_finished]
