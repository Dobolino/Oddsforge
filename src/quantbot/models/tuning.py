"""Hyperparameter tuning for time-decay (xi) via out-of-sample Brier score.

Uses expanding-window (time-series) cross-validation so tuning stays leak-free:
every fold trains on a chronological prefix and scores the immediately
following block. The xi minimizing the mean multiclass Brier score wins.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from sklearn.model_selection import TimeSeriesSplit

from quantbot.analysis.calibration import brier_score
from quantbot.features.extractor import OUTCOME_TO_LABEL
from quantbot.logging import get_logger
from quantbot.models.base import BaseModel
from quantbot.schemas import Match

logger = get_logger(__name__)


@dataclass(frozen=True)
class TuningResult:
    """Result of an xi sweep."""

    best_xi: float
    best_score: float
    scores: dict[float, float]  # xi -> mean OOS Brier (inf if never fittable)


def _fold_brier(model: BaseModel, train: Sequence[Match], val: Sequence[Match]) -> float | None:
    try:
        model.fit(train)
        probs = np.array(
            [[p.prob_home, p.prob_draw, p.prob_away] for p in (model.predict(m) for m in val)],
            dtype=float,
        )
        labels = np.array([OUTCOME_TO_LABEL[m.result.outcome] for m in val], dtype=int)  # type: ignore[union-attr]
    except (ValueError, RuntimeError):
        return None
    return brier_score(probs, labels)


def tune_time_decay(
    matches: Sequence[Match],
    xi_grid: Sequence[float],
    build_model: Callable[[float], BaseModel],
    n_splits: int = 3,
) -> TuningResult:
    """Grid-search xi by mean OOS Brier over expanding-window folds.

    Args:
        matches: Finished matches (sorted internally by kickoff).
        xi_grid: Candidate decay rates.
        build_model: Factory ``xi -> BaseModel`` producing a fresh model.
        n_splits: Number of expanding-window CV folds.
    """

    if not xi_grid:
        raise ValueError("xi_grid must not be empty")
    ordered = sorted(
        (m for m in matches if m.is_finished and m.result is not None),
        key=lambda m: m.kickoff,
    )
    if len(ordered) <= n_splits:
        raise ValueError("need more matches than folds")

    splitter = TimeSeriesSplit(n_splits=n_splits)
    folds = [
        ([ordered[i] for i in train_idx], [ordered[i] for i in val_idx])
        for train_idx, val_idx in splitter.split(ordered)
    ]

    scores: dict[float, float] = {}
    for xi in xi_grid:
        fold_scores = [
            score
            for train, val in folds
            if (score := _fold_brier(build_model(xi), train, val)) is not None
        ]
        scores[xi] = float(np.mean(fold_scores)) if fold_scores else float("inf")
        logger.debug("xi=%.5f mean OOS Brier=%.5f (%d folds)", xi, scores[xi], len(fold_scores))

    best_xi = min(scores, key=lambda k: scores[k])
    return TuningResult(best_xi=best_xi, best_score=scores[best_xi], scores=scores)
