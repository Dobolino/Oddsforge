"""Cross-sport tip slip and smart multi-sport picker."""

from __future__ import annotations

from datetime import datetime, timezone

from quantbot.dashboard.leagues import league_choices, resolve_leagues, resolve_sport
from quantbot.dashboard.slip import (
    BettingSlip,
    SlipLeg,
    build_safe_slip,
    build_smart_cross_sport_slip,
)
from quantbot.dashboard.ux import pages_for, UXMode
from quantbot.data.basketball import BasketballDataProvider
from quantbot.data.composite import CompositeDataProvider
from quantbot.data.dummy import DummyDataProvider
from quantbot.orchestrator import QuantBotOrchestrator, SignalReport
from quantbot.schemas import League
from quantbot.schemas.enums import MatchOutcome, Sport, TotalsSide


def _synthetic_report(
    *,
    match_id: str,
    league: League,
    sport: Sport,
    edge: float,
    quality: float,
    odds: float,
    model_prob: float,
    outcome: MatchOutcome | TotalsSide = MatchOutcome.HOME,
) -> SignalReport:
    from quantbot.analysis.confidence import ConfidenceLevel
    from quantbot.analysis.engine import AnalysisResult
    from quantbot.schemas import Match, Team, ValueMetrics, ValueSignal
    from quantbot.schemas.enums import MatchStatus, SignalType

    kickoff = datetime(2024, 12, 20, 20, 0, tzinfo=timezone.utc)
    match = Match(
        match_id=match_id,
        league=league,
        season="2024-2025",
        kickoff=kickoff,
        prediction_timestamp=kickoff.replace(hour=18),
        home_team=Team(team_id=f"{match_id}_h", name=f"Home {match_id}"),
        away_team=Team(team_id=f"{match_id}_a", name=f"Away {match_id}"),
        status=MatchStatus.SCHEDULED,
        sport=sport,
    )
    metrics = (
        ValueMetrics(
            outcome=outcome,
            model_prob=model_prob,
            fair_market_prob=max(0.01, model_prob - edge),
            decimal_odds=odds,
            edge=edge,
            expected_value=model_prob * odds - 1.0,
        ),
    )
    signal_type = {
        MatchOutcome.HOME: SignalType.VALUE_HOME,
        MatchOutcome.AWAY: SignalType.VALUE_AWAY,
        MatchOutcome.DRAW: SignalType.VALUE_DRAW,
        TotalsSide.OVER: SignalType.VALUE_OVER,
        TotalsSide.UNDER: SignalType.VALUE_UNDER,
    }[outcome]
    signal = ValueSignal(
        match_id=match_id,
        timestamp=kickoff.replace(hour=18),
        signal=signal_type,
        chosen_outcome=outcome,
        edge=edge,
        expected_value=model_prob * odds - 1.0,
        decimal_odds=odds,
        model_confidence=80.0,
        data_quality=quality,
        stake_fraction=0.01,
        rationale="synthetic",
        rationale_de="synthetisch",
        rationale_en="synthetic",
        reason_codes=("VALUE",),
        metrics=metrics,
        totals_line=225.5 if isinstance(outcome, TotalsSide) else None,
    )
    analysis = AnalysisResult(
        match_id=match_id,
        metrics=metrics,
        best_ev=metrics[0],
        data_quality=quality,
        model_confidence=80.0,
        confidence_level=ConfidenceLevel.HIGH,
        ensemble_agreement=1.0,
    )
    return SignalReport(match=match, signal=signal, analysis=analysis)


def test_safe_slip_excludes_big_underdog_leg() -> None:
    favorite = _synthetic_report(
        match_id="fav", league=League.LA_LIGA, sport=Sport.FOOTBALL,
        edge=0.05, quality=80.0, odds=1.8, model_prob=0.6,
    )
    underdog = _synthetic_report(
        match_id="dog", league=League.LA_LIGA, sport=Sport.FOOTBALL,
        edge=0.10, quality=80.0, odds=10.0, model_prob=0.2,
    )
    slip = build_safe_slip([favorite, underdog], lang="de", max_legs=3)
    assert slip is not None
    ids = {leg.match_id for leg in slip.legs}
    assert "fav" in ids
    assert "dog" not in ids  # odds 10.0 filtered out before building


