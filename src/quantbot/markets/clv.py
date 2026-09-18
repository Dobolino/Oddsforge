"""Closing-line value helpers with comparability gates (P2).

Odds-ratio CLV and fair-probability ``closing_reference_ev`` are kept
separate. Missing or incomparable closes stay N/A with an explicit reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite


class ClvStatus(str, Enum):
    OK = "ok"
    NA_MISSING_CLOSE = "na_missing_close"
    NA_LINE_MISMATCH = "na_line_mismatch"
    NA_MARKET_MISMATCH = "na_market_mismatch"
    NA_PERIOD_MISMATCH = "na_period_mismatch"
    NA_RULES_MISMATCH = "na_rules_mismatch"
    NA_POST_KICKOFF = "na_post_kickoff"
    NA_INVALID_ODDS = "na_invalid_odds"


@dataclass(frozen=True)
class ClosingQuoteRef:
    """Comparable closing reference for one selection."""

    decimal_odds: float
    fair_probability: float | None = None
    market_kind: str | None = None
    line: float | None = None
    period: str | None = None
    rules: str | None = None
    timestamp: datetime | None = None
    source: str = "closing_snapshot"


@dataclass(frozen=True)
class EntryQuoteRef:
    decimal_odds: float
    market_kind: str | None = None
    line: float | None = None
    period: str | None = None
    rules: str | None = None
    kickoff: datetime | None = None


@dataclass(frozen=True)
class ClvResult:
    status: ClvStatus
    odds_ratio_clv: float | None = None
    closing_reference_ev: float | None = None
    closing_odds: float | None = None
    seconds_before_kickoff: float | None = None
    reason: str = ""


def closing_line_value_odds_ratio(entry_odds: float, closing_odds: float) -> float:
    """``entry / close - 1`` (positive = beat the close on price)."""

    if entry_odds <= 1.0 or closing_odds <= 1.0:
        raise ValueError("odds must be > 1.0")
    if not isfinite(entry_odds) or not isfinite(closing_odds):
        raise ValueError("odds must be finite")
    return entry_odds / closing_odds - 1.0


def closing_reference_ev(taken_odds: float, closing_fair_probability: float) -> float:
    """Binary no-push reference EV vs closing fair probability.

    ``taken_odds * closing_fair_p - 1``. Not interchangeable with odds-ratio CLV.
    """

    if taken_odds <= 1.0 or not isfinite(taken_odds):
        raise ValueError("taken_odds must be finite and > 1.0")
    if not (0.0 < closing_fair_probability < 1.0) or not isfinite(closing_fair_probability):
        raise ValueError("closing_fair_probability must be in (0, 1)")
    return taken_odds * closing_fair_probability - 1.0


def _lines_equal(a: float | None, b: float | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= 1e-9


def evaluate_clv(
    entry: EntryQuoteRef,
    closing: ClosingQuoteRef | None,
    *,
    require_fair: bool = False,
) -> ClvResult:
    """Compute CLV only when the closing quote is comparable to the entry."""

    if closing is None:
        return ClvResult(
            status=ClvStatus.NA_MISSING_CLOSE,
            reason="no comparable closing snapshot",
        )
    if (
        not isfinite(entry.decimal_odds)
        or entry.decimal_odds <= 1.0
        or not isfinite(closing.decimal_odds)
        or closing.decimal_odds <= 1.0
    ):
        return ClvResult(status=ClvStatus.NA_INVALID_ODDS, reason="invalid entry or close odds")

    if entry.market_kind is not None and closing.market_kind is not None:
        if entry.market_kind != closing.market_kind:
            return ClvResult(
                status=ClvStatus.NA_MARKET_MISMATCH,
                reason=f"market {entry.market_kind!r} vs {closing.market_kind!r}",
            )
    if not _lines_equal(entry.line, closing.line):
        return ClvResult(
            status=ClvStatus.NA_LINE_MISMATCH,
            reason=f"line {entry.line!r} vs {closing.line!r}",
        )
    if entry.period is not None and closing.period is not None and entry.period != closing.period:
        return ClvResult(
            status=ClvStatus.NA_PERIOD_MISMATCH,
            reason=f"period {entry.period!r} vs {closing.period!r}",
        )
    if entry.rules is not None and closing.rules is not None and entry.rules != closing.rules:
        return ClvResult(
            status=ClvStatus.NA_RULES_MISMATCH,
            reason=f"rules {entry.rules!r} vs {closing.rules!r}",
        )

    seconds_before: float | None = None
    if entry.kickoff is not None and closing.timestamp is not None:
        kick = entry.kickoff
        close_ts = closing.timestamp
        if kick.tzinfo is None or close_ts.tzinfo is None:
            raise ValueError("kickoff and closing timestamp must be timezone-aware")
        kick = kick.astimezone(timezone.utc)
        close_ts = close_ts.astimezone(timezone.utc)
        seconds_before = (kick - close_ts).total_seconds()
        if seconds_before < 0:
            return ClvResult(
                status=ClvStatus.NA_POST_KICKOFF,
                reason="closing quote timestamp is at or after kickoff",
                seconds_before_kickoff=seconds_before,
            )

    odds_ratio = closing_line_value_odds_ratio(entry.decimal_odds, closing.decimal_odds)
    ref_ev: float | None = None
    if closing.fair_probability is not None:
        ref_ev = closing_reference_ev(entry.decimal_odds, closing.fair_probability)
    elif require_fair:
        return ClvResult(
            status=ClvStatus.NA_MISSING_CLOSE,
            reason="closing fair probability unavailable",
            closing_odds=closing.decimal_odds,
            odds_ratio_clv=odds_ratio,
            seconds_before_kickoff=seconds_before,
        )

    return ClvResult(
        status=ClvStatus.OK,
        odds_ratio_clv=odds_ratio,
        closing_reference_ev=ref_ev,
        closing_odds=closing.decimal_odds,
        seconds_before_kickoff=seconds_before,
        reason="",
    )
