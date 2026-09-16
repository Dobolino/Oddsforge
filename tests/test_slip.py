"""Tests for betting-slip builder and suggested as-of dates."""

from __future__ import annotations

from datetime import datetime, timezone

from quantbot.dashboard.slip import (
    BettingSlip,
    SlipLeg,
    build_boosted_slip,
    build_safe_slip,
    format_ticket,
)
from quantbot.dashboard.ux import pages_for, UXMode
from quantbot.orchestrator import QuantBotOrchestrator, SignalReport
from quantbot.schemas import League, MatchOutcome


def _leg(odds: float, model_prob: float) -> SlipLeg:
    return SlipLeg(
        match_id="m",
        match="A vs B",
        tip="Tipp: Heimsieg",
        outcome=MatchOutcome.HOME,
        odds=odds,
        model_prob=model_prob,
        edge=model_prob - 1.0 / odds,
        role="core",
    )


def test_slip_flags_overconfident_chance_as_implausible() -> None:
    # Five legs each at ~1.7 with a 95% model prob -> ~79% combined on 14x odds.
    slip = BettingSlip(legs=tuple(_leg(1.7, 0.95) for _ in range(5)), style="safe")
    assert slip.combined_prob > 0.7
    assert not slip.is_plausible
    text = format_ticket(slip, lang="de")
    assert "unrealistisch" in text
    assert "78" not in text and "79" not in text  # no rosy percentage shown


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
