"""Typed settlement for spreads/totals including quarter-line splits (P2).

Payoff factors per unit stake:
- WIN: ``o``
- LOSS: ``0``
- PUSH / VOID: ``1``
- HALF_WIN: ``(o + 1) / 2``
- HALF_LOSS: ``0.5``

Quarter lines are decomposed into two adjacent half/whole lines at half stake.
Unknown / unsupported rules return PENDING or UNSUPPORTED rather than guessing VOID.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from math import isfinite

from quantbot.schemas.enums import SettlementStatus
from quantbot.schemas.lines import exact_line, is_quarter_line

_QUARTER = Decimal("0.25")
_ZERO = Decimal("0")


class LineMarketKind(str, Enum):
    TOTALS = "totals"
    SPREAD = "spread"


@dataclass(frozen=True)
class SettlementResult:
    status: SettlementStatus
    payoff_factor: float
    """Gross return per unit stake (before subtracting the stake for PnL)."""

    components: tuple[SettlementStatus, ...] = ()


def split_quarter_line(line: Decimal) -> tuple[Decimal, Decimal]:
    """Adjacent half/whole neighbours for a quarter line (lower, upper)."""

    if not is_quarter_line(line):
        raise ValueError("split_quarter_line requires a quarter tick")
    return line - _QUARTER, line + _QUARTER


def _raw_margin(
    *,
    kind: LineMarketKind,
    selection: str,
    line: Decimal,
    home_score: int,
    away_score: int,
) -> Decimal:
    if kind is LineMarketKind.TOTALS:
        total = Decimal(home_score + away_score)
        diff = total - line
        if selection == "under":
            diff = -diff
        elif selection != "over":
            raise ValueError(f"unknown totals selection: {selection!r}")
        return diff
    if selection == "home":
        return Decimal(home_score - away_score) + line
    if selection == "away":
        return Decimal(away_score - home_score) + line
    raise ValueError(f"unknown spread selection: {selection!r}")


def settle_simple_line(margin: Decimal) -> SettlementStatus:
    """Win / loss / push for a single half or whole line (no quarter split)."""

    if margin == _ZERO:
        return SettlementStatus.PUSH
    return SettlementStatus.WON if margin > _ZERO else SettlementStatus.LOST


def _combine_half_stakes(a: SettlementStatus, b: SettlementStatus) -> SettlementStatus:
    """Combine two half-stake settlements into one ticket status."""

    pair = {a, b}
    if a is b:
        return a
    if pair == {SettlementStatus.WON, SettlementStatus.PUSH}:
        return SettlementStatus.HALF_WIN
    if pair == {SettlementStatus.LOST, SettlementStatus.PUSH}:
        return SettlementStatus.HALF_LOSS
    if pair == {SettlementStatus.WON, SettlementStatus.LOST}:
        return SettlementStatus.PUSH
    return SettlementStatus.UNSUPPORTED


def settle_line_market(
    *,
    kind: LineMarketKind,
    selection: str,
    line: float | Decimal | str,
    home_score: int,
    away_score: int,
    decimal_odds: float,
) -> SettlementResult:
    """Settle a totals/spread selection including quarter-line splits."""

    if home_score < 0 or away_score < 0:
        raise ValueError("scores must be non-negative")
    if not isfinite(decimal_odds) or decimal_odds <= 1.0:
        raise ValueError("decimal_odds must be finite and > 1.0")

    try:
        line_d = exact_line(line)
    except ValueError:
        return SettlementResult(
            status=SettlementStatus.UNSUPPORTED,
            payoff_factor=0.0,
            components=(),
        )

    if kind is LineMarketKind.TOTALS and line_d <= _ZERO:
        return SettlementResult(status=SettlementStatus.UNSUPPORTED, payoff_factor=0.0)

    if is_quarter_line(line_d):
        lower, upper = split_quarter_line(line_d)
        s_lo = settle_simple_line(
            _raw_margin(
                kind=kind,
                selection=selection,
                line=lower,
                home_score=home_score,
                away_score=away_score,
            )
        )
        s_hi = settle_simple_line(
            _raw_margin(
                kind=kind,
                selection=selection,
                line=upper,
                home_score=home_score,
                away_score=away_score,
            )
        )
        status = _combine_half_stakes(s_lo, s_hi)
        return SettlementResult(
            status=status,
            payoff_factor=payoff_factor(status, decimal_odds),
            components=(s_lo, s_hi),
        )

    status = settle_simple_line(
        _raw_margin(
            kind=kind,
            selection=selection,
            line=line_d,
            home_score=home_score,
            away_score=away_score,
        )
    )
    return SettlementResult(
        status=status,
        payoff_factor=payoff_factor(status, decimal_odds),
        components=(status,),
    )


def payoff_factor(status: SettlementStatus, decimal_odds: float) -> float:
    if status is SettlementStatus.WON:
        return float(decimal_odds)
    if status is SettlementStatus.LOST:
        return 0.0
    if status in (SettlementStatus.PUSH, SettlementStatus.VOID):
        return 1.0
    if status is SettlementStatus.HALF_WIN:
        return (float(decimal_odds) + 1.0) / 2.0
    if status is SettlementStatus.HALF_LOSS:
        return 0.5
    if status in (SettlementStatus.PENDING, SettlementStatus.UNSUPPORTED):
        raise ValueError(f"no payoff for status {status.value}")
    raise ValueError(f"unknown settlement status: {status!r}")


def multi_state_ev(
    state_probs: dict[SettlementStatus, float],
    *,
    decimal_odds: float,
) -> float:
    """``EV = sum(p_s * payout_s) - 1`` for push/quarter markets."""

    if not isfinite(decimal_odds) or decimal_odds <= 1.0:
        raise ValueError("decimal_odds must be finite and > 1.0")
    total_p = 0.0
    ev = 0.0
    for status, prob in state_probs.items():
        if prob < 0.0 or not isfinite(prob):
            raise ValueError("probabilities must be finite and >= 0")
        if status in (SettlementStatus.PENDING, SettlementStatus.UNSUPPORTED):
            continue
        total_p += prob
        ev += prob * payoff_factor(status, decimal_odds)
    if abs(total_p - 1.0) > 1e-6:
        raise ValueError(f"state probabilities must sum to 1, got {total_p}")
    return ev - 1.0
