"""API-Football (api-sports.io) provider: Asian-handicap and totals odds.

The Odds API covers 1X2 and Over/Under. API-Football adds the Asian-handicap
market QuantBot needs for spread value. This client:

* authenticates with the ``x-apisports-key`` header (never logged),
* validates a key cheaply via ``/status`` (account + quota),
* fetches the ``/odds`` endpoint and turns the ``bookmakers -> bets -> values``
  envelope into QuantBot :class:`SpreadOdds` and :class:`TotalsOdds`.

The odds envelope shape (``response[].bookmakers[].bets[].values[]`` with a
``value`` label and a string ``odd``) is stable across the v3 API. The exact
label formatting for Asian handicap (e.g. ``"Home -0.5"``) can vary by
bookmaker, so parsing is tolerant and :meth:`summarize_markets` exists to show
the raw labels for verification before trusting the parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from quantbot.data.providers.base_http import (
    FileCache,
    RateLimiter,
    get_with_rate_limit_retry,
)
from quantbot.logging import get_logger
from quantbot.schemas import SpreadOdds, TotalsOdds

logger = get_logger(__name__)

_BASE_URL = "https://v3.football.api-sports.io"

# Bet catalogue names on API-Football (matched case-insensitively).
_BET_ASIAN_HANDICAP = "asian handicap"
_BET_GOALS_OU = "goals over/under"

# "Home -0.5", "Away +1.5", "Over 2.5", "Under 2.5" — a side word plus a signed
# number. Quarter lines like "-0.75" or "-0.5/-1.0" are intentionally not
# matched so only clean, push-free half-lines survive.
_VALUE_RE = re.compile(
    r"^\s*(home|away|over|under)\s*([+-]?\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)


class ApiFootballError(RuntimeError):
    """API-Football returned an error or an unusable response."""


@dataclass(frozen=True)
class AccountStatus:
    """Result of a ``/status`` probe: proof the key works, plus quota."""

    account: str
    plan: str
    requests_used: int
    requests_limit: int

    @property
    def requests_left(self) -> int:
        return max(self.requests_limit - self.requests_used, 0)


@dataclass
class BetSummary:
    """One bet market found on one bookmaker (for the test/verify view)."""

    bet_name: str
    sample_values: list[str] = field(default_factory=list)


@dataclass
class MarketSummary:
    """Plain-text view of the markets a fixture's odds actually contain."""

    fixture_id: int | None
    bookmakers: dict[str, list[BetSummary]] = field(default_factory=dict)

    @property
    def bet_names(self) -> list[str]:
        names: list[str] = []
        for bets in self.bookmakers.values():
            for bet in bets:
                if bet.bet_name not in names:
                    names.append(bet.bet_name)
        return names

    def has_market(self, name: str) -> bool:
        target = name.strip().lower()
        return any(n.lower() == target for n in self.bet_names)


def _parse_odd(raw: Any) -> float | None:
    """Decimal odds come back as strings; reject anything <= 1.0 or junk."""

    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if value <= 1.0:
        return None
    return value


