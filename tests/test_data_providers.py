"""Tests for the data provider layer: reproducibility and temporal filtering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from quantbot.data import DummyDataProvider
from quantbot.schemas import League, MatchStatus

UTC = timezone.utc
SEASON = "2024-2025"
# After the whole generated season; every match is finished by then.
FAR_FUTURE = datetime(2026, 1, 1, tzinfo=UTC)
# Before any kickoff; nothing is finished yet.
BEFORE_SEASON = datetime(2024, 1, 1, tzinfo=UTC)


def test_provider_name_includes_seed() -> None:
    assert DummyDataProvider(seed=7).provider_name == "dummy(seed=7)"


def test_reproducible_matches_same_seed() -> None:
    a = DummyDataProvider(seed=42).get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE)
    b = DummyDataProvider(seed=42).get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE)
    assert [m.model_dump() for m in a] == [m.model_dump() for m in b]
    # 6 teams single round-robin -> 15 matches.
    assert len(a) == 15


def test_different_seed_changes_data() -> None:
    a = DummyDataProvider(seed=1).get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE)
    b = DummyDataProvider(seed=2).get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE)
    results_a = [(m.result.home_goals, m.result.away_goals) for m in a if m.result]
    results_b = [(m.result.home_goals, m.result.away_goals) for m in b if m.result]
    assert results_a != results_b


def test_reproducible_odds_same_seed() -> None:
    provider = DummyDataProvider(seed=42)
    match_id = provider.get_matches(League.BUNDESLIGA, SEASON, FAR_FUTURE)[0].match_id
    odds_a = provider.get_odds(match_id, FAR_FUTURE)
    odds_b = DummyDataProvider(seed=42).get_odds(match_id, FAR_FUTURE)
    assert [o.model_dump() for o in odds_a] == [o.model_dump() for o in odds_b]


def test_both_leagues_present() -> None:
    provider = DummyDataProvider()
    pl = provider.get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE)
    bl = provider.get_matches(League.BUNDESLIGA, SEASON, FAR_FUTURE)
    assert len(pl) == 15
    assert len(bl) == 15
    assert all(m.league is League.PREMIER_LEAGUE for m in pl)
    assert all(m.league is League.BUNDESLIGA for m in bl)


def test_results_masked_before_kickoff() -> None:
    provider = DummyDataProvider()
    matches = provider.get_matches(League.PREMIER_LEAGUE, SEASON, BEFORE_SEASON)
    assert matches, "expected fixtures to still be listed before the season"
    for m in matches:
        assert m.result is None
        assert m.status is MatchStatus.SCHEDULED
        assert not m.is_finished


def test_results_present_after_kickoff() -> None:
    provider = DummyDataProvider()
    matches = provider.get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE)
    assert all(m.is_finished for m in matches)
    assert all(m.result is not None for m in matches)


def test_as_of_between_partitions_finished_and_upcoming() -> None:
    provider = DummyDataProvider()
    all_matches = provider.get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE)
    kickoffs = sorted(m.kickoff for m in all_matches)
    # Pick an instant after the earliest kickoff but before the latest.
    as_of = kickoffs[len(kickoffs) // 2]

    finished = provider.get_finished_matches(League.PREMIER_LEAGUE, SEASON, as_of)
    upcoming = provider.get_upcoming_matches(League.PREMIER_LEAGUE, SEASON, as_of)

    assert finished and upcoming
    assert all(m.kickoff <= as_of for m in finished)
    assert all(m.is_finished for m in finished)
    assert all(m.kickoff > as_of for m in upcoming)
    assert all(m.result is None for m in upcoming)
    assert len(finished) + len(upcoming) == len(all_matches)


def test_get_odds_filters_by_as_of() -> None:
    provider = DummyDataProvider()
    match = provider.get_matches(League.BUNDESLIGA, SEASON, FAR_FUTURE)[0]
    # 24h before kickoff: only the 72h and 24h snapshots exist.
    as_of = match.kickoff - timedelta(hours=24)
    odds = provider.get_odds(match.match_id, as_of)
    assert len(odds) == 2
    assert all(o.timestamp <= as_of for o in odds)
    # Snapshots returned oldest first.
    assert odds == sorted(odds, key=lambda o: o.timestamp)


def test_get_latest_odds() -> None:
    provider = DummyDataProvider()
    match = provider.get_matches(League.BUNDESLIGA, SEASON, FAR_FUTURE)[0]
    latest = provider.get_latest_odds(match.match_id, match.kickoff - timedelta(hours=24))
    assert latest is not None
    assert latest.timestamp == match.kickoff - timedelta(hours=24)


def test_closing_odds_not_visible_before_close() -> None:
    provider = DummyDataProvider()
    match = provider.get_matches(League.BUNDESLIGA, SEASON, FAR_FUTURE)[0]
    # Long before kickoff the closing snapshot must not leak into get_odds.
    early = provider.get_odds(match.match_id, match.kickoff - timedelta(hours=48))
    assert all(not o.is_closing for o in early)
    # But closing line is available post-hoc for CLV.
    closing = provider.get_closing_odds(match.match_id)
    assert closing is not None
    assert closing.is_closing


def test_get_odds_requires_aware_timestamp() -> None:
    provider = DummyDataProvider()
    with pytest.raises(ValueError, match="timezone-aware"):
        provider.get_odds("whatever", datetime(2025, 1, 1))


def test_get_match_by_id() -> None:
    provider = DummyDataProvider()
    match = provider.get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE)[0]
    fetched = provider.get_match(match.match_id, FAR_FUTURE)
    assert fetched is not None
    assert fetched.match_id == match.match_id
    assert provider.get_match("missing", FAR_FUTURE) is None


def test_odds_have_positive_overround() -> None:
    provider = DummyDataProvider()
    match = provider.get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE)[0]
    for o in provider.get_odds(match.match_id, FAR_FUTURE):
        assert o.overround > 0.0
