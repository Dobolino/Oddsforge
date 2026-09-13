"""Bookmaker margin (overround) removal algorithms.

Given decimal odds for the mutually exclusive outcomes of one market, each
function returns fair probabilities that sum to 1.0. Raw implied
probabilities ``1 / odds`` sum to more than 1.0 by the margin; removing it
yields the bookmaker's (or, for Shin, the insider-adjusted) fair estimate.

Methods:
    * ``naive_normalization`` -- divide implied probs by their sum.
    * ``power_method`` -- raise implied probs to a common exponent k so they
      sum to 1 (root-found via scipy). Adjusts the margin non-uniformly.
    * ``shins_method`` -- Shin's insider-trading model; corrects the
      favorite-longshot bias by attributing more margin to longshots.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from scipy.optimize import brentq

# Below this booksum there is no positive margin to remove (e.g. best-odds
# aggregation across books), so we fall back to plain normalization.
_NO_MARGIN_BOOKSUM = 1.0 + 1e-9


def validate_odds(odds: Sequence[float]) -> None:
    """Reject empty, non-finite, or non-positive-margin decimal odds."""

    if len(odds) < 2:
        raise ValueError("need at least two outcomes")
    for o in odds:
        if not math.isfinite(o):
            raise ValueError(f"odds must be finite, got {o}")
        if o <= 1.0:
            raise ValueError(f"decimal odds must be > 1.0, got {o}")


def implied_probabilities(odds: Sequence[float]) -> list[float]:
    """Raw implied probabilities ``1 / odds`` (still contain the margin)."""

    validate_odds(odds)
    return [1.0 / o for o in odds]


def booksum(odds: Sequence[float]) -> float:
    """Sum of raw implied probabilities. ``booksum - 1`` is the overround."""

    return sum(implied_probabilities(odds))


def naive_normalization(odds: Sequence[float]) -> list[float]:
    """Multiplicative margin removal: implied probs scaled to sum 1."""

    implied = implied_probabilities(odds)
    total = sum(implied)
    return [p / total for p in implied]


def power_method(odds: Sequence[float]) -> tuple[list[float], float]:
    """Return (fair probabilities, exponent k).

    Solves ``sum(implied_i ** k) = 1`` for k. With a positive margin, k > 1
    and larger implied probabilities are shrunk relative to the naive method.
    """

    implied = implied_probabilities(odds)
    if sum(implied) <= _NO_MARGIN_BOOKSUM:
        return naive_normalization(odds), 1.0

    def objective(k: float) -> float:
        return sum(p**k for p in implied) - 1.0

    # objective(1) = booksum - 1 > 0; objective grows negative as k increases.
    k = brentq(objective, 1.0, 100.0, xtol=1e-12)
    fair = [p**k for p in implied]
    total = sum(fair)
    return [p / total for p in fair], k


def shins_method(odds: Sequence[float]) -> tuple[list[float], float]:
    """Return (fair probabilities, insider proportion z) via Shin's model.

    ``p_i = (sqrt(z^2 + 4(1-z) * pi_i^2 / B) - z) / (2(1-z))`` with z chosen so
    the probabilities sum to 1. ``pi_i`` are raw implied probs, ``B`` their sum.
    """

    implied = implied_probabilities(odds)
    b = sum(implied)
    if b <= _NO_MARGIN_BOOKSUM:
        return naive_normalization(odds), 0.0

    def prob(pi: float, z: float) -> float:
        return (math.sqrt(z * z + 4.0 * (1.0 - z) * pi * pi / b) - z) / (2.0 * (1.0 - z))

    def objective(z: float) -> float:
        return sum(prob(pi, z) for pi in implied) - 1.0

    # objective(0) = sqrt(B) - 1 > 0; objective(z->1) < 1, so a root exists.
    z = brentq(objective, 0.0, 1.0 - 1e-9, xtol=1e-12)
    fair = [prob(pi, z) for pi in implied]
    total = sum(fair)
    return [p / total for p in fair], z


def remove_margin(odds: Sequence[float], method: str) -> list[float]:
    """Dispatch margin removal by method name.

    Accepts 'shin', 'power', 'multiplicative' (naive). Raises on unknown names.
    """

    key = method.lower()
    if key == "shin":
        return shins_method(odds)[0]
    if key == "power":
        return power_method(odds)[0]
    if key in {"multiplicative", "naive"}:
        return naive_normalization(odds)
    raise ValueError(f"unknown margin method: {method!r}")
