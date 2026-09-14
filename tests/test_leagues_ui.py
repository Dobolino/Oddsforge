"""Tests for Alle-leagues helpers and multi-league / date-window slips."""

from __future__ import annotations

from datetime import timedelta

from quantbot.dashboard.leagues import (
    ALL_LEAGUES,
    format_league_choice,
    league_choices,
    resolve_leagues,
)
from quantbot.dashboard.slip import build_safe_slip, format_ticket, ticket_html
from quantbot.orchestrator import QuantBotOrchestrator
from quantbot.schemas import League


def test_league_choices_start_with_all() -> None:
    choices = league_choices()
    assert choices[0] == ALL_LEAGUES
    assert League.PREMIER_LEAGUE.value in choices


def test_resolve_all_leagues() -> None:
    leagues = resolve_leagues(ALL_LEAGUES)
    assert set(leagues) == set(League)


def test_format_all_label_de() -> None:
    assert "Alle" in format_league_choice(ALL_LEAGUES, "de")


def test_multi_league_slip_carries_league_and_date() -> None:
    orch = QuantBotOrchestrator()
    as_of = orch.default_as_of(League.PREMIER_LEAGUE, "2024-2025")
    reports = orch.predict(League.PREMIER_LEAGUE, "2024-2025", as_of)
    reports += orch.predict(League.BUNDESLIGA, "2024-2025", as_of)
    end = as_of.date() + timedelta(days=20)
    windowed = [r for r in reports if as_of.date() <= r.match.kickoff.date() <= end]
    slip = build_safe_slip(windowed, lang="de", max_legs=5)
    if slip is None:
        return
    assert all(leg.league for leg in slip.legs)
    assert all(leg.kickoff_date for leg in slip.legs)
    text = format_ticket(slip, lang="de", stake=10.0)
    assert "TIPPSCHEIN" in text
    html = ticket_html(slip, lang="de", stake=10.0)
    assert "TIPPSCHEIN" in html
