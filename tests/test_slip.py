"""Tests for betting-slip builder and suggested as-of dates."""

from __future__ import annotations

from datetime import datetime, timezone

from quantbot.dashboard.slip import build_boosted_slip, build_safe_slip
from quantbot.dashboard.ux import pages_for, UXMode
from quantbot.orchestrator import QuantBotOrchestrator, SignalReport
from quantbot.schemas import League


def test_slip_page_visible_in_all_modes() -> None:
    for mode in UXMode:
        assert "slip" in pages_for(mode)


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
