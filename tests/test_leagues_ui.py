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


def test_ticket_html_renders_compact_markup() -> None:
    from quantbot.dashboard.slip import BettingSlip, SlipLeg, ticket_html
    from quantbot.schemas import MatchOutcome

    slip = BettingSlip(
        legs=(
            SlipLeg(
                match_id="1",
                match="Brighton & Hove vs Arsenal",
                tip="Tipp: Heimsieg",
                outcome=MatchOutcome.HOME,
                odds=1.85,
                model_prob=0.55,
                edge=0.05,
                role="core",
                league="Premier League",
                kickoff_date="2026-09-20",
            ),
        ),
        style="safe",
    )
    html = ticket_html(slip, lang="de", stake=10.0)
    assert "<table" in html and "<tr>" in html
    assert "Brighton &amp; Hove" in html  # escaped ampersand
    assert "```" not in html
    assert "\n            <tr>" not in html


def test_tip_badge_colors_home_away_draw() -> None:
    from quantbot.dashboard.ux import tip_badge_html, tip_kind_from_label
    from quantbot.schemas import SignalType

    home = tip_badge_html(SignalType.VALUE_HOME, "de")
    away = tip_badge_html(SignalType.VALUE_AWAY, "de", text="Auswärtssieg")
    draw = tip_badge_html(SignalType.VALUE_DRAW, "de")
    assert "#1b7f4a" in home and "Heimsieg" in home
    assert "#1f5fbf" in away and "Auswärtssieg" in away
    assert "#c47a00" in draw
    assert tip_kind_from_label("Tipp: Heimsieg") is SignalType.VALUE_HOME


def test_as_of_for_live_window_uses_now() -> None:
    from datetime import date, datetime, timedelta, timezone

    from quantbot.dashboard.app import _as_of_for_window, _as_of_cache_key

    today = datetime.now(timezone.utc).date()
    as_of = _as_of_for_window(today, today + timedelta(days=2), live=True)
    assert as_of.date() == today
    assert as_of.tzinfo is not None
    # Live stand is rounded to the minute so Streamlit cache keys stay stable.
    assert as_of.second == 0
    assert as_of.microsecond == 0
    assert as_of >= datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    assert _as_of_cache_key(as_of) == as_of.isoformat()
    noisy = as_of.replace(second=17, microsecond=123456)
    assert _as_of_cache_key(noisy) == as_of.isoformat()


def test_as_of_for_demo_window_is_midnight() -> None:
    from datetime import date, datetime, timezone

    from quantbot.dashboard.app import _as_of_for_window

    start = date(2024, 10, 5)
    as_of = _as_of_for_window(start, start, live=False)
    assert as_of == datetime(2024, 10, 5, tzinfo=timezone.utc)
