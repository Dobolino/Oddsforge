"""Margin removal router: Shin for 3-way books, Power for every 2-way book.

Shin handles favourite-longshot bias better on 1X2. Highly asymmetric two-way
markets (totals, spreads, moneyline) are more stable under the Power method.
"""

from __future__ import annotations

from collections.abc import Sequence

from quantbot.markets.margin import remove_margin
from quantbot.schemas.enums import MarginMethod, MarketKind


def method_for_market(kind: MarketKind) -> MarginMethod:
    """Shin only for three-way 1X2; Power for all two-way markets."""

    if kind is MarketKind.ONE_X_TWO:
        return MarginMethod.SHIN
    return MarginMethod.POWER


def method_for_n_ways(n_ways: int) -> MarginMethod:
    if n_ways == 3:
        return MarginMethod.SHIN
    if n_ways == 2:
        return MarginMethod.POWER
    raise ValueError(f"demargin supports 2- or 3-way books, got n_ways={n_ways}")


def demargin_prices(
    prices: Sequence[float],
    *,
    kind: MarketKind | None = None,
    n_ways: int | None = None,
    method: MarginMethod | None = None,
) -> list[float]:
    """Remove bookmaker margin; defaults follow the Shin/Power split above."""

    if method is None:
        if kind is not None:
            method = method_for_market(kind)
        elif n_ways is not None:
            method = method_for_n_ways(n_ways)
        else:
            method = method_for_n_ways(len(prices))
    if method is MarginMethod.SHIN and len(prices) != 3:
        raise ValueError("Shin demargining requires exactly three outcomes")
    if method is MarginMethod.POWER and len(prices) != 2:
        raise ValueError("Power demargining requires exactly two outcomes")
    return remove_margin(list(prices), method.value)
