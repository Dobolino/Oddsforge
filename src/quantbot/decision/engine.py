"""Decision Engine (Layer 4).

Consumes a Layer-3 :class:`AnalysisResult`, applies the versioned
:class:`DecisionPolicy`, and emits an auditable :class:`ValueSignal`.
UI modes must not change these rules.
"""

from __future__ import annotations

from quantbot.analysis.engine import AnalysisResult
from quantbot.decision.policy import (
    HIGH_RISK_FORCED,
    MODEL_UNVALIDATED_NO_SIZING,
    DecisionPolicy,
    DecisionStatus,
    live_policy,
    validate_candidate_inputs,
)
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
    policy: DecisionPolicy,
    decision_status: DecisionStatus,
    chosen_outcome: MatchOutcome | TotalsSide | None = None,
    edge: float | None = None,
    expected_value: float | None = None,
    decimal_odds: float | None = None,
    stake_fraction: float = 0.0,
    totals_line: float | None = None,
    handicap_line: float | None = None,
    sizing_allowed: bool = False,
    p_final: float | None = None,
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
        reason_codes=tuple(r.code for r in reasons),
        metrics=metrics,
        totals_line=totals_line,
        handicap_line=handicap_line,
        policy_version=policy.version,
        policy_profile=policy.profile.value,
        validation_status=policy.validation_status.value,
        decision_status=decision_status.value,
        sizing_allowed=sizing_allowed,
        p_final=p_final,
    )


