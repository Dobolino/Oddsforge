"""Market Engine (Layer 2): implied probabilities, margin removal, aggregation.

Turns raw bookmaker :class:`Odds` into fair :class:`MarketData` and aggregates
across bookmakers via consensus (average fair probabilities) or best odds
(highest decimal odds per outcome).
"""

from __future__ import annotations

from collections.abc import Sequence

from quantbot.markets.margin import booksum, remove_margin
from quantbot.schemas import MarginMethod, MarketData, MatchOutcome, Odds

# Positional outcome order used throughout the engine.
_ORDER: tuple[MatchOutcome, ...] = (MatchOutcome.HOME, MatchOutcome.DRAW, MatchOutcome.AWAY)


class MarketEngine:
    """Processes odds into fair market probabilities.

    Args:
        method: Default margin-removal method for produced MarketData.
    """

    def __init__(self, method: MarginMethod = MarginMethod.SHIN) -> None:
        if method is MarginMethod.POWER:
            raise ValueError("Power margin removal is reserved for two-way markets")
        self.method = method

    def _method(self, override: MarginMethod | None) -> MarginMethod:
        used = override or self.method
        if used is MarginMethod.POWER:
            raise ValueError("Power margin removal is reserved for two-way markets")
        return used

    # --- Single bookmaker ---

    @staticmethod
    def implied(odds: Odds) -> dict[MatchOutcome, float]:
        return odds.implied_probabilities()

    def fair_probabilities(
        self, odds: Odds, method: MarginMethod | None = None
    ) -> dict[MatchOutcome, float]:
        used = self._method(method)
        vec = [odds.home, odds.draw, odds.away]
        fair = remove_margin(vec, used.value)
        return dict(zip(_ORDER, fair, strict=True))

    def to_market_data(self, odds: Odds, method: MarginMethod | None = None) -> MarketData:
        used = self._method(method)
        vec = [odds.home, odds.draw, odds.away]
        fair = remove_margin(vec, used.value)
        overround = max(0.0, booksum(vec) - 1.0)
        return MarketData(
            match_id=odds.match_id,
            bookmaker=odds.bookmaker,
            timestamp=odds.timestamp,
            method=used,
            fair_home=fair[0],
            fair_draw=fair[1],
            fair_away=fair[2],
            overround=overround,
            is_closing=odds.is_closing,
        )

    # --- Aggregation across bookmakers ---

    @staticmethod
    def _validate_group(odds_list: Sequence[Odds]) -> str:
        if not odds_list:
            raise ValueError("odds_list must not be empty")
        match_ids = {o.match_id for o in odds_list}
        if len(match_ids) != 1:
            raise ValueError(f"all odds must share one match_id, got {sorted(match_ids)}")
        return next(iter(match_ids))

    def best_odds(self, odds_list: Sequence[Odds]) -> dict[MatchOutcome, tuple[float, str]]:
        """Highest decimal odds per outcome with the offering bookmaker."""

        self._validate_group(odds_list)
        best: dict[MatchOutcome, tuple[float, str]] = {}
        for outcome in _ORDER:
            top = max(odds_list, key=lambda o: o.decimal_odds()[outcome])
            best[outcome] = (top.decimal_odds()[outcome], top.bookmaker)
        return best

    def best_odds_market(
        self, odds_list: Sequence[Odds], method: MarginMethod | None = None
    ) -> MarketData:
        """Fair market from the best available odds per outcome.

        Combining best odds across books usually yields a booksum <= 1, so the
        margin functions fall back to plain normalization.
        """

        match_id = self._validate_group(odds_list)
        used = self._method(method)
        best = self.best_odds(odds_list)
        vec = [best[o][0] for o in _ORDER]
        fair = remove_margin(vec, used.value)
        overround = max(0.0, booksum(vec) - 1.0)
        timestamp = max(o.timestamp for o in odds_list)
        return MarketData(
            match_id=match_id,
            bookmaker="best",
            timestamp=timestamp,
            method=used,
            fair_home=fair[0],
            fair_draw=fair[1],
            fair_away=fair[2],
            overround=overround,
            is_closing=all(o.is_closing for o in odds_list),
        )

    def consensus(
        self, odds_list: Sequence[Odds], method: MarginMethod | None = None
    ) -> MarketData:
        """Consensus fair probabilities: average each book's fair probs.

        Removing each book's margin first, then averaging, avoids letting a
        higher-margin book dominate the aggregate.
        """

        match_id = self._validate_group(odds_list)
        used = self._method(method)

        sums = dict.fromkeys(_ORDER, 0.0)
        overrounds = 0.0
        for odds in odds_list:
            fair = self.fair_probabilities(odds, used)
            for outcome in _ORDER:
                sums[outcome] += fair[outcome]
            overrounds += max(0.0, booksum([odds.home, odds.draw, odds.away]) - 1.0)

        n = len(odds_list)
        avg = {outcome: sums[outcome] / n for outcome in _ORDER}
        total = sum(avg.values())
        fair = {outcome: avg[outcome] / total for outcome in _ORDER}
        timestamp = max(o.timestamp for o in odds_list)

        return MarketData(
            match_id=match_id,
            bookmaker="consensus",
            timestamp=timestamp,
            method=used,
            fair_home=fair[MatchOutcome.HOME],
            fair_draw=fair[MatchOutcome.DRAW],
            fair_away=fair[MatchOutcome.AWAY],
            overround=overrounds / n,
            is_closing=all(o.is_closing for o in odds_list),
        )
