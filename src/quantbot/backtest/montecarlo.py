"""Monte-Carlo bankroll simulation (Layer 5).

Given a set of bet specifications (stake fraction, decimal odds, model win
probability), simulates many compounded bankroll paths under the model's own
probabilities. Reports risk of ruin and the distribution of final bankroll and
max drawdown. Paper analysis only; no bets are placed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from quantbot.backtest.engine import BacktestResult


@dataclass(frozen=True)
class BetSpec:
    """One bet's inputs to the simulation."""

    stake_fraction: float
    decimal_odds: float
    win_prob: float


@dataclass(frozen=True)
class MonteCarloResult:
    n_sims: int
    n_bets: int
    initial_bankroll: float
    ruin_fraction: float
    risk_of_ruin: float
    final_mean: float
    final_median: float
    final_p5: float
    final_p95: float
    drawdown_mean: float
    drawdown_median: float
    drawdown_p95: float


def bet_specs_from_result(result: BacktestResult) -> list[BetSpec]:
    """Reconstruct per-bet specs from a completed backtest.

    Stake fraction is the stake relative to the bankroll just before the bet.
    """

    specs: list[BetSpec] = []
    for i, bet in enumerate(result.settled_bets):
        bankroll_before = result.bankroll_curve[i]
        fraction = bet.stake / bankroll_before if bankroll_before > 0.0 else 0.0
        specs.append(
            BetSpec(
                stake_fraction=fraction,
                decimal_odds=bet.entry_odds,
                win_prob=bet.model_prob,
            )
        )
    return specs


def monte_carlo_bankroll(
    specs: Sequence[BetSpec],
    initial_bankroll: float = 1000.0,
    n_sims: int = 10_000,
    ruin_fraction: float = 0.5,
    seed: int = 0,
) -> MonteCarloResult:
    """Simulate ``n_sims`` compounded bankroll paths over the given bets.

    Args:
        ruin_fraction: A path is "ruined" if bankroll ever drops to or below
            this fraction of the initial bankroll.
    """

    if initial_bankroll <= 0.0:
        raise ValueError("initial_bankroll must be positive")
    if not 0.0 < ruin_fraction < 1.0:
        raise ValueError("ruin_fraction must be in (0, 1)")

    n_bets = len(specs)
    if n_bets == 0:
        return MonteCarloResult(
            n_sims=n_sims,
            n_bets=0,
            initial_bankroll=initial_bankroll,
            ruin_fraction=ruin_fraction,
            risk_of_ruin=0.0,
            final_mean=initial_bankroll,
            final_median=initial_bankroll,
            final_p5=initial_bankroll,
            final_p95=initial_bankroll,
            drawdown_mean=0.0,
            drawdown_median=0.0,
            drawdown_p95=0.0,
        )

    rng = np.random.default_rng(seed)
    bankroll = np.full(n_sims, float(initial_bankroll))
    peak = bankroll.copy()
    max_dd = np.zeros(n_sims)
    ruin_threshold = initial_bankroll * ruin_fraction
    ruined = np.zeros(n_sims, dtype=bool)

    for spec in specs:
        stake = spec.stake_fraction * bankroll
        wins = rng.random(n_sims) < spec.win_prob
        pnl = np.where(wins, stake * (spec.decimal_odds - 1.0), -stake)
        bankroll = bankroll + pnl
        peak = np.maximum(peak, bankroll)
        drawdown = np.where(peak > 0.0, (peak - bankroll) / peak, 0.0)
        max_dd = np.maximum(max_dd, drawdown)
        ruined |= bankroll <= ruin_threshold

    return MonteCarloResult(
        n_sims=n_sims,
        n_bets=n_bets,
        initial_bankroll=initial_bankroll,
        ruin_fraction=ruin_fraction,
        risk_of_ruin=float(ruined.mean()),
        final_mean=float(bankroll.mean()),
        final_median=float(np.median(bankroll)),
        final_p5=float(np.percentile(bankroll, 5)),
        final_p95=float(np.percentile(bankroll, 95)),
        drawdown_mean=float(max_dd.mean()),
        drawdown_median=float(np.median(max_dd)),
        drawdown_p95=float(np.percentile(max_dd, 95)),
    )
