"""Block C tests: The Odds API and Football-Data providers (mocked httpx),
cache/rate-limit behavior, DTO transformation, and the arbitrage engine."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from quantbot.data.providers import (
    FileCache,
    FootballDataProvider,
    RateLimiter,
    RateLimitError,
    TheOddsAPIProvider,
)
from quantbot.markets import ArbitrageEngine
from quantbot.schemas import MatchOutcome, MatchStatus, Odds

UTC = timezone.utc
TS = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)

ODDS_API_EVENTS = [
    {
        "id": "evt1",
        "sport_key": "soccer_epl",
        "commence_time": "2024-08-17T14:00:00Z",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "bookmakers": [
            {
                "key": "pinnacle",
                "title": "Pinnacle",
                "last_update": "2024-08-17T12:00:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2024-08-17T12:00:00Z",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.1},
                            {"name": "Chelsea", "price": 3.6},
                            {"name": "Draw", "price": 3.4},
                        ],
                    }
                ],
            },
            {
                "key": "bet365",
                "title": "Bet365",
                "last_update": "2024-08-17T12:05:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.2},
                            {"name": "Chelsea", "price": 3.5},
                            {"name": "Draw", "price": 3.3},
                        ],
                    }
                ],
            },
        ],
    }
]

FD_MATCHES = {
    "matches": [
        {
            "id": 1,
            "utcDate": "2024-08-17T14:00:00Z",
            "status": "FINISHED",
            "homeTeam": {"id": 57, "name": "Arsenal"},
            "awayTeam": {"id": 61, "name": "Chelsea"},
            "score": {"fullTime": {"home": 2, "away": 1}},
        },
        {
            "id": 2,
            "utcDate": "2024-08-24T14:00:00Z",
            "status": "TIMED",
            "homeTeam": {"id": 65, "name": "Man City"},
            "awayTeam": {"id": 66, "name": "Man Utd"},
            "score": {"fullTime": {"home": None, "away": None}},
        },
    ]
}

FD_STANDINGS = {
    "standings": [
        {
            "type": "TOTAL",
            "table": [
                {"position": 1, "team": {"name": "Arsenal"}, "playedGames": 3, "points": 9},
                {"position": 2, "team": {"name": "Chelsea"}, "playedGames": 3, "points": 6},
            ],
        }
    ]
}


def _odds_client(counter: list[int] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if counter is not None:
            counter[0] += 1
        return httpx.Response(200, json=ODDS_API_EVENTS)

    return httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.the-odds-api.com"
    )


# --- The Odds API: transformation ---


def test_odds_api_transforms_to_odds(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = TheOddsAPIProvider("key", cache_dir=tmp_path, client=_odds_client())
    odds_by_match = provider.fetch_odds("soccer_epl")
    assert set(odds_by_match) == {"evt1"}
    odds = odds_by_match["evt1"]
    assert len(odds) == 2
    pinnacle = next(o for o in odds if o.bookmaker == "pinnacle")
    assert pinnacle.home == pytest.approx(2.1)  # Arsenal is home
    assert pinnacle.away == pytest.approx(3.6)  # Chelsea is away
    assert pinnacle.draw == pytest.approx(3.4)
    assert pinnacle.timestamp == datetime(2024, 8, 17, 12, 0, tzinfo=UTC)


def test_odds_api_skips_decimal_odds_of_one() -> None:
    """Live feeds can return home=1.0; that must not raise ValidationError."""

    provider = TheOddsAPIProvider.__new__(TheOddsAPIProvider)
    event = {
        "id": "evt-suspended",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "commence_time": "2024-08-17T14:00:00Z",
        "bookmakers": [
            {
                "key": "suspended",
                "title": "Suspended",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Arsenal", "price": 1.0},
                            {"name": "Chelsea", "price": 3.5},
                            {"name": "Draw", "price": 3.3},
                        ],
                    }
                ],
            },
            {
                "key": "bet365",
                "title": "Bet365",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.2},
                            {"name": "Chelsea", "price": 3.5},
                            {"name": "Draw", "price": 3.3},
                        ],
                    }
                ],
            },
        ],
    }
    odds = provider.event_to_odds(event)
    assert len(odds) == 1
    assert odds[0].bookmaker == "bet365"
    assert odds[0].home == pytest.approx(2.2)


def test_odds_api_market_data_consensus(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = TheOddsAPIProvider("key", cache_dir=tmp_path, client=_odds_client())
    markets = provider.fetch_market_data("soccer_epl")
    assert len(markets) == 1
    total = markets[0].fair_home + markets[0].fair_draw + markets[0].fair_away
    assert abs(total - 1.0) < 1e-6


# --- The Odds API: cache & rate limiting ---


def test_odds_api_cache_hit_and_expiry(tmp_path) -> None:  # type: ignore[no-untyped-def]
    clock = [1000.0]
    cache = FileCache(tmp_path, ttl_seconds=100.0, time_fn=lambda: clock[0])
    counter = [0]
    provider = TheOddsAPIProvider(
        "key", cache_dir=tmp_path, client=_odds_client(counter), cache=cache
    )

    provider.fetch_events("soccer_epl")
    assert counter[0] == 1  # network call
    clock[0] = 1050.0
    provider.fetch_events("soccer_epl")
    assert counter[0] == 1  # served from cache
    clock[0] = 1101.0  # past ttl
    provider.fetch_events("soccer_epl")
    assert counter[0] == 2  # cache expired -> refetch


def test_odds_api_rate_limit(tmp_path) -> None:  # type: ignore[no-untyped-def]
    mono = [0.0]
    limiter = RateLimiter(min_interval=60.0, monotonic_fn=lambda: mono[0])
    provider = TheOddsAPIProvider(
        "key", cache_dir=tmp_path, client=_odds_client(), rate_limiter=limiter
    )
    provider.fetch_events("soccer_epl")  # first call allowed
    with pytest.raises(RateLimitError):
        provider.fetch_events("soccer_bundesliga")  # different key, too soon


# --- Football-Data: transformation ---


def _fd_client(payload: dict, captured: dict | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured["token"] = request.headers.get("X-Auth-Token")
        return httpx.Response(200, json=payload)

    return httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.football-data.org"
    )


def test_football_data_transforms_matches(tmp_path) -> None:  # type: ignore[no-untyped-def]
    captured: dict = {}
    provider = FootballDataProvider(
        "token", cache_dir=tmp_path, client=_fd_client(FD_MATCHES, captured)
    )
    matches = provider.fetch_matches("PL")
    assert len(matches) == 2
    finished = next(m for m in matches if m.match_id == "1")
    assert finished.status is MatchStatus.FINISHED
    assert finished.result is not None
    assert finished.result.outcome is MatchOutcome.HOME
    assert finished.season == "2024-2025"

    scheduled = next(m for m in matches if m.match_id == "2")
    assert scheduled.status is MatchStatus.SCHEDULED
    assert scheduled.result is None
    # Auth token header was sent.
    assert captured["token"] == "token"


def test_football_data_rejects_unknown_competition(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = FootballDataProvider("token", cache_dir=tmp_path, client=_fd_client(FD_MATCHES))
    with pytest.raises(ValueError, match="unsupported competition"):
        provider.fetch_matches("XYZ")


def test_football_data_standings(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = FootballDataProvider("token", cache_dir=tmp_path, client=_fd_client(FD_STANDINGS))
    table = provider.fetch_standings("PL")
    assert len(table) == 2
    assert table[0]["team"] == "Arsenal"
    assert table[0]["points"] == 9


def test_football_data_error_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "too many requests"})

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.football-data.org"
    )
    provider = FootballDataProvider("token", cache_dir=tmp_path, client=client)
    with pytest.raises(httpx.HTTPStatusError):
        provider.fetch_matches("PL")


# --- Arbitrage engine ---


def _odds(bookmaker: str, home: float, draw: float, away: float) -> Odds:
    return Odds(match_id="m1", bookmaker=bookmaker, timestamp=TS, home=home, draw=draw, away=away)


def test_line_shopping_picks_best_per_outcome() -> None:
    engine = ArbitrageEngine()
    books = [_odds("A", 2.1, 3.5, 4.0), _odds("B", 2.3, 4.1, 4.6)]
    best = engine.line_shopping(books)
    assert best[MatchOutcome.HOME] == (2.3, "B")
    assert best[MatchOutcome.DRAW] == (4.1, "B")
    assert best[MatchOutcome.AWAY] == (4.6, "B")


def test_arbitrage_detected_and_risk_free() -> None:
    engine = ArbitrageEngine()
    books = [_odds("A", 2.1, 3.5, 4.0), _odds("B", 2.3, 4.1, 4.6)]
    opp = engine.find_arbitrage(books, total_stake=100.0)
    assert opp.is_arbitrage
    assert opp.booksum < 1.0
    assert opp.profit_margin > 0.0
    assert opp.guaranteed_profit > 0.0
    # Stakes sum to the total and every outcome pays out equally (risk-free).
    assert sum(opp.stakes.values()) == pytest.approx(100.0)
    payouts = [opp.stakes[o] * opp.best_odds[o][0] for o in opp.stakes]
    assert max(payouts) == pytest.approx(min(payouts))


def test_no_arbitrage_when_market_has_margin() -> None:
    engine = ArbitrageEngine()
    books = [_odds("A", 2.0, 3.5, 3.8)]  # single book, positive overround
    opp = engine.find_arbitrage(books)
    assert not opp.is_arbitrage
    assert opp.booksum > 1.0
    assert opp.guaranteed_profit < 0.0


def test_allocate_stakes_requires_positive_total() -> None:
    engine = ArbitrageEngine()
    best = {
        MatchOutcome.HOME: (2.3, "B"),
        MatchOutcome.DRAW: (4.1, "B"),
        MatchOutcome.AWAY: (4.6, "B"),
    }
    with pytest.raises(ValueError, match="total_stake must be positive"):
        engine.allocate_stakes(best, 0.0)
