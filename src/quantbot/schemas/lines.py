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
