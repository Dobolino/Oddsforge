"""Decision Engine (Layer 4).

Consumes a Layer-3 :class:`AnalysisResult`, applies the no-bet rules to the
best-EV candidate, and emits the final :class:`ValueSignal`: a recommendation
(VALUE_HOME/DRAW/AWAY or NO_BET), a theoretical stake, and bilingual rejection
or acceptance reasons.
"""

from __future__ import annotations

from quantbot.analysis.engine import AnalysisResult
from quantbot.decision.rules import KELLY_ZERO, NoBetRules, Reason, value_reason
from quantbot.decision.sizing import KellySizer
from quantbot.logging import get_logger
from quantbot.schemas import (
    MarketData,
    MatchOutcome,
    SignalType,
    TotalsMarketData,
    TotalsSide,
    ValueSignal,
)

logger = get_logger(__name__)

_OUTCOME_TO_SIGNAL: dict[MatchOutcome | TotalsSide, SignalType] = {
    MatchOutcome.HOME: SignalType.VALUE_HOME,
    MatchOutcome.DRAW: SignalType.VALUE_DRAW,
    MatchOutcome.AWAY: SignalType.VALUE_AWAY,
    TotalsSide.OVER: SignalType.VALUE_OVER,
    TotalsSide.UNDER: SignalType.VALUE_UNDER,
}


def _signal_from_reasons(
    *,
    match_id: str,
    timestamp,
    signal: SignalType,
    reasons: tuple[Reason, ...],
    model_confidence: float,
    data_quality: float,
    metrics,
    chosen_outcome: MatchOutcome | TotalsSide | None = None,
    edge: float | None = None,
    expected_value: float | None = None,
    decimal_odds: float | None = None,
    stake_fraction: float = 0.0,
    totals_line: float | None = None,
) -> ValueSignal:
    return ValueSignal(
        match_id=match_id,
        timestamp=timestamp,
        signal=signal,
        chosen_outcome=chosen_outcome,
        edge=edge,
        expected_value=expected_value,
        decimal_odds=decimal_odds,
        model_confidence=model_confidence,
        data_quality=data_quality,
        stake_fraction=stake_fraction,
        rationale="; ".join(r.technical for r in reasons),
        rationale_de="; ".join(r.de for r in reasons),
        rationale_en="; ".join(r.en for r in reasons),
        metrics=metrics,
        totals_line=totals_line,
    )


class DecisionEngine:
    """Turns analysis into a final, auditable value signal.

    Args:
        rules: No-bet filters. Defaults applied if omitted.
        sizer: Kelly sizer for the theoretical stake.
    """

    def __init__(
        self,
        rules: NoBetRules | None = None,
        sizer: KellySizer | None = None,
    ) -> None:
        self.rules = rules or NoBetRules()
        self.sizer = sizer or KellySizer()

    def decide(self, analysis: AnalysisResult, market: MarketData) -> ValueSignal:
        if analysis.match_id != market.match_id:
            raise ValueError(
                f"analysis/market match_id mismatch: "
                f"{analysis.match_id!r} vs {market.match_id!r}"
            )

        return self._decide_candidate(
            match_id=analysis.match_id,
            timestamp=market.timestamp,
            candidate=analysis.best_ev,
            metrics=analysis.metrics,
            overround=market.overround,
            data_quality=analysis.data_quality,
            model_confidence=analysis.model_confidence,
            totals_line=None,
        )

    def decide_totals(
        self,
        *,
        match_id: str,
        market: TotalsMarketData,
        metrics: tuple,
        data_quality: float,
        model_confidence: float,
    ) -> ValueSignal:
        """Same no-bet rules for an Over/Under candidate set."""

        if not metrics:
            raise ValueError("totals metrics must not be empty")
        candidate = max(metrics, key=lambda m: m.expected_value)
        return self._decide_candidate(
            match_id=match_id,
            timestamp=market.timestamp,
            candidate=candidate,
            metrics=metrics,
            overround=market.overround,
            data_quality=data_quality,
            model_confidence=model_confidence,
            totals_line=market.line,
        )

    def _decide_candidate(
        self,
        *,
        match_id: str,
        timestamp,
        candidate,
        metrics,
        overround: float,
        data_quality: float,
        model_confidence: float,
        totals_line: float | None,
    ) -> ValueSignal:
        result = self.rules.evaluate(
            candidate,
            overround=overround,
            data_quality=data_quality,
            model_confidence=model_confidence,
        )

        if not result.passed:
            logger.debug("NO_BET %s: %s", match_id, result.join(technical=True))
            return _signal_from_reasons(
                match_id=match_id,
                timestamp=timestamp,
                signal=SignalType.NO_BET,
                reasons=result.reasons,
                model_confidence=model_confidence,
                data_quality=data_quality,
                metrics=metrics,
            )

        stake = self.sizer.stake_fraction(candidate.model_prob, candidate.decimal_odds)
        if stake <= 0.0:
            return _signal_from_reasons(
                match_id=match_id,
                timestamp=timestamp,
                signal=SignalType.NO_BET,
                reasons=(KELLY_ZERO,),
                model_confidence=model_confidence,
                data_quality=data_quality,
                metrics=metrics,
            )

        reason = value_reason(
            candidate.outcome.value, candidate.edge, candidate.expected_value, stake
        )
        signal_type = _OUTCOME_TO_SIGNAL[candidate.outcome]
        logger.debug(
            "%s %s: edge=%.4f ev=%.4f stake=%.4f",
            signal_type.value,
            match_id,
            candidate.edge,
            candidate.expected_value,
            stake,
        )
        return _signal_from_reasons(
            match_id=match_id,
            timestamp=timestamp,
            signal=signal_type,
            reasons=(reason,),
            model_confidence=model_confidence,
            data_quality=data_quality,
            metrics=metrics,
            chosen_outcome=candidate.outcome,
            edge=candidate.edge,
            expected_value=candidate.expected_value,
            decimal_odds=candidate.decimal_odds,
            stake_fraction=stake,
            totals_line=totals_line,
        )
