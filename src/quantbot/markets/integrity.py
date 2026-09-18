"""Prematch market integrity checks (quotes, completeness, staleness).

These checks produce ``INVALID_DATA_*`` reasons for the DecisionPolicy path.
They do not invent fair probabilities or silently swap margin methods.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite

from quantbot.decision.rules import Reason
from quantbot.schemas import Odds, TotalsOdds

# Heuristic default: documented as such — justify from provider refresh rates
# when live evidence exists; not a hidden “sharp” whitelist.
DEFAULT_MAX_QUOTE_AGE = timedelta(hours=24)

INVALID_ODDS_NAN = Reason(
    code="INVALID_DATA_ODDS_NAN",
    de="Quote enthält ungültige Zahlen (NaN/Inf) — Auswertung gesperrt.",
    en="Odds contain invalid numbers (NaN/Inf) — evaluation blocked.",
    technical="non-finite decimal odds",
)
INVALID_ODDS_RANGE = Reason(
    code="INVALID_DATA_ODDS_RANGE",
    de="Quote außerhalb des zulässigen Bereichs (> 1.0) — Auswertung gesperrt.",
    en="Odds outside the allowed range (> 1.0) — evaluation blocked.",
    technical="decimal odds must be finite and > 1.0",
)
INVALID_BOOK_INCOMPLETE = Reason(
    code="INVALID_DATA_BOOK_INCOMPLETE",
    de="Buch unvollständig (Seiten fehlen) — keine Margenbereinigung.",
    en="Incomplete book (missing sides) — no margin removal.",
    technical="1X2/totals book missing required outcomes",
)
INVALID_QUOTE_AFTER_KICKOFF = Reason(
    code="INVALID_DATA_QUOTE_AFTER_KICKOFF",
    de="Prematch-Pfad: Quote liegt nach Anpfiff — gesperrt.",
    en="Prematch path: quote is after kickoff — blocked.",
    technical="odds timestamp is at/after kickoff",
)
INVALID_QUOTE_STALE = Reason(
    code="INVALID_DATA_QUOTE_STALE",
    de="Quote zu alt relativ zum Prognosezeitpunkt — gesperrt.",
    en="Quote too stale relative to prediction time — blocked.",
    technical="odds older than configured max age before as_of",
)


def check_1x2_odds(
    odds: Odds,
    *,
    as_of: datetime,
    kickoff: datetime | None = None,
    max_age: timedelta = DEFAULT_MAX_QUOTE_AGE,
) -> tuple[Reason, ...]:
    """Integrity reasons for a single-book 1X2 quote used as reference book."""

    if as_of.tzinfo is None or odds.timestamp.tzinfo is None:
        raise ValueError("as_of and odds.timestamp must be timezone-aware")
    reasons: list[Reason] = []
    sides = (odds.home, odds.draw, odds.away)
    if any(not isfinite(x) for x in sides):
        reasons.append(INVALID_ODDS_NAN)
    elif any(x <= 1.0 for x in sides):
        reasons.append(INVALID_ODDS_RANGE)
    # Schema already requires three sides; keep explicit incomplete guard for
    # callers that may pass partially constructed objects in tests.
    if any(x is None for x in sides):  # type: ignore[comparison-overlap]
        reasons.append(INVALID_BOOK_INCOMPLETE)
    if kickoff is not None:
        if kickoff.tzinfo is None:
            raise ValueError("kickoff must be timezone-aware")
        if odds.timestamp >= kickoff:
            reasons.append(INVALID_QUOTE_AFTER_KICKOFF)
    age = as_of - odds.timestamp
    if age > max_age:
        reasons.append(INVALID_QUOTE_STALE)
    return tuple(reasons)


def check_totals_odds(
    odds: TotalsOdds,
    *,
    as_of: datetime,
    kickoff: datetime | None = None,
    max_age: timedelta = DEFAULT_MAX_QUOTE_AGE,
) -> tuple[Reason, ...]:
    if as_of.tzinfo is None or odds.timestamp.tzinfo is None:
        raise ValueError("as_of and odds.timestamp must be timezone-aware")
    reasons: list[Reason] = []
    sides = (odds.over, odds.under)
    if any(not isfinite(x) for x in sides) or not isfinite(odds.line):
        reasons.append(INVALID_ODDS_NAN)
    elif any(x <= 1.0 for x in sides):
        reasons.append(INVALID_ODDS_RANGE)
    if kickoff is not None:
        if kickoff.tzinfo is None:
            raise ValueError("kickoff must be timezone-aware")
        if odds.timestamp >= kickoff:
            reasons.append(INVALID_QUOTE_AFTER_KICKOFF)
    if as_of - odds.timestamp > max_age:
        reasons.append(INVALID_QUOTE_STALE)
    return tuple(reasons)
