"""Kelly stake sizing (Layer 4).

Guardrail: stakes are theoretical suggestions only. QuantBot v1 never places
bets. The sizer returns a fraction of bankroll; fractional Kelly and hard caps
keep the suggestion conservative.

Binary Kelly for decimal odds ``o`` with model probability ``p``:
``f = (p * o - 1) / (o - 1)`` which equals ``EV / (o - 1)``.

For push / quarter markets use :meth:`generalized_stake_fraction` which
maximises ``sum p_s * log(1 + f * (payout_s - 1))`` under the same caps.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, log

HARD_STAKE_CAP = 0.05


@dataclass(frozen=True)
class KellySizer:
    """Fractional Kelly sizing with bankroll caps.

    Args:
        kelly_fraction: Multiplier on full Kelly (e.g. 0.25 = quarter Kelly).
        max_fraction: Hard cap on the stake as a fraction of bankroll.
        min_fraction: Stakes below this are rounded down to 0 (skip dust).
    """

    kelly_fraction: float = 0.10
    max_fraction: float = 0.05
    min_fraction: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 < self.kelly_fraction <= 1.0:
            raise ValueError("kelly_fraction must be in (0, 1]")
        if not 0.0 < self.max_fraction <= 1.0:
            raise ValueError("max_fraction must be in (0, 1]")
        if not 0.0 <= self.min_fraction <= self.max_fraction:
            raise ValueError("min_fraction must be in [0, max_fraction]")

    def full_kelly(self, prob: float, decimal_odds: float) -> float:
        """Full Kelly fraction. May be negative when there is no edge."""

        if not isfinite(prob) or not 0.0 <= prob <= 1.0:
            raise ValueError("prob must be finite and in [0, 1]")
        if not isfinite(decimal_odds) or decimal_odds <= 1.0:
            raise ValueError("decimal_odds must be finite and > 1.0")
        return (prob * decimal_odds - 1.0) / (decimal_odds - 1.0)

    def stake_fraction(self, prob: float, decimal_odds: float) -> float:
        """Capped fractional-Kelly stake as a fraction of bankroll, in [0, cap]."""

        f = self.full_kelly(prob, decimal_odds) * self.kelly_fraction
        if f <= 0.0:
            return 0.0
        f = min(f, self.max_fraction, HARD_STAKE_CAP)
        if f < self.min_fraction:
            return 0.0
        return f

    def stake_amount(self, prob: float, decimal_odds: float, bankroll: float) -> float:
        """Theoretical stake in currency units for a given bankroll."""

        if not isfinite(bankroll) or bankroll < 0.0:
            raise ValueError("bankroll must be finite and non-negative")
        return self.stake_fraction(prob, decimal_odds) * bankroll

    @staticmethod
    def generalized_growth(
        stake_fraction: float,
        outcomes: Sequence[tuple[float, float]],
    ) -> float:
        """Expected log-growth ``E[log(1 + f*(payoff-1))]`` for multi-state bets.

        ``outcomes`` is a sequence of ``(probability, gross_payoff_per_unit)``.
        """

        if not isfinite(stake_fraction) or stake_fraction < 0.0:
            raise ValueError("stake_fraction must be finite and >= 0")
        if not outcomes:
            raise ValueError("outcomes must not be empty")
        total_p = 0.0
        growth = 0.0
        for prob, payoff in outcomes:
            if not isfinite(prob) or prob < 0.0:
                raise ValueError("probabilities must be finite and >= 0")
            if not isfinite(payoff) or payoff < 0.0:
                raise ValueError("payoffs must be finite and >= 0")
            wealth = 1.0 + stake_fraction * (payoff - 1.0)
            if wealth <= 0.0:
                return float("-inf")
            total_p += prob
            growth += prob * log(wealth)
        if abs(total_p - 1.0) > 1e-6:
            raise ValueError(f"outcome probabilities must sum to 1, got {total_p}")
        return growth

    def full_generalized_kelly(
        self,
        outcomes: Sequence[tuple[float, float]],
        *,
        grid: int = 200,
    ) -> float:
        """Numerically maximise log-growth over ``f`` in ``[0, 1]`` (uncapped)."""

        best_f = 0.0
        best_g = self.generalized_growth(0.0, outcomes)
        for i in range(1, max(2, grid) + 1):
            f = i / float(grid)
            g = self.generalized_growth(f, outcomes)
            if g > best_g:
                best_g = g
                best_f = f
        return best_f

    def generalized_stake_fraction(
        self,
        outcomes: Sequence[tuple[float, float]],
        *,
        grid: int = 200,
    ) -> float:
        """Capped fractional generalized-Kelly stake for multi-state markets."""

        pairs = [(float(p), float(pay)) for p, pay in outcomes]
        full = self.full_generalized_kelly(pairs, grid=grid)
        f = full * self.kelly_fraction
        if f <= 0.0:
            return 0.0
        f = min(f, self.max_fraction, HARD_STAKE_CAP)
        if f < self.min_fraction:
            return 0.0
        return f

    @staticmethod
    def binary_win_lose_outcomes(
        prob: float,
        decimal_odds: float,
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """``(win, lose)`` payoff pairs for no-push markets (half-lines)."""

        if not isfinite(prob) or not 0.0 <= prob <= 1.0:
            raise ValueError("prob must be finite and in [0, 1]")
        if not isfinite(decimal_odds) or decimal_odds <= 1.0:
            raise ValueError("decimal_odds must be finite and > 1.0")
        return ((prob, decimal_odds), (1.0 - prob, 0.0))

    @staticmethod
    def push_market_outcomes(
        *,
        p_win: float,
        p_push: float,
        p_lose: float,
        decimal_odds: float,
    ) -> tuple[tuple[float, float], ...]:
        """Win / push / lose payoff pairs for whole-line AH (stake refunded on push)."""

        for name, p in (("p_win", p_win), ("p_push", p_push), ("p_lose", p_lose)):
            if not isfinite(p) or p < 0.0:
                raise ValueError(f"{name} must be finite and >= 0")
        if abs(p_win + p_push + p_lose - 1.0) > 1e-6:
            raise ValueError("p_win + p_push + p_lose must sum to 1")
        if not isfinite(decimal_odds) or decimal_odds <= 1.0:
            raise ValueError("decimal_odds must be finite and > 1.0")
        return (
            (p_win, decimal_odds),
            (p_push, 1.0),
            (p_lose, 0.0),
        )
