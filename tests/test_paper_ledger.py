"""Paper ledger exposure caps and idempotent booking tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from quantbot.ledger import (
    BookingLeg,
    BookingStatus,
    CapReason,
    CapViolationError,
    ExposureCaps,
    PaperLedger,
)


UTC = timezone.utc


def _leg(match_id: str, selection: str = "home", odds: float = 2.0) -> BookingLeg:
    return BookingLeg(match_id=match_id, selection=selection, decimal_odds=odds)


def _ledger(tmp_path: Path, capital: float = 1000.0) -> PaperLedger:
    return PaperLedger(
        path=tmp_path / "paper.sqlite3",
        mode="demo",
        caps=ExposureCaps(
            paper_capital=capital,
            max_match_fraction=0.05,
            max_open_fraction=0.10,
        ),
    )


def test_preview_does_not_reserve(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    before = ledger.snapshot()
    preview = ledger.preview(stake=40.0, legs=[_leg("m1")])
    assert preview.ok
    after = ledger.snapshot()
    assert after.open_reserved == before.open_reserved == 0.0
    assert after.available == before.available == 1000.0
    assert ledger.list_bookings() == []


def test_commit_reserves_and_reduces_available(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    booking = ledger.commit(
        client_key="k1",
        stake=40.0,
        legs=[_leg("m1")],
        decimal_odds=2.1,
    )
    assert booking.status is BookingStatus.RESERVED
    snap = ledger.snapshot()
    assert snap.open_reserved == pytest.approx(40.0)
    assert snap.available == pytest.approx(960.0)
    assert snap.open_by_match["m1"] == pytest.approx(40.0)


def test_idempotent_client_key_no_double_reserve(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    a = ledger.commit(client_key="rerun", stake=30.0, legs=[_leg("m1")], decimal_odds=2.0)
    b = ledger.commit(client_key="rerun", stake=30.0, legs=[_leg("m1")], decimal_odds=2.0)
    assert a.booking_id == b.booking_id
    assert ledger.snapshot().open_reserved == pytest.approx(30.0)
    assert len(ledger.list_bookings(status=BookingStatus.RESERVED)) == 1


def test_match_exposure_cap_blocks(tmp_path: Path) -> None:
    # 5% of 1000 = 50
    ledger = _ledger(tmp_path)
    ledger.commit(client_key="a", stake=40.0, legs=[_leg("m1")], decimal_odds=2.0)
    preview = ledger.preview(stake=20.0, legs=[_leg("m1")])
    assert preview.ok is False
    assert CapReason.MATCH_EXPOSURE_CAP.value in preview.reasons
    with pytest.raises(CapViolationError) as exc:
        ledger.commit(client_key="b", stake=20.0, legs=[_leg("m1")], decimal_odds=2.0)
    assert CapReason.MATCH_EXPOSURE_CAP.value in exc.value.reasons


def test_total_open_cap_blocks(tmp_path: Path) -> None:
    # 10% of 1000 = 100
    ledger = _ledger(tmp_path)
    ledger.commit(client_key="a", stake=50.0, legs=[_leg("m1")], decimal_odds=2.0)
    ledger.commit(client_key="b", stake=50.0, legs=[_leg("m2")], decimal_odds=2.0)
    preview = ledger.preview(stake=1.0, legs=[_leg("m3")])
    assert CapReason.TOTAL_OPEN_CAP.value in preview.reasons
    with pytest.raises(CapViolationError):
        ledger.commit(client_key="c", stake=1.0, legs=[_leg("m3")], decimal_odds=2.0)


def test_combo_attributes_full_stake_to_each_match(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    legs = (_leg("m1", "home", 2.0), _leg("m2", "away", 1.8))
    booking = ledger.commit(
        client_key="combo",
        stake=40.0,
        legs=legs,
        decimal_odds=3.6,
    )
    snap = ledger.snapshot()
    assert snap.open_reserved == pytest.approx(40.0)  # counted once
    assert snap.open_by_match["m1"] == pytest.approx(40.0)
    assert snap.open_by_match["m2"] == pytest.approx(40.0)
    assert booking.match_ids == ("m1", "m2")

    # Another 20 on m1 would breach 50 match cap (40+20).
    preview = ledger.preview(stake=20.0, legs=[_leg("m1")])
    assert CapReason.MATCH_EXPOSURE_CAP.value in preview.reasons


def test_settle_win_releases_and_updates_pnl(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    booking = ledger.commit(
        client_key="w", stake=50.0, legs=[_leg("m1")], decimal_odds=2.0
    )
    settled = ledger.settle(booking.booking_id, won=True)
    assert settled.status is BookingStatus.SETTLED
    assert settled.pnl == pytest.approx(50.0)
    assert settled.payout == pytest.approx(100.0)
    snap = ledger.snapshot()
    assert snap.open_reserved == pytest.approx(0.0)
    assert snap.realized_pnl == pytest.approx(50.0)
    assert snap.available == pytest.approx(1050.0)
    # Caps still vs paper capital base — wins do not raise the 5%/10% ceilings.
    assert snap.max_match_stake == pytest.approx(50.0)
    assert snap.max_open_stake == pytest.approx(100.0)


def test_settle_loss_and_void(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    lost = ledger.commit(client_key="l", stake=40.0, legs=[_leg("m1")], decimal_odds=2.5)
    ledger.settle(lost.booking_id, won=False)
    snap = ledger.snapshot()
    assert snap.realized_pnl == pytest.approx(-40.0)
    assert snap.available == pytest.approx(960.0)

    voided = ledger.commit(client_key="v", stake=30.0, legs=[_leg("m2")], decimal_odds=1.9)
    ledger.settle(voided.booking_id, void=True)
    snap2 = ledger.snapshot()
    assert snap2.open_reserved == 0.0
    assert snap2.realized_pnl == pytest.approx(-40.0)  # void pnl 0
    assert snap2.available == pytest.approx(960.0)


def test_settle_idempotent(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    booking = ledger.commit(client_key="id", stake=20.0, legs=[_leg("m1")], decimal_odds=2.0)
    a = ledger.settle(booking.booking_id, won=True)
    b = ledger.settle(booking.booking_id, won=True)
    assert a.booking_id == b.booking_id
    assert ledger.snapshot().realized_pnl == pytest.approx(20.0)


def test_cancel_releases_reservation(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    booking = ledger.commit(client_key="c", stake=25.0, legs=[_leg("m1")], decimal_odds=2.0)
    cancelled = ledger.cancel(booking.booking_id)
    assert cancelled.status is BookingStatus.CANCELLED
    assert ledger.snapshot().open_reserved == 0.0
    assert ledger.snapshot().available == pytest.approx(1000.0)


def test_caps_ignore_unsettled_for_reinvestment(tmp_path: Path) -> None:
    """Open reserved funds are not available for new exposure beyond open cap."""

    ledger = PaperLedger(
        path=tmp_path / "small.sqlite3",
        mode="demo",
        caps=ExposureCaps(
            paper_capital=100.0, max_match_fraction=0.05, max_open_fraction=0.10
        ),
    )
    # Match cap 5, open cap 10 — fill open with two matches.
    ledger.commit(client_key="a", stake=5.0, legs=[_leg("m1")], decimal_odds=2.0)
    ledger.commit(client_key="b", stake=5.0, legs=[_leg("m2")], decimal_odds=2.0)
    preview = ledger.preview(stake=1.0, legs=[_leg("m3")])
    assert CapReason.TOTAL_OPEN_CAP.value in preview.reasons
    assert ledger.snapshot().available == pytest.approx(90.0)


def test_turnover_window(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    t0 = datetime(2024, 1, 1, 12, tzinfo=UTC)
    t1 = datetime(2024, 1, 2, 12, tzinfo=UTC)
    ledger.commit(
        client_key="t0",
        stake=10.0,
        legs=[_leg("m1")],
        decimal_odds=2.0,
        reserved_at=t0,
    )
    ledger.commit(
        client_key="t1",
        stake=20.0,
        legs=[_leg("m2")],
        decimal_odds=2.0,
        reserved_at=t1,
    )
    assert ledger.turnover(since=t0, until=t0) == pytest.approx(10.0)
    assert ledger.turnover(since=t0, until=t1) == pytest.approx(30.0)


def test_duplicate_match_legs_rejected(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    preview = ledger.preview(
        stake=10.0,
        legs=[_leg("m1", "home"), _leg("m1", "draw")],
    )
    assert CapReason.DUPLICATE_MATCH.value in preview.reasons
