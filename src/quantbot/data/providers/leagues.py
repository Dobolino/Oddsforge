"""Mapping between QuantBot leagues and the two external APIs.

``fd`` is the Football-Data.org competition code (empty for non-football),
``odds`` is The Odds API sport key. Basketball results can come from BallDontLie
when configured; Odds API still supplies moneyline/totals/spreads.
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
    League.NBA: {"fd": "", "odds": "basketball_nba"},
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
