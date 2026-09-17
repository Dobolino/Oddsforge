"""Football-Data.org provider: results, fixtures, and standings via httpx.

Transforms competition matches into QuantBot :class:`Match` DTOs (with results
for finished games) and returns standings tables as plain rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from quantbot.data.providers.base_http import (
    FileCache,
    RateLimiter,
    get_with_rate_limit_retry,
    redact_secrets,
)
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
        parsed = parsed.replace(tzinfo=UTC)
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
        response = get_with_rate_limit_retry(
            self._client, path, params=params, headers={"X-Auth-Token": self.api_key}
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise httpx.HTTPStatusError(
                f"Football-Data error {exc.response.status_code} for {redact_secrets(str(exc.request.url))}",
                request=exc.request,
                response=exc.response,
            ) from None
        data = response.json()
        self._cache.set(key, data)
        return data

    # --- Matches / fixtures ---

    def fetch_matches(
        self,
        competition: str,
        *,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        season: int | None = None,
    ) -> list[Match]:
        """Return matches for a competition code (e.g. 'PL', 'BL1', 'CL').

        Optional filters are forwarded to the upstream API so callers can skip
        finished fixtures once results are archived locally. ``season`` is the
        Football-Data start year (e.g. 2025 for 2025-2026).
        """

        if competition not in _COMPETITION_TO_LEAGUE:
            raise ValueError(f"unsupported competition code: {competition!r}")
        league = _COMPETITION_TO_LEAGUE[competition]
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        if season is not None:
            params["season"] = str(season)
        data = self._get(f"/v4/competitions/{competition}/matches", params=params or None)
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

        # This is the provider's last publication time, not an inferred
        # match duration. If absent, use the fetch time and fail closed for
        # historical as-of requests.
        updated_raw = raw.get("lastUpdated")
        observed_at = _parse_iso(updated_raw) if updated_raw else datetime.now(UTC)
        if observed_at <= kickoff:
            observed_at = datetime.now(UTC)

        return Match(
            match_id=str(raw["id"]),
            league=league,
            season=_season_label(kickoff),
            kickoff=kickoff,
            prediction_timestamp=kickoff - _PREDICTION_LEAD,
            home_team=Team(
                team_id=str(home["id"]),
                name=home.get("name", str(home["id"])),
                short_name=home.get("shortName") or home.get("tla"),
            ),
            away_team=Team(
                team_id=str(away["id"]),
                name=away.get("name", str(away["id"])),
                short_name=away.get("shortName") or away.get("tla"),
            ),
            status=status,
            result=result,
            result_available_at=observed_at if result is not None else None,
            status_available_at=observed_at if status in (MatchStatus.POSTPONED, MatchStatus.CANCELLED) else None,
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
