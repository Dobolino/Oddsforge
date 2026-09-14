"""Permanent finished-match archive: save once, reuse without network."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from quantbot.data.finished_cache import CachingMatchProvider, FinishedMatchCache
from quantbot.schemas import League, Match, MatchResult, MatchStatus, Team

UTC = timezone.utc


def _match(
    match_id: str,
    *,
    finished: bool,
    kickoff: datetime | None = None,
    league: League = League.PREMIER_LEAGUE,
) -> Match:
    kickoff = kickoff or datetime(2025, 1, 10, 15, 0, tzinfo=UTC)
    return Match(
        match_id=match_id,
        league=league,
        season="2024-2025",
        kickoff=kickoff,
        prediction_timestamp=kickoff - timedelta(hours=2),
        home_team=Team(team_id=f"h-{match_id}", name=f"Home {match_id}"),
        away_team=Team(team_id=f"a-{match_id}", name=f"Away {match_id}"),
        status=MatchStatus.FINISHED if finished else MatchStatus.SCHEDULED,
        result=MatchResult(home_goals=2, away_goals=1) if finished else None,
    )


class FakeMatchAPI:
    """Counts network calls; supports status filters like the real client."""

    def __init__(self, matches: list[Match]) -> None:
        self.matches = list(matches)
        self.calls = 0
        self.last_status: str | None = None

    def fetch_matches(
        self,
        competition: str,
        *,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[Match]:
        del competition, date_from, date_to
        self.calls += 1
        self.last_status = status
        if status is None:
            return list(self.matches)
        tokens = {t.strip() for t in status.split(",") if t.strip()}
        if tokens == {"FINISHED"}:
            return [m for m in self.matches if m.is_finished]
        return [m for m in self.matches if not m.is_finished]


def test_finished_cache_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "finished.json"
    cache = FinishedMatchCache(path)
    done = _match("m1", finished=True)
    open_m = _match("m2", finished=False, kickoff=datetime(2025, 2, 1, tzinfo=UTC))

    assert cache.put_finished([done, open_m]) == 1
    assert cache.get("m1") is not None
    assert cache.get("m2") is None
    assert cache.last_updated is not None

    reloaded = FinishedMatchCache(path)
    assert reloaded.get("m1") is not None
    assert reloaded.get("m1").result.home_goals == 2  # type: ignore[union-attr]
    assert reloaded.last_updated is not None


def test_finished_match_fetched_once_then_served_from_disk(tmp_path: Path) -> None:
    done = _match("fin-1", finished=True)
    upcoming = _match("open-1", finished=False, kickoff=datetime(2025, 3, 1, tzinfo=UTC))
    api = FakeMatchAPI([done, upcoming])
    cache = FinishedMatchCache(tmp_path / "matches.json")
    provider = CachingMatchProvider(api, cache)

    first = provider.ensure_finished("PL", "fin-1")
    assert first is not None
    assert first.match_id == "fin-1"
    assert api.calls == 1
    assert provider.network_calls == 1

    second = provider.ensure_finished("PL", "fin-1")
    assert second is not None
    assert api.calls == 1
    assert provider.network_calls == 1

    cached = provider.get_finished_cached("fin-1")
    assert cached is not None
    assert api.calls == 1


def test_warm_refresh_keeps_finished_from_disk(tmp_path: Path) -> None:
    done = _match("fin-2", finished=True)
    upcoming = _match("open-2", finished=False, kickoff=datetime(2025, 3, 1, tzinfo=UTC))
    api = FakeMatchAPI([done, upcoming])
    provider = CachingMatchProvider(api, FinishedMatchCache(tmp_path / "m.json"))

    first = provider.fetch_matches("PL")
    assert {m.match_id for m in first} == {"fin-2", "open-2"}
    assert api.calls == 1

    # Finished game no longer in the live open dump — still served from disk.
    api.matches = [upcoming]
    second = provider.fetch_matches("PL")
    ids = {m.match_id for m in second}
    assert "fin-2" in ids
    assert "open-2" in ids
    assert api.calls >= 2
    assert provider.get_finished_cached("fin-2") is not None
    assert provider.get_finished_cached("fin-2").result is not None  # type: ignore[union-attr]
