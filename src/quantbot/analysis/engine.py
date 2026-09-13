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
    ) -> None:
        self._value = value_calculator or ValueCalculator()
        self._confidence = confidence_evaluator or ConfidenceEvaluator()

    def analyze(
        self,
        prediction: Prediction,
        market: MarketData,
        decimal_odds: dict[MatchOutcome, float],
        quality_signals: DataQualitySignals | None = None,
        sub_predictions: Sequence[Prediction] | None = None,
    ) -> AnalysisResult:
        metrics = self._value.metrics(prediction, market, decimal_odds)
        best_ev = self._value.best_by_ev(metrics)

        agreement = ensemble_agreement(sub_predictions) if sub_predictions else 1.0
        # Neutral default quality when no signals are supplied.
        data_quality = (
            self._confidence.data_quality(quality_signals)
            if quality_signals is not None
            else 60.0
        )
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
