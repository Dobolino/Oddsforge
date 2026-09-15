"""League selection helpers for the dashboard (including „Alle“ + sport filter)."""

from __future__ import annotations

from quantbot.i18n import t
from quantbot.schemas import League
from quantbot.schemas.enums import Sport, leagues_for_sport

# Sentinel value in the sidebar selectbox for every supported league.
ALL_LEAGUES = "all"
ALL_SPORTS = "all"


def sport_choices() -> list[str]:
    """Sport filter options: All / Football / Basketball."""

    return [ALL_SPORTS, Sport.FOOTBALL.value, Sport.BASKETBALL.value]


def resolve_sport(choice: str) -> Sport | None:
    """``None`` means all sports."""

    if choice == ALL_SPORTS:
        return None
    return Sport(choice)


def format_sport_choice(choice: str, lang: str = "de") -> str:
    if choice == ALL_SPORTS:
        return t("ctrl.sport_all", lang)
    if choice == Sport.FOOTBALL.value:
        return t("ctrl.sport_football", lang)
    if choice == Sport.BASKETBALL.value:
        return t("ctrl.sport_basketball", lang)
    return choice


def league_choices(sport: Sport | None = None) -> list[str]:
    """Selectbox options: Alle first, then each league (optionally sport-filtered)."""

    leagues = leagues_for_sport(sport)
    return [ALL_LEAGUES, *[lg.value for lg in leagues]]


def resolve_leagues(choice: str, sport: Sport | None = None) -> list[League]:
    """Turn a sidebar choice into one or more League enums."""

    allowed = leagues_for_sport(sport)
    if choice == ALL_LEAGUES:
        return list(allowed)
    league = League(choice)
    if league not in allowed:
        raise ValueError(f"league {choice!r} not in sport filter {sport}")
    return [league]


def format_league_choice(choice: str, lang: str = "de") -> str:
    """Human label for the sidebar selectbox."""

    if choice == ALL_LEAGUES:
        return t("ctrl.league_all", lang)
    return choice.replace("_", " ").title()


def league_title(league: League) -> str:
    """Short display name for section headers on the tips page."""

    return league.value.replace("_", " ").title()
