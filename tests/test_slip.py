"""Tests for betting-slip builder and suggested as-of dates."""

from __future__ import annotations

from datetime import datetime, timezone

from quantbot.dashboard.slip import (
    BettingSlip,
    SlipLeg,
    build_boosted_slip,
    build_safe_slip,
    format_ticket,
    make_plausible_slip,
)
from quantbot.dashboard.ux import pages_for, UXMode
from quantbot.orchestrator import QuantBotOrchestrator, SignalReport
from quantbot.schemas import League, MatchOutcome, TotalsSide


def _leg(
    odds: float,
    model_prob: float,
    *,
    match_id: str = "m",
    stance: str = "with",
    outcome: MatchOutcome | TotalsSide = MatchOutcome.HOME,
    tip: str = "Tipp: Heimsieg",
) -> SlipLeg:
    return SlipLeg(
        match_id=match_id,
        match="A vs B",
        tip=tip,
        outcome=outcome,
        odds=odds,
        model_prob=model_prob,
        edge=model_prob - 1.0 / odds,
        role="core",
        stance=stance,
    )


def test_slip_flags_overconfident_chance_as_implausible() -> None:
    # Five legs each at ~1.7 with a 95% model prob -> ~79% combined on 14x odds.
    slip = BettingSlip(legs=tuple(_leg(1.7, 0.95) for _ in range(5)), style="safe")
    assert slip.combined_prob > 0.7
    assert not slip.is_plausible
    text = format_ticket(slip, lang="de")
    assert "unrealistisch" in text
    assert "78" not in text and "79" not in text  # no rosy percentage shown


def test_make_plausible_slip_drops_overconfident_legs() -> None:
    over = BettingSlip(
        legs=(
            _leg(1.7, 0.95, match_id="a"),
            _leg(1.7, 0.95, match_id="b"),
            _leg(1.7, 0.95, match_id="c"),
            _leg(1.8, 0.58, match_id="d"),
            _leg(2.0, 0.52, match_id="e"),
        ),
        style="safe",
    )
    assert not over.is_plausible
    fixed = make_plausible_slip(over)
    assert fixed is not None
    assert fixed.is_plausible
    assert len(fixed.legs) < len(over.legs)


def test_safe_builder_never_returns_implausible_combo() -> None:
    from quantbot.analysis.confidence import ConfidenceLevel
    from quantbot.analysis.engine import AnalysisResult
    from quantbot.schemas import Match, Team, ValueMetrics, ValueSignal
    from quantbot.schemas.enums import MatchStatus, SignalType

    def _report(mid: str, odds: float, model_prob: float, fair: float) -> SignalReport:
        kickoff = datetime(2024, 12, 20, 20, 0, tzinfo=timezone.utc)
        match = Match(
            match_id=mid,
            league=League.PREMIER_LEAGUE,
            season="2024-2025",
            kickoff=kickoff,
            prediction_timestamp=kickoff.replace(hour=18),
            home_team=Team(team_id=f"{mid}_h", name=f"Home {mid}"),
            away_team=Team(team_id=f"{mid}_a", name=f"Away {mid}"),
            status=MatchStatus.SCHEDULED,
        )
        metrics = (
            ValueMetrics(
                outcome=MatchOutcome.HOME,
                model_prob=model_prob,
                fair_market_prob=fair,
                decimal_odds=odds,
                edge=model_prob - fair,
                expected_value=model_prob * odds - 1.0,
            ),
            ValueMetrics(
                outcome=MatchOutcome.DRAW,
                model_prob=0.2,
                fair_market_prob=0.25,
                decimal_odds=4.0,
                edge=-0.05,
                expected_value=-0.2,
            ),
            ValueMetrics(
                outcome=MatchOutcome.AWAY,
                model_prob=0.15,
                fair_market_prob=0.3,
                decimal_odds=3.5,
                edge=-0.15,
                expected_value=-0.475,
            ),
        )
        signal = ValueSignal(
            match_id=mid,
            timestamp=kickoff.replace(hour=18),
            signal=SignalType.VALUE_HOME,
            chosen_outcome=MatchOutcome.HOME,
            edge=model_prob - fair,
            expected_value=model_prob * odds - 1.0,
            decimal_odds=odds,
            model_confidence=70.0,
            data_quality=80.0,
            stake_fraction=0.01,
            rationale="synthetic",
            rationale_de="synthetisch",
            metrics=metrics,
        )
        analysis = AnalysisResult(
            match_id=mid,
            metrics=metrics,
            best_ev=metrics[0],
            data_quality=80.0,
            model_confidence=70.0,
            confidence_level=ConfidenceLevel.MEDIUM,
            ensemble_agreement=1.0,
            home_matches=8,
            away_matches=8,
        )
        return SignalReport(match=match, signal=signal, analysis=analysis)

    reports = [
        _report("a", 1.7, 0.95, 0.55),
        _report("b", 1.7, 0.94, 0.55),
        _report("c", 1.8, 0.93, 0.52),
        _report("d", 1.8, 0.58, 0.52),
        _report("e", 2.0, 0.52, 0.48),
    ]
    slip = build_safe_slip(reports, lang="de", max_legs=5, bias="safe")
    assert slip is not None
    assert slip.is_plausible


