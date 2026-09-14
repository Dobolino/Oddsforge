"""The Odds API provider: live/historical odds via httpx.

Transforms h2h (1X2) markets into QuantBot :class:`Odds` snapshots (one per
bookmaker) and, via the Market Engine, into fair :class:`MarketData`. Uses a
file cache with TTL and a rate limiter to protect the API quota.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from quantbot.data.providers.base_http import FileCache, RateLimiter
from quantbot.logging import get_logger
from quantbot.markets.odds import MarketEngine
from quantbot.schemas import MarketData, Odds

logger = get_logger(__name__)

_BASE_URL = "https://api.the-odds-api.com"


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp (accepting a trailing Z) as aware UTC."""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class TheOddsAPIProvider:
    """Client for The Odds API (v4) h2h markets.

    Args:
        api_key: The Odds API key.
        cache_dir: Directory for the response cache.
        client: Injected httpx client (tests pass a MockTransport client).
        ttl_seconds: Cache time-to-live.
        min_interval: Minimum seconds between network calls.
        cache: Optional pre-built cache (overrides cache_dir/ttl).
        rate_limiter: Optional pre-built rate limiter (overrides min_interval).
    """

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
        self._client = client or httpx.Client(base_url=_BASE_URL, timeout=10.0)
        self._cache = cache or FileCache(Path(cache_dir), ttl_seconds=ttl_seconds)
        self._limiter = rate_limiter or RateLimiter(min_interval=min_interval)
        self._market_engine = MarketEngine()

    # --- Raw fetch with cache + rate limit ---

    def _get(self, path: str, params: dict[str, str]) -> Any:
        key = f"{path}?{sorted(params.items())}"
        cached = self._cache.get(key)
        if cached is not None:
            logger.debug("Cache hit for %s", path)
            return cached

        self._limiter.acquire()
        logger.debug("Fetching %s from The Odds API", path)
        response = self._client.get(path, params=params)
        response.raise_for_status()
        data = response.json()
        self._cache.set(key, data)
        return data

    def fetch_events(
        self, sport_key: str, regions: str = "eu", markets: str = "h2h"
    ) -> list[dict[str, Any]]:
        """Raw event list for a sport (odds included)."""

        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal",
        }
        return list(self._get(f"/v4/sports/{sport_key}/odds", params))

    # --- Transformation to DTOs ---

    def fetch_odds(
        self, sport_key: str, regions: str = "eu"
    ) -> dict[str, list[Odds]]:
        """Return per-match lists of bookmaker :class:`Odds` snapshots."""

        events = self.fetch_events(sport_key, regions=regions)
        out: dict[str, list[Odds]] = {}
        for event in events:
            out[event["id"]] = self.event_to_odds(event)
        return out

    def event_to_odds(self, event: dict[str, Any]) -> list[Odds]:
        match_id = event["id"]
        home_name = event["home_team"]
        away_name = event["away_team"]
        commence = event.get("commence_time")
        odds: list[Odds] = []

        for bookmaker in event.get("bookmakers", []):
            h2h = next(
                (m for m in bookmaker.get("markets", []) if m.get("key") == "h2h"), None
            )
            if h2h is None:
                continue
            prices: dict[str, float] = {}
            for outcome in h2h.get("outcomes", []):
                prices[outcome["name"]] = float(outcome["price"])
            if not {home_name, away_name, "Draw"} <= set(prices):
                continue  # incomplete 1X2 market
            ts = h2h.get("last_update") or bookmaker.get("last_update") or commence
            odds.append(
                Odds(
                    match_id=match_id,
                    bookmaker=bookmaker.get("key", bookmaker.get("title", "unknown")),
                    timestamp=_parse_iso(ts),
                    home=prices[home_name],
                    draw=prices["Draw"],
                    away=prices[away_name],
                )
            )
        return odds

    def fetch_market_data(self, sport_key: str, regions: str = "eu") -> list[MarketData]:
        """Consensus fair :class:`MarketData` per match with any 1X2 odds."""

        markets: list[MarketData] = []
        for _match_id, odds_list in self.fetch_odds(sport_key, regions=regions).items():
            if odds_list:
                markets.append(self._market_engine.consensus(odds_list))
        return markets
