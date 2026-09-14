"""League selection helpers for the dashboard (including „Alle“)."""

from __future__ import annotations

from quantbot.i18n import t
from quantbot.schemas import League

# Sentinel value in the sidebar selectbox for every supported league.
ALL_LEAGUES = "all"


def league_choices() -> list[str]:
    """Selectbox options: Alle first, then each league value."""

    return [ALL_LEAGUES, *[lg.value for lg in League]]


def resolve_leagues(choice: str) -> list[League]:
    """Turn a sidebar choice into one or more League enums."""

    if choice == ALL_LEAGUES:
        return list(League)
    return [League(choice)]


def format_league_choice(choice: str, lang: str = "de") -> str:
    """Human label for the sidebar selectbox."""

    if choice == ALL_LEAGUES:
        return t("ctrl.league_all", lang)
    return choice.replace("_", " ").title()


def league_title(league: League) -> str:
    """Short display name for section headers on the tips page."""

    return league.value.replace("_", " ").title()
