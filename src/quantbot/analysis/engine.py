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
        market_shrinkage: bool = False,
    ) -> None:
        self._value = value_calculator or ValueCalculator()
        self._confidence = confidence_evaluator or ConfidenceEvaluator()
        # When True, model probabilities are pulled toward the fair market
        # before computing value: thin data (low quality) trusts the market
        # more, which tames overconfident edges from sparse fits.
        self._market_shrinkage = market_shrinkage

    def _model_weight(
        self, quality_signals: DataQualitySignals | None, data_quality: float
    ) -> float:
        """How far to trust the model vs. the market, in [0, 1].

        Driven by games played per team (the real signal for a goals model),
        not the overall data-quality score — that stays high early season
        because bookmaker coverage is always full. Few games -> trust the
        market more.
        """

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

        if not self._market_shrinkage:
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

        if self._market_shrinkage:
            w = self._model_weight(quality_signals, data_quality)
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
