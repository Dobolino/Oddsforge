"""Table helpers: turn pipeline objects into pandas DataFrames for display."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from quantbot.backtest.metrics import BacktestMetrics
from quantbot.dashboard.ux import (
    SIGNAL_COLUMNS_BY_MODE,
    UXMode,
    plain_signal_label,
    reason_for_mode,
)
from quantbot.orchestrator import SignalReport

SIGNAL_COLUMNS = [
    "Match",
    "Signal",
    "Odds",
    "Edge",
    "EV",
    "Stake %",
    "Confidence",
    "Data quality",
    "Reason",
]


def signals_dataframe(
    reports: Sequence[SignalReport],
    *,
    mode: UXMode = UXMode.EXPERT,
    lang: str = "de",
) -> pd.DataFrame:
    """One row per signal. Column depth follows the UX mode."""

    rows: list[dict[str, object]] = []
    for report in reports:
        s = report.signal
        m = report.match
        tip = plain_signal_label(s.signal, lang)
        why = reason_for_mode(s, mode, lang)
        rows.append(
            {
                "Match": f"{m.home_team.name} vs {m.away_team.name}",
                "Tipp": tip,
                "Begründung": why,
                "Signal": tip if mode is not UXMode.EXPERT else s.signal.value,
                "Odds": "-" if s.decimal_odds is None else round(s.decimal_odds, 3),
                "Edge": "-" if s.edge is None else round(s.edge, 4),
                "EV": "-" if s.expected_value is None else round(s.expected_value, 4),
                "Stake %": round(s.stake_fraction * 100.0, 2),
                "Confidence": round(s.model_confidence, 1),
                "Data quality": round(s.data_quality, 1),
                "Reason": why,
            }
        )
    columns = list(SIGNAL_COLUMNS_BY_MODE[mode])
    return pd.DataFrame(rows, columns=columns)


def beginner_tip_cards(
    reports: Sequence[SignalReport],
    *,
    lang: str = "de",
    limit: int = 5,
) -> list[dict[str, str]]:
    """Top value tips for the beginner home view (bets first, then no-bets)."""

    bets = [r for r in reports if r.signal.is_bet]
    others = [r for r in reports if not r.signal.is_bet]
    ordered = bets + others
    cards: list[dict[str, str]] = []
    for report in ordered[:limit]:
        s = report.signal
        m = report.match
        cards.append(
            {
                "match": f"{m.home_team.name} vs {m.away_team.name}",
                "tip": plain_signal_label(s.signal, lang),
                "why": reason_for_mode(s, UXMode.BEGINNER, lang),
                "is_bet": "1" if s.is_bet else "0",
            }
        )
    return cards


def metrics_dataframe(
    metrics: BacktestMetrics,
    *,
    mode: UXMode = UXMode.EXPERT,
) -> pd.DataFrame:
    """Two-column (Metric, Value) frame of formatted backtest metrics."""

    def pct(x: float) -> str:
        return f"{x * 100:.2f}%"

    basic = [
        ("Bets placed", str(metrics.n_bets)),
        ("ROI (yield)", pct(metrics.roi)),
        ("Win rate", pct(metrics.win_rate)),
        ("Max drawdown", pct(metrics.max_drawdown)),
    ]
    advanced = [
        ("Total return", pct(metrics.total_return)),
        ("Profit factor", f"{metrics.profit_factor:.2f}"),
        (
            "Beat-CLV rate",
            "-" if metrics.beat_clv_rate is None else pct(metrics.beat_clv_rate),
        ),
    ]
    expert = [
        ("Total staked", f"{metrics.total_staked:.2f}"),
        ("Total PnL", f"{metrics.total_pnl:.2f}"),
        ("Sharpe", f"{metrics.sharpe:.3f}"),
        ("Sortino", f"{metrics.sortino:.3f}"),
        ("Avg CLV", "-" if metrics.avg_clv is None else f"{metrics.avg_clv:.4f}"),
    ]

    if mode is UXMode.BEGINNER:
        rows = basic
    elif mode is UXMode.ADVANCED:
        rows = basic + advanced
    else:
        rows = basic + advanced + expert
    return pd.DataFrame(rows, columns=["Metric", "Value"])
