"""Arbitrage detection and line shopping (Layer 2).

Line shopping picks the best available odds per outcome across bookmakers. If
the combined implied probability of the best odds falls below 1.0, the market
offers a surebet: staking proportionally locks in a risk-free profit.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quantbot.markets.odds import MarketEngine
from quantbot.schemas import MatchOutcome, Odds

_ORDER: tuple[MatchOutcome, ...] = (MatchOutcome.HOME, MatchOutcome.DRAW, MatchOutcome.AWAY)


@dataclass(frozen=True)
class ArbitrageOpportunity:
    """Result of scanning one match's odds across bookmakers.

    Attributes:
        best_odds: Best decimal odds per outcome with the offering bookmaker.
        booksum: Sum of implied probabilities of the best odds.
        profit_margin: Guaranteed return fraction (``1/booksum - 1``); positive
            only when it is a true arbitrage.
        is_arbitrage: True when ``booksum < 1``.
        stakes: Per-outcome stake for the given total stake (equal payout).
        guaranteed_profit: Locked-in profit for the given total stake.
        total_stake: The total stake the allocation was computed for.
    """

    match_id: str
    best_odds: dict[MatchOutcome, tuple[float, str]]
    booksum: float
    profit_margin: float
    is_arbitrage: bool
    stakes: dict[MatchOutcome, float]
    guaranteed_profit: float
    total_stake: float


class ArbitrageEngine:
    """Line shopping and surebet detection across bookmakers."""

    def __init__(self, market_engine: MarketEngine | None = None) -> None:
        self._market_engine = market_engine or MarketEngine()

    def line_shopping(self, odds_list: Sequence[Odds]) -> dict[MatchOutcome, tuple[float, str]]:
        """Best decimal odds per outcome with the offering bookmaker."""

        return self._market_engine.best_odds(odds_list)

    @staticmethod
    def booksum(best_odds: dict[MatchOutcome, tuple[float, str]]) -> float:
        return sum(1.0 / best_odds[o][0] for o in _ORDER)

    def allocate_stakes(
        self,
        best_odds: dict[MatchOutcome, tuple[float, str]],
        total_stake: float,
    ) -> tuple[dict[MatchOutcome, float], float]:
        """Split ``total_stake`` so every outcome pays out equally.

        Returns per-outcome stakes and the guaranteed profit. When the market
        is not an arbitrage the profit is negative (informational only).
        """

        if total_stake <= 0.0:
            raise ValueError("total_stake must be positive")
        book = self.booksum(best_odds)
        stakes = {
            o: total_stake * (1.0 / best_odds[o][0]) / book for o in _ORDER
        }
        # Payout on any outcome equals total_stake / book (equalized).
        guaranteed_profit = total_stake / book - total_stake
        return stakes, guaranteed_profit

    def find_arbitrage(
        self, odds_list: Sequence[Odds], total_stake: float = 100.0
    ) -> ArbitrageOpportunity:
        """Scan a match's odds and build the arbitrage opportunity report."""

        match_id = self._market_engine._validate_group(odds_list)  # noqa: SLF001
        best = self.line_shopping(odds_list)
        book = self.booksum(best)
        stakes, profit = self.allocate_stakes(best, total_stake)
        return ArbitrageOpportunity(
            match_id=match_id,
            best_odds=best,
            booksum=book,
            profit_margin=(1.0 / book) - 1.0,
            is_arbitrage=book < 1.0,
            stakes=stakes,
            guaranteed_profit=profit,
            total_stake=total_stake,
        )
