"""Tests for SnapshotRepository and market integrity checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantbot.data.snapshot_repo import DataMode, SnapshotRepository
from quantbot.markets.integrity import (
    DEFAULT_MAX_QUOTE_AGE,
    check_1x2_odds,
    check_totals_odds,
)
from quantbot.schemas import MarketKind, Odds, TotalsOdds


def _odds(*, ts: datetime, home: float = 2.0, draw: float = 3.4, away: float = 3.5) -> Odds:
    return Odds(
        match_id="m1",
        bookmaker="book_a",
        timestamp=ts,
        home=home,
        draw=draw,
        away=away,
        kind=MarketKind.ONE_X_TWO,
    )


def test_snapshot_repo_persists_and_filters_by_as_of(tmp_path: Path) -> None:
    repo = SnapshotRepository(path=tmp_path / "s.sqlite3")
    t0 = datetime(2024, 10, 1, 12, tzinfo=timezone.utc)
    t1 = datetime(2024, 10, 2, 12, tzinfo=timezone.utc)
    s0 = repo.put_odds(
        _odds(ts=t0),
        provider="dummy",
        endpoint="https://example.test/v4/odds?apiKey=SECRET",
        data_mode=DataMode.DEMO,
        fetched_at=t0 + timedelta(minutes=1),
    )
    assert "SECRET" not in s0.endpoint
    assert "[redacted]" in s0.endpoint or "?" not in s0.endpoint or "apiKey" not in s0.endpoint
    repo.put_odds(
        _odds(ts=t1, home=2.1),
        provider="dummy",
        endpoint="https://example.test/v4/odds",
        data_mode=DataMode.DEMO,
        fetched_at=t1 + timedelta(minutes=1),
    )
    as_of = datetime(2024, 10, 1, 18, tzinfo=timezone.utc)
    rows = repo.list_for_match("m1", as_of=as_of, data_mode=DataMode.DEMO)
    assert len(rows) == 1
    assert rows[0].source_timestamp == t0
    latest = repo.latest_for_match("m1", as_of=t1, data_mode=DataMode.DEMO)
    assert latest is not None
    assert latest.selection_payload["home"] == 2.1


def test_snapshot_repo_separates_historical_import(tmp_path: Path) -> None:
    repo = SnapshotRepository(path=tmp_path / "s.sqlite3")
    ts = datetime(2024, 5, 1, tzinfo=timezone.utc)
    repo.put_odds(
        _odds(ts=ts),
        provider="archive",
        endpoint="file://local/odds.json",
        data_mode=DataMode.HISTORICAL_IMPORT,
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    liveish = repo.list_for_match("m1", data_mode=DataMode.LIVE_REPLAY)
    assert liveish == []
    hist = repo.list_for_match("m1", data_mode=DataMode.HISTORICAL_IMPORT)
    assert len(hist) == 1
    # fetched_at much later does not change data_mode tagging
    assert hist[0].fetched_at.year == 2026
    assert hist[0].data_mode is DataMode.HISTORICAL_IMPORT


def test_integrity_flags_stale_and_after_kickoff() -> None:
    kickoff = datetime(2024, 10, 5, 15, tzinfo=timezone.utc)
    as_of = kickoff - timedelta(hours=1)
    fresh = _odds(ts=as_of - timedelta(hours=2))
    assert check_1x2_odds(fresh, as_of=as_of, kickoff=kickoff) == ()

    stale = _odds(ts=as_of - DEFAULT_MAX_QUOTE_AGE - timedelta(minutes=1))
    codes = {r.code for r in check_1x2_odds(stale, as_of=as_of, kickoff=kickoff)}
    assert "INVALID_DATA_QUOTE_STALE" in codes

    late = _odds(ts=kickoff + timedelta(minutes=1))
    codes = {r.code for r in check_1x2_odds(late, as_of=as_of, kickoff=kickoff)}
    assert "INVALID_DATA_QUOTE_AFTER_KICKOFF" in codes


def test_integrity_rejects_nan_odds() -> None:
    ts = datetime(2024, 10, 1, tzinfo=timezone.utc)
    # Bypass schema so the integrity helper can still flag non-finite values
    # that might arrive from partially trusted adapters.
    bad = Odds.model_construct(
        match_id="m1",
        bookmaker="book_a",
        timestamp=ts,
        home=float("nan"),
        draw=3.4,
        away=3.5,
        kind=MarketKind.ONE_X_TWO,
        is_closing=False,
    )
    codes = {r.code for r in check_1x2_odds(bad, as_of=ts)}
    assert "INVALID_DATA_ODDS_NAN" in codes


def test_totals_integrity_basic() -> None:
    ts = datetime(2024, 10, 1, tzinfo=timezone.utc)
    ok = TotalsOdds(
        match_id="m1",
        bookmaker="b",
        timestamp=ts,
        line=2.5,
        over=1.9,
        under=1.9,
    )
    assert check_totals_odds(ok, as_of=ts) == ()
    bad = TotalsOdds.model_construct(
        match_id="m1",
        bookmaker="b",
        timestamp=ts,
        line=2.5,
        over=float("inf"),
        under=1.9,
    )
    assert "INVALID_DATA_ODDS_NAN" in {r.code for r in check_totals_odds(bad, as_of=ts)}


def test_orchestrator_can_persist_demo_snapshots(tmp_path: Path) -> None:
    from quantbot.data.dummy import DummyDataProvider
    from quantbot.orchestrator import QuantBotOrchestrator
    from quantbot.schemas import League

    repo = SnapshotRepository(path=tmp_path / "demo.sqlite3")
    orch = QuantBotOrchestrator(
        provider=DummyDataProvider(),
        snapshot_repo=repo,
        persist_snapshots=True,
        live=False,
        min_team_matches=0,
    )
    reports = orch.predict(League.PREMIER_LEAGUE, "2024-2025")
    assert reports
    # At least one snapshot stored for a reported match
    found = False
    for r in reports:
        if repo.list_for_match(r.match.match_id, data_mode=DataMode.DEMO):
            found = True
            break
    assert found


def test_live_mode_enables_snapshot_persist_by_default(tmp_path: Path) -> None:
    from quantbot.data.dummy import DummyDataProvider
    from quantbot.orchestrator import QuantBotOrchestrator

    repo = SnapshotRepository(path=tmp_path / "live.sqlite3")
    orch = QuantBotOrchestrator(
        provider=DummyDataProvider(),
        snapshot_repo=repo,
        live=True,
        min_team_matches=0,
    )
    assert orch.persist_snapshots is True
    assert orch.snapshot_repo is repo


def test_snapshot_db_defaults_under_home_quantbot() -> None:
    from quantbot.data.snapshot_repo import snapshot_db_path

    path = snapshot_db_path()
    assert path.name == "snapshots.sqlite3"
    assert ".quantbot" in path.parts
    assert "snapshots" in path.parts


def test_odds_cache_ttl_defaults_protect_credits() -> None:
    from quantbot.data.providers.live import (
        DEFAULT_FIXTURE_CACHE_TTL_SECONDS,
        DEFAULT_ODDS_CACHE_TTL_SECONDS,
    )

    assert DEFAULT_ODDS_CACHE_TTL_SECONDS >= 3600.0
    assert DEFAULT_ODDS_CACHE_TTL_SECONDS <= 7200.0
    assert DEFAULT_FIXTURE_CACHE_TTL_SECONDS >= 1800.0


def test_predict_integrity_shell_uses_prob_home_not_home() -> None:
    """Regression: invalid-odds shell must not touch Prediction attributes."""

    import inspect
    from datetime import timedelta

    from quantbot.data.dummy import DummyDataProvider
    from quantbot.orchestrator import QuantBotOrchestrator
    from quantbot.schemas import League, Odds

    source = inspect.getsource(QuantBotOrchestrator.predict)
    assert "prediction.home" not in source
    # Integrity placeholder must not depend on model output field names.
    assert "prediction.prob_home" not in source

    class _StaleOddsProvider(DummyDataProvider):
        def _fetch_odds(self, match_id: str):  # type: ignore[no-untyped-def]
            match = next(m for m in self._fetch_matches() if m.match_id == match_id)
            return (
                Odds(
                    match_id=match_id,
                    bookmaker="stale_book",
                    timestamp=match.kickoff - timedelta(hours=48),
                    home=2.10,
                    draw=3.40,
                    away=3.50,
                ),
            )

    orch = QuantBotOrchestrator(
        provider=_StaleOddsProvider(),
        live=True,
        min_team_matches=0,
        persist_snapshots=False,
    )
    reports = orch.predict(League.PREMIER_LEAGUE, "2024-2025")
    assert reports
    assert any(
        (r.signal.decision_status or "").lower() == "invalid_data"
        or "INVALID_DATA" in (r.signal.reason_codes or ())
        for r in reports
    )
