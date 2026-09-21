"""Multi-season fit: prior-season backbone for early-season predictions."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from quantbot.data.base import BaseDataProvider
from quantbot.orchestrator import QuantBotOrchestrator, previous_season
from quantbot.schemas import League, Match, MatchResult, MatchStatus, Odds, Team

UTC = timezone.utc
CURRENT = "2026-2027"
PRIOR = "2025-2026"


def _match(mid: str, season: str, kickoff: datetime, result: MatchResult | None) -> Match:
    return Match(
        match_id=mid,
        league=League.PREMIER_LEAGUE,
        season=season,
        kickoff=kickoff,
        prediction_timestamp=kickoff - timedelta(hours=2),
        home_team=Team(team_id="A", name="A"),
        away_team=Team(team_id="B", name="B"),
        status=MatchStatus.FINISHED if result else MatchStatus.SCHEDULED,
        result=result,
        result_available_at=(kickoff + timedelta(hours=2)) if result else None,
    )


class _TwoSeasonProvider(BaseDataProvider):
    """Two finished prior-season matches, one finished + one upcoming current."""

    @property
    def provider_name(self) -> str:
        return "two-season"

    def _fetch_matches(self) -> Sequence[Match]:
        return [
            _match("p1", PRIOR, datetime(2025, 9, 1, 15, tzinfo=UTC), MatchResult(home_goals=2, away_goals=1)),
            _match("p2", PRIOR, datetime(2025, 10, 1, 15, tzinfo=UTC), MatchResult(home_goals=0, away_goals=0)),
            _match("c1", CURRENT, datetime(2026, 8, 20, 15, tzinfo=UTC), MatchResult(home_goals=1, away_goals=0)),
            _match("c2", CURRENT, datetime(2026, 9, 30, 15, tzinfo=UTC), None),
        ]

    def _fetch_odds(self, match_id: str) -> Sequence[Odds]:
        return ()


def test_previous_season_labels() -> None:
    assert previous_season("2026-2027") == "2025-2026"
    assert previous_season("2024-2025") == "2023-2024"
    assert previous_season("2026") == "2025"
    assert previous_season("nonsense") is None


def test_fit_universe_includes_prior_season() -> None:
    orch = QuantBotOrchestrator(provider=_TwoSeasonProvider(), fit_prior_seasons=1)
    current_only = orch.universe(League.PREMIER_LEAGUE, CURRENT)
    fit = orch.fit_universe(League.PREMIER_LEAGUE, CURRENT)
    assert {m.match_id for m in current_only} == {"c1", "c2"}
    # Prior season's p1/p2 are added on top of the current-season fixtures.
    assert {m.match_id for m in fit} == {"c1", "c2", "p1", "p2"}


def test_fit_universe_default_is_current_only() -> None:
    orch = QuantBotOrchestrator(provider=_TwoSeasonProvider(), fit_prior_seasons=0)
    fit = orch.fit_universe(League.PREMIER_LEAGUE, CURRENT)
    assert {m.match_id for m in fit} == {"c1", "c2"}


def test_missing_prior_season_is_safe() -> None:
    # Requesting 3 prior seasons when only 1 exists must not error.
    orch = QuantBotOrchestrator(provider=_TwoSeasonProvider(), fit_prior_seasons=3)
    fit = orch.fit_universe(League.PREMIER_LEAGUE, CURRENT)
    assert {m.match_id for m in fit} == {"c1", "c2", "p1", "p2"}


# --- Live provider loads prior seasons ---


class _FakeFootball:
    """Records the season kwargs asked for and returns one match per season."""

    def __init__(self) -> None:
        self.seasons_requested: list[int] = []

    def fetch_matches(self, code: str, season: int | None = None):
        self.seasons_requested.append(season)
        year = season if season is not None else 2026
        start = 2000 + (year % 100)
        return [
            _match(f"{code}-{year}", f"{year}-{year + 1}", datetime(start, 9, 1, 15, tzinfo=UTC), MatchResult(home_goals=1, away_goals=1))
        ]


def test_live_provider_loads_history_seasons(monkeypatch) -> None:
    from quantbot.data.providers.live import LiveDataProvider

    # Fixed "current" season year so the test is deterministic.
    monkeypatch.setattr(LiveDataProvider, "_season_start_year", lambda self: 2026)
    fake = _FakeFootball()
    provider = LiveDataProvider(
        fake, odds=object(), leagues=[League.PREMIER_LEAGUE], history_seasons=1
    )
    matches = provider._fetch_matches()
    # Current (2026) and one prior (2025) season requested.
    assert set(fake.seasons_requested) == {2026, 2025}
    assert len(matches) == 2
