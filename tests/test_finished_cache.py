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
        season: int | None = None,
    ) -> list[Match]:
        del competition, date_from, date_to
        self.calls += 1
        self.last_status = status
        self.last_season = season
        matches = list(self.matches)
        if season is not None:
            label = f"{season}-{season + 1}"
            matches = [m for m in matches if m.season == label]
        if status is None:
            return matches
        tokens = {t.strip() for t in status.split(",") if t.strip()}
        if tokens == {"FINISHED"}:
            return [m for m in matches if m.is_finished]
        return [m for m in matches if not m.is_finished]


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


def test_cold_start_falls_back_to_previous_season(tmp_path: Path) -> None:
    older = _match("old-1", finished=True)
    api = FakeMatchAPI([older])
    provider = CachingMatchProvider(api, FinishedMatchCache(tmp_path / "fb.json"))

    # Prefer 2026 — empty — then 2025 which matches season "2024-2025"? 
    # older is 2024-2025 → start year 2024.
    got = provider.fetch_matches("PL", season=2026)
    assert {m.match_id for m in got} == {"old-1"}
    assert api.last_season in (2026, 2025, 2024, None)


def test_thin_archive_triggers_full_finished_backfill(tmp_path: Path) -> None:
    """Warm path with a thin season archive must re-fetch all FINISHED rows."""

    thin = _match("thin-1", finished=True, kickoff=datetime(2024, 8, 20, tzinfo=UTC))
    more = [
        _match(
            f"fin-{i}",
            finished=True,
            kickoff=datetime(2024, 8, 20, tzinfo=UTC) + timedelta(days=i),
        )
        for i in range(2, 45)
    ]
    upcoming = _match("open-thin", finished=False, kickoff=datetime(2025, 3, 1, tzinfo=UTC))
    api = FakeMatchAPI([thin, *more, upcoming])
    cache = FinishedMatchCache(tmp_path / "thin.json")
    # Seed a deliberately thin archive (1 finished) so warm path backfills.
    cache.put_finished([thin])
    provider = CachingMatchProvider(api, cache)

    got = provider.fetch_matches("PL", season=2024)
    finished_ids = {m.match_id for m in got if m.is_finished}
    assert "thin-1" in finished_ids
    assert len(finished_ids) >= 40
    assert "open-thin" in {m.match_id for m in got}
    assert any(status == "FINISHED" for status in [api.last_status])
