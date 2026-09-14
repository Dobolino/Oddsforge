"""Tests for persistent tip history (TipHistoryStore)."""

from __future__ import annotations

from pathlib import Path

from quantbot.data import DummyDataProvider
from quantbot.schemas import League, MatchOutcome
from quantbot.tracking import (
    TipHistoryStore,
    TipRecord,
    collect_tip_records,
    sync_tip_history,
    tracker_path,
)

SEASON = "2024-2025"


def test_tracker_path_separates_demo_and_live(tmp_path: Path) -> None:
    demo = tracker_path("demo", base=tmp_path)
    live = tracker_path("live", base=tmp_path)
    assert demo.name == "demo.json"
    assert live.name == "live.json"
    assert demo != live


def test_tip_history_save_reload_and_append(tmp_path: Path) -> None:
    path = tmp_path / "demo.json"
    store = TipHistoryStore(path)
    records = collect_tip_records(
        DummyDataProvider(), League.PREMIER_LEAGUE, SEASON, mode="demo", hold_out_last=1
    )
    assert records
    added = store.append_new(records)
    assert added == len(records)
    # Second sync must not duplicate.
    assert store.append_new(records) == 0

    reloaded = TipHistoryStore(path)
    assert len(reloaded.all_tips()) == len(records)
    assert reloaded.hit_rate() == store.hit_rate()


def test_tip_history_settle_updates_hit_rate(tmp_path: Path) -> None:
    path = tmp_path / "demo.json"
    store = TipHistoryStore(path)
    pending = TipRecord(
        tip_id="m1::asof",
        match_id="m1",
        kickoff="2024-10-05T15:00:00+00:00",
        league="premier_league",
        home="A",
        away="B",
        tip="home",
        odds=1.9,
        model_prob=0.55,
        as_of="2024-10-05T13:00:00+00:00",
        mode="demo",
        settled=False,
    )
    store.append_new([pending])
    assert store.hit_rate() is None
    assert store.settle("m1", MatchOutcome.HOME) == 1
    assert store.settle("m1", MatchOutcome.HOME) == 0  # already settled
    bets, correct = store.totals()
    assert bets == 1 and correct == 1
    assert store.hit_rate() == 100.0

    store.settle("missing", "away")
    # Wrong tip case
    store.append_new(
        [
            TipRecord(
                tip_id="m2::asof",
                match_id="m2",
                kickoff="2024-10-12T15:00:00+00:00",
                league="premier_league",
                home="C",
                away="D",
                tip="away",
                odds=3.1,
                model_prob=0.3,
                as_of="2024-10-12T13:00:00+00:00",
                mode="demo",
            )
        ]
    )
    store.settle("m2", "home")
    bets, correct = store.totals()
    assert bets == 2 and correct == 1
    assert store.hit_rate() == 50.0


def test_sync_tip_history_persists_across_instances(tmp_path: Path) -> None:
    path = tracker_path("demo", base=tmp_path)
    provider = DummyDataProvider()
    store = TipHistoryStore(path)
    view1 = sync_tip_history(
        store, provider, [League.PREMIER_LEAGUE], SEASON, mode="demo"
    )
    assert view1.total_bets >= 0
    n1 = len(store.all_tips())
    assert n1 > 0

    store2 = TipHistoryStore(path)
    view2 = sync_tip_history(
        store2, provider, [League.PREMIER_LEAGUE], SEASON, mode="demo"
    )
    assert len(store2.all_tips()) == n1
    assert view2.total_bets == view1.total_bets
    assert view2.hit_rate == view1.hit_rate


def test_demo_and_live_files_do_not_mix(tmp_path: Path) -> None:
    provider = DummyDataProvider()
    demo = TipHistoryStore(tracker_path("demo", base=tmp_path))
    live = TipHistoryStore(tracker_path("live", base=tmp_path))
    sync_tip_history(demo, provider, [League.PREMIER_LEAGUE], SEASON, mode="demo")
    # Live store stays empty until synced as live.
    assert live.all_tips() == []
    assert all(t.mode == "demo" for t in demo.all_tips())
