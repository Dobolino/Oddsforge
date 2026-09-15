"""Compose football + basketball providers behind one BaseDataProvider."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from quantbot.data.base import BaseDataProvider
from quantbot.schemas import League, Match, Odds, TotalsOdds
from quantbot.schemas.enums import Sport, sport_for_league


class CompositeDataProvider(BaseDataProvider):
    """Route league queries to the football or basketball backend."""

    def __init__(
        self,
        football: BaseDataProvider,
        basketball: BaseDataProvider,
    ) -> None:
        self._football = football
        self._basketball = basketball

    @property
    def provider_name(self) -> str:
        return f"composite({self._football.provider_name}+{self._basketball.provider_name})"

    def _backend(self, league: League) -> BaseDataProvider:
        if sport_for_league(league) is Sport.BASKETBALL:
            return self._basketball
        return self._football

    def _fetch_matches(self) -> Sequence[Match]:
        # Merge both universes once; base class filters by league/season.
        foot = list(self._football._fetch_matches())  # noqa: SLF001
        basket = list(self._basketball._fetch_matches())  # noqa: SLF001
        return tuple(foot + basket)

    def _fetch_odds(self, match_id: str) -> Sequence[Odds]:
        odds = self._football._fetch_odds(match_id)  # noqa: SLF001
        if odds:
            return odds
        return self._basketball._fetch_odds(match_id)  # noqa: SLF001

    def _fetch_totals_odds(self, match_id: str) -> Sequence[TotalsOdds]:
        totals = self._football._fetch_totals_odds(match_id)  # noqa: SLF001
        if totals:
            return totals
        return self._basketball._fetch_totals_odds(match_id)  # noqa: SLF001

    def available_seasons(self, league: League | None = None) -> list[str]:
        seasons: set[str] = set()
        for backend in (self._football, self._basketball):
            fn = getattr(backend, "available_seasons", None)
            if callable(fn):
                try:
                    seasons.update(fn(league) if league is not None else fn())
                except TypeError:
                    seasons.update(fn())
        if not seasons:
            seasons = {m.season for m in self._fetch_matches() if league is None or m.league is league}
        return sorted(seasons, reverse=True)

    @property
    def load_errors(self) -> list[str]:
        errs: list[str] = []
        for backend in (self._football, self._basketball):
            errs.extend(getattr(backend, "load_errors", []) or [])
        return errs

    @property
    def finished_last_updated(self) -> datetime | None:
        times = [
            getattr(backend, "finished_last_updated", None)
            for backend in (self._football, self._basketball)
        ]
        times = [t for t in times if t is not None]
        return max(times) if times else None
