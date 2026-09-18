"""P0 DecisionPolicy and high-risk removal tests."""

from __future__ import annotations

from datetime import datetime, timezone

from quantbot.analysis.confidence import ConfidenceLevel
from quantbot.analysis.engine import AnalysisResult
from quantbot.decision import (
    DecisionEngine,
    DecisionStatus,
    ValidationStatus,
    demo_tracker_policy,
    live_policy,
)
from quantbot.decision.policy import POLICY_VERSION
from quantbot.markets.odds import MarketEngine
from quantbot.schemas import MatchOutcome, Odds, ValueMetrics


def _metric(prob: float = 0.55, fair: float = 0.48, odds: float = 2.0) -> ValueMetrics:
    return ValueMetrics(
        outcome=MatchOutcome.HOME,
        model_prob=prob,
        fair_market_prob=fair,
        decimal_odds=odds,
        edge=prob - fair,
        expected_value=prob * odds - 1.0,
    )


def _analysis(metric: ValueMetrics, home: int = 8, away: int = 8) -> AnalysisResult:
    return AnalysisResult(
        match_id="m1",
        metrics=(metric,),
        best_ev=metric,
        data_quality=80.0,
        model_confidence=70.0,
        confidence_level=ConfidenceLevel.MEDIUM,
        ensemble_agreement=1.0,
        home_matches=home,
        away_matches=away,
    )


def test_live_policy_blocks_sizing_when_unvalidated() -> None:
    policy = live_policy()
    assert policy.validation_status is ValidationStatus.UNVALIDATED
    engine = DecisionEngine.from_policy(policy)
    metric = _metric(0.60, 0.50, 2.10)
    ts = datetime(2024, 12, 1, tzinfo=timezone.utc)
    entry = Odds(
        match_id="m1",
        bookmaker="x",
        timestamp=ts,
        home=2.10,
        draw=3.40,
        away=3.50,
    )
    market = MarketEngine().to_market_data(entry)
    signal = engine.decide(_analysis(metric), market, home_matches=8, away_matches=8)
    assert signal.is_bet
    assert signal.stake_fraction == 0.0
    assert signal.sizing_allowed is False
    assert signal.decision_status == DecisionStatus.VALUE_EXPLORATORY.value
    assert signal.policy_version == POLICY_VERSION
    assert "MODEL_NOT_VALIDATED_NO_SIZING" in signal.reason_codes


def test_valid_policy_releases_sizing() -> None:
    policy = live_policy().with_validation(ValidationStatus.VALID)
    engine = DecisionEngine.from_policy(policy)
    metric = _metric(0.60, 0.50, 2.10)
    ts = datetime(2024, 12, 1, tzinfo=timezone.utc)
    entry = Odds(
        match_id="m1",
        bookmaker="x",
        timestamp=ts,
        home=2.10,
        draw=3.40,
        away=3.50,
    )
    market = MarketEngine().to_market_data(entry)
    signal = engine.decide(_analysis(metric), market, home_matches=8, away_matches=8)
    assert signal.is_bet
    assert signal.stake_fraction > 0.0
    assert signal.sizing_allowed is True
    assert signal.decision_status == DecisionStatus.VALUE_RELEASED.value


def test_invalid_history_is_invalid_data() -> None:
    engine = DecisionEngine.from_policy(live_policy())
    metric = _metric()
    ts = datetime(2024, 12, 1, tzinfo=timezone.utc)
    entry = Odds(
        match_id="m1",
        bookmaker="x",
        timestamp=ts,
        home=2.0,
        draw=3.4,
        away=3.5,
    )
    market = MarketEngine().to_market_data(entry)
    signal = engine.decide(_analysis(metric, 1, 1), market, home_matches=1, away_matches=1)
    assert not signal.is_bet
    assert signal.decision_status == DecisionStatus.INVALID_DATA.value
    assert "INVALID_DATA_HISTORY" in signal.reason_codes


def test_demo_tracker_policy_allows_sizing() -> None:
    policy = demo_tracker_policy()
    assert policy.sizing_released is True
    assert policy.profile.value == "demo"


def test_slip_rejects_same_match_and_hides_combo_p() -> None:
    from quantbot.dashboard.slip import BettingSlip, SlipLeg, format_ticket

    legs = (
        SlipLeg(
            match_id="same",
            match="A vs B",
            tip="Tipp: Heimsieg",
            outcome=MatchOutcome.HOME,
            odds=1.8,
            model_prob=0.55,
            edge=0.05,
            role="core",
            stance="with",
        ),
        SlipLeg(
            match_id="same",
            match="A vs B",
            tip="Tipp: Unter",
            outcome=MatchOutcome.AWAY,
            odds=1.9,
            model_prob=0.52,
            edge=0.04,
            role="core",
            stance="with",
        ),
    )
    slip = BettingSlip(legs=legs, style="safe")
    assert not slip.is_plausible
    assert slip.geschaetzte_chance == "n/a"
    text = format_ticket(slip, lang="de")
    assert "nicht belastbar" in text