class DecisionEngine:
    """Turns analysis into a final, auditable value signal.

    Prefer constructing via :meth:`from_policy`. Passing bare ``rules``/``sizer``
    without a policy builds an implicit live policy around them (legacy).
    """

    def __init__(
        self,
        rules: NoBetRules | None = None,
        sizer: KellySizer | None = None,
        *,
        policy: DecisionPolicy | None = None,
    ) -> None:
        if policy is not None:
            self.policy = policy
            self.rules = policy.rules()
            self.sizer = policy.sizer()
        else:
            self.policy = live_policy()
            self.rules = rules or self.policy.rules()
            self.sizer = sizer or self.policy.sizer()

    @classmethod
    def from_policy(cls, policy: DecisionPolicy) -> DecisionEngine:
        return cls(policy=policy)

    def decide(
        self,
        analysis: AnalysisResult,
        market: MarketData,
        *,
        home_matches: int | None = None,
        away_matches: int | None = None,
    ) -> ValueSignal:
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
            home_matches=home_matches,
            away_matches=away_matches,
        )

    def decide_totals(
        self,
        *,
        match_id: str,
        market: TotalsMarketData,
        metrics: tuple,
        data_quality: float,
        model_confidence: float,
        home_matches: int | None = None,
        away_matches: int | None = None,
    ) -> ValueSignal:
        """Same policy path for an Over/Under candidate set."""

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
            home_matches=home_matches,
            away_matches=away_matches,
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
        home_matches: int | None,
        away_matches: int | None,
        handicap_line: float | None = None,
    ) -> ValueSignal:
        invalid = validate_candidate_inputs(
            model_prob=getattr(candidate, "model_prob", None),
            decimal_odds=getattr(candidate, "decimal_odds", None),
            home_matches=home_matches,
            away_matches=away_matches,
            min_team_matches=self.policy.min_team_matches,
        )
        if invalid:
            forced = self._forced_high_risk_value(
                match_id=match_id,
                timestamp=timestamp,
                candidate=candidate,
                metrics=metrics,
                data_quality=data_quality,
                model_confidence=model_confidence,
                totals_line=totals_line,
                handicap_line=handicap_line,
                prior_reasons=invalid,
            )
            if forced is not None:
                return forced
            logger.debug("INVALID_DATA %s: %s", match_id, "; ".join(r.code for r in invalid))
            return _signal_from_reasons(
                match_id=match_id,
                timestamp=timestamp,
                signal=SignalType.NO_BET,
                reasons=invalid,
                model_confidence=model_confidence,
                data_quality=data_quality,
                metrics=metrics,
                policy=self.policy,
                decision_status=DecisionStatus.INVALID_DATA,
            )

        result = self.rules.evaluate(
            candidate,
            overround=overround,
            data_quality=data_quality,
            model_confidence=model_confidence,
        )
        if not result.passed:
            forced = self._forced_high_risk_value(
                match_id=match_id,
                timestamp=timestamp,
                candidate=candidate,
                metrics=metrics,
                data_quality=data_quality,
                model_confidence=model_confidence,
                totals_line=totals_line,
                handicap_line=handicap_line,
                prior_reasons=result.reasons,
            )
            if forced is not None:
                return forced
            logger.debug("NO_BET %s: %s", match_id, result.join(technical=True))
            return _signal_from_reasons(
                match_id=match_id,
                timestamp=timestamp,
                signal=SignalType.NO_BET,
                reasons=result.reasons,
                model_confidence=model_confidence,
                data_quality=data_quality,
                metrics=metrics,
                policy=self.policy,
                decision_status=DecisionStatus.NO_BET,
                p_final=float(candidate.model_prob),
            )

        stake = self.sizer.stake_fraction(candidate.model_prob, candidate.decimal_odds)
        if stake <= 0.0:
            forced = self._forced_high_risk_value(
                match_id=match_id,
                timestamp=timestamp,
                candidate=candidate,
                metrics=metrics,
                data_quality=data_quality,
                model_confidence=model_confidence,
                totals_line=totals_line,
                handicap_line=handicap_line,
                prior_reasons=(KELLY_ZERO,),
            )
            if forced is not None:
                return forced
            return _signal_from_reasons(
                match_id=match_id,
                timestamp=timestamp,
                signal=SignalType.NO_BET,
                reasons=(KELLY_ZERO,),
                model_confidence=model_confidence,
                data_quality=data_quality,
                metrics=metrics,
                policy=self.policy,
                decision_status=DecisionStatus.NO_BET,
                p_final=float(candidate.model_prob),
            )

        sizing_ok = self.policy.sizing_released
        reasons: list[Reason] = [
            value_reason(
                candidate.outcome.value, candidate.edge, candidate.expected_value, stake
            )
        ]
        if not sizing_ok:
            reasons.append(MODEL_UNVALIDATED_NO_SIZING)
            stake_out = 0.0
            if not self.policy.allow_exploratory_value_signals:
                return _signal_from_reasons(
                    match_id=match_id,
                    timestamp=timestamp,
                    signal=SignalType.NO_BET,
                    reasons=tuple(reasons),
                    model_confidence=model_confidence,
                    data_quality=data_quality,
                    metrics=metrics,
                    policy=self.policy,
                    decision_status=DecisionStatus.MODEL_NOT_VALIDATED,
                    p_final=float(candidate.model_prob),
                )
            status = DecisionStatus.VALUE_EXPLORATORY
        else:
            stake_out = stake
            status = DecisionStatus.VALUE_RELEASED

        signal_type = _OUTCOME_TO_SIGNAL[candidate.outcome]
        logger.debug(
            "%s %s: edge=%.4f ev=%.4f stake=%.4f status=%s",
            signal_type.value,
            match_id,
            candidate.edge,
            candidate.expected_value,
            stake_out,
            status.value,
        )
        return _signal_from_reasons(
            match_id=match_id,
            timestamp=timestamp,
            signal=signal_type,
            reasons=tuple(reasons),
            model_confidence=model_confidence,
            data_quality=data_quality,
            metrics=metrics,
            policy=self.policy,
            decision_status=status,
            chosen_outcome=candidate.outcome,
            edge=candidate.edge,
            expected_value=candidate.expected_value,
            decimal_odds=candidate.decimal_odds,
            stake_fraction=stake_out,
            totals_line=totals_line,
            handicap_line=handicap_line,
            sizing_allowed=sizing_ok,
            p_final=float(candidate.model_prob),
        )

    def _forced_high_risk_value(
        self,
        *,
        match_id: str,
        timestamp,
        candidate,
        metrics,
        data_quality: float,
        model_confidence: float,
        totals_line: float | None,
        handicap_line: float | None,
        prior_reasons: tuple[Reason, ...],
    ) -> ValueSignal | None:
        """High-risk UI: release best-EV side as exploratory VALUE (stake 0)."""

        if not self.policy.force_best_ev_on_no_bet:
            return None
        if not self.policy.allow_exploratory_value_signals:
            return None
        model_prob = getattr(candidate, "model_prob", None)
        decimal_odds = getattr(candidate, "decimal_odds", None)
        outcome = getattr(candidate, "outcome", None)
        if outcome is None or outcome not in _OUTCOME_TO_SIGNAL:
            return None
        if model_prob is None or decimal_odds is None:
            return None
        from math import isfinite

        if not isfinite(model_prob) or not 0.0 <= float(model_prob) <= 1.0:
            return None
        if not isfinite(decimal_odds) or float(decimal_odds) <= 1.0:
            return None
        edge = float(getattr(candidate, "edge", 0.0) or 0.0)
        ev = float(getattr(candidate, "expected_value", 0.0) or 0.0)
        reasons = tuple(prior_reasons) + (
            HIGH_RISK_FORCED,
            MODEL_UNVALIDATED_NO_SIZING,
        )
        return _signal_from_reasons(
            match_id=match_id,
            timestamp=timestamp,
            signal=_OUTCOME_TO_SIGNAL[outcome],
            reasons=reasons,
            model_confidence=model_confidence,
            data_quality=data_quality,
            metrics=metrics,
            policy=self.policy,
            decision_status=DecisionStatus.VALUE_EXPLORATORY,
            chosen_outcome=outcome,
            edge=edge,
            expected_value=ev,
            decimal_odds=float(decimal_odds),
            stake_fraction=0.0,
            totals_line=totals_line,
            handicap_line=handicap_line,
            sizing_allowed=False,
            p_final=float(model_prob),
        )

    def decide_ah(
        self,
        *,
        match_id: str,
        timestamp,
        metrics: tuple,
        handicap_line: float,
        data_quality: float,
        model_confidence: float,
        overround: float,
        home_matches: int | None = None,
        away_matches: int | None = None,
        ah_sizing_released: bool = False,
    ) -> ValueSignal:
        """        Experimental AH path: exploratory signals; sizing only with AH VALID.

        Half-line AH uses generalized Kelly on binary win/lose payoffs.
        Without an AH ValidationArtifact, stake stays 0 even if 1X2 sizing
        is unlocked.
        """

        if not metrics:
            raise ValueError("AH metrics must not be empty")
        candidate = max(metrics, key=lambda m: m.expected_value)
        invalid = validate_candidate_inputs(
            model_prob=getattr(candidate, "model_prob", None),
            decimal_odds=getattr(candidate, "decimal_odds", None),
            home_matches=home_matches,
            away_matches=away_matches,
            min_team_matches=self.policy.min_team_matches,
        )
        if invalid:
            return _signal_from_reasons(
                match_id=match_id,
                timestamp=timestamp,
                signal=SignalType.NO_BET,
                reasons=invalid,
                model_confidence=model_confidence,
                data_quality=data_quality,
                metrics=metrics,
                policy=self.policy,
                decision_status=DecisionStatus.INVALID_DATA,
                handicap_line=handicap_line,
            )

        result = self.rules.evaluate(
            candidate,
            overround=overround,
            data_quality=data_quality,
            model_confidence=model_confidence,
        )
        if not result.passed:
            return _signal_from_reasons(
                match_id=match_id,
                timestamp=timestamp,
                signal=SignalType.NO_BET,
                reasons=result.reasons,
                model_confidence=model_confidence,
                data_quality=data_quality,
                metrics=metrics,
                policy=self.policy,
                decision_status=DecisionStatus.NO_BET,
                handicap_line=handicap_line,
                p_final=float(candidate.model_prob),
            )

        # Half-line AH uses generalized Kelly on binary win/lose payoffs
        # (same optimum as closed-form Kelly). Push/quarter markets pass
        # explicit multi-state outcomes via the sizer helpers. Sizing stays
        # off without a dedicated AH ValidationArtifact.
        outcomes = KellySizer.binary_win_lose_outcomes(
            float(candidate.model_prob), float(candidate.decimal_odds)
        )
        stake = self.sizer.generalized_stake_fraction(outcomes)
        if stake <= 0.0:
            return _signal_from_reasons(
                match_id=match_id,
                timestamp=timestamp,
                signal=SignalType.NO_BET,
                reasons=(KELLY_ZERO,),
                model_confidence=model_confidence,
                data_quality=data_quality,
                metrics=metrics,
                policy=self.policy,
                decision_status=DecisionStatus.NO_BET,
                handicap_line=handicap_line,
                p_final=float(candidate.model_prob),
            )

        sizing_ok = bool(ah_sizing_released)
        reasons: list[Reason] = [
            value_reason(
                candidate.outcome.value, candidate.edge, candidate.expected_value, stake
            )
        ]
        if not sizing_ok:
            reasons.append(MODEL_UNVALIDATED_NO_SIZING)
            stake_out = 0.0
            if not self.policy.allow_exploratory_value_signals:
                return _signal_from_reasons(
                    match_id=match_id,
                    timestamp=timestamp,
                    signal=SignalType.NO_BET,
                    reasons=tuple(reasons),
                    model_confidence=model_confidence,
                    data_quality=data_quality,
                    metrics=metrics,
                    policy=self.policy,
                    decision_status=DecisionStatus.MODEL_NOT_VALIDATED,
                    handicap_line=handicap_line,
                    p_final=float(candidate.model_prob),
                )
            status = DecisionStatus.VALUE_EXPLORATORY
        else:
            stake_out = stake
            status = DecisionStatus.VALUE_RELEASED

        signal_type = (
            SignalType.VALUE_AH_HOME
            if candidate.outcome is MatchOutcome.HOME
            else SignalType.VALUE_AH_AWAY
        )
        return _signal_from_reasons(
            match_id=match_id,
            timestamp=timestamp,
            signal=signal_type,
            reasons=tuple(reasons),
            model_confidence=model_confidence,
            data_quality=data_quality,
            metrics=metrics,
            policy=self.policy,
            decision_status=status,
            chosen_outcome=candidate.outcome,
            edge=candidate.edge,
            expected_value=candidate.expected_value,
            decimal_odds=candidate.decimal_odds,
            stake_fraction=stake_out,
            handicap_line=handicap_line,
            sizing_allowed=sizing_ok,
            p_final=float(candidate.model_prob),
        )

    def invalid_data_signal(
        self,
        *,
        match_id: str,
        timestamp,
        reasons: tuple[Reason, ...],
        data_quality: float = 0.0,
        model_confidence: float = 0.0,
        metrics: tuple = (),
    ) -> ValueSignal:
        """Emit an INVALID_DATA decision without computing Kelly/EV release."""

        if not reasons:
            raise ValueError("invalid_data_signal requires at least one reason")
        return _signal_from_reasons(
            match_id=match_id,
            timestamp=timestamp,
            signal=SignalType.NO_BET,
            reasons=reasons,
            model_confidence=model_confidence,
            data_quality=data_quality,
            metrics=metrics,
            policy=self.policy,
            decision_status=DecisionStatus.INVALID_DATA,
        )
