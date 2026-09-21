"""The Odds API provider: live/historical odds via httpx.

Transforms h2h (1X2) markets into QuantBot :class:`Odds` snapshots (one per
bookmaker) and, via the Market Engine, into fair :class:`MarketData`. Uses a
file cache with TTL and a rate limiter to protect the API quota.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from quantbot.data.providers.base_http import FileCache, RateLimiter, get_with_rate_limit_retry, redact_secrets
from quantbot.logging import get_logger
from quantbot.markets.odds import MarketEngine
from quantbot.schemas import League, Match, MatchResult, MatchStatus, Odds, Team, MarketData, TotalsOdds

logger = get_logger(__name__)

_BASE_URL = "https://api.the-odds-api.com"
_PREDICTION_LEAD = timedelta(hours=2)


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp (accepting a trailing Z) as aware UTC."""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _slug(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned[:64] or "team"


def _valid_decimal_odds(*prices: float) -> bool:
    """Decimal odds must be strictly greater than 1.0 (schema + EV math)."""

    return all(price > 1.0 for price in prices)


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
        ttl_seconds: float = 7200.0,
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
        response = get_with_rate_limit_retry(self._client, path, params=params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Never leak apiKey=... into logs / Streamlit exception panels.
            raise httpx.HTTPStatusError(
                f"The Odds API error {exc.response.status_code} for {redact_secrets(str(exc.request.url))}",
                request=exc.request,
                response=exc.response,
            ) from None
        data = response.json()
        self._cache.set(key, data)
        return data

    def fetch_events(
        self, sport_key: str, regions: str = "eu", markets: str = "h2h,totals"
    ) -> list[dict[str, Any]]:
        """Raw event list for a sport (odds included)."""

        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal",
        }
        return list(self._get(f"/v4/sports/{sport_key}/odds", params))

    def fetch_scores(self, sport_key: str, *, days_from: int = 3) -> list[dict[str, Any]]:
        """Recent/live scores (completed games limited by ``days_from``, max 3)."""

        days = max(1, min(3, int(days_from)))
        params = {
            "apiKey": self.api_key,
            "daysFrom": str(days),
        }
        return list(self._get(f"/v4/sports/{sport_key}/scores", params))

    def events_to_matches(
        self,
        events: list[dict[str, Any]],
        *,
        league: League,
        finished_only: bool = False,
    ) -> list[Match]:
        """Turn Odds API events/scores into QuantBot :class:`Match` rows."""

        out: list[Match] = []
        for event in events:
            match = self.event_to_match(event, league=league)
            if match is None:
                continue
            if finished_only and match.status is not MatchStatus.FINISHED:
                continue
            out.append(match)
        return out

    def event_to_match(self, event: dict[str, Any], *, league: League) -> Match | None:
        """Map one Odds API event or score payload to a :class:`Match`."""

        event_id = str(event.get("id") or "").strip()
        home_name = str(event.get("home_team") or "").strip()
        away_name = str(event.get("away_team") or "").strip()
        commence = event.get("commence_time")
        if not event_id or not home_name or not away_name or not commence:
            return None
        kickoff = _parse_iso(str(commence))
        completed = bool(event.get("completed"))
        scores = event.get("scores")
        result: MatchResult | None = None
        status = MatchStatus.SCHEDULED
        observed_at: datetime | None = None
        if completed and isinstance(scores, list) and len(scores) >= 2:
            by_name = {
                str(row.get("name", "")).strip(): row.get("score") for row in scores if isinstance(row, dict)
            }
            home_raw = by_name.get(home_name)
            away_raw = by_name.get(away_name)
            try:
                if home_raw is not None and away_raw is not None:
                    result = MatchResult(home_goals=int(home_raw), away_goals=int(away_raw))
                    status = MatchStatus.FINISHED
                    # Publication time must be after kickoff (schema guardrail).
                    observed_at = max(kickoff + timedelta(hours=2), datetime.now(timezone.utc))
            except (TypeError, ValueError):
                result = None
                observed_at = None
                status = MatchStatus.SCHEDULED
        season_start = kickoff.year if kickoff.month >= 7 else kickoff.year - 1
        season = f"{season_start}-{season_start + 1}"
        return Match(
            match_id=event_id,
            league=league,
            season=season,
            kickoff=kickoff,
            prediction_timestamp=kickoff - _PREDICTION_LEAD,
            home_team=Team(team_id=f"odds:{_slug(home_name)}", name=home_name),
            away_team=Team(team_id=f"odds:{_slug(away_name)}", name=away_name),
            status=status,
            result=result,
            result_available_at=observed_at,
            status_available_at=observed_at if status is MatchStatus.FINISHED else None,
        )

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
            home_p = prices[home_name]
            draw_p = prices["Draw"]
            away_p = prices[away_name]
            # Live feeds occasionally return 1.0 / <=1 (suspended or junk lines).
            # Skip that bookmaker instead of crashing dashboard validation.
            if not _valid_decimal_odds(home_p, draw_p, away_p):
                logger.warning(
                    "Skipping invalid 1X2 odds for %s @ %s (home=%.3f draw=%.3f away=%.3f)",
                    match_id,
                    bookmaker.get("key", bookmaker.get("title", "unknown")),
                    home_p,
                    draw_p,
                    away_p,
                )
                continue
            ts = h2h.get("last_update") or bookmaker.get("last_update") or commence
            odds.append(
                Odds(
                    match_id=match_id,
                    bookmaker=bookmaker.get("key", bookmaker.get("title", "unknown")),
                    timestamp=_parse_iso(ts),
                    home=home_p,
                    draw=draw_p,
                    away=away_p,
                )
            )
        return odds

    def event_to_totals(
        self, event: dict[str, Any], *, line: float = 2.5
    ) -> list[TotalsOdds]:
        """Parse totals (Over/Under) quotes for a preferred line."""

        from quantbot.schemas import TotalsOdds

        match_id = event["id"]
        commence = event.get("commence_time")
        out: list[TotalsOdds] = []

        for bookmaker in event.get("bookmakers", []):
            totals_markets = [
                m for m in bookmaker.get("markets", []) if m.get("key") == "totals"
            ]
            for market in totals_markets:
                over_price: float | None = None
                under_price: float | None = None
                market_line: float | None = None
                for outcome in market.get("outcomes", []):
                    name = str(outcome.get("name", "")).lower()
                    point = outcome.get("point")
                    if point is None:
                        continue
                    point_f = float(point)
                    if abs(point_f - line) > 1e-9:
                        continue
                    market_line = point_f
                    price = float(outcome["price"])
                    if name.startswith("over"):
                        over_price = price
                    elif name.startswith("under"):
                        under_price = price
                if over_price is None or under_price is None or market_line is None:
                    continue
                if not _valid_decimal_odds(over_price, under_price):
                    logger.warning(
                        "Skipping invalid totals odds for %s @ %s (over=%.3f under=%.3f line=%.1f)",
                        match_id,
                        bookmaker.get("key", bookmaker.get("title", "unknown")),
                        over_price,
                        under_price,
                        market_line,
                    )
                    continue
                ts = market.get("last_update") or bookmaker.get("last_update") or commence
                out.append(
                    TotalsOdds(
                        match_id=match_id,
                        bookmaker=bookmaker.get("key", bookmaker.get("title", "unknown")),
                        timestamp=_parse_iso(ts),
                        line=market_line,
                        over=over_price,
                        under=under_price,
                    )
                )
        return out

    def fetch_market_data(self, sport_key: str, regions: str = "eu") -> list[MarketData]:
        """Consensus fair :class:`MarketData` per match with any 1X2 odds."""

        markets: list[MarketData] = []
        for _match_id, odds_list in self.fetch_odds(sport_key, regions=regions).items():
            if odds_list:
                markets.append(self._market_engine.consensus(odds_list))
        return markets
