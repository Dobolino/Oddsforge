"""Football-Data.org provider: results, fixtures, and standings via httpx.

Transforms competition matches into QuantBot :class:`Match` DTOs (with results
for finished games) and returns standings tables as plain rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from quantbot.data.providers.base_http import FileCache, RateLimiter
from quantbot.logging import get_logger
from quantbot.schemas import League, Match, MatchResult, MatchStatus, Team

logger = get_logger(__name__)

_BASE_URL = "https://api.football-data.org"
_PREDICTION_LEAD = timedelta(hours=2)

# Football-Data competition code -> QuantBot league.
_COMPETITION_TO_LEAGUE: dict[str, League] = {
    "PL": League.PREMIER_LEAGUE,
    "BL1": League.BUNDESLIGA,
    "PD": League.LA_LIGA,
    "SA": League.SERIE_A,
    "FL1": League.LIGUE_1,
    "CL": League.CHAMPIONS_LEAGUE,
}

# Football-Data status -> QuantBot status.
_STATUS_MAP: dict[str, MatchStatus] = {
    "FINISHED": MatchStatus.FINISHED,
    "IN_PLAY": MatchStatus.LIVE,
    "PAUSED": MatchStatus.LIVE,
    "POSTPONED": MatchStatus.POSTPONED,
    "CANCELLED": MatchStatus.CANCELLED,
    "SUSPENDED": MatchStatus.POSTPONED,
}


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _season_label(kickoff: datetime) -> str:
    """Derive a season string like '2024-2025' from a kickoff date."""

    start_year = kickoff.year if kickoff.month >= 7 else kickoff.year - 1
    return f"{start_year}-{start_year + 1}"


class FootballDataProvider:
    """Client for Football-Data.org (v4)."""

    def __init__(
        self,
        api_key: str,
        cache_dir: Path,
        client: httpx.Client | None = None,
        ttl_seconds: float = 3600.0,
        min_interval: float = 0.0,
        cache: FileCache | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.api_key = api_key
        self._client = client or httpx.Client(
            base_url=_BASE_URL, headers={"X-Auth-Token": api_key}, timeout=10.0
        )
        self._cache = cache or FileCache(Path(cache_dir), ttl_seconds=ttl_seconds)
        self._limiter = rate_limiter or RateLimiter(min_interval=min_interval)

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        params = params or {}
        key = f"{path}?{sorted(params.items())}"
        cached = self._cache.get(key)
        if cached is not None:
            logger.debug("Cache hit for %s", path)
            return cached

        self._limiter.acquire()
        logger.debug("Fetching %s from Football-Data", path)
        response = self._client.get(path, params=params, headers={"X-Auth-Token": self.api_key})
        response.raise_for_status()
        data = response.json()
        self._cache.set(key, data)
        return data

    # --- Matches / fixtures ---

    def fetch_matches(self, competition: str) -> list[Match]:
        """Return matches for a competition code (e.g. 'PL', 'BL1', 'CL')."""

        if competition not in _COMPETITION_TO_LEAGUE:
            raise ValueError(f"unsupported competition code: {competition!r}")
        league = _COMPETITION_TO_LEAGUE[competition]
        data = self._get(f"/v4/competitions/{competition}/matches")
        matches: list[Match] = []
        for raw in data.get("matches", []):
            match = self._to_match(raw, league)
            if match is not None:
                matches.append(match)
        return matches

    def _to_match(self, raw: dict[str, Any], league: League) -> Match | None:
        home = raw.get("homeTeam", {})
        away = raw.get("awayTeam", {})
        if home.get("id") is None or away.get("id") is None:
            return None  # placeholder fixture (e.g. unresolved knockout)

        kickoff = _parse_iso(raw["utcDate"])
        status = _STATUS_MAP.get(raw.get("status", ""), MatchStatus.SCHEDULED)

        result: MatchResult | None = None
        full_time = raw.get("score", {}).get("fullTime", {})
        if status is MatchStatus.FINISHED and full_time.get("home") is not None:
            result = MatchResult(
                home_goals=int(full_time["home"]),
                away_goals=int(full_time["away"]),
            )

        return Match(
            match_id=str(raw["id"]),
            league=league,
            season=_season_label(kickoff),
            kickoff=kickoff,
            prediction_timestamp=kickoff - _PREDICTION_LEAD,
            home_team=Team(team_id=str(home["id"]), name=home.get("name", str(home["id"]))),
            away_team=Team(team_id=str(away["id"]), name=away.get("name", str(away["id"]))),
            status=status,
            result=result,
        )

    # --- Standings ---

    def fetch_standings(self, competition: str) -> list[dict[str, Any]]:
        """Return the TOTAL standings table as position/team/points rows."""

        data = self._get(f"/v4/competitions/{competition}/standings")
        for table in data.get("standings", []):
            if table.get("type") == "TOTAL":
                return [
                    {
                        "position": row["position"],
                        "team": row["team"]["name"],
                        "played": row["playedGames"],
                        "points": row["points"],
                    }
                    for row in table.get("table", [])
                ]
        return []