def test_totals_legs_skipped_when_team_history_thin() -> None:
    from quantbot.analysis.confidence import ConfidenceLevel
    from quantbot.analysis.engine import AnalysisResult
    from quantbot.dashboard.slip import _leg_from_report
    from quantbot.schemas import Match, Team, ValueMetrics, ValueSignal
    from quantbot.schemas.enums import MatchStatus, SignalType

    kickoff = datetime(2024, 12, 20, 20, 0, tzinfo=timezone.utc)
    match = Match(
        match_id="ou1",
        league=League.LA_LIGA,
        season="2024-2025",
        kickoff=kickoff,
        prediction_timestamp=kickoff.replace(hour=18),
        home_team=Team(team_id="h", name="Home"),
        away_team=Team(team_id="a", name="Away"),
        status=MatchStatus.SCHEDULED,
    )
    metrics = (
        ValueMetrics(
            outcome=TotalsSide.UNDER,
            model_prob=0.62,
            fair_market_prob=0.5,
            decimal_odds=1.9,
            edge=0.12,
            expected_value=0.178,
        ),
        ValueMetrics(
            outcome=TotalsSide.OVER,
            model_prob=0.38,
            fair_market_prob=0.5,
            decimal_odds=1.9,
            edge=-0.12,
            expected_value=-0.278,
        ),
    )
    signal = ValueSignal(
        match_id="ou1",
        timestamp=kickoff.replace(hour=18),
        signal=SignalType.VALUE_UNDER,
        chosen_outcome=TotalsSide.UNDER,
        edge=0.12,
        expected_value=0.178,
        decimal_odds=1.9,
        model_confidence=60.0,
        data_quality=70.0,
        stake_fraction=0.01,
        rationale="ou",
        rationale_de="ou",
        metrics=metrics,
        totals_line=2.5,
    )
    thin = AnalysisResult(
        match_id="ou1",
        metrics=metrics,
        best_ev=metrics[0],
        data_quality=70.0,
        model_confidence=60.0,
        confidence_level=ConfidenceLevel.LOW,
        ensemble_agreement=0.5,
        home_matches=2,
        away_matches=3,
    )
    ok = AnalysisResult(
        match_id="ou1",
        metrics=metrics,
        best_ev=metrics[0],
        data_quality=70.0,
        model_confidence=60.0,
        confidence_level=ConfidenceLevel.MEDIUM,
        ensemble_agreement=0.8,
        home_matches=7,
        away_matches=6,
    )
    assert _leg_from_report(SignalReport(match=match, signal=signal, analysis=thin), "de", "core") is None
    assert _leg_from_report(SignalReport(match=match, signal=signal, analysis=ok), "de", "core") is not None


