"""Settlement-safe market line validation."""

from __future__ import annotations

import math


def require_half_line(line: float) -> float:
    """Only half-lines can use a binary win/loss EV and settlement model."""

    if not math.isfinite(line) or line <= 0.0:
        raise ValueError("totals line must be positive and finite")
    if abs(line - (math.floor(line) + 0.5)) > 1e-9:
        raise ValueError("only half-point totals are supported until pushes are settled")
    return line


def require_handicap_half_line(line: float) -> float:
    """Asian-handicap half-line (signed): a clean two-way market with no push.

    Handicaps can be negative (home favored, e.g. -0.5, -1.5) or positive
    (home underdog, e.g. +0.5). Only half-points are supported so a bet is
    always won or lost, never refunded. Level (0) and whole lines (push
    possible) are rejected until void settlement is modeled for them.
    """

    if not math.isfinite(line):
        raise ValueError("handicap line must be finite")
    if abs(line - (math.floor(line) + 0.5)) > 1e-9:
        raise ValueError("only half-point handicaps are supported (no push)")
    return line
