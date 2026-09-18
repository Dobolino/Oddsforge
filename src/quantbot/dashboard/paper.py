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


def booking_ticket_html(booking: Booking, *, lang: str = "de") -> str:
    """Cream receipt card for a paper reservation (same look as Kombi ticket)."""

    from html import escape

    from quantbot.dashboard.ux import tip_badge_html, tip_kind_from_label

    de = lang.startswith("de")
    payout = float(booking.stake) * float(booking.decimal_odds)
    title = "PAPIER-RESERVIERUNG" if de else "PAPER RESERVATION"
    kind = (
        f"{'Kombi' if len(booking.legs) > 1 else 'Einzel'} · ID {booking.booking_id[:8]}"
        if de
        else f"{'Combo' if len(booking.legs) > 1 else 'Single'} · ID {booking.booking_id[:8]}"
    )
    rows: list[str] = []
    for i, leg in enumerate(booking.legs, start=1):
        tip_text = format_selection(leg.selection, lang)
        tip_badge = tip_badge_html(
            tip_kind_from_label(leg.selection),
            lang,
            text=tip_text,
        )
        match_label = (
            f"Spiel {escape(str(leg.match_id))}"
            if de
            else f"Match {escape(str(leg.match_id))}"
        )
        rows.append(
            "<tr>"
            f'<td style="padding:10px 8px;border-bottom:1px dashed #ccc;vertical-align:top;width:2rem;">{i}.</td>'
            f'<td style="padding:10px 8px;border-bottom:1px dashed #ccc;">'
            f'<div style="font-weight:700;">{match_label}</div>'
            f'<div style="margin-top:4px;">→ {tip_badge}</div>'
            "</td>"
            f'<td style="padding:10px 8px;border-bottom:1px dashed #ccc;text-align:right;'
            f'font-size:1.15rem;font-weight:700;">{float(leg.decimal_odds):.2f}</td>'
            "</tr>"
        )
    stake_lbl = "Einheiten" if de else "Units"
    odds_lbl = "Gesamtquote" if de else "Combined odds"
    win_lbl = "Sim. Auszahlung" if de else "Sim. payout"
    sub = (
        "Nur Papier — QuantBot wettet nicht."
        if de
        else "Paper only — QuantBot does not bet."
    )
    return (
        '<div style="max-width:520px;margin:0.5rem 0 0.75rem 0;padding:1.25rem 1.4rem;'
        "background:linear-gradient(180deg,#fffef8 0%,#f7f1e1 100%);"
        "color:#1a1a1a;border:2px solid #222;border-radius:6px;"
        'box-shadow:4px 4px 0 #222;font-family:ui-monospace,Menlo,Consolas,monospace;">'
        f'<div style="text-align:center;letter-spacing:0.18em;font-weight:800;font-size:1.15rem;">{title}</div>'
        f'<div style="text-align:center;margin:0.35rem 0 0.9rem 0;font-size:0.9rem;">{escape(kind)}</div>'
        f'<table style="width:100%;border-collapse:collapse;">{"".join(rows)}</table>'
        '<div style="margin-top:1rem;padding-top:0.75rem;border-top:2px solid #222;">'
        f'<div style="display:flex;justify-content:space-between;margin:0.25rem 0;"><span>{stake_lbl}</span>'
        f"<b>{float(booking.stake):.2f}</b></div>"
        f'<div style="display:flex;justify-content:space-between;margin:0.25rem 0;"><span>{odds_lbl}</span>'
        f"<b>{float(booking.decimal_odds):.2f}</b></div>"
        f'<div style="display:flex;justify-content:space-between;margin:0.25rem 0;font-size:1.15rem;">'
        f"<span>{win_lbl}</span><b>{payout:.2f}</b></div>"
        "</div>"
        f'<div style="margin-top:0.9rem;text-align:center;font-size:0.8rem;opacity:0.8;">{sub}</div>'
        "</div>"
    )
