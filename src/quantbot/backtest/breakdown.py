"""Backtest breakdowns: slice settled bets by odds, edge, league and period.

Each breakdown answers "where does the edge actually come from?" so a headline
ROI is never taken at face value.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from quantbot.backtest.execution import SettledBet


def _group_stats(bets: Sequence[SettledBet], label: str) -> dict[str, object]:
    n = len(bets)
    staked = sum(b.stake for b in bets)
    pnl = sum(b.pnl for b in bets)
    wins = sum(1 for b in bets if b.won)
    return {
        "label": label,
        "n": n,
        "staked": round(staked, 2),
        "pnl": round(pnl, 2),
        "roi": round(pnl / staked * 100, 2) if staked > 0 else 0.0,
        "hit_rate": round(wins / n * 100, 1) if n else 0.0,
    }


def _bucket(
    bets: Sequence[SettledBet],
    edges: Sequence[float],
    value: Callable[[SettledBet], float | None],
    unit: str = "",
) -> list[dict[str, object]]:
    """Bucket bets into ranges defined by ascending ``edges`` boundaries."""

    bounds = [-float("inf"), *edges, float("inf")]
    rows: list[dict[str, object]] = []
    for lo, hi in zip(bounds[:-1], bounds[1:], strict=True):
        group = [b for b in bets if (v := value(b)) is not None and lo <= v < hi]
        if lo == -float("inf"):
            label = f"< {hi:g}{unit}"
        elif hi == float("inf"):
            label = f">= {lo:g}{unit}"
        else:
            label = f"{lo:g}-{hi:g}{unit}"
        if group:
            rows.append(_group_stats(group, label))
    return rows


def by_odds(bets: Sequence[SettledBet]) -> list[dict[str, object]]:
    return _bucket(bets, [1.5, 2.0, 3.0], lambda b: b.entry_odds)


def by_edge(bets: Sequence[SettledBet]) -> list[dict[str, object]]:
    return _bucket(
        bets,
        [0.02, 0.05, 0.08, 0.12],
        lambda b: b.edge,
        unit="",
    )


def by_league(bets: Sequence[SettledBet]) -> list[dict[str, object]]:
    leagues = sorted({b.league for b in bets if b.league is not None})
    return [_group_stats([b for b in bets if b.league == lg], lg) for lg in leagues]


def by_month(bets: Sequence[SettledBet]) -> list[dict[str, object]]:
    months = sorted({b.kickoff[:7] for b in bets if b.kickoff})
    return [_group_stats([b for b in bets if b.kickoff and b.kickoff[:7] == m], m) for m in months]
