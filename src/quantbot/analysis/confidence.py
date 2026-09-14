"""Confidence and data-quality evaluation (Layer 3).

Two orthogonal scores feed the Decision Engine:

* Data Quality (0-100): how deep and complete the inputs are (match history,
  number of bookmakers, injury knowledge, liquidity).
* Model Confidence (0-100 plus Low/Medium/High): how much the ensemble's
  sub-models agree, tempered by data quality.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

import numpy as np

from quantbot.schemas import Prediction


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def ensemble_agreement(predictions: Sequence[Prediction]) -> float:
    """Agreement in [0, 1]: 1 minus the mean pairwise total-variation distance.

    A single prediction trivially agrees with itself (1.0). Identical
    distributions give 1.0; fully opposite distributions give 0.0. Averaging
    over all model pairs uses the full range (unlike distance-to-the-mean,
    which floors at 0.5 for two opposite models).
    """

    if len(predictions) < 2:
        return 1.0
    arr = np.array(
        [[p.prob_home, p.prob_draw, p.prob_away] for p in predictions], dtype=float
    )
    n = len(arr)
    distances: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            distances.append(float(np.abs(arr[i] - arr[j]).sum() / 2.0))
    return float(max(0.0, 1.0 - np.mean(distances)))


@dataclass(frozen=True)
class DataQualitySignals:
    """Raw inputs to the data-quality score.

    Attributes:
        home_matches / away_matches: Finished matches available per team.
        n_bookmakers: Distinct bookmakers quoting the market.
        injuries_known: Whether injury data was available (proxy guardrail).
        liquidity: Optional market liquidity/volume proxy.
    """

    home_matches: int
    away_matches: int
    n_bookmakers: int
    injuries_known: bool
    liquidity: float | None = None


class ConfidenceEvaluator:
    """Computes data-quality and model-confidence scores.

    Args:
        target_matches: Match count at which history depth is considered full.
        target_bookmakers: Bookmaker count considered full market coverage.
        target_liquidity: Liquidity considered full (neutral when unknown).
        medium_threshold / high_threshold: Confidence-level cutoffs (0-100).
        agreement_weight / quality_weight: Blend of the two confidence inputs.
    """

    def __init__(
        self,
        target_matches: int = 10,
        target_bookmakers: int = 3,
        target_liquidity: float = 100_000.0,
        medium_threshold: float = 45.0,
        high_threshold: float = 70.0,
        agreement_weight: float = 0.6,
        quality_weight: float = 0.4,
    ) -> None:
        if not 0.0 < medium_threshold < high_threshold < 100.0:
            raise ValueError("thresholds must satisfy 0 < medium < high < 100")
        self.target_matches = target_matches
        self.target_bookmakers = target_bookmakers
        self.target_liquidity = target_liquidity
        self.medium_threshold = medium_threshold
        self.high_threshold = high_threshold
        self.agreement_weight = agreement_weight
        self.quality_weight = quality_weight

    def data_quality(self, signals: DataQualitySignals) -> float:
        """Weighted data-quality score in [0, 100]."""

        match_depth = min(
            min(signals.home_matches, signals.away_matches) / self.target_matches, 1.0
        )
        market_depth = min(signals.n_bookmakers / self.target_bookmakers, 1.0)
        injuries = 1.0 if signals.injuries_known else 0.4
        if signals.liquidity is None:
            liquidity = 0.6  # neutral when unknown
        else:
            liquidity = min(max(signals.liquidity, 0.0) / self.target_liquidity, 1.0)

        score = 0.40 * match_depth + 0.30 * market_depth + 0.15 * injuries + 0.15 * liquidity
        return round(100.0 * score, 2)

    def model_confidence(
        self,
        agreement: float,
        data_quality: float,
        base_confidence: float | None = None,
    ) -> tuple[float, ConfidenceLevel]:
        """Blend ensemble agreement and data quality into a 0-100 score + level.

        ``base_confidence`` (a model's own self-assessment, 0-100) nudges the
        agreement term when provided.
        """

        agreement = float(np.clip(agreement, 0.0, 1.0))
        dq = float(np.clip(data_quality, 0.0, 100.0)) / 100.0
        agree_term = agreement
        if base_confidence is not None:
            agree_term = 0.7 * agreement + 0.3 * (float(np.clip(base_confidence, 0.0, 100.0)) / 100.0)

        score = 100.0 * (self.agreement_weight * agree_term + self.quality_weight * dq)
        score = round(float(np.clip(score, 0.0, 100.0)), 2)
        return score, self._level(score)

    def data_quality_components(self, signals: DataQualitySignals) -> list[dict[str, object]]:
        """Break the data-quality score into pass/fail components for display."""

        return [
            {
                "key": "history",
                "ok": min(signals.home_matches, signals.away_matches) >= self.target_matches // 2,
                "detail": f"{min(signals.home_matches, signals.away_matches)} matches",
            },
            {
                "key": "market",
                "ok": signals.n_bookmakers >= 2,
                "detail": f"{signals.n_bookmakers} bookmakers",
            },
            {"key": "injuries", "ok": signals.injuries_known, "detail": ""},
            {"key": "liquidity", "ok": signals.liquidity is not None, "detail": ""},
        ]

    def reliability_score(
        self,
        agreement: float,
        data_quality: float,
        sample_matches: int,
        liquidity: float | None = None,
    ) -> tuple[float, ConfidenceLevel]:
        """A 0-100 trust score for the signal, separate from win probability.

        Combines model agreement, data quality, sample size and liquidity. It
        says how much to trust the estimate, never how likely the outcome is.
        """

        a = float(np.clip(agreement, 0.0, 1.0))
        dq = float(np.clip(data_quality, 0.0, 100.0)) / 100.0
        ss = min(max(sample_matches, 0) / self.target_matches, 1.0)
        liq = 0.6 if liquidity is None else min(max(liquidity, 0.0) / self.target_liquidity, 1.0)
        score = 100.0 * (0.35 * a + 0.35 * dq + 0.20 * ss + 0.10 * liq)
        score = round(float(np.clip(score, 0.0, 100.0)), 1)
        return score, self._level(score)

    def _level(self, score: float) -> ConfidenceLevel:
        if score < self.medium_threshold:
            return ConfidenceLevel.LOW
        if score < self.high_threshold:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.HIGH
