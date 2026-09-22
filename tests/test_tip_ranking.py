"""Best-tips ranking: composite score, risk buckets, cross-league ordering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quantbot.dashboard.components.tables import best_tips_dataframe
from quantbot.dashboard.ux import chosen_model_prob, risk_level, tip_score
from quantbot.orchestrator import SignalReport
from quantbot.schemas import (
    League,
    Match,
    MatchOutcome,
    MatchStatus,
    SignalType,
    Team,
    ValueMetrics,
    ValueSignal,
)

UTC = timezone.utc
TS = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def _signal(
    *,
    match_id: str,
    outcome: MatchOutcome,
    model_prob: float,
    odds: float,
    fair: float,
    data_quality: float = 80.0,
    model_confidence: float = 70.0,
    bet: bool = True,
) -> ValueSignal:
    if not bet:
        return ValueSignal(
            match_id=match_id, timestamp=TS, signal=SignalType.NO_BET,
            model_confidence=model_confidence, data_quality=data_quality,
        )
    ev = model_prob * odds - 1.0
    metric = ValueMetrics(
        outcome=outcome, model_prob=model_prob, fair_market_prob=fair,
        decimal_odds=odds, edge=model_prob - fair, expected_value=ev,
    )
    sig_type = {
        MatchOutcome.HOME: SignalType.VALUE_HOME,
        MatchOutcome.DRAW: SignalType.VALUE_DRAW,
        MatchOutcome.AWAY: SignalType.VALUE_AWAY,
    }[outcome]
    return ValueSignal(
        match_id=match_id, timestamp=TS, signal=sig_type, chosen_outcome=outcome,
        edge=model_prob - fair, expected_value=ev, decimal_odds=odds,
        model_confidence=model_confidence, data_quality=data_quality,
        stake_fraction=0.02, metrics=(metric,),
    )


def _report(match_id: str, league: League, signal: ValueSignal) -> SignalReport:
    match = Match(
        match_id=match_id, league=league, season="2026-2027",
        kickoff=TS + timedelta(days=1), prediction_timestamp=TS,
        home_team=Team(team_id=f"{match_id}H", name=f"{match_id} Home"),
        away_team=Team(team_id=f"{match_id}A", name=f"{match_id} Away"),
        status=MatchStatus.SCHEDULED, result=None,
    )
    return SignalReport(match=match, signal=signal, analysis=None)


def test_chosen_model_prob() -> None:
    s = _signal(match_id="m", outcome=MatchOutcome.HOME, model_prob=0.62, odds=1.9, fair=0.55)
    assert chosen_model_prob(s) == 0.62
    nb = _signal(match_id="m", outcome=MatchOutcome.HOME, model_prob=0.0, odds=2.0, fair=0.5, bet=False)
    assert chosen_model_prob(nb) is None


def test_no_bet_scores_zero() -> None:
    nb = _signal(match_id="m", outcome=MatchOutcome.HOME, model_prob=0.0, odds=2.0, fair=0.5, bet=False)
    assert tip_score(nb) == 0.0


def test_score_in_range_and_rewards_value_and_reliability() -> None:
    strong = _signal(match_id="a", outcome=MatchOutcome.HOME, model_prob=0.65, odds=2.0, fair=0.5,
                     data_quality=90, model_confidence=85)
    weak = _signal(match_id="b", outcome=MatchOutcome.HOME, model_prob=0.52, odds=1.95, fair=0.51,
                   data_quality=45, model_confidence=40)
    assert 0.0 <= tip_score(weak) <= 100.0
    assert 0.0 <= tip_score(strong) <= 100.0
    assert tip_score(strong) > tip_score(weak)


def test_low_data_quality_pulls_score_down() -> None:
    good = _signal(match_id="a", outcome=MatchOutcome.HOME, model_prob=0.6, odds=2.0, fair=0.5,
                   data_quality=90, model_confidence=90)
    thin = _signal(match_id="a", outcome=MatchOutcome.HOME, model_prob=0.6, odds=2.0, fair=0.5,
                   data_quality=30, model_confidence=30)
    assert tip_score(good) > tip_score(thin)


def test_risk_buckets() -> None:
    safe = _signal(match_id="a", outcome=MatchOutcome.HOME, model_prob=0.70, odds=1.6, fair=0.6)
    balanced = _signal(match_id="b", outcome=MatchOutcome.HOME, model_prob=0.50, odds=2.2, fair=0.45)
    risky = _signal(match_id="c", outcome=MatchOutcome.AWAY, model_prob=0.30, odds=4.0, fair=0.25)
    assert risk_level(safe) == "safe"
    assert risk_level(balanced) == "balanced"
    assert risk_level(risky) == "risky"


def test_best_tips_dataframe_ranks_across_leagues() -> None:
    high = _report("high", League.LA_LIGA, _signal(
        match_id="high", outcome=MatchOutcome.HOME, model_prob=0.66, odds=2.1, fair=0.5,
        data_quality=90, model_confidence=85))
    low = _report("low", League.SERIE_A, _signal(
        match_id="low", outcome=MatchOutcome.HOME, model_prob=0.5, odds=1.9, fair=0.5,
        data_quality=50, model_confidence=45))
    nobet = _report("nb", League.BUNDESLIGA, _signal(
        match_id="nb", outcome=MatchOutcome.HOME, model_prob=0.0, odds=2.0, fair=0.5, bet=False))

    df = best_tips_dataframe([low, nobet, high], lang="de", limit=10)
    # No-bet excluded; higher score first, and leagues are mixed in one ranking.
    assert len(df) == 2
    assert list(df["Rang"]) == [1, 2]
    assert df.iloc[0]["Spiel"].startswith("high")
    assert df.iloc[1]["Spiel"].startswith("low")
    assert set(df["Liga"]) == {"La Liga", "Serie A"}


def test_best_tips_respects_limit() -> None:
    reports = [
        _report(f"m{i}", League.LA_LIGA, _signal(
            match_id=f"m{i}", outcome=MatchOutcome.HOME, model_prob=0.55 + i * 0.01,
            odds=2.0, fair=0.5))
        for i in range(8)
    ]
    df = best_tips_dataframe(reports, lang="en", limit=3)
    assert len(df) == 3
    assert list(df.columns)[:3] == ["Rank", "Match", "League"]
