"""High-risk slip bypass and date-window draft helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone

from quantbot.dashboard.app import _fixture_days, _window_draft_key, _window_key
from quantbot.dashboard.slip import build_safe_slip
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
from quantbot.schemas.enums import Sport


UTC = timezone.utc


def _report(match_id: str, odds: float, model_prob: float, kickoff: datetime) -> SignalReport:
    from quantbot.analysis.confidence import ConfidenceLevel
    from quantbot.analysis.engine import AnalysisResult

    metric = ValueMetrics(
        outcome=MatchOutcome.HOME,
        model_prob=model_prob,
        fair_market_prob=max(0.05, min(0.95, 1.0 / odds)),
        decimal_odds=odds,
        edge=model_prob - max(0.05, min(0.95, 1.0 / odds)),
        expected_value=model_prob * odds - 1.0,
    )
    signal = ValueSignal(
        match_id=match_id,
        timestamp=kickoff,
        signal=SignalType.VALUE_HOME,
        chosen_outcome=MatchOutcome.HOME,
        edge=metric.edge,
        expected_value=metric.expected_value,
        decimal_odds=odds,
        model_confidence=70.0,
        data_quality=80.0,
        stake_fraction=0.0,
        metrics=(metric,),
        sizing_allowed=False,
    )
    match = Match(
        match_id=match_id,
        league=League.LA_LIGA,
        season="2026-2027",
        kickoff=kickoff,
        prediction_timestamp=kickoff,
        home_team=Team(team_id=f"h-{match_id}", name=f"Home {match_id}"),
        away_team=Team(team_id=f"a-{match_id}", name=f"Away {match_id}"),
        status=MatchStatus.SCHEDULED,
        sport=Sport.FOOTBALL,
    )
    analysis = AnalysisResult(
        match_id=match_id,
        metrics=(metric,),
        best_ev=metric,
        data_quality=80.0,
        model_confidence=70.0,
        confidence_level=ConfidenceLevel.HIGH,
        ensemble_agreement=0.8,
    )
    return SignalReport(match=match, signal=signal, analysis=analysis)


def test_high_risk_allows_more_legs_than_safe_cap() -> None:
    base = datetime(2026, 9, 20, 15, 0, tzinfo=UTC)
    reports = [
        _report(f"m{i}", odds=1.55 + i * 0.05, model_prob=0.62, kickoff=base)
        for i in range(6)
    ]
    safe = build_safe_slip(reports, lang="de", max_legs=6, bias="safe", allow_high_risk=False)
    risky = build_safe_slip(reports, lang="de", max_legs=6, bias="safe", allow_high_risk=True)
    assert safe is not None and risky is not None
    assert len(safe.legs) <= 4
    assert len(risky.legs) >= len(safe.legs)


def test_window_keys_differ_for_draft() -> None:
    leagues = [League.LA_LIGA]
    assert _window_key(leagues, "2026-2027", True) != _window_draft_key(
        leagues, "2026-2027", True
    )


def test_fixture_days_groups_by_kickoff() -> None:
    class _Orch:
        def universe(self, league, season):  # noqa: ANN001
            return [
                Match(
                    match_id="a",
                    league=League.LA_LIGA,
                    season="2026-2027",
                    kickoff=datetime(2026, 9, 20, 15, tzinfo=UTC),
                    prediction_timestamp=datetime(2026, 9, 19, tzinfo=UTC),
                    home_team=Team(team_id="h1", name="Valencia"),
                    away_team=Team(team_id="a1", name="Sociedad"),
                    status=MatchStatus.SCHEDULED,
                    sport=Sport.FOOTBALL,
                ),
                Match(
                    match_id="b",
                    league=League.LA_LIGA,
                    season="2026-2027",
                    kickoff=datetime(2026, 9, 20, 18, tzinfo=UTC),
                    prediction_timestamp=datetime(2026, 9, 19, tzinfo=UTC),
                    home_team=Team(team_id="h2", name="Getafe"),
                    away_team=Team(team_id="a2", name="Malaga"),
                    status=MatchStatus.SCHEDULED,
                    sport=Sport.FOOTBALL,
                ),
            ]

    days = _fixture_days(
        _Orch(),
        [League.LA_LIGA],
        "2026-2027",
        date(2026, 9, 19),
        date(2026, 9, 21),
    )
    assert len(days) == 1
    assert days[0][0] == date(2026, 9, 20)
    assert len(days[0][1]) == 2
