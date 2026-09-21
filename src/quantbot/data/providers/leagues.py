"""Mapping between QuantBot leagues and the two external APIs.

``fd`` is the Football-Data.org competition code (empty for non-football or
odds-only internationals), ``odds`` is The Odds API sport key. Basketball
results can come from BallDontLie when configured; Odds API still supplies
moneyline/totals/spreads.
"""

from __future__ import annotations

from quantbot.schemas import League
from quantbot.schemas.enums import Sport, sport_for_league

LEAGUE_CODES: dict[League, dict[str, str]] = {
    League.PREMIER_LEAGUE: {"fd": "PL", "odds": "soccer_epl"},
    League.BUNDESLIGA: {"fd": "BL1", "odds": "soccer_germany_bundesliga"},
    League.LA_LIGA: {"fd": "PD", "odds": "soccer_spain_la_liga"},
    League.SERIE_A: {"fd": "SA", "odds": "soccer_italy_serie_a"},
    League.LIGUE_1: {"fd": "FL1", "odds": "soccer_france_ligue_one"},
    League.CHAMPIONS_LEAGUE: {"fd": "CL", "odds": "soccer_uefa_champs_league"},
    # Nations League / Euro Quali: no Free Football-Data code — fixtures from Odds API.
    League.NATIONS_LEAGUE: {"fd": "", "odds": "soccer_uefa_nations_league"},
    # WC Quali UEFA: Football-Data ``QUFA`` (often paid); Odds API always available.
    League.WORLD_CUP_QUALIFIERS_EUROPE: {
        "fd": "QUFA",
        "odds": "soccer_fifa_world_cup_qualifiers_europe",
    },
    League.EURO_QUALIFICATION: {"fd": "", "odds": "soccer_uefa_euro_qualification"},
    League.NBA: {"fd": "", "odds": "basketball_nba"},
}

# Local finished-archive competition keys for odds-sourced internationals.
ODDS_ARCHIVE_CODES: dict[League, str] = {
    League.NATIONS_LEAGUE: "UNL",
    League.EURO_QUALIFICATION: "ECQ",
    League.WORLD_CUP_QUALIFIERS_EUROPE: "QUFA",
}


def football_data_code(league: League) -> str:
    code = LEAGUE_CODES[league]["fd"]
    if not code:
        raise ValueError(f"{league.value} has no Football-Data competition code")
    return code


def odds_api_key(league: League) -> str:
    return LEAGUE_CODES[league]["odds"]


def has_football_data(league: League) -> bool:
    return bool(LEAGUE_CODES.get(league, {}).get("fd"))


def football_leagues() -> tuple[League, ...]:
    return tuple(lg for lg in League if sport_for_league(lg) is Sport.FOOTBALL)


def basketball_leagues() -> tuple[League, ...]:
    return tuple(lg for lg in League if sport_for_league(lg) is Sport.BASKETBALL)