class ApiFootballProvider:
    """Client for the API-Football v3 ``/odds`` and ``/status`` endpoints.

    Args:
        api_key: The user's ``x-apisports-key``. Never logged.
        cache_dir: Directory for the response cache.
        client: Injected httpx client (tests pass a MockTransport client).
        ttl_seconds: Cache time-to-live.
        min_interval: Minimum seconds between network calls (quota guard).
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
        self._client = client or httpx.Client(base_url=_BASE_URL, timeout=15.0)
        self._cache = cache or FileCache(Path(cache_dir), ttl_seconds=ttl_seconds)
        self._limiter = rate_limiter or RateLimiter(min_interval=min_interval)

    @property
    def _headers(self) -> dict[str, str]:
        return {"x-apisports-key": self.api_key}

    # --- Raw fetch with cache + rate limit ---

    def _get(self, path: str, params: dict[str, str], *, use_cache: bool = True) -> Any:
        key = f"{path}?{sorted(params.items())}"
        if use_cache:
            cached = self._cache.get(key)
            if cached is not None:
                logger.debug("Cache hit for %s", path)
                return cached

        self._limiter.acquire()
        logger.debug("Fetching %s from API-Football", path)
        response = get_with_rate_limit_retry(
            self._client, path, params=params, headers=self._headers
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Key travels in a header, not the URL, so the URL is safe to show.
            raise ApiFootballError(
                f"API-Football HTTP {exc.response.status_code} for {path}"
            ) from None

        payload = response.json()
        # API-Football reports auth/quota problems in a 200 body under "errors".
        errors = payload.get("errors") if isinstance(payload, dict) else None
        if errors:
            raise ApiFootballError(_format_errors(errors))
        if use_cache:
            self._cache.set(key, payload)
        return payload

    # --- Status probe (cheap key validation) ---

    def fetch_status(self) -> AccountStatus:
        """Validate the key and read remaining quota (does not use cache)."""

        payload = self._get("/status", {}, use_cache=False)
        response = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(response, dict):
            raise ApiFootballError("unexpected /status response shape")
        account = response.get("account") or {}
        subscription = response.get("subscription") or {}
        requests = response.get("requests") or {}
        name = " ".join(
            part
            for part in (account.get("firstname"), account.get("lastname"))
            if part
        ).strip()
        return AccountStatus(
            account=name or str(account.get("email", "") or "unbekannt"),
            plan=str(subscription.get("plan", "") or "unbekannt"),
            requests_used=int(requests.get("current", 0) or 0),
            requests_limit=int(requests.get("limit_day", 0) or 0),
        )

    # --- Odds fetch ---

    def fetch_odds(
        self,
        *,
        fixture: int | None = None,
        league: int | None = None,
        season: int | None = None,
        date: str | None = None,
        bookmaker: int | None = None,
    ) -> dict[str, Any]:
        """Raw ``/odds`` payload. Supply a fixture, or league+season, or date."""

        params: dict[str, str] = {}
        if fixture is not None:
            params["fixture"] = str(fixture)
        if league is not None:
            params["league"] = str(league)
        if season is not None:
            params["season"] = str(season)
        if date is not None:
            params["date"] = date
        if bookmaker is not None:
            params["bookmaker"] = str(bookmaker)
        if not params:
            raise ValueError("fetch_odds needs at least one of fixture/league/date")
        payload = self._get("/odds", params)
        if not isinstance(payload, dict):
            raise ApiFootballError("unexpected /odds response shape")
        return payload

    # --- Verification helper (drives the dashboard test button) ---

    def summarize_markets(
        self, payload: dict[str, Any], *, max_values: int = 8
    ) -> list[MarketSummary]:
        """Turn a raw ``/odds`` payload into a readable market listing.

        Used before trusting the parser: it shows the exact ``value`` labels
        each bookmaker returns, so a human can confirm ``"Home -0.5"``-style
        formatting matches what :meth:`parse_asian_handicap` expects.
        """

        summaries: list[MarketSummary] = []
        for entry in payload.get("response", []) or []:
            if not isinstance(entry, dict):
                continue
            fixture_id = _fixture_id(entry)
            summary = MarketSummary(fixture_id=fixture_id)
            for book in entry.get("bookmakers", []) or []:
                book_name = str(book.get("name", "") or f"id={book.get('id')}")
                bets: list[BetSummary] = []
                for bet in book.get("bets", []) or []:
                    values = [
                        f"{v.get('value')} @ {v.get('odd')}"
                        for v in (bet.get("values", []) or [])
                        if isinstance(v, dict)
                    ][:max_values]
                    bets.append(
                        BetSummary(bet_name=str(bet.get("name", "") or "?"), sample_values=values)
                    )
                summary.bookmakers[book_name] = bets
            summaries.append(summary)
        return summaries

    # --- Parsers ---

    def parse_asian_handicap(
        self, payload: dict[str, Any], match_id: str
    ) -> list[SpreadOdds]:
        """Extract half-line Asian-handicap quotes as :class:`SpreadOdds`.

        For each bookmaker, pairs a ``Home h`` price with the matching
        ``Away -h`` price to form one spread quote whose ``line`` is the home
        handicap. Only clean half-lines (no push) are kept.
        """

        out: list[SpreadOdds] = []
        for entry in payload.get("response", []) or []:
            if not isinstance(entry, dict):
                continue
            ts = _entry_timestamp(entry)
            for book in entry.get("bookmakers", []) or []:
                name = str(book.get("name", "") or f"id={book.get('id')}")
                bet = _find_bet(book, _BET_ASIAN_HANDICAP)
                if bet is None:
                    continue
                home_prices, away_prices = _split_sides(bet.get("values", []) or [])
                for line, home_odd in home_prices.items():
                    away_odd = away_prices.get(-line)
                    if away_odd is None:
                        continue
                    out.append(
                        SpreadOdds(
                            match_id=match_id,
                            bookmaker=name,
                            timestamp=ts,
                            line=line,
                            home=home_odd,
                            away=away_odd,
                        )
                    )
        return out

    def parse_totals(
        self, payload: dict[str, Any], match_id: str, *, line: float = 2.5
    ) -> list[TotalsOdds]:
        """Extract Over/Under quotes for one line as :class:`TotalsOdds`."""

        out: list[TotalsOdds] = []
        for entry in payload.get("response", []) or []:
            if not isinstance(entry, dict):
                continue
            ts = _entry_timestamp(entry)
            for book in entry.get("bookmakers", []) or []:
                name = str(book.get("name", "") or f"id={book.get('id')}")
                bet = _find_bet(book, _BET_GOALS_OU)
                if bet is None:
                    continue
                over = under = None
                for value in bet.get("values", []) or []:
                    if not isinstance(value, dict):
                        continue
                    parsed = _VALUE_RE.match(str(value.get("value", "")))
                    if parsed is None:
                        continue
                    side, num = parsed.group(1).lower(), float(parsed.group(2))
                    if abs(num - line) > 1e-9:
                        continue
                    odd = _parse_odd(value.get("odd"))
                    if odd is None:
                        continue
                    if side == "over":
                        over = odd
                    elif side == "under":
                        under = odd
                if over is not None and under is not None:
                    out.append(
                        TotalsOdds(
                            match_id=match_id,
                            bookmaker=name,
                            timestamp=ts,
                            line=line,
                            over=over,
                            under=under,
                        )
                    )
        return out


def _format_errors(errors: Any) -> str:
    if isinstance(errors, dict):
        return "; ".join(f"{k}: {v}" for k, v in errors.items()) or "unknown API error"
    if isinstance(errors, list):
        return "; ".join(str(item) for item in errors) or "unknown API error"
    return str(errors)


def _fixture_id(entry: dict[str, Any]) -> int | None:
    fixture = entry.get("fixture")
    if isinstance(fixture, dict) and fixture.get("id") is not None:
        try:
            return int(fixture["id"])
        except (TypeError, ValueError):
            return None
    return None


def _entry_timestamp(entry: dict[str, Any]) -> datetime:
    """Best-effort update time; falls back to now (UTC, aware)."""

    raw = entry.get("update")
    if isinstance(raw, str) and raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
    return datetime.now(timezone.utc)


def _find_bet(book: dict[str, Any], name: str) -> dict[str, Any] | None:
    target = name.strip().lower()
    for bet in book.get("bets", []) or []:
        if isinstance(bet, dict) and str(bet.get("name", "")).strip().lower() == target:
            return bet
    return None


def _split_sides(values: list[Any]) -> tuple[dict[float, float], dict[float, float]]:
    """Return ``(home_by_line, away_by_line)`` for clean half-line quotes only."""

    home: dict[float, float] = {}
    away: dict[float, float] = {}
    for value in values:
        if not isinstance(value, dict):
            continue
        parsed = _VALUE_RE.match(str(value.get("value", "")))
        if parsed is None:
            continue
        side = parsed.group(1).lower()
        line = float(parsed.group(2))
        # Half-line only: a bet that can never push.
        if abs(line * 2 - round(line * 2)) > 1e-9 or round(line * 2) % 2 == 0:
            continue
        odd = _parse_odd(value.get("odd"))
        if odd is None:
            continue
        if side == "home":
            home[line] = odd
        elif side == "away":
            away[line] = odd
    return home, away
