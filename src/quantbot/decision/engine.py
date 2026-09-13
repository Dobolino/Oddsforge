"""Decision Engine (Layer 4).

Consumes a Layer-3 :class:`AnalysisResult`, applies the no-bet rules to the
best-EV candidate, and emits the final :class:`ValueSignal`: a recommendation
(VALUE_HOME/DRAW/AWAY or NO_BET), a theoretical stake, and the rejection
reasons when no bet is recommended.
"""

from __future__ import annotations

from quantbot.analysis.engine import AnalysisResult
from quantbot.decision.rules import NoBetRules
from quantbot.decision.sizing import KellySizer
from quantbot.schemas import (
    MarketData,
    MatchOutcome,
    SignalType,
    ValueSignal,
)

_OUTCOME_TO_SIGNAL: dict[MatchOutcome, SignalType] = {
    MatchOutcome.HOME: SignalType.VALUE_HOME,
    MatchOutcome.DRAW: SignalType.VALUE_DRAW,
    MatchOutcome.AWAY: SignalType.VALUE_AWAY,
}


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

        candidate = analysis.best_ev
        result = self.rules.evaluate(
            candidate,
            overround=market.overround,
            data_quality=analysis.data_quality,
            model_confidence=analysis.model_confidence,
        )

        if not result.passed:
            return ValueSignal(
                match_id=analysis.match_id,
                timestamp=market.timestamp,
                signal=SignalType.NO_BET,
                model_confidence=analysis.model_confidence,
                data_quality=analysis.data_quality,
                stake_fraction=0.0,
                rationale="; ".join(result.reasons),
                metrics=analysis.metrics,
            )

        stake = self.sizer.stake_fraction(candidate.model_prob, candidate.decimal_odds)
        if stake <= 0.0:
            # Passed the filters but Kelly sizing rounds the stake to zero.
            return ValueSignal(
                match_id=analysis.match_id,
                timestamp=market.timestamp,
                signal=SignalType.NO_BET,
                model_confidence=analysis.model_confidence,
                data_quality=analysis.data_quality,
                stake_fraction=0.0,
                rationale="kelly stake rounds to zero",
                metrics=analysis.metrics,
            )

        signal_type = _OUTCOME_TO_SIGNAL[candidate.outcome]
        return ValueSignal(
            match_id=analysis.match_id,
            timestamp=market.timestamp,
            signal=signal_type,
            chosen_outcome=candidate.outcome,
            edge=candidate.edge,
            expected_value=candidate.expected_value,
            decimal_odds=candidate.decimal_odds,
            model_confidence=analysis.model_confidence,
            data_quality=analysis.data_quality,
            stake_fraction=stake,
            rationale=(
                f"value on {candidate.outcome.value}: edge {candidate.edge:.4f}, "
                f"ev {candidate.expected_value:.4f}, stake {stake:.4f} of bankroll"
            ),
            metrics=analysis.metrics,
        )
