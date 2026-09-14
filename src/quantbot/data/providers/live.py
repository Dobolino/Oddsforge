"""Live data provider: fixtures/results from Football-Data, odds from The Odds API.

Composes the two API clients into a single :class:`BaseDataProvider`, so the
whole QuantBot pipeline (orchestrator, backtester) runs on real current-season
matches. The base class enforces the ``as_of`` leakage guarantee; this class
only supplies the raw ground truth.

The hard part is matching an odds event (identified by team names) to a
Football-Data fixture (identified by numeric ids). Matching is by normalized
team-name pair within the same league. Names are normalized (lowercased,
accent- and suffix-stripped) with a small alias table for known mismatches.
Real-world coverage depends on both APIs and will need alias tuning.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from pathlib import Path

from quantbot.data.base import BaseDataProvider
from quantbot.data.providers.football_data import FootballDataProvider
from quantbot.data.providers.leagues import football_data_code, odds_api_key
from quantbot.data.providers.the_odds_api import TheOddsAPIProvider
from quantbot.logging import get_logger
from quantbot.schemas import League, Match, Odds

logger = get_logger(__name__)

# Common club-name tokens dropped during normalization.
_DROP_TOKENS = {
    "fc", "cf", "afc", "sc", "ac", "as", "ssc", "rc", "cd", "ud", "fk", "bk",
    "calcio", "club", "de", "the", "1", "1899", "1846", "1900", "1904", "1909",
}

# Known cross-API aliases (normalized Football-Data name -> normalized Odds name).
_ALIASES: dict[str, str] = {
    "brighton hove albion": "brighton and hove albion",
    "wolverhampton wanderers": "wolves",
    "tottenham hotspur": "tottenham",
    "internazionale": "inter milan",
    "borussia monchengladbach": "monchengladbach",
    "paris saint germain": "paris saint germain",
}


def normalize_team(name: str) -> str:
    """Normalize a club name for cross-API matching."""

    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)
    )
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in stripped.lower()).split()]
    kept = [t for t in tokens if t not in _DROP_TOKENS]
    key = " ".join(kept or tokens)
    return _ALIASES.get(key, key)


class LiveDataProvider(BaseDataProvider):
    """Real-data provider combining Football-Data and The Odds API.

    Args:
        football: Football-Data client (fixtures and results).
        odds: The Odds API client (bookmaker odds).
        leagues: Competitions to load.
        regions: The Odds API bookmaker regions (e.g. "eu,uk").
    """

    def __init__(
        self,
        football: FootballDataProvider,
        odds: TheOddsAPIProvider,
        leagues: Sequence[League],
        regions: str = "eu,uk",
    ) -> None:
        if not leagues:
            raise ValueError("at least one league is required")
        self._football = football
        self._odds = odds
        self._leagues = list(leagues)
        self._regions = regions
        self._matches_cache: list[Match] | None = None
        self._match_league: dict[str, League] = {}
        self._odds_cache: dict[League, dict[str, list[Odds]]] = {}

    @property
    def provider_name(self) -> str:
        codes = ",".join(lg.value for lg in self._leagues)
        return f"live(football_data+the_odds_api; {codes})"

    # --- Matches / fixtures (Football-Data) ---

    def _fetch_matches(self) -> Sequence[Match]:
        if self._matches_cache is not None:
            return self._matches_cache

        matches: list[Match] = []
        for league in self._leagues:
            try:
                league_matches = self._football.fetch_matches(football_data_code(league))
            except Exception as exc:  # noqa: BLE001 - one league must not break the rest
                logger.warning("Could not load %s fixtures: %s", league.value, exc)
                continue
            for m in league_matches:
                self._match_league[m.match_id] = league
            matches.extend(league_matches)
        self._matches_cache = matches
        logger.info("Loaded %d fixtures across %d leagues", len(matches), len(self._leagues))
        return matches

    # --- Odds (The Odds API), matched to fixtures by team names ---

    def _odds_for_league(self, league: League) -> dict[str, list[Odds]]:
        if league in self._odds_cache:
            return self._odds_cache[league]

        self._fetch_matches()  # ensure fixtures and league index are populated
        index: dict[tuple[str, str], str] = {}
        for m in self._matches_cache or []:
            if m.league is league:
                key = (normalize_team(m.home_team.name), normalize_team(m.away_team.name))
                index[key] = m.match_id

        mapped: dict[str, list[Odds]] = {}
        try:
            events = self._odds.fetch_events(odds_api_key(league), regions=self._regions)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load %s odds: %s", league.value, exc)
            events = []

        matched = 0
        for event in events:
            key = (normalize_team(event.get("home_team", "")), normalize_team(event.get("away_team", "")))
            fd_id = index.get(key)
            if fd_id is None:
                continue
            odds = [o.model_copy(update={"match_id": fd_id}) for o in self._odds.event_to_odds(event)]
            if odds:
                mapped[fd_id] = odds
                matched += 1

        logger.info("%s: matched odds for %d/%d events", league.value, matched, len(events))
        self._odds_cache[league] = mapped
        return mapped

    def _fetch_odds(self, match_id: str) -> Sequence[Odds]:
        league = self._match_league.get(match_id)
        if league is None:
            self._fetch_matches()
            league = self._match_league.get(match_id)
        if league is None:
            return ()
        return self._odds_for_league(league).get(match_id, ())


def build_live_provider(
    football_api_key: str,
    the_odds_api_key: str,
    leagues: Sequence[League],
    cache_dir: Path,
    ttl_seconds: float = 1800.0,
    min_interval: float = 1.0,
    regions: str = "eu,uk",
) -> LiveDataProvider:
    """Build a :class:`LiveDataProvider` from API keys and a cache directory."""

    cache_dir = Path(cache_dir)
    football = FootballDataProvider(
        football_api_key,
        cache_dir=cache_dir / "football_data",
        ttl_seconds=ttl_seconds,
        min_interval=min_interval,
    )
    odds = TheOddsAPIProvider(
        the_odds_api_key,
        cache_dir=cache_dir / "the_odds_api",
        ttl_seconds=ttl_seconds,
        min_interval=min_interval,
    )
    return LiveDataProvider(football, odds, leagues, regions=regions)
