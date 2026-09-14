"""Tests for tip-slip leg selection and beginner defaults."""

from __future__ import annotations

from pathlib import Path

from quantbot.dashboard.slip import (
    BettingSlip,
    SlipLeg,
    default_leg_count,
    slip_with_legs,
)
from quantbot.preferences import (
    clear_welcome_dismissed,
    is_welcome_dismissed,
    set_welcome_dismissed,
)
from quantbot.schemas import MatchOutcome


def _leg(match_id: str, odds: float = 1.8, prob: float = 0.5) -> SlipLeg:
    return SlipLeg(
        match_id=match_id,
        match=f"Team {match_id}",
        tip="Tipp: Heimsieg",
        outcome=MatchOutcome.HOME,
        odds=odds,
        model_prob=prob,
        edge=0.05,
        role="core",
    )


def test_slip_with_legs_filters_and_recomputes() -> None:
    slip = BettingSlip(legs=(_leg("a", 2.0, 0.5), _leg("b", 1.5, 0.6), _leg("c", 3.0, 0.4)), style="safe")
    trimmed = slip_with_legs(slip, ["a", "c"])
    assert [leg.match_id for leg in trimmed.legs] == ["a", "c"]
    assert trimmed.style == "safe"
    assert trimmed.combined_odds == 2.0 * 3.0
    empty = slip_with_legs(slip, [])
    assert empty.legs == ()


def test_default_leg_count_beginner_is_short() -> None:
    assert default_leg_count(beginner=True, span_days=7, available=10) == 3
    assert default_leg_count(beginner=True, span_days=1, available=2) == 2
    assert default_leg_count(beginner=False, span_days=7, available=10) == 8


def test_welcome_dismiss_persists(tmp_path: Path) -> None:
    path = tmp_path / "welcome_dismissed"
    assert is_welcome_dismissed(path=path) is False
    set_welcome_dismissed(path=path)
    assert is_welcome_dismissed(path=path) is True
    assert clear_welcome_dismissed(path=path) is True
    assert is_welcome_dismissed(path=path) is False
