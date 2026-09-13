"""Table helpers: turn pipeline objects into pandas DataFrames for display."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from quantbot.backtest.metrics import BacktestMetrics
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


def signals_dataframe(reports: Sequence[SignalReport]) -> pd.DataFrame:
    """One row per signal with odds, EV, Kelly stake, and rejection reason."""

    rows: list[dict[str, object]] = []
    for report in reports:
        s = report.signal
        m = report.match
        rows.append(
            {
                "Match": f"{m.home_team.name} vs {m.away_team.name}",
                "Signal": s.signal.value,
                "Odds": "-" if s.decimal_odds is None else round(s.decimal_odds, 3),
                "Edge": "-" if s.edge is None else round(s.edge, 4),
                "EV": "-" if s.expected_value is None else round(s.expected_value, 4),
                "Stake %": round(s.stake_fraction * 100.0, 2),
                "Confidence": round(s.model_confidence, 1),
                "Data quality": round(s.data_quality, 1),
                "Reason": s.rationale,
            }
        )
    return pd.DataFrame(rows, columns=SIGNAL_COLUMNS)


def metrics_dataframe(metrics: BacktestMetrics) -> pd.DataFrame:
    """Two-column (Metric, Value) frame of formatted backtest metrics."""

    def pct(x: float) -> str:
        return f"{x * 100:.2f}%"

    rows = [
        ("Bets placed", str(metrics.n_bets)),
        ("Total staked", f"{metrics.total_staked:.2f}"),
        ("Total PnL", f"{metrics.total_pnl:.2f}"),
        ("Total return", pct(metrics.total_return)),
        ("ROI (yield)", pct(metrics.roi)),
        ("Win rate", pct(metrics.win_rate)),
        ("Profit factor", f"{metrics.profit_factor:.2f}"),
        ("Sharpe", f"{metrics.sharpe:.3f}"),
        ("Sortino", f"{metrics.sortino:.3f}"),
        ("Max drawdown", pct(metrics.max_drawdown)),
        ("Avg CLV", "-" if metrics.avg_clv is None else f"{metrics.avg_clv:.4f}"),
        (
            "Beat-CLV rate",
            "-" if metrics.beat_clv_rate is None else pct(metrics.beat_clv_rate),
        ),
    ]
    return pd.DataFrame(rows, columns=["Metric", "Value"])
