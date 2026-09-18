"""Dashboard paper-ledger helpers: slip mapping, preview, idempotent commit."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantbot.dashboard.paper import (
    commit_slip,
    legs_from_slip,
    open_bookings,
    paper_ledger_for_mode,
    preview_slip,
    slip_client_key,
)
from quantbot.dashboard.slip import BettingSlip, SlipLeg
from quantbot.ledger import BookingStatus, CapViolationError, ExposureCaps
from quantbot.schemas import MatchOutcome


def _slip(*odds: float) -> BettingSlip:
    legs = []
    for i, o in enumerate(odds, start=1):
        legs.append(
            SlipLeg(
                match_id=f"m{i}",
                match=f"Home{i} vs Away{i}",
                tip="Heim",
                outcome=MatchOutcome.HOME,
                odds=o,
                model_prob=0.55,
                edge=0.05,
                role="core",
                stance="with",
            )
        )
    return BettingSlip(legs=tuple(legs), style="safe")


def test_legs_from_slip_maps_outcome(tmp_path: Path) -> None:
    slip = _slip(2.0, 1.8)
    legs = legs_from_slip(slip)
    assert len(legs) == 2
    assert legs[0].match_id == "m1"
    assert legs[0].selection == MatchOutcome.HOME.value
    assert legs[0].decimal_odds == pytest.approx(2.0)


def test_slip_client_key_stable(tmp_path: Path) -> None:
    slip = _slip(2.0)
    a = slip_client_key(slip, mode="demo")
    b = slip_client_key(slip, mode="demo")
    assert a == b
    assert "demo" in a
    assert slip_client_key(slip, mode="live") != a


def test_commit_slip_idempotent_and_open_list(tmp_path: Path) -> None:
    ledger = paper_ledger_for_mode(
        "demo",
        path=tmp_path / "paper.sqlite3",
        caps=ExposureCaps(paper_capital=1000.0),
    )
    slip = _slip(2.0)
    preview = preview_slip(ledger, slip, stake_units=25.0, mode="demo")
    assert preview.ok
    a = commit_slip(ledger, slip, stake_units=25.0, mode="demo")
    b = commit_slip(ledger, slip, stake_units=25.0, mode="demo")
    assert a.booking_id == b.booking_id
    assert a.status is BookingStatus.RESERVED
    again = preview_slip(ledger, slip, stake_units=25.0, mode="demo")
    assert again.already_committed
    assert again.existing_booking_id == a.booking_id
    opens = open_bookings(ledger)
    assert len(opens) == 1
    assert opens[0].booking_id == a.booking_id


def test_commit_slip_respects_match_cap(tmp_path: Path) -> None:
    ledger = paper_ledger_for_mode(
        "demo",
        path=tmp_path / "paper.sqlite3",
        caps=ExposureCaps(
            paper_capital=1000.0,
            max_match_fraction=0.05,
            max_open_fraction=0.10,
        ),
    )
    slip = _slip(2.0)
    commit_slip(ledger, slip, stake_units=40.0, mode="demo")
    other = _slip(2.1)  # same match ids → second stake on m1
    preview = preview_slip(ledger, other, stake_units=20.0, mode="demo")
    assert preview.ok is False
    with pytest.raises(CapViolationError):
        commit_slip(ledger, other, stake_units=20.0, mode="demo")