def test_slip_bias_changes_leg_priority() -> None:
    favorite = _synthetic_report(
        match_id="fav", league=League.LA_LIGA, sport=Sport.FOOTBALL,
        edge=0.03, quality=80.0, odds=1.6, model_prob=0.65,
    )
    underdog = _synthetic_report(
        match_id="dog", league=League.LA_LIGA, sport=Sport.FOOTBALL,
        edge=0.15, quality=80.0, odds=3.0, model_prob=0.40,
    )
    safe = build_safe_slip([favorite, underdog], lang="de", max_legs=1, bias="safe")
    contra = build_safe_slip([favorite, underdog], lang="de", max_legs=1, bias="contra")
    assert safe is not None and contra is not None
    assert safe.legs[0].match_id == "fav"     # highest model probability
    assert contra.legs[0].match_id == "dog"   # biggest edge vs market


def test_sport_filter_limits_leagues() -> None:
    basketball = resolve_sport("basketball")
    choices = league_choices(basketball)
    assert choices[0] == "all"
    assert choices[1:] == ["nba"]
    assert resolve_leagues("all", basketball) == [League.NBA]


def test_settings_page_visible_in_modes() -> None:
    assert "settings" in pages_for(UXMode.BEGINNER)
    assert "settings" in pages_for(UXMode.ADVANCED)
    assert "settings" in pages_for(UXMode.EXPERT)


def test_safe_slip_accepts_mixed_sports() -> None:
    reports = [
        _synthetic_report(
            match_id="fb1",
            league=League.PREMIER_LEAGUE,
            sport=Sport.FOOTBALL,
            edge=0.05,
            quality=80,
            odds=1.9,
            model_prob=0.58,
        ),
        _synthetic_report(
            match_id="nba1",
            league=League.NBA,
            sport=Sport.BASKETBALL,
            edge=0.06,
            quality=75,
            odds=1.85,
            model_prob=0.6,
            outcome=TotalsSide.UNDER,
        ),
    ]
    slip = build_safe_slip(reports, lang="en", max_legs=2)
    assert slip is not None
    assert len(slip.legs) == 2
    sports = {leg.sport for leg in slip.legs}
    assert sports == {"football", "basketball"}


def test_smart_cross_sport_respects_gates_and_mixes() -> None:
    reports = [
        _synthetic_report(
            match_id="fb_low",
            league=League.PREMIER_LEAGUE,
            sport=Sport.FOOTBALL,
            edge=0.01,
            quality=90,
            odds=2.0,
            model_prob=0.55,
        ),
        _synthetic_report(
            match_id="fb_ok",
            league=League.BUNDESLIGA,
            sport=Sport.FOOTBALL,
            edge=0.05,
            quality=80,
            odds=2.1,
            model_prob=0.57,
        ),
        _synthetic_report(
            match_id="nba_ok",
            league=League.NBA,
            sport=Sport.BASKETBALL,
            edge=0.07,
            quality=78,
            odds=1.95,
            model_prob=0.59,
            outcome=MatchOutcome.AWAY,
        ),
    ]
    slip = build_smart_cross_sport_slip(
        reports, lang="de", max_legs=3, min_edge=0.02, min_data_quality=70.0
    )
    assert slip is not None
    assert slip.style == "smart"
    ids = {leg.match_id for leg in slip.legs}
    assert "fb_low" not in ids
    assert "fb_ok" in ids and "nba_ok" in ids
    assert slip.combined_odds > 1.0
    assert 0.0 < slip.combined_prob <= 1.0


def test_composite_provider_serves_both_sports() -> None:
    # Dummy already includes NBA; composite with explicit basketball still works.
    foot = DummyDataProvider()
    basket = BasketballDataProvider(seed=11)
    provider = CompositeDataProvider(foot, basket)
    orch = QuantBotOrchestrator(provider=provider)
    fb = orch.predict(League.PREMIER_LEAGUE, "2024-2025")
    nba = orch.predict(League.NBA, "2024-2025")
    assert isinstance(fb, list) and isinstance(nba, list)
    assert nba and nba[0].match.sport is Sport.BASKETBALL


def test_slip_leg_math_independence() -> None:
    slip = BettingSlip(
        legs=(
            SlipLeg(
                match_id="1",
                match="A vs B",
                tip="Home",
                outcome=MatchOutcome.HOME,
                odds=2.0,
                model_prob=0.5,
                edge=0.05,
                role="core",
                league="Premier League",
                kickoff_date="2024-12-01",
                sport="football",
            ),
            SlipLeg(
                match_id="2",
                match="C vs D",
                tip="Away",
                outcome=MatchOutcome.AWAY,
                odds=1.8,
                model_prob=0.6,
                edge=0.04,
                role="core",
                league="Nba",
                kickoff_date="2024-12-02",
                sport="basketball",
            ),
        ),
        style="smart",
    )
    assert abs(slip.combined_odds - 3.6) < 1e-9
    assert abs(slip.combined_prob - 0.3) < 1e-9
    assert abs(slip.expected_value - (0.3 * 3.6 - 1.0)) < 1e-9
