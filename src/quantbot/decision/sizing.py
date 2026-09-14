"""Kelly stake sizing (Layer 4).

Guardrail: stakes are theoretical suggestions only. QuantBot v1 never places
bets. The sizer returns a fraction of bankroll; fractional Kelly and hard caps
keep the suggestion conservative.

Kelly fraction for a single bet at decimal odds ``o`` with model probability
``p``: ``f = (p * o - 1) / (o - 1)`` which equals ``EV / (o - 1)``.
"""

from __future__ import annotations

from dataclasses import dataclass


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

        if decimal_odds <= 1.0:
            raise ValueError("decimal_odds must be > 1.0")
        return (prob * decimal_odds - 1.0) / (decimal_odds - 1.0)

    def stake_fraction(self, prob: float, decimal_odds: float) -> float:
        """Capped fractional-Kelly stake as a fraction of bankroll, in [0, cap]."""

        f = self.full_kelly(prob, decimal_odds) * self.kelly_fraction
        if f <= 0.0:
            return 0.0
        f = min(f, self.max_fraction)
        if f < self.min_fraction:
            return 0.0
        return f

    def stake_amount(self, prob: float, decimal_odds: float, bankroll: float) -> float:
        """Theoretical stake in currency units for a given bankroll."""

        if bankroll < 0.0:
            raise ValueError("bankroll must be non-negative")
        return self.stake_fraction(prob, decimal_odds) * bankroll
