"""Mapping between QuantBot leagues and the two external APIs.

``fd`` is the Football-Data.org competition code, ``odds`` is The Odds API
sport key. Extend this table to support more competitions (e.g. add the Swiss
Super League with fd code ``None`` and odds key
``soccer_switzerland_superleague`` once a results source is available).
"""

from __future__ import annotations

from quantbot.schemas import League

LEAGUE_CODES: dict[League, dict[str, str]] = {
    League.PREMIER_LEAGUE: {"fd": "PL", "odds": "soccer_epl"},
    League.BUNDESLIGA: {"fd": "BL1", "odds": "soccer_germany_bundesliga"},
    League.LA_LIGA: {"fd": "PD", "odds": "soccer_spain_la_liga"},
    League.SERIE_A: {"fd": "SA", "odds": "soccer_italy_serie_a"},
    League.LIGUE_1: {"fd": "FL1", "odds": "soccer_france_ligue_one"},
    League.CHAMPIONS_LEAGUE: {"fd": "CL", "odds": "soccer_uefa_champs_league"},
}


def football_data_code(league: League) -> str:
    return LEAGUE_CODES[league]["fd"]


def odds_api_key(league: League) -> str:
    return LEAGUE_CODES[league]["odds"]
