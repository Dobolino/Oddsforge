"""High-Risk profile: list every fixture + force exploratory tips on thin data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from quantbot.analysis.confidence import ConfidenceLevel
from quantbot.analysis.engine import AnalysisResult
from quantbot.dashboard.slip import _leg_from_report, build_safe_slip
from quantbot.data.dummy import DummyDataProvider
from quantbot.decision import DecisionEngine, DecisionStatus, high_risk_policy, live_policy
from quantbot.markets.odds import MarketEngine
from quantbot.models.dixon_coles import DixonColesModel
from quantbot.orchestrator import QuantBotOrchestrator, SignalReport
from quantbot.schemas import (
    League,
    Match,
    MatchOutcome,
    MatchStatus,
    Odds,
    Team,
    TotalsSide,
    ValueMetrics,
    ValueSignal,
)
from quantbot.schemas.enums import SignalType


UTC = timezone.utc


def _metric(prob: float = 0.52, fair: float = 0.48, odds: float = 2.05) -> ValueMetrics:
    return ValueMetrics(
        outcome=MatchOutcome.HOME,
        model_prob=prob,
        fair_market_prob=fair,
        decimal_odds=odds,
        edge=prob - fair,
        expected_value=prob * odds - 1.0,
    )


def _analysis(metric: ValueMetrics, home: int = 2, away: int = 2) -> AnalysisResult:
    return AnalysisResult(
        match_id="m1",
        metrics=(metric,),
        best_ev=metric,
        data_quality=40.0,
        model_confidence=35.0,
        confidence_level=ConfidenceLevel.LOW,
        ensemble_agreement=0.5,
        home_matches=home,
        away_matches=away,
    )


def test_high_risk_forces_value_on_thin_history() -> None:
    """Nations-League-thin history: still get exploratory tip under High-Risk."""

    ts = datetime(2024, 12, 1, tzinfo=UTC)
    entry = Odds(
        match_id="m1",
        bookmaker="x",
        timestamp=ts,
        home=2.05,
        draw=3.40,
        away=3.50,
    )
    market = MarketEngine().to_market_data(entry)
    metric = _metric()
    analysis = _analysis(metric, home=1, away=1)

    normal = DecisionEngine.from_policy(live_policy()).decide(
        analysis, market, home_matches=1, away_matches=1
    )
    assert not normal.is_bet
    assert "INVALID_DATA_HISTORY" in normal.reason_codes

    # min_team_matches=0 + loose filters → tip clears normally as exploratory.
    risky = DecisionEngine.from_policy(high_risk_policy()).decide(
        analysis, market, home_matches=1, away_matches=1
    )
    assert risky.is_bet
    assert risky.stake_fraction == 0.0
    assert risky.sizing_allowed is False
    assert risky.decision_status == DecisionStatus.VALUE_EXPLORATORY.value
    assert "MODEL_NOT_VALIDATED_NO_SIZING" in risky.reason_codes


def test_high_risk_forces_value_when_filters_fail() -> None:
    """Negative/low EV still surfaces best side under force_best_ev_on_no_bet."""

    ts = datetime(2024, 12, 1, tzinfo=UTC)
    entry = Odds(
        match_id="m1",
        bookmaker="x",
        timestamp=ts,
        home=1.90,
        draw=3.40,
        away=4.00,
    )
    market = MarketEngine().to_market_data(entry)
    # Model slightly below market → normal NO_BET_LOW_EV / LOW_EDGE.
    metric = _metric(prob=0.48, fair=0.50, odds=1.90)
    analysis = _analysis(metric, home=10, away=10)
    risky = DecisionEngine.from_policy(high_risk_policy()).decide(
        analysis, market, home_matches=10, away_matches=10
    )
    assert risky.is_bet
    assert "VALUE_HIGH_RISK_FORCED" in risky.reason_codes


def test_predict_lists_matches_without_odds() -> None:
    class _NoOdds(DummyDataProvider):
        def get_latest_odds(self, match_id: str, as_of):  # type: ignore[no-untyped-def]
            return None

    orch = QuantBotOrchestrator(
        provider=_NoOdds(),
        live=False,
        min_team_matches=0,
        persist_snapshots=False,
        decision_policy=high_risk_policy(),
    )
    reports = orch.predict(League.PREMIER_LEAGUE, "2024-2025")
    assert reports
    assert all(not r.signal.is_bet for r in reports)
    assert all("INVALID_DATA_MISSING_ODDS" in r.signal.reason_codes for r in reports)


def test_predict_lists_matches_when_model_not_fit() -> None:
    orch = QuantBotOrchestrator(
        provider=DummyDataProvider(),
        model=DixonColesModel(min_matches=10_000),
        live=False,
        min_team_matches=0,
        persist_snapshots=False,
        decision_policy=high_risk_policy(),
    )
    reports = orch.predict(League.PREMIER_LEAGUE, "2024-2025")
    assert reports
    assert all("INVALID_DATA_MODEL_NOT_FIT" in r.signal.reason_codes for r in reports)


def test_slip_high_risk_keeps_thin_totals_legs() -> None:
    from quantbot.schemas.enums import Sport

    kickoff = datetime(2024, 12, 20, 20, 0, tzinfo=UTC)
    match = Match(
        match_id="ou_thin",
        league=League.PREMIER_LEAGUE,
        season="2024-2025",
        kickoff=kickoff,
        prediction_timestamp=kickoff - timedelta(hours=2),
        home_team=Team(team_id="h", name="Home"),
        away_team=Team(team_id="a", name="Away"),
        status=MatchStatus.SCHEDULED,
        sport=Sport.FOOTBALL,
    )
    metric = ValueMetrics(
        outcome=TotalsSide.OVER,
        model_prob=0.55,
        fair_market_prob=0.48,
        decimal_odds=2.05,
        edge=0.07,
        expected_value=0.55 * 2.05 - 1.0,
    )
    signal = ValueSignal(
        match_id=match.match_id,
        timestamp=kickoff - timedelta(hours=1),
        signal=SignalType.VALUE_OVER,
        chosen_outcome=TotalsSide.OVER,
        edge=0.07,
        expected_value=0.55 * 2.05 - 1.0,
        decimal_odds=2.05,
        model_confidence=40.0,
        data_quality=30.0,
        stake_fraction=0.0,
        metrics=(metric,),
        totals_line=2.5,
    )
    thin = AnalysisResult(
        match_id=match.match_id,
        metrics=(metric,),
        best_ev=metric,
        data_quality=30.0,
        model_confidence=40.0,
        confidence_level=ConfidenceLevel.LOW,
        ensemble_agreement=0.5,
        home_matches=2,
        away_matches=2,
    )
    report = SignalReport(match=match, signal=signal, analysis=thin)
    assert _leg_from_report(report, "de", "core") is None
    assert _leg_from_report(report, "de", "core", allow_high_risk=True) is not None
    slip = build_safe_slip([report], lang="de", max_legs=3, bias="balanced", allow_high_risk=True)
    assert slip is not None
    assert len(slip.legs) == 1
