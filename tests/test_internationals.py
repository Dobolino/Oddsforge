"""Nations League / qualifier mappings and Odds-API fixture conversion."""

from __future__ import annotations

from quantbot.data.providers.leagues import (
    LEAGUE_CODES,
    football_data_code,
    has_football_data,
    odds_api_key,
)
from quantbot.data.providers.the_odds_api import TheOddsAPIProvider
from quantbot.schemas import League, MatchStatus
from quantbot.schemas.enums import Sport, sport_for_league


def test_international_league_mappings() -> None:
    assert odds_api_key(League.NATIONS_LEAGUE) == "soccer_uefa_nations_league"
    assert odds_api_key(League.WORLD_CUP_QUALIFIERS_EUROPE) == (
        "soccer_fifa_world_cup_qualifiers_europe"
    )
    assert odds_api_key(League.EURO_QUALIFICATION) == "soccer_uefa_euro_qualification"
    assert has_football_data(League.WORLD_CUP_QUALIFIERS_EUROPE)
    assert football_data_code(League.WORLD_CUP_QUALIFIERS_EUROPE) == "QUFA"
    assert not has_football_data(League.NATIONS_LEAGUE)
    assert not has_football_data(League.EURO_QUALIFICATION)
    assert LEAGUE_CODES[League.NATIONS_LEAGUE]["fd"] == ""
    for league in (
        League.NATIONS_LEAGUE,
        League.WORLD_CUP_QUALIFIERS_EUROPE,
        League.EURO_QUALIFICATION,
    ):
        assert sport_for_league(league) is Sport.FOOTBALL


def test_odds_event_to_match_upcoming_and_finished(tmp_path) -> None:  # type: ignore[no-untyped-def]
    provider = TheOddsAPIProvider(api_key="test", cache_dir=tmp_path / "odds")
    kickoff = "2026-10-10T18:45:00Z"
    upcoming = provider.event_to_match(
        {
            "id": "evt-1",
            "home_team": "Germany",
            "away_team": "Italy",
            "commence_time": kickoff,
            "completed": False,
        },
        league=League.NATIONS_LEAGUE,
    )
    assert upcoming is not None
    assert upcoming.match_id == "evt-1"
    assert upcoming.league is League.NATIONS_LEAGUE
    assert upcoming.status is MatchStatus.SCHEDULED
    assert upcoming.result is None
    assert upcoming.home_team.name == "Germany"

    finished = provider.event_to_match(
        {
            "id": "evt-2",
            "home_team": "Spain",
            "away_team": "France",
            "commence_time": kickoff,
            "completed": True,
            "scores": [
                {"name": "Spain", "score": "2"},
                {"name": "France", "score": "1"},
            ],
        },
        league=League.EURO_QUALIFICATION,
    )
    assert finished is not None
    assert finished.status is MatchStatus.FINISHED
    assert finished.result is not None
    assert finished.result.home_goals == 2
    assert finished.result.away_goals == 1
    assert finished.result_available_at is not None
    assert finished.result_available_at.tzinfo is not None


def test_league_ui_labels_include_internationals() -> None:
    from quantbot.dashboard.leagues import format_league_choice, league_title

    assert "Nations" in format_league_choice("nations_league", "de")
    assert "WM-Quali" in format_league_choice("world_cup_qualifiers_europe", "de")
    assert "EM-Quali" in format_league_choice("euro_qualification", "de")
    assert "Nations" in league_title(League.NATIONS_LEAGUE)
