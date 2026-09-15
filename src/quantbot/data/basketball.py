"""Basketball data provider (Layer 0) — demo NBA fixtures/odds/spreads."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from quantbot.data.base import BaseDataProvider
from quantbot.data.basketball_demo import (
    build_nba_matches,
    build_nba_odds,
    build_nba_spreads,
    build_nba_totals,
)
from quantbot.schemas import League, Match, Odds, TotalsOdds
from quantbot.schemas.enums import Sport
from quantbot.schemas.odds import SpreadOdds


class BasketballDataProvider(BaseDataProvider):
    """Deterministic NBA provider implementing moneyline, totals, and spreads.

    Live BallDontLie / Odds-API backends can replace the demo fetch hooks later;
    temporal masking stays in :class:`BaseDataProvider`.
    """

    def __init__(self, seed: int = 7) -> None:
        self._seed = seed

    @property
    def provider_name(self) -> str:
        return f"basketball_demo(seed={self._seed})"

    @lru_cache(maxsize=1)
    def _universe(self) -> tuple[Match, ...]:
        return tuple(build_nba_matches(seed=self._seed))

    def _fetch_matches(self) -> Sequence[Match]:
        return self._universe()

    def _fetch_odds(self, match_id: str) -> Sequence[Odds]:
        match = next((m for m in self._universe() if m.match_id == match_id), None)
        if match is None or match.sport is not Sport.BASKETBALL:
            return ()
        return tuple(build_nba_odds([match], seed=self._seed).get(match_id, []))

    def _fetch_totals_odds(self, match_id: str) -> Sequence[TotalsOdds]:
        match = next((m for m in self._universe() if m.match_id == match_id), None)
        if match is None:
            return ()
        return tuple(build_nba_totals([match], seed=self._seed).get(match_id, []))

    def get_spreads(self, match_id: str) -> list[SpreadOdds]:
        """Raw spread quotes (not as_of-masked — callers must filter)."""

        match = next((m for m in self._universe() if m.match_id == match_id), None)
        if match is None:
            return []
        return list(build_nba_spreads([match], seed=self._seed).get(match_id, []))

    def available_seasons(self, league: League | None = None) -> list[str]:
        seasons = {
            m.season
            for m in self._universe()
            if league is None or m.league is league
        }
        return sorted(seasons, reverse=True)
