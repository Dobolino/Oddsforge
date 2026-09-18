"""Analysis Engine (Layer 3 orchestration).

Joins a model :class:`Prediction` with fair :class:`MarketData` and the odds
available to bet, producing per-outcome :class:`ValueMetrics` plus data-quality
and model-confidence scores. The result is the input the Decision Engine
(Layer 4, Step 08) turns into a :class:`ValueSignal`. This engine deliberately
does not decide whether to bet.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

import numpy as np

from quantbot.analysis.confidence import (
    ConfidenceEvaluator,
    ConfidenceLevel,
    DataQualitySignals,
    ensemble_agreement,
)
from quantbot.analysis.value import ValueCalculator, odds_to_dict
from quantbot.schemas import (
    MarketData,
    MatchOutcome,
    Odds,
    Prediction,
    ValueMetrics,
)


class ShrinkageMode(str, Enum):
    """How model probabilities are pulled toward the fair market.

    ``LEGACY_DEPTH`` keeps the historical ``depth / target_matches`` weight.
    ``EFF_SAMPLE`` uses ``w = n_eff / (n_eff + k)`` with a conservative
    effective sample size. Neither mode claims calibration; prefer the mode
    selected on held-out development data.
    """

    OFF = "off"
    LEGACY_DEPTH = "legacy_depth"
    EFF_SAMPLE = "eff_sample"


def effective_sample_size(
    weights: Sequence[float] | None = None,
    *,
    home_matches: int = 0,
    away_matches: int = 0,
) -> float:
    """Time-weighted effective n, or conservative min(home, away) proxy.

    With observation weights ``a_i``: ``n_eff = (sum a_i)^2 / sum(a_i^2)``.
    Without weights, both teams are merged conservatively via ``min``.
    """

    if weights is not None and len(weights) > 0:
        a = np.asarray(list(weights), dtype=float)
        a = a[np.isfinite(a) & (a > 0.0)]
        if a.size == 0:
            return 0.0
        s1 = float(a.sum())
        s2 = float(np.square(a).sum())
        if s2 <= 0.0:
            return 0.0
        return (s1 * s1) / s2
    return float(min(max(int(home_matches), 0), max(int(away_matches), 0)))


def eff_sample_weight(n_eff: float, k: float) -> float:
    """Model vs market weight ``w = n_eff / (n_eff + k)`` in [0, 1]."""

    if k <= 0.0:
        raise ValueError("shrinkage_k must be > 0 for EFF_SAMPLE")
    n = max(float(n_eff), 0.0)
    return n / (n + float(k))


@dataclass(frozen=True)
class AnalysisResult:
    """Layer-3 output for one match.

    Attributes:
        metrics: ValueMetrics per outcome (HOME, DRAW, AWAY).
        best_ev: The outcome with the highest expected value.
        data_quality: 0-100 data-quality score.
        model_confidence: 0-100 confidence score.
        confidence_level: Low/Medium/High bucket.
        ensemble_agreement: Sub-model agreement in [0, 1].
        shrinkage_mode / shrinkage_weight: Audit of market pull (if any).
        p_raw_*: Model probabilities before shrinkage (1X2).
    """

    match_id: str
    metrics: tuple[ValueMetrics, ...]
    best_ev: ValueMetrics
    data_quality: float
    model_confidence: float
    confidence_level: ConfidenceLevel
    ensemble_agreement: float
    home_matches: int = 0
    away_matches: int = 0
    shrinkage_mode: str = ShrinkageMode.OFF.value
    shrinkage_weight: float | None = None
    p_raw_home: float | None = None
    p_raw_draw: float | None = None
    p_raw_away: float | None = None

    def metric_for(self, outcome: MatchOutcome) -> ValueMetrics:
        for m in self.metrics:
            if m.outcome is outcome:
                return m
        raise KeyError(outcome)


class AnalysisEngine:
    """Combines value calculation with confidence and quality scoring."""

    def __init__(
        self,
        value_calculator: ValueCalculator | None = None,
        confidence_evaluator: ConfidenceEvaluator | None = None,
        market_shrinkage: bool | None = None,
        *,
        shrinkage_mode: ShrinkageMode | None = None,
        shrinkage_k: float = 10.0,
        match_weights: Sequence[float] | None = None,
    ) -> None:
        self._value = value_calculator or ValueCalculator()
        self._confidence = confidence_evaluator or ConfidenceEvaluator()
        # Legacy bool maps to LEGACY_DEPTH; explicit mode wins when both set.
        if shrinkage_mode is not None:
            self._shrinkage_mode = ShrinkageMode(shrinkage_mode)
        elif market_shrinkage is True:
            self._shrinkage_mode = ShrinkageMode.LEGACY_DEPTH
        else:
            self._shrinkage_mode = ShrinkageMode.OFF
        if self._shrinkage_mode is ShrinkageMode.EFF_SAMPLE and shrinkage_k <= 0.0:
            raise ValueError("shrinkage_k must be > 0 for EFF_SAMPLE")
        self._shrinkage_k = float(shrinkage_k)
        self._match_weights = (
            tuple(float(w) for w in match_weights) if match_weights is not None else None
        )

    @property
    def shrinkage_mode(self) -> ShrinkageMode:
        return self._shrinkage_mode

    @property
    def shrinkage_k(self) -> float:
        return self._shrinkage_k

    def _model_weight(
        self, quality_signals: DataQualitySignals | None, data_quality: float
    ) -> float:
        """How far to trust the model vs. the market, in [0, 1]."""

        if self._shrinkage_mode is ShrinkageMode.OFF:
            return 1.0

        if self._shrinkage_mode is ShrinkageMode.EFF_SAMPLE:
            home = quality_signals.home_matches if quality_signals is not None else 0
            away = quality_signals.away_matches if quality_signals is not None else 0
            n_eff = effective_sample_size(
                self._match_weights, home_matches=home, away_matches=away
            )
            return eff_sample_weight(n_eff, self._shrinkage_k)

        # LEGACY_DEPTH: games played per team (not overall data-quality score).
        if quality_signals is not None:
            depth = min(quality_signals.home_matches, quality_signals.away_matches)
            target = max(1, self._confidence.target_matches)
            return min(max(depth / target, 0.0), 1.0)
        return min(max(data_quality / 100.0, 0.0), 1.0)

    @staticmethod
    def _shrink_to_market(
        prediction: Prediction, market: MarketData, w: float
    ) -> Prediction:
        """Blend model 1X2 probabilities toward the fair market with weight ``w``."""

        fair = market.fair_probabilities()
        ph = w * prediction.prob_home + (1.0 - w) * fair[MatchOutcome.HOME]
        pd = w * prediction.prob_draw + (1.0 - w) * fair[MatchOutcome.DRAW]
        pa = w * prediction.prob_away + (1.0 - w) * fair[MatchOutcome.AWAY]
        total = ph + pd + pa
        if total <= 0:
            return prediction
        return prediction.model_copy(
            update={"prob_home": ph / total, "prob_draw": pd / total, "prob_away": pa / total}
        )

    def shrink_totals_metrics(
        self,
        metrics: Sequence[ValueMetrics],
        quality_signals: DataQualitySignals | None,
    ) -> tuple[ValueMetrics, ...]:
        """Pull Over/Under model probabilities toward the market when data is thin.

        The goals market is derived from the same sparse-data model as 1X2, so
        it needs the same discipline; without it every match looks like value.
        Returns the metrics unchanged when shrinkage is disabled.
        """

        if self._shrinkage_mode is ShrinkageMode.OFF:
            return tuple(metrics)
        data_quality = (
            self._confidence.data_quality(quality_signals)
            if quality_signals is not None
            else 60.0
        )
        w = self._model_weight(quality_signals, data_quality)
        out: list[ValueMetrics] = []
        for m in metrics:
            shrunk = w * m.model_prob + (1.0 - w) * m.fair_market_prob
            out.append(
                m.model_copy(
                    update={
                        "model_prob": shrunk,
                        "edge": shrunk - m.fair_market_prob,
                        "expected_value": shrunk * m.decimal_odds - 1.0,
                    }
                )
            )
        return tuple(out)

    def analyze(
        self,
        prediction: Prediction,
        market: MarketData,
        decimal_odds: dict[MatchOutcome, float],
        quality_signals: DataQualitySignals | None = None,
        sub_predictions: Sequence[Prediction] | None = None,
    ) -> AnalysisResult:
        agreement = ensemble_agreement(sub_predictions) if sub_predictions else 1.0
        # Neutral default quality when no signals are supplied.
        data_quality = (
            self._confidence.data_quality(quality_signals)
            if quality_signals is not None
            else 60.0
        )

        p_raw_home = float(prediction.prob_home)
        p_raw_draw = float(prediction.prob_draw)
        p_raw_away = float(prediction.prob_away)
        shrinkage_weight: float | None = None

        if self._shrinkage_mode is not ShrinkageMode.OFF:
            w = self._model_weight(quality_signals, data_quality)
            shrinkage_weight = w
            prediction = self._shrink_to_market(prediction, market, w)

        metrics = self._value.metrics(prediction, market, decimal_odds)
        best_ev = self._value.best_by_ev(metrics)
        confidence, level = self._confidence.model_confidence(
            agreement, data_quality, base_confidence=prediction.confidence
        )

        return AnalysisResult(
            match_id=prediction.match_id,
            metrics=metrics,
            best_ev=best_ev,
            data_quality=data_quality,
            model_confidence=confidence,
            confidence_level=level,
            ensemble_agreement=agreement,
            home_matches=quality_signals.home_matches if quality_signals else 0,
            away_matches=quality_signals.away_matches if quality_signals else 0,
            shrinkage_mode=self._shrinkage_mode.value,
            shrinkage_weight=shrinkage_weight,
            p_raw_home=p_raw_home,
            p_raw_draw=p_raw_draw,
            p_raw_away=p_raw_away,
        )

    def analyze_with_odds(
        self,
        prediction: Prediction,
        market: MarketData,
        odds: Odds,
        quality_signals: DataQualitySignals | None = None,
        sub_predictions: Sequence[Prediction] | None = None,
    ) -> AnalysisResult:
        """Convenience overload taking an :class:`Odds` snapshot for the odds."""

        return self.analyze(
            prediction,
            market,
            odds_to_dict(odds),
            quality_signals=quality_signals,
            sub_predictions=sub_predictions,
        )