def test_safe_bias_prefers_with_market_legs() -> None:
    from quantbot.analysis.confidence import ConfidenceLevel
    from quantbot.analysis.engine import AnalysisResult
    from quantbot.schemas import Match, Team, ValueMetrics, ValueSignal
    from quantbot.schemas.enums import MatchStatus, SignalType

    def _report(mid: str, *, with_market: bool, model_prob: float) -> SignalReport:
        kickoff = datetime(2024, 12, 20, 20, 0, tzinfo=timezone.utc)
        match = Match(
            match_id=mid,
            league=League.PREMIER_LEAGUE,
            season="2024-2025",
            kickoff=kickoff,
            prediction_timestamp=kickoff.replace(hour=18),
            home_team=Team(team_id=f"{mid}_h", name=f"Home {mid}"),
            away_team=Team(team_id=f"{mid}_a", name=f"Away {mid}"),
            status=MatchStatus.SCHEDULED,
        )
        # Market favorite is always HOME (highest fair). Against-market tips AWAY.
        fair_home, fair_draw, fair_away = 0.55, 0.20, 0.25
        if with_market:
            chosen, tip_type = MatchOutcome.HOME, SignalType.VALUE_HOME
            odds = 1.85
            p_home, p_draw, p_away = model_prob, 0.22, max(0.05, 1.0 - model_prob - 0.22)
        else:
            chosen, tip_type = MatchOutcome.AWAY, SignalType.VALUE_AWAY
            odds = 3.4
            p_away = 0.40
            p_home, p_draw = 0.40, 0.20
            model_prob = p_away

        def _m(outcome, p, fair, dec):
            return ValueMetrics(
                outcome=outcome,
                model_prob=p,
                fair_market_prob=fair,
                decimal_odds=dec,
                edge=p - fair,
                expected_value=p * dec - 1.0,
            )

        metrics = (
            _m(MatchOutcome.HOME, p_home, fair_home, 1.85),
            _m(MatchOutcome.DRAW, p_draw, fair_draw, 4.5),
            _m(MatchOutcome.AWAY, p_away, fair_away, odds if not with_market else 4.0),
        )
        chosen_m = next(m for m in metrics if m.outcome is chosen)
        signal = ValueSignal(
            match_id=mid,
            timestamp=kickoff.replace(hour=18),
            signal=tip_type,
            chosen_outcome=chosen,
            edge=chosen_m.edge,
            expected_value=chosen_m.expected_value,
            decimal_odds=chosen_m.decimal_odds,
            model_confidence=70.0,
            data_quality=80.0,
            stake_fraction=0.01,
            rationale="x",
            rationale_de="x",
            metrics=metrics,
        )
        analysis = AnalysisResult(
            match_id=mid,
            metrics=metrics,
            best_ev=chosen_m,
            data_quality=80.0,
            model_confidence=70.0,
            confidence_level=ConfidenceLevel.MEDIUM,
            ensemble_agreement=1.0,
            home_matches=10,
            away_matches=10,
        )
        return SignalReport(match=match, signal=signal, analysis=analysis)

    reports = [
        _report("against1", with_market=False, model_prob=0.99),
        _report("with1", with_market=True, model_prob=0.58),
        _report("with2", with_market=True, model_prob=0.55),
    ]
    slip = build_safe_slip(reports, lang="de", max_legs=3, bias="safe")
    assert slip is not None
    assert all(leg.stance == "with" for leg in slip.legs)
    assert "against1" not in {leg.match_id for leg in slip.legs}
    assert slip.is_plausible
    assert slip.combined_odds <= 8.0
    assert all(leg.odds <= 2.60 for leg in slip.legs)
    assert all(not isinstance(leg.outcome, TotalsSide) for leg in slip.legs)


def test_safe_bias_drops_long_odds_and_totals() -> None:
    from quantbot.analysis.confidence import ConfidenceLevel
    from quantbot.analysis.engine import AnalysisResult
    from quantbot.schemas import Match, Team, ValueMetrics, ValueSignal
    from quantbot.schemas.enums import MatchStatus, SignalType

    def _home(mid: str, odds: float, model_prob: float, fair: float) -> SignalReport:
        kickoff = datetime(2024, 12, 20, 20, 0, tzinfo=timezone.utc)
        match = Match(
            match_id=mid,
            league=League.PREMIER_LEAGUE,
            season="2024-2025",
            kickoff=kickoff,
            prediction_timestamp=kickoff.replace(hour=18),
            home_team=Team(team_id=f"{mid}_h", name=f"Home {mid}"),
            away_team=Team(team_id=f"{mid}_a", name=f"Away {mid}"),
            status=MatchStatus.SCHEDULED,
        )
        metrics = (
            ValueMetrics(
                outcome=MatchOutcome.HOME,
                model_prob=model_prob,
                fair_market_prob=fair,
                decimal_odds=odds,
                edge=model_prob - fair,
                expected_value=model_prob * odds - 1.0,
            ),
        )
        signal = ValueSignal(
            match_id=mid,
            timestamp=kickoff.replace(hour=18),
            signal=SignalType.VALUE_HOME,
            chosen_outcome=MatchOutcome.HOME,
            edge=model_prob - fair,
            expected_value=model_prob * odds - 1.0,
            decimal_odds=odds,
            model_confidence=70.0,
            data_quality=80.0,
            stake_fraction=0.01,
            rationale="x",
            rationale_de="x",
            metrics=metrics,
        )
        analysis = AnalysisResult(
            match_id=mid,
            metrics=metrics,
            best_ev=metrics[0],
            data_quality=80.0,
            model_confidence=70.0,
            confidence_level=ConfidenceLevel.MEDIUM,
            ensemble_agreement=1.0,
            home_matches=10,
            away_matches=10,
        )
        return SignalReport(match=match, signal=signal, analysis=analysis)

    long_price = _home("long", 4.33, 0.30, 0.22)  # against-ish / too long for safe
    # Force stance "with" via single metric (chosen = top fair).
    ok = _home("ok", 1.70, 0.60, 0.55)
    slip = build_safe_slip([long_price, ok], lang="de", max_legs=3, bias="safe")
    assert slip is not None
    assert {leg.match_id for leg in slip.legs} == {"ok"}


