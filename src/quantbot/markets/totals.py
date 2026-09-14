"""Totals (Over/Under) market helpers — kept separate from 1X2."""

from __future__ import annotations

from collections.abc import Sequence

from quantbot.markets.margin import booksum, remove_margin
from quantbot.schemas import MarginMethod, TotalsMarketData, TotalsOdds, TotalsSide
from quantbot.schemas.enums import DEFAULT_TOTALS_LINE, TOTALS_ORDER


class TotalsMarketEngine:
    """Two-way margin removal for Over/Under quotes."""

    def __init__(self, method: MarginMethod = MarginMethod.SHIN) -> None:
        self.method = method

    def to_market_data(
        self, odds: TotalsOdds, method: MarginMethod | None = None
    ) -> TotalsMarketData:
        used = method or self.method
        vec = [odds.over, odds.under]
        fair = remove_margin(vec, used.value)
        overround = max(0.0, booksum(vec) - 1.0)
        return TotalsMarketData(
            match_id=odds.match_id,
            bookmaker=odds.bookmaker,
            timestamp=odds.timestamp,
            method=used,
            line=odds.line,
            fair_over=fair[0],
            fair_under=fair[1],
            overround=overround,
            is_closing=odds.is_closing,
        )

    def best_odds(
        self, odds_list: Sequence[TotalsOdds]
    ) -> dict[TotalsSide, tuple[float, str]]:
        if not odds_list:
            raise ValueError("odds_list must not be empty")
        match_ids = {o.match_id for o in odds_list}
        if len(match_ids) != 1:
            raise ValueError("all totals odds must share one match_id")
        lines = {o.line for o in odds_list}
        if len(lines) != 1:
            raise ValueError("all totals odds must share one line")
        best: dict[TotalsSide, tuple[float, str]] = {}
        for side in TOTALS_ORDER:
            top = max(odds_list, key=lambda o: o.decimal_odds()[side])
            best[side] = (top.decimal_odds()[side], top.bookmaker)
        return best


def tip_label_for(side: TotalsSide, line: float = DEFAULT_TOTALS_LINE) -> str:
    line_s = str(int(line)) if float(line).is_integer() else str(line)
    return f"{side.value}_{line_s}"


def actual_totals_label(total_goals: int, line: float = DEFAULT_TOTALS_LINE) -> str:
    side = TotalsSide.OVER if total_goals > line else TotalsSide.UNDER
    return tip_label_for(side, line)
