"""Closing-line resolution with honest provenance (P3).

True exchange closes are preferred (``is_closing=True``). When those are
missing, the last valid *prematch* quote before kickoff may be used as a
documented proxy — never invented from post-kickoff or settled results.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from quantbot.schemas import Match, Odds


class ClosingSource(str, Enum):
    TAGGED_CLOSING = "tagged_closing"
    LAST_PREMATCH = "last_prematch"
    MISSING = "missing"


@dataclass(frozen=True)
class ClosingResolution:
    odds: Odds | None
    source: ClosingSource
    seconds_before_kickoff: float | None = None
    reason: str = ""


def resolve_closing_odds(
    match: Match,
    snapshots: list[Odds] | tuple[Odds, ...],
) -> ClosingResolution:
    """Pick a closing 1X2 quote for CLV — tagged close, else last prematch."""

    kick = match.kickoff
    if kick.tzinfo is None:
        raise ValueError("match.kickoff must be timezone-aware")
    kick = kick.astimezone(timezone.utc)

    aware: list[Odds] = []
    for o in snapshots:
        if o.timestamp.tzinfo is None:
            continue
        aware.append(o)

    tagged = [o for o in aware if o.is_closing and o.timestamp <= kick]
    if tagged:
        best = max(tagged, key=lambda o: o.timestamp)
        return ClosingResolution(
            odds=best,
            source=ClosingSource.TAGGED_CLOSING,
            seconds_before_kickoff=(kick - best.timestamp.astimezone(timezone.utc)).total_seconds(),
            reason="provider-tagged closing snapshot",
        )

    prematch = [o for o in aware if o.timestamp < kick]
    if not prematch:
        return ClosingResolution(
            odds=None,
            source=ClosingSource.MISSING,
            reason="no prematch 1X2 snapshot before kickoff",
        )

    best = max(prematch, key=lambda o: o.timestamp)
    return ClosingResolution(
        odds=best,
        source=ClosingSource.LAST_PREMATCH,
        seconds_before_kickoff=(kick - best.timestamp.astimezone(timezone.utc)).total_seconds(),
        reason="last prematch snapshot (not a tagged exchange close)",
    )


def closing_selection_odds(resolution: ClosingResolution, selection: str) -> float | None:
    """Decimal odds for home/draw/away from a resolved closing quote."""

    if resolution.odds is None:
        return None
    o = resolution.odds
    key = selection.lower()
    if key == "home":
        return float(o.home)
    if key == "draw":
        return float(o.draw)
    if key == "away":
        return float(o.away)
    return None
