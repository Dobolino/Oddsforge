"""Paper-simulation ledger: reservations, caps, and settlement (P0).

This is **not** a real-money wallet. ``allow_automated_betting`` stays false.
Caps are heuristic start limits relative to a documented paper capital base
(without counting expected or unsettled winnings):

* ≤ 5 % exposure per match (combo stake attributed in full to every leg match)
* ≤ 10 % total open reserved exposure

``preview`` never writes. ``commit`` is idempotent on ``client_key`` so Streamlit
reruns cannot double-reserve.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from quantbot.config import DATA_DIR

SCHEMA_VERSION = 1

# Documented heuristic paper-capital defaults (not a live staking recommendation).
DEFAULT_PAPER_CAPITAL = 1000.0
DEFAULT_MAX_MATCH_EXPOSURE = 0.05
DEFAULT_MAX_OPEN_EXPOSURE = 0.10


class BookingStatus(str, Enum):
    RESERVED = "reserved"
    SETTLED = "settled"
    VOIDED = "voided"
    CANCELLED = "cancelled"


class CapReason(str, Enum):
    INVALID_STAKE = "INVALID_STAKE"
    INSUFFICIENT_AVAILABLE = "INSUFFICIENT_AVAILABLE"
    MATCH_EXPOSURE_CAP = "MATCH_EXPOSURE_CAP"
    TOTAL_OPEN_CAP = "TOTAL_OPEN_CAP"
    EMPTY_LEGS = "EMPTY_LEGS"
    DUPLICATE_MATCH = "DUPLICATE_MATCH"


def ledger_db_path(*, mode: str = "demo", base: Path | None = None) -> Path:
    root = Path(base) if base is not None else DATA_DIR / "ledger"
    safe = "".join(c for c in mode if c.isalnum() or c in ("-", "_")) or "demo"
    return root / f"{safe}.sqlite3"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class BookingLeg:
    match_id: str
    selection: str
    decimal_odds: float


@dataclass(frozen=True)
class ExposureCaps:
    """Heuristic portfolio caps vs paper capital base (not Kelly)."""

    paper_capital: float = DEFAULT_PAPER_CAPITAL
    max_match_fraction: float = DEFAULT_MAX_MATCH_EXPOSURE
    max_open_fraction: float = DEFAULT_MAX_OPEN_EXPOSURE

    def __post_init__(self) -> None:
        if self.paper_capital <= 0.0:
            raise ValueError("paper_capital must be > 0")
        if not 0.0 < self.max_match_fraction <= 1.0:
            raise ValueError("max_match_fraction must be in (0, 1]")
        if not 0.0 < self.max_open_fraction <= 1.0:
            raise ValueError("max_open_fraction must be in (0, 1]")
        if self.max_match_fraction > self.max_open_fraction:
            raise ValueError("max_match_fraction cannot exceed max_open_fraction")

    @property
    def max_match_stake(self) -> float:
        return self.paper_capital * self.max_match_fraction

    @property
    def max_open_stake(self) -> float:
        return self.paper_capital * self.max_open_fraction


@dataclass(frozen=True)
class AccountSnapshot:
    mode: str
    paper_capital: float
    realized_pnl: float
    open_reserved: float
    available: float
    open_by_match: dict[str, float]
    max_match_stake: float
    max_open_stake: float

    @property
    def equity(self) -> float:
        """Settled equity (capital + realized); open stakes still reserved."""

        return self.paper_capital + self.realized_pnl


@dataclass(frozen=True)
class ExposurePreview:
    ok: bool
    reasons: tuple[str, ...]
    stake: float
    match_ids: tuple[str, ...]
    open_by_match_after: dict[str, float]
    total_open_after: float
    available_before: float
    available_after: float
    already_committed: bool = False
    existing_booking_id: str | None = None


@dataclass(frozen=True)
class Booking:
    booking_id: str
    client_key: str
    mode: str
    status: BookingStatus
    stake: float
    decimal_odds: float
    legs: tuple[BookingLeg, ...]
    tip_id: str | None
    reserved_at: datetime
    settled_at: datetime | None
    payout: float | None
    pnl: float | None
    schema_version: int = SCHEMA_VERSION

    @property
    def match_ids(self) -> tuple[str, ...]:
        return tuple(leg.match_id for leg in self.legs)


class PaperLedger:
    """Transactional local paper ledger (SQLite)."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        mode: str = "demo",
        caps: ExposureCaps | None = None,
    ) -> None:
        self.mode = mode
        self.caps = caps or ExposureCaps()
        self.path = Path(path) if path is not None else ledger_db_path(mode=mode)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._ensure_account()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS account (
                    mode TEXT PRIMARY KEY,
                    paper_capital REAL NOT NULL,
                    realized_pnl REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bookings (
                    booking_id TEXT PRIMARY KEY,
                    client_key TEXT NOT NULL UNIQUE,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stake REAL NOT NULL,
                    decimal_odds REAL NOT NULL,
                    tip_id TEXT,
                    legs_json TEXT NOT NULL,
                    reserved_at TEXT NOT NULL,
                    settled_at TEXT,
                    payout REAL,
                    pnl REAL,
                    schema_version INTEGER NOT NULL,
                    FOREIGN KEY (mode) REFERENCES account(mode)
                );
                CREATE INDEX IF NOT EXISTS idx_bookings_status
                    ON bookings(mode, status);
                CREATE INDEX IF NOT EXISTS idx_bookings_reserved_at
                    ON bookings(mode, reserved_at);
                """
            )
            conn.commit()

    def _ensure_account(self) -> None:
        now = _utc_iso(_utc_now())
        with self._connect() as conn:
            row = conn.execute(
                "SELECT mode FROM account WHERE mode = ?", (self.mode,)
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO account
                    (mode, paper_capital, realized_pnl, created_at, updated_at, schema_version)
                    VALUES (?, ?, 0.0, ?, ?, ?)
                    """,
                    (self.mode, float(self.caps.paper_capital), now, now, SCHEMA_VERSION),
                )
                conn.commit()
                return
            # Keep stored capital in sync when caps are constructed with a new base.
            conn.execute(
                """
                UPDATE account SET paper_capital = ?, updated_at = ?
                WHERE mode = ?
                """,
                (float(self.caps.paper_capital), now, self.mode),
            )
            conn.commit()

    @staticmethod
    def _legs_from_json(raw: str) -> tuple[BookingLeg, ...]:
        data = json.loads(raw)
        return tuple(
            BookingLeg(
                match_id=str(item["match_id"]),
                selection=str(item["selection"]),
                decimal_odds=float(item["decimal_odds"]),
            )
            for item in data
        )

    @staticmethod
    def _legs_to_json(legs: Sequence[BookingLeg]) -> str:
        payload = [
            {
                "match_id": leg.match_id,
                "selection": leg.selection,
                "decimal_odds": leg.decimal_odds,
            }
            for leg in legs
        ]
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    def _booking_from_row(self, row: sqlite3.Row) -> Booking:
        return Booking(
            booking_id=str(row["booking_id"]),
            client_key=str(row["client_key"]),
            mode=str(row["mode"]),
            status=BookingStatus(str(row["status"])),
            stake=float(row["stake"]),
            decimal_odds=float(row["decimal_odds"]),
            legs=self._legs_from_json(str(row["legs_json"])),
            tip_id=str(row["tip_id"]) if row["tip_id"] is not None else None,
            reserved_at=_parse_dt(str(row["reserved_at"])) or _utc_now(),
            settled_at=_parse_dt(row["settled_at"]),
            payout=float(row["payout"]) if row["payout"] is not None else None,
            pnl=float(row["pnl"]) if row["pnl"] is not None else None,
            schema_version=int(row["schema_version"]),
        )

    def _open_exposure(
        self, conn: sqlite3.Connection
    ) -> tuple[float, dict[str, float]]:
        """Total open stake once per booking; full stake per match (combo rule)."""

        rows = conn.execute(
            """
            SELECT stake, legs_json FROM bookings
            WHERE mode = ? AND status = ?
            """,
            (self.mode, BookingStatus.RESERVED.value),
        ).fetchall()
        total = 0.0
        by_match: dict[str, float] = {}
        for row in rows:
            stake = float(row["stake"])
            total += stake
            for leg in self._legs_from_json(str(row["legs_json"])):
                by_match[leg.match_id] = by_match.get(leg.match_id, 0.0) + stake
        return total, by_match

    def snapshot(self) -> AccountSnapshot:
        with self._connect() as conn:
            acc = conn.execute(
                "SELECT paper_capital, realized_pnl FROM account WHERE mode = ?",
                (self.mode,),
            ).fetchone()
            if acc is None:
                raise RuntimeError(f"missing account for mode {self.mode!r}")
            capital = float(acc["paper_capital"])
            realized = float(acc["realized_pnl"])
            open_reserved, by_match = self._open_exposure(conn)
        available = capital + realized - open_reserved
        return AccountSnapshot(
            mode=self.mode,
            paper_capital=capital,
            realized_pnl=realized,
            open_reserved=open_reserved,
            available=available,
            open_by_match=dict(sorted(by_match.items())),
            max_match_stake=self.caps.max_match_stake,
            max_open_stake=self.caps.max_open_stake,
        )

    def get_by_client_key(self, client_key: str) -> Booking | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE mode = ? AND client_key = ?",
                (self.mode, client_key),
            ).fetchone()
        return self._booking_from_row(row) if row is not None else None

    def get_booking(self, booking_id: str) -> Booking | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE booking_id = ? AND mode = ?",
                (booking_id, self.mode),
            ).fetchone()
        return self._booking_from_row(row) if row is not None else None

    def list_bookings(
        self, *, status: BookingStatus | None = None
    ) -> list[Booking]:
        with self._connect() as conn:
            if status is None:
                rows = conn.execute(
                    "SELECT * FROM bookings WHERE mode = ? ORDER BY reserved_at",
                    (self.mode,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM bookings
                    WHERE mode = ? AND status = ?
                    ORDER BY reserved_at
                    """,
                    (self.mode, status.value),
                ).fetchall()
        return [self._booking_from_row(r) for r in rows]

    def _validate_legs(
        self, legs: Sequence[BookingLeg]
    ) -> tuple[CapReason, ...] | None:
        if not legs:
            return (CapReason.EMPTY_LEGS,)
        ids = [leg.match_id for leg in legs]
        if len(ids) != len(set(ids)):
            return (CapReason.DUPLICATE_MATCH,)
        for leg in legs:
            if not leg.match_id or not leg.selection:
                return (CapReason.EMPTY_LEGS,)
            if leg.decimal_odds <= 1.0:
                return (CapReason.INVALID_STAKE,)
        return None

    def preview(
        self,
        *,
        stake: float,
        legs: Sequence[BookingLeg],
        client_key: str | None = None,
    ) -> ExposurePreview:
        """Dry-run exposure check. Does not write."""

        if client_key is not None:
            existing = self.get_by_client_key(client_key)
            if existing is not None and existing.status is BookingStatus.RESERVED:
                snap = self.snapshot()
                return ExposurePreview(
                    ok=True,
                    reasons=(),
                    stake=existing.stake,
                    match_ids=existing.match_ids,
                    open_by_match_after=snap.open_by_match,
                    total_open_after=snap.open_reserved,
                    available_before=snap.available,
                    available_after=snap.available,
                    already_committed=True,
                    existing_booking_id=existing.booking_id,
                )

        snap = self.snapshot()
        reasons: list[str] = []
        leg_err = self._validate_legs(legs)
        if leg_err:
            reasons.extend(r.value for r in leg_err)
        if stake <= 0.0 or stake != stake:  # NaN check
            reasons.append(CapReason.INVALID_STAKE.value)

        match_ids = tuple(leg.match_id for leg in legs)
        by_after = dict(snap.open_by_match)
        total_after = snap.open_reserved
        available_after = snap.available

        if not reasons:
            total_after = snap.open_reserved + stake
            available_after = snap.available - stake
            if available_after < -1e-12:
                reasons.append(CapReason.INSUFFICIENT_AVAILABLE.value)
            if total_after > self.caps.max_open_stake + 1e-12:
                reasons.append(CapReason.TOTAL_OPEN_CAP.value)
            for mid in match_ids:
                # Combo: full stake counts against each match (conservative).
                by_after[mid] = by_after.get(mid, 0.0) + stake
                if by_after[mid] > self.caps.max_match_stake + 1e-12:
                    reasons.append(CapReason.MATCH_EXPOSURE_CAP.value)

        # Deduplicate reason codes while preserving order.
        uniq: list[str] = []
        for code in reasons:
            if code not in uniq:
                uniq.append(code)

        return ExposurePreview(
            ok=not uniq,
            reasons=tuple(uniq),
            stake=float(stake),
            match_ids=match_ids,
            open_by_match_after=dict(sorted(by_after.items())),
            total_open_after=total_after,
            available_before=snap.available,
            available_after=available_after if not uniq else snap.available,
            already_committed=False,
        )

    def commit(
        self,
        *,
        client_key: str,
        stake: float,
        legs: Sequence[BookingLeg],
        decimal_odds: float,
        tip_id: str | None = None,
        reserved_at: datetime | None = None,
    ) -> Booking:
        """Reserve stake atomically. Idempotent on ``client_key``."""

        if not client_key.strip():
            raise ValueError("client_key must be non-empty")
        if decimal_odds <= 1.0:
            raise ValueError("decimal_odds must be > 1.0")

        existing = self.get_by_client_key(client_key)
        if existing is not None:
            return existing

        preview = self.preview(stake=stake, legs=legs)
        if not preview.ok:
            raise CapViolationError(preview.reasons, preview)

        booking_id = str(uuid4())
        when = reserved_at or _utc_now()
        legs_t = tuple(legs)
        with self._connect() as conn:
            # Re-check inside the transaction against concurrent writers.
            open_total, by_match = self._open_exposure(conn)
            acc = conn.execute(
                "SELECT paper_capital, realized_pnl FROM account WHERE mode = ?",
                (self.mode,),
            ).fetchone()
            assert acc is not None
            capital = float(acc["paper_capital"])
            realized = float(acc["realized_pnl"])
            available = capital + realized - open_total
            if stake > available + 1e-12:
                raise CapViolationError((CapReason.INSUFFICIENT_AVAILABLE.value,), preview)
            if open_total + stake > self.caps.max_open_stake + 1e-12:
                raise CapViolationError((CapReason.TOTAL_OPEN_CAP.value,), preview)
            for mid in preview.match_ids:
                if by_match.get(mid, 0.0) + stake > self.caps.max_match_stake + 1e-12:
                    raise CapViolationError((CapReason.MATCH_EXPOSURE_CAP.value,), preview)

            try:
                conn.execute(
                    """
                    INSERT INTO bookings (
                        booking_id, client_key, mode, status, stake, decimal_odds,
                        tip_id, legs_json, reserved_at, settled_at, payout, pnl,
                        schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?)
                    """,
                    (
                        booking_id,
                        client_key,
                        self.mode,
                        BookingStatus.RESERVED.value,
                        float(stake),
                        float(decimal_odds),
                        tip_id,
                        self._legs_to_json(legs_t),
                        _utc_iso(when),
                        SCHEMA_VERSION,
                    ),
                )
            except sqlite3.IntegrityError:
                # Lost the race on client_key — return the winner.
                conn.rollback()
                again = self.get_by_client_key(client_key)
                if again is None:
                    raise
                return again
            conn.execute(
                "UPDATE account SET updated_at = ? WHERE mode = ?",
                (_utc_iso(_utc_now()), self.mode),
            )
            conn.commit()

        booked = self.get_booking(booking_id)
        assert booked is not None
        return booked

    def cancel(self, booking_id: str) -> Booking:
        """Release a reserved booking without PnL."""

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE booking_id = ? AND mode = ?",
                (booking_id, self.mode),
            ).fetchone()
            if row is None:
                raise KeyError(booking_id)
            booking = self._booking_from_row(row)
            if booking.status is not BookingStatus.RESERVED:
                raise ValueError(f"cannot cancel booking in status {booking.status.value}")
            now = _utc_iso(_utc_now())
            conn.execute(
                """
                UPDATE bookings
                SET status = ?, settled_at = ?, payout = 0.0, pnl = 0.0
                WHERE booking_id = ?
                """,
                (BookingStatus.CANCELLED.value, now, booking_id),
            )
            conn.execute(
                "UPDATE account SET updated_at = ? WHERE mode = ?",
                (now, self.mode),
            )
            conn.commit()
        out = self.get_booking(booking_id)
        assert out is not None
        return out

    def settle(
        self,
        booking_id: str,
        *,
        won: bool | None = None,
        payout_factor: float | None = None,
        void: bool = False,
        settled_at: datetime | None = None,
    ) -> Booking:
        """Settle a reserved booking. Idempotent if already terminal with same outcome.

        Pass either ``void=True``, or ``payout_factor`` (gross return per unit stake:
        win=odds, loss=0, push/void=1), or ``won`` for a simple binary settle
        against the booking's ticket odds.
        """

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE booking_id = ? AND mode = ?",
                (booking_id, self.mode),
            ).fetchone()
            if row is None:
                raise KeyError(booking_id)
            booking = self._booking_from_row(row)

            if void:
                factor = 1.0
                new_status = BookingStatus.VOIDED
            elif payout_factor is not None:
                if payout_factor < 0.0 or payout_factor != payout_factor:
                    raise ValueError("payout_factor must be finite and >= 0")
                factor = float(payout_factor)
                new_status = BookingStatus.SETTLED
            elif won is not None:
                factor = float(booking.decimal_odds) if won else 0.0
                new_status = BookingStatus.SETTLED
            else:
                raise ValueError("settle requires won, payout_factor, or void=True")

            payout = booking.stake * factor
            pnl = payout - booking.stake

            if booking.status is not BookingStatus.RESERVED:
                # Idempotent replay: same terminal numbers are OK.
                if (
                    booking.status in (BookingStatus.SETTLED, BookingStatus.VOIDED)
                    and booking.pnl is not None
                    and abs(booking.pnl - pnl) <= 1e-9
                    and booking.payout is not None
                    and abs(booking.payout - payout) <= 1e-9
                ):
                    return booking
                raise ValueError(
                    f"cannot settle booking in status {booking.status.value}"
                )

            when = settled_at or _utc_now()
            conn.execute(
                """
                UPDATE bookings
                SET status = ?, settled_at = ?, payout = ?, pnl = ?
                WHERE booking_id = ? AND status = ?
                """,
                (
                    new_status.value,
                    _utc_iso(when),
                    payout,
                    pnl,
                    booking_id,
                    BookingStatus.RESERVED.value,
                ),
            )
            if conn.total_changes != 1:
                raise RuntimeError("settle race: booking status changed")
            conn.execute(
                """
                UPDATE account
                SET realized_pnl = realized_pnl + ?, updated_at = ?
                WHERE mode = ?
                """,
                (pnl, _utc_iso(_utc_now()), self.mode),
            )
            conn.commit()

        out = self.get_booking(booking_id)
        assert out is not None
        return out

    def turnover(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> float:
        """Sum of stakes reserved in the window (includes later settled/cancelled)."""

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT stake, reserved_at FROM bookings WHERE mode = ?",
                (self.mode,),
            ).fetchall()
        total = 0.0
        for row in rows:
            when = _parse_dt(str(row["reserved_at"]))
            if when is None:
                continue
            if since is not None and when < since.astimezone(timezone.utc):
                continue
            if until is not None and when > until.astimezone(timezone.utc):
                continue
            total += float(row["stake"])
        return total


class CapViolationError(ValueError):
    """Raised when commit would breach exposure or availability caps."""

    def __init__(self, reasons: tuple[str, ...], preview: ExposurePreview) -> None:
        self.reasons = reasons
        self.preview = preview
        super().__init__(", ".join(reasons) if reasons else "cap violation")
