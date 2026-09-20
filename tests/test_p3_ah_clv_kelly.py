"""P3: generalized Kelly, AH exploratory path, closing last-prematch, CLV UI path."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantbot.decision.engine import DecisionEngine
from quantbot.decision.policy import (
    DecisionPolicy,
    DecisionStatus,
    PolicyProfile,
    ValidationStatus,
)
from quantbot.decision.sizing import KellySizer
from quantbot.markets.closing import ClosingSource, resolve_closing_odds
from quantbot.schemas import (
    League,
    Match,
    MatchOutcome,
    MatchResult,
    MatchStatus,
    Odds,
    SignalType,
    Team,
    ValueMetrics,
    ValueSignal,
)
from quantbot.schemas.enums import Sport
from quantbot.schemas.odds import SpreadOdds
from quantbot.tracking import TipHistoryStore, TipRecord, _parse_ah_tip

UTC = timezone.utc
TS = datetime(2025, 3, 1, 12, 0, tzinfo=UTC)


def _metric(outcome: MatchOutcome, model_prob: float, fair: float, odds: float) -> ValueMetrics:
    return ValueMetrics(
        outcome=outcome,
        model_prob=model_prob,
        fair_market_prob=fair,
        decimal_odds=odds,
        edge=model_prob - fair,
        expected_value=model_prob * odds - 1.0,
    )


def test_generalized_kelly_matches_binary_on_half_line() -> None:
    sizer = KellySizer(kelly_fraction=0.25, max_fraction=0.05)
    p, odds = 0.58, 2.05
    binary = sizer.stake_fraction(p, odds)
    outcomes = KellySizer.binary_win_lose_outcomes(p, odds)
    gen = sizer.generalized_stake_fraction(outcomes, grid=400)
    assert gen == pytest.approx(binary, abs=0.005)


def test_push_market_outcomes_prefer_lower_stake_than_no_push() -> None:
    sizer = KellySizer(kelly_fraction=1.0, max_fraction=0.05)
    # Same win/lose edge, but 20% push mass reduces growth → smaller or equal f.
    no_push = sizer.generalized_stake_fraction(
        KellySizer.binary_win_lose_outcomes(0.55, 2.1),
        grid=300,
    )
    with_push = sizer.generalized_stake_fraction(
        KellySizer.push_market_outcomes(p_win=0.44, p_push=0.20, p_lose=0.36, decimal_odds=2.1),
        grid=300,
    )
    assert with_push <= no_push


def test_resolve_closing_prefers_tagged_then_last_prematch() -> None:
    kick = datetime(2025, 4, 1, 15, 0, tzinfo=UTC)
    match = Match(
        match_id="m-close",
        league=League.BUNDESLIGA,
        season="2024-2025",
        kickoff=kick,
        prediction_timestamp=kick - timedelta(hours=1),
        home_team=Team(team_id="h", name="Home"),
        away_team=Team(team_id="a", name="Away"),
        status=MatchStatus.SCHEDULED,
        sport=Sport.FOOTBALL,
    )
    early = Odds(
        match_id="m-close",
        bookmaker="b",
        timestamp=kick - timedelta(hours=24),
        home=2.1,
        draw=3.4,
        away=3.5,
        is_closing=False,
    )
    tagged = Odds(
        match_id="m-close",
        bookmaker="b",
        timestamp=kick - timedelta(minutes=5),
        home=1.95,
        draw=3.5,
        away=3.8,
        is_closing=True,
    )
    res = resolve_closing_odds(match, [early, tagged])
    assert res.source is ClosingSource.TAGGED_CLOSING
    assert res.odds is tagged

    last = Odds(
        match_id="m-close",
        bookmaker="b",
        timestamp=kick - timedelta(minutes=12),
        home=2.0,
        draw=3.3,
        away=3.6,
        is_closing=False,
    )
    res2 = resolve_closing_odds(match, [early, last])
    assert res2.source is ClosingSource.LAST_PREMATCH
    assert res2.odds is last
    assert "last prematch" in res2.reason.lower()

    missing = resolve_closing_odds(match, [])
    assert missing.source is ClosingSource.MISSING
    assert missing.odds is None


def test_decide_ah_exploratory_zero_stake_without_release() -> None:
    policy = DecisionPolicy(
        version="test",
        profile=PolicyProfile.LIVE,
        validation_status=ValidationStatus.UNVALIDATED,
        allow_exploratory_value_signals=True,
        min_edge=0.01,
        min_ev=0.01,
        max_overround=0.12,
        min_data_quality=0.0,
        min_model_confidence=0.0,
        min_team_matches=0,
        kelly_fraction=0.25,
        max_stake_fraction=0.05,
    )
    engine = DecisionEngine.from_policy(policy)
    metrics = (
        _metric(MatchOutcome.HOME, 0.62, 0.48, 2.20),
        _metric(MatchOutcome.AWAY, 0.38, 0.52, 2.05),
    )
    signal = engine.decide_ah(
        match_id="m1",
        timestamp=TS,
        metrics=metrics,
        handicap_line=-0.5,
        data_quality=80.0,
        model_confidence=70.0,
        overround=0.04,
        ah_sizing_released=False,
    )
    assert signal.signal is SignalType.VALUE_AH_HOME
    assert signal.stake_fraction == 0.0
    assert signal.sizing_allowed is False
    assert signal.decision_status == DecisionStatus.VALUE_EXPLORATORY.value
    assert signal.tip_label == "ah_home_-0.5"

    released = engine.decide_ah(
        match_id="m1",
        timestamp=TS,
        metrics=metrics,
        handicap_line=-0.5,
        data_quality=80.0,
        model_confidence=70.0,
        overround=0.04,
        ah_sizing_released=True,
    )
    assert released.stake_fraction > 0.0
    assert released.sizing_allowed is True
    assert released.decision_status == DecisionStatus.VALUE_RELEASED.value


def test_parse_and_settle_ah_tip(tmp_path: Path) -> None:
    assert _parse_ah_tip("ah_home_-0.5") == ("home", -0.5)
    assert _parse_ah_tip("ah_away_0.5") == ("away", 0.5)
    assert _parse_ah_tip("home") is None

    store = TipHistoryStore(tmp_path / "demo.json")
    tip = TipRecord(
        tip_id="t1",
        match_id="m1",
        kickoff=TS.isoformat(),
        league=League.BUNDESLIGA.value,
        home="H",
        away="A",
        tip="ah_home_-0.5",
        odds=1.95,
        model_prob=0.55,
        as_of=TS.isoformat(),
        mode="demo",
        settled=False,
        actual=None,
        correct=None,
    )
    store.append_new([tip])
    # Home wins 2-0 → covers -0.5
    match = Match(
        match_id="m1",
        league=League.BUNDESLIGA,
        season="2024-2025",
        kickoff=TS,
        prediction_timestamp=TS - timedelta(hours=2),
        home_team=Team(team_id="h", name="H"),
        away_team=Team(team_id="a", name="A"),
        status=MatchStatus.FINISHED,
        sport=Sport.FOOTBALL,
        result=MatchResult(home_goals=2, away_goals=0),
    )
    n = store.settle_from_matches([match])
    assert n >= 1
    settled = store.all_tips()[0]
    assert settled.settled is True
    assert settled.correct is True
    assert settled.actual == "won"


def test_ah_value_signal_schema_requires_handicap_line() -> None:
    with pytest.raises(ValueError, match="handicap_line"):
        ValueSignal(
            match_id="m1",
            timestamp=TS,
            signal=SignalType.VALUE_AH_HOME,
            chosen_outcome=MatchOutcome.HOME,
            edge=0.05,
            expected_value=0.1,
            decimal_odds=2.0,
            model_confidence=70.0,
            data_quality=80.0,
            stake_fraction=0.0,
        )


def test_dummy_spreads_available() -> None:
    from quantbot.data.dummy import DummyDataProvider

    provider = DummyDataProvider()
    matches = provider.get_matches(League.PREMIER_LEAGUE, "2024-2025", datetime(2100, 1, 1, tzinfo=UTC))
    assert matches
    spreads = provider.get_spreads(matches[0].match_id, matches[0].kickoff)
    assert spreads
    assert isinstance(spreads[0], SpreadOdds)
