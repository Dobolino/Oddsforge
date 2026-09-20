"""Asian-handicap (spread) market helpers — kept separate from 1X2 and totals."""

from __future__ import annotations

from collections.abc import Sequence

from quantbot.markets.margin import booksum, remove_margin
from quantbot.schemas import HandicapSide, MarginMethod, SpreadMarketData, SpreadOdds
from quantbot.schemas.enums import HANDICAP_ORDER


class SpreadMarketEngine:
    """Two-way margin removal for Asian-handicap quotes (home vs. away)."""

    def __init__(self, method: MarginMethod = MarginMethod.POWER) -> None:
        if method is not MarginMethod.POWER:
            raise ValueError("two-way spreads require Power margin removal")
        self.method = method

    def to_market_data(
        self, odds: SpreadOdds, method: MarginMethod | None = None
    ) -> SpreadMarketData:
        used = method or self.method
        if used is not MarginMethod.POWER:
            raise ValueError("two-way spreads require Power margin removal")
        vec = [odds.home, odds.away]
        fair = remove_margin(vec, used.value)
        overround = max(0.0, booksum(vec) - 1.0)
        return SpreadMarketData(
            match_id=odds.match_id,
            bookmaker=odds.bookmaker,
            timestamp=odds.timestamp,
            method=used,
            line=odds.line,
            fair_home=fair[0],
            fair_away=fair[1],
            overround=overround,
            is_closing=odds.is_closing,
        )

    def best_odds(
        self, odds_list: Sequence[SpreadOdds]
    ) -> dict[HandicapSide, tuple[float, str]]:
        if not odds_list:
            raise ValueError("odds_list must not be empty")
        match_ids = {o.match_id for o in odds_list}
        if len(match_ids) != 1:
            raise ValueError("all spread odds must share one match_id")
        lines = {o.line for o in odds_list}
        if len(lines) != 1:
            raise ValueError("all spread odds must share one line")
        prices = {HandicapSide.HOME: "home", HandicapSide.AWAY: "away"}
        best: dict[HandicapSide, tuple[float, str]] = {}
        for side in HANDICAP_ORDER:
            attr = prices[side]
            top = max(odds_list, key=lambda o: getattr(o, attr))
            best[side] = (getattr(top, attr), top.bookmaker)
        return best