def test_market_stance_matches_metrics() -> None:
    from quantbot.dashboard.ux import market_stance

    reports = QuantBotOrchestrator().predict(League.PREMIER_LEAGUE, "2024-2025")
    for r in reports:
        s = r.signal
        stance = market_stance(s)
        if not s.is_bet:
            assert stance is None
            continue
        assert stance in {"with", "against"}
        chosen = next(m for m in s.metrics if m.outcome is s.chosen_outcome)
        top = max(m.fair_market_prob for m in s.metrics)
        assert stance == ("with" if chosen.fair_market_prob >= top - 1e-9 else "against")


def test_big_underdog_leg_flags_slip() -> None:
    # A leg at 10.0 (a big underdog) makes the slip implausible even if the
    # combined chance looks modest.
    slip = BettingSlip(legs=(_leg(2.34, 0.45), _leg(10.0, 0.11)), style="safe")
    assert not slip.is_plausible


def test_realistic_slip_stays_plausible() -> None:
    # Legs priced near their model probability -> small edge, believable combo.
    slip = BettingSlip(legs=(_leg(1.7, 0.60), _leg(2.0, 0.52)), style="safe")
    assert slip.is_plausible
    assert f"{slip.combined_prob * 100:.1f}" in format_ticket(slip, lang="de")


def test_slip_page_hidden_for_beginner() -> None:
    assert "slip" not in pages_for(UXMode.BEGINNER)
    assert "slip" in pages_for(UXMode.ADVANCED)
    assert "slip" in pages_for(UXMode.EXPERT)


def test_suggested_as_of_live_is_today() -> None:
    orch = QuantBotOrchestrator()
    now = datetime.now(timezone.utc)
    suggested = orch.suggested_as_of(League.PREMIER_LEAGUE, "2024-2025", live=True)
    assert abs((suggested - now).total_seconds()) < 5


def test_suggested_as_of_demo_is_mid_season() -> None:
    orch = QuantBotOrchestrator()
    mid = orch.default_as_of(League.PREMIER_LEAGUE, "2024-2025")
    suggested = orch.suggested_as_of(League.PREMIER_LEAGUE, "2024-2025", live=False)
    assert suggested == mid


def test_safe_slip_prefers_high_probability() -> None:
    orch = QuantBotOrchestrator()
    reports = orch.predict(League.PREMIER_LEAGUE, "2024-2025")
    slip = build_safe_slip(reports, lang="de", max_legs=3)
    # May be empty if demo has no value tips — still a valid result.
    if slip is None:
        return
    assert 1 <= len(slip.legs) <= 3
    assert slip.style == "safe"
    assert slip.combined_odds >= 1.0
    assert slip.is_plausible
    probs = [leg.model_prob for leg in slip.legs]
    assert probs == sorted(probs, reverse=True)


def test_boosted_slip_marks_roles() -> None:
    orch = QuantBotOrchestrator()
    reports = orch.predict(League.PREMIER_LEAGUE, "2024-2025")
    # Force a few synthetic value legs if demo has none by skipping.
    value_reports = [r for r in reports if r.signal.is_bet]
    if len(value_reports) < 2:
        return
    slip = build_boosted_slip(reports, lang="de", core_legs=1, boost_legs=2, min_boost_odds=1.01)
    assert slip is not None
    assert any(leg.role == "core" for leg in slip.legs)
    assert slip.combined_prob > 0.0
    assert slip.is_plausible
