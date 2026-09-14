"""Block D tests: extra leagues, team-name normalization, and the live
data provider composed from mocked Football-Data and The Odds API clients."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from quantbot.data.providers import (
    FootballDataProvider,
    LiveDataProvider,
    TheOddsAPIProvider,
    football_data_code,
    normalize_team,
    odds_api_key,
)
from quantbot.schemas import League, MatchStatus

UTC = timezone.utc
FAR_FUTURE = datetime(2030, 1, 1, tzinfo=UTC)

FD_MATCHES = {
    "matches": [
        {
            "id": 100,
            "utcDate": "2025-02-01T15:00:00Z",
            "status": "TIMED",
            "homeTeam": {"id": 57, "name": "Arsenal FC"},
            "awayTeam": {"id": 61, "name": "Chelsea FC"},
            "score": {"fullTime": {"home": None, "away": None}},
        },
        {
            "id": 101,
            "utcDate": "2024-09-01T15:00:00Z",
            "status": "FINISHED",
            "homeTeam": {"id": 57, "name": "Arsenal FC"},
            "awayTeam": {"id": 64, "name": "Liverpool FC"},
            "score": {"fullTime": {"home": 2, "away": 1}},
        },
    ]
}

ODDS_EVENTS = [
    {
        "id": "odds-evt-1",
        "sport_key": "soccer_epl",
        "commence_time": "2025-02-01T15:00:00Z",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "bookmakers": [
            {
                "key": "pinnacle",
                "title": "Pinnacle",
                "last_update": "2025-01-31T12:00:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2025-01-31T12:00:00Z",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.0},
                            {"name": "Chelsea", "price": 3.8},
                            {"name": "Draw", "price": 3.5},
                        ],
                    }
                ],
            }
        ],
    },
    {
        "id": "odds-evt-2",
        "sport_key": "soccer_epl",
        "commence_time": "2025-02-02T15:00:00Z",
        "home_team": "Unknown United",
        "away_team": "Nowhere City",
        "bookmakers": [
            {
                "key": "pinnacle",
                "last_update": "2025-01-31T12:00:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Unknown United", "price": 2.0},
                            {"name": "Nowhere City", "price": 3.8},
                            {"name": "Draw", "price": 3.5},
                        ],
                    }
                ],
            }
        ],
    },
]


def _live(tmp_path) -> LiveDataProvider:  # type: ignore[no-untyped-def]
    fd_client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=FD_MATCHES)),
        base_url="https://api.football-data.org",
    )
    odds_client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=ODDS_EVENTS)),
        base_url="https://api.the-odds-api.com",
    )
    football = FootballDataProvider("fd", cache_dir=tmp_path / "fd", client=fd_client)
    odds = TheOddsAPIProvider("odds", cache_dir=tmp_path / "odds", client=odds_client)
    return LiveDataProvider(football, odds, [League.PREMIER_LEAGUE])


# --- Leagues ---


def test_new_leagues_exist() -> None:
    assert League.LA_LIGA.value == "la_liga"
    assert League.SERIE_A.value == "serie_a"
    assert League.LIGUE_1.value == "ligue_1"


def test_league_codes_present() -> None:
    assert football_data_code(League.SERIE_A) == "SA"
    assert odds_api_key(League.LA_LIGA) == "soccer_spain_la_liga"


# --- Normalization ---


def test_normalize_drops_suffixes() -> None:
    assert normalize_team("Arsenal FC") == "arsenal"
    assert normalize_team("Chelsea FC") == normalize_team("Chelsea")


def test_normalize_accents_and_alias() -> None:
    assert normalize_team("Borussia Mönchengladbach") == "monchengladbach"
    assert normalize_team("Wolverhampton Wanderers") == "wolves"


def test_normalize_bundesliga_cross_api_names() -> None:
    """Football-Data German names must map onto The Odds API English names."""

    assert normalize_team("1. FC Köln") == normalize_team("Cologne")
    assert normalize_team("FC Bayern München") == normalize_team("Bayern Munich")
    assert normalize_team("1. FSV Mainz 05") == normalize_team("Mainz")
    assert normalize_team("RasenBallsport Leipzig") == normalize_team("RB Leipzig")
    assert normalize_team("TSG 1899 Hoffenheim") == normalize_team("Hoffenheim")
    assert normalize_team("Borussia Mönchengladbach") == normalize_team("M'gladbach")


# --- Live provider ---


def test_live_provider_name(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert "live" in _live(tmp_path).provider_name


def test_live_fetches_matches_across_league(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = _live(tmp_path)
    matches = provider.get_matches(League.PREMIER_LEAGUE, "2024-2025", FAR_FUTURE)
    assert {m.match_id for m in matches} == {"100", "101"}
    finished = provider.get_match("101", FAR_FUTURE)
    assert finished is not None and finished.status is MatchStatus.FINISHED
    assert finished.result is not None


def test_live_matches_odds_to_fixture(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = _live(tmp_path)
    as_of = datetime(2025, 2, 1, 14, 0, tzinfo=UTC)
    odds = provider.get_latest_odds("100", as_of)
    assert odds is not None
    # Odds are re-keyed to the Football-Data fixture id, not the odds event id.
    assert odds.match_id == "100"
    assert odds.home == pytest.approx(2.0)   # Arsenal (home)
    assert odds.away == pytest.approx(3.8)   # Chelsea (away)
    assert odds.timestamp <= as_of


def test_live_unmatched_event_has_no_odds(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = _live(tmp_path)
    # Fixture 101 (Arsenal vs Liverpool) has no matching odds event.
    assert provider.get_odds("101", FAR_FUTURE) == []


def test_live_name_match_report_flags_unmatched(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = _live(tmp_path)
    report = provider.name_match_report(League.PREMIER_LEAGUE)
    assert report is not None
    assert report.matched_exact == 1
    assert report.unmatched_odds == 1
    assert report.has_warnings
    assert any(i.kind == "unmatched_odds" for i in report.issues)


def test_live_fuzzy_match_is_flagged(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Near-identical names that only match after fuzzy scoring.
    fd = {
        "matches": [
            {
                "id": 200,
                "utcDate": "2025-02-01T15:00:00Z",
                "status": "TIMED",
                "homeTeam": {"id": 1, "name": "Manchester United FC"},
                "awayTeam": {"id": 2, "name": "Newcastle United FC"},
                "score": {"fullTime": {"home": None, "away": None}},
            }
        ]
    }
    odds = [
        {
            "id": "odds-fuzzy",
            "sport_key": "soccer_epl",
            "commence_time": "2025-02-01T15:00:00Z",
            "home_team": "Manchester Utd",
            "away_team": "Newcastle Utd",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "title": "Pinnacle",
                    "last_update": "2025-01-31T12:00:00Z",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Manchester Utd", "price": 2.1},
                                {"name": "Newcastle Utd", "price": 3.4},
                                {"name": "Draw", "price": 3.3},
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    fd_client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=fd)),
        base_url="https://api.football-data.org",
    )
    odds_client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=odds)),
        base_url="https://api.the-odds-api.com",
    )
    football = FootballDataProvider("fd", cache_dir=tmp_path / "fd2", client=fd_client)
    odds_api = TheOddsAPIProvider("odds", cache_dir=tmp_path / "odds2", client=odds_client)
    provider = LiveDataProvider(football, odds_api, [League.PREMIER_LEAGUE])
    as_of = datetime(2025, 2, 1, 14, 0, tzinfo=UTC)
    linked = provider.get_latest_odds("200", as_of)
    assert linked is not None
    report = provider.name_match_report(League.PREMIER_LEAGUE)
    assert report is not None
    assert report.matched_fuzzy == 1
    assert report.has_warnings
    assert any(i.kind == "fuzzy" and i.match_id == "200" for i in report.issues)


def test_live_requires_at_least_one_league(tmp_path) -> None:  # type: ignore[no-untyped-def]
    fd = FootballDataProvider("fd", cache_dir=tmp_path / "fd")
    odds = TheOddsAPIProvider("odds", cache_dir=tmp_path / "odds")
    with pytest.raises(ValueError, match="at least one league"):
        LiveDataProvider(fd, odds, [])
