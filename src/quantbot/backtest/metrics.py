"""Backtest metrics (Layer 5).

Aggregates settled bets and a bankroll curve into performance statistics:
total return, ROI/yield, Sharpe ratio, max drawdown, win rate, profit factor,
average CLV and beat-CLV rate.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from quantbot.backtest.execution import SettledBet


@dataclass(frozen=True)
class BacktestMetrics:
    n_bets: int
    total_staked: float
    total_pnl: float
    total_return: float
    roi: float
    win_rate: float
    profit_factor: float
    sharpe: float
    max_drawdown: float
    avg_clv: float | None
    beat_clv_rate: float | None


def max_drawdown(curve: Sequence[float]) -> float:
    """Largest peak-to-trough decline as a fraction of the running peak."""

    peak = -math.inf
    mdd = 0.0
    for value in curve:
        peak = max(peak, value)
        if peak > 0.0:
            mdd = max(mdd, (peak - value) / peak)
    return mdd


def sharpe_ratio(returns: Sequence[float]) -> float:
    """Mean/std of per-bet returns. Zero when undefined (<2 bets or no spread)."""

    if len(returns) < 2:
        return 0.0
    arr = np.asarray(returns, dtype=float)
    std = float(arr.std(ddof=1))
    if std < 1e-12:  # numerically flat returns
        return 0.0
    return float(arr.mean() / std)


def compute_metrics(
    settled_bets: Sequence[SettledBet],
    bankroll_curve: Sequence[float],
    initial_bankroll: float,
) -> BacktestMetrics:
    if initial_bankroll <= 0.0:
        raise ValueError("initial_bankroll must be positive")

    n = len(settled_bets)
    total_staked = sum(b.stake for b in settled_bets)
    total_pnl = sum(b.pnl for b in settled_bets)
    final = bankroll_curve[-1] if bankroll_curve else initial_bankroll

    wins = sum(1 for b in settled_bets if b.won)
    gross_win = sum(b.pnl for b in settled_bets if b.pnl > 0.0)
    gross_loss = -sum(b.pnl for b in settled_bets if b.pnl < 0.0)

    if gross_loss > 0.0:
        profit_factor = gross_win / gross_loss
    elif gross_win > 0.0:
        profit_factor = math.inf
    else:
        profit_factor = 0.0

    returns = [b.pnl / initial_bankroll for b in settled_bets]

    clvs = [b.clv for b in settled_bets if b.clv is not None]
    avg_clv = float(np.mean(clvs)) if clvs else None
    beat_clv_rate = (
        float(np.mean([1.0 if b.beat_closing else 0.0 for b in settled_bets if b.beat_closing is not None]))
        if any(b.beat_closing is not None for b in settled_bets)
        else None
    )

    return BacktestMetrics(
        n_bets=n,
        total_staked=total_staked,
        total_pnl=total_pnl,
        total_return=(final - initial_bankroll) / initial_bankroll,
        roi=(total_pnl / total_staked) if total_staked > 0.0 else 0.0,
        win_rate=(wins / n) if n > 0 else 0.0,
        profit_factor=profit_factor,
        sharpe=sharpe_ratio(returns),
        max_drawdown=max_drawdown(bankroll_curve) if bankroll_curve else 0.0,
        avg_clv=avg_clv,
        beat_clv_rate=beat_clv_rate,
    )
