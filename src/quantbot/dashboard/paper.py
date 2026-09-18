"""Dashboard helpers for the paper-simulation ledger (P1).

Separate from tip hit-rate tracking. No real-money framing: units against a
documented paper capital base with exposure caps.
"""

from __future__ import annotations

from pathlib import Path

from quantbot.dashboard.slip import BettingSlip
from quantbot.ledger import (
    Booking,
    BookingLeg,
    BookingStatus,
    CapViolationError,
    ExposureCaps,
    ExposurePreview,
    PaperLedger,
    ledger_db_path,
)


def paper_ledger_for_mode(
    mode: str,
    *,
    path: Path | None = None,
    caps: ExposureCaps | None = None,
) -> PaperLedger:
    """Return the mode-scoped paper ledger (demo/live stay separate)."""

    return PaperLedger(
        path=path if path is not None else ledger_db_path(mode=mode),
        mode=mode,
        caps=caps or ExposureCaps(),
    )


def legs_from_slip(slip: BettingSlip) -> tuple[BookingLeg, ...]:
    """Map a UI slip to ledger legs (one match per leg, already enforced)."""

    out: list[BookingLeg] = []
    for leg in slip.legs:
        selection = getattr(leg.outcome, "value", str(leg.outcome))
        out.append(
            BookingLeg(
                match_id=leg.match_id,
                selection=str(selection),
                decimal_odds=float(leg.odds),
            )
        )
    return tuple(out)


def slip_client_key(slip: BettingSlip, *, mode: str) -> str:
    """Stable idempotency key for Streamlit reruns of the same slip."""

    parts = [mode, f"{slip.combined_odds:.4f}"]
    for leg in slip.legs:
        sel = getattr(leg.outcome, "value", str(leg.outcome))
        parts.append(f"{leg.match_id}:{sel}:{leg.odds:.3f}")
    return "|".join(parts)


def preview_slip(
    ledger: PaperLedger,
    slip: BettingSlip,
    *,
    stake_units: float,
    mode: str,
) -> ExposurePreview:
    return ledger.preview(
        stake=float(stake_units),
        legs=legs_from_slip(slip),
        client_key=slip_client_key(slip, mode=mode),
    )


def commit_slip(
    ledger: PaperLedger,
    slip: BettingSlip,
    *,
    stake_units: float,
    mode: str,
) -> Booking:
    """Reserve paper units for the slip; idempotent on composition + mode."""

    return ledger.commit(
        client_key=slip_client_key(slip, mode=mode),
        stake=float(stake_units),
        legs=legs_from_slip(slip),
        decimal_odds=float(slip.combined_odds),
    )


def open_bookings(ledger: PaperLedger) -> list[Booking]:
    return ledger.list_bookings(status=BookingStatus.RESERVED)


_SELECTION_LABELS = {
    "de": {
        "home": "Heimsieg",
        "draw": "Unentschieden",
        "away": "Auswärtssieg",
        "over": "Über",
        "under": "Unter",
    },
    "en": {
        "home": "Home",
        "draw": "Draw",
        "away": "Away",
        "over": "Over",
        "under": "Under",
    },
}


def format_selection(selection: str, lang: str = "de") -> str:
    """Human label for a stored booking selection (home/under/…)."""

    key = "de" if lang.startswith("de") else "en"
    raw = str(selection).strip().lower()
    # totals may be stored as under / over; line lives only on the tip side
    base = raw.split("_", 1)[0] if "_" in raw else raw
    mapped = _SELECTION_LABELS[key].get(base)
    if mapped is None:
        return str(selection)
    if "_" in raw:
        return f"{mapped} {raw.split('_', 1)[1]}"
    return mapped


def format_booking_leg_line(leg: BookingLeg, *, index: int, lang: str = "de") -> str:
    """One readable line for an open reservation card."""

    sel = format_selection(leg.selection, lang)
    match = leg.match_id
    if lang.startswith("de"):
        return f"{index}. Spiel {match} · {sel} @ {leg.decimal_odds:.2f}"
    return f"{index}. Match {match} · {sel} @ {leg.decimal_odds:.2f}"
