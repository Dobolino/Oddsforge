"""Prematch market integrity checks (quotes, completeness, staleness).

Hard blockers (NaN, range, incomplete book, quote after kickoff) abort the
value path. Stale quotes are a **soft** quality penalty — analysis continues
with reduced ``data_quality`` so free-tier APIs with laggy ``last_update`` do
not halt every tip as ``invalid_data``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite

from quantbot.decision.rules import Reason
from quantbot.schemas import Odds, TotalsOdds

# Heuristic default for matches close to kickoff. Distant fixtures often keep
# the same book ``last_update`` for days — a flat 24h gate then blocks every tip.
DEFAULT_MAX_QUOTE_AGE = timedelta(hours=24)
_NEAR_KICKOFF = timedelta(hours=48)
_MID_HORIZON = timedelta(days=7)
_MID_QUOTE_AGE = timedelta(days=3)
_FAR_QUOTE_AGE = timedelta(days=7)

# Soft penalty applied to AnalysisResult.data_quality when quotes are stale.
STALE_QUALITY_PENALTY = 0.25


def max_quote_age_for_kickoff(
    *,
    as_of: datetime,
    kickoff: datetime | None,
    base: timedelta = DEFAULT_MAX_QUOTE_AGE,
) -> timedelta:
    """Allow older quotes when kickoff is still far from ``as_of``.

    Prematch books do not refresh every day for mid-week / next-week fixtures.
    Near kickoff we keep the strict ``base`` (24h) gate.
    """

    if kickoff is None:
        return base
    if kickoff.tzinfo is None or as_of.tzinfo is None:
        raise ValueError("as_of and kickoff must be timezone-aware")
    lead = kickoff - as_of
    if lead <= _NEAR_KICKOFF:
        return base
    if lead <= _MID_HORIZON:
        return max(base, _MID_QUOTE_AGE)
    return max(base, _FAR_QUOTE_AGE)


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
    de="Quote älter als üblich — Datenqualität um 25 % reduziert (kein Hard-Block).",
    en="Quote older than usual — data quality reduced by 25% (not a hard block).",
    technical="odds older than configured max age before as_of; soft quality penalty",
)

_HARD_INTEGRITY_CODES = frozenset(
    {
        INVALID_ODDS_NAN.code,
        INVALID_ODDS_RANGE.code,
        INVALID_BOOK_INCOMPLETE.code,
        INVALID_QUOTE_AFTER_KICKOFF.code,
    }
)


def is_hard_integrity(reason: Reason) -> bool:
    """True when the reason must abort EV/Kelly (not merely a quality warning)."""

    return reason.code in _HARD_INTEGRITY_CODES


def partition_integrity(
    reasons: tuple[Reason, ...],
) -> tuple[tuple[Reason, ...], tuple[Reason, ...]]:
    """Split integrity reasons into (hard blockers, soft quality warnings)."""

    hard = tuple(r for r in reasons if is_hard_integrity(r))
    soft = tuple(r for r in reasons if not is_hard_integrity(r))
    return hard, soft


def apply_stale_quality_penalty(data_quality: float) -> float:
    """Reduce data quality by ``STALE_QUALITY_PENALTY`` (floor at 0)."""

    return round(max(0.0, float(data_quality) * (1.0 - STALE_QUALITY_PENALTY)), 2)


def check_1x2_odds(
    odds: Odds,
    *,
    as_of: datetime,
    kickoff: datetime | None = None,
    max_age: timedelta | None = None,
) -> tuple[Reason, ...]:
    """Integrity reasons for a single-book 1X2 quote used as reference book."""

    if as_of.tzinfo is None or odds.timestamp.tzinfo is None:
        raise ValueError("as_of and odds.timestamp must be timezone-aware")
    effective_max = (
        max_age
        if max_age is not None
        else max_quote_age_for_kickoff(as_of=as_of, kickoff=kickoff)
    )
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
    if age > effective_max:
        reasons.append(INVALID_QUOTE_STALE)
    return tuple(reasons)


def check_totals_odds(
    odds: TotalsOdds,
    *,
    as_of: datetime,
    kickoff: datetime | None = None,
    max_age: timedelta | None = None,
) -> tuple[Reason, ...]:
    if as_of.tzinfo is None or odds.timestamp.tzinfo is None:
        raise ValueError("as_of and odds.timestamp must be timezone-aware")
    effective_max = (
        max_age
        if max_age is not None
        else max_quote_age_for_kickoff(as_of=as_of, kickoff=kickoff)
    )
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
    if as_of - odds.timestamp > effective_max:
        reasons.append(INVALID_QUOTE_STALE)
    return tuple(reasons)
