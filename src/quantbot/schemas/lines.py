"""Settlement-safe market line validation (quarter-tick lattice)."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_QUARTER = Decimal("0.25")
_ONE = Decimal("1")
_ZERO = Decimal("0")


def exact_line(value: float | Decimal | str) -> Decimal:
    """Parse a market line onto the quarter-tick lattice (no float equality)."""

    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid line: {value!r}") from exc
    if not d.is_finite():
        raise ValueError("line must be finite")
    ticks = (d / _QUARTER).quantize(_ONE, rounding=ROUND_HALF_UP)
    snapped = ticks * _QUARTER
    if abs(d - snapped) > Decimal("1e-9"):
        raise ValueError(f"line must be a quarter-tick (…, -0.5, -0.25, 0, 0.25, …), got {value}")
    return snapped


def is_quarter_line(line: Decimal) -> bool:
    """True for …, -0.75, -0.25, 0.25, 0.75, … (odd multiples of 0.25)."""

    ticks = line / _QUARTER
    if ticks != ticks.to_integral_value():
        return False
    return abs(int(ticks)) % 2 == 1


def is_half_line(line: Decimal) -> bool:
    """True for …, -1.5, -0.5, 0.5, 1.5, … (odd multiples of 0.5)."""

    doubled = line * 2
    if doubled != doubled.to_integral_value():
        return False
    return abs(int(doubled)) % 2 == 1


def is_whole_line(line: Decimal) -> bool:
    return line == line.to_integral_value()


def require_half_line(line: float) -> float:
    """Half-lines only for the legacy binary win/loss EV path (no push)."""

    if not math.isfinite(line) or line <= 0.0:
        raise ValueError("totals line must be positive and finite")
    d = exact_line(line)
    if not is_half_line(d):
        raise ValueError("only half-point totals are supported on the binary path")
    return float(d)


def require_handicap_half_line(line: float) -> float:
    """Asian-handicap half-line (signed) for the binary no-push path."""

    if not math.isfinite(line):
        raise ValueError("handicap line must be finite")
    d = exact_line(line)
    if not is_half_line(d):
        raise ValueError("only half-point handicaps are supported on the binary path")
    return float(d)


def require_quarter_tick(line: float) -> float:
    """Any quarter-tick line (whole / half / quarter) for typed settlement."""

    if not math.isfinite(line):
        raise ValueError("line must be finite")
    return float(exact_line(line))


def line_allows_push(line: float) -> bool:
    """True when whole or quarter lines can push / half-settle."""

    d = exact_line(line)
    return is_quarter_line(d) or is_whole_line(d)
