"""Tests for the weekly tracker (suggestions vs results)."""

from __future__ import annotations

from quantbot.data import DummyDataProvider
from quantbot.schemas import League
from quantbot.tracking import TrackerStore, build_rounds

SEASON = "2024-2025"


def test_build_rounds_produces_history_and_upcoming() -> None:
    view = build_rounds(DummyDataProvider(), League.PREMIER_LEAGUE, SEASON, hold_out_last=1)
    assert view.rounds
    # Exactly one upcoming round (results hidden), the rest settled.
    upcoming = [r for r in view.rounds if r["upcoming"]]
    settled = [r for r in view.rounds if not r["upcoming"]]
    assert len(upcoming) == 1
    assert settled
    for r in settled:
        for e in r["entries"]:
            assert e["settled"] is True
            assert e["actual"] in ("home", "draw", "away")
            assert isinstance(e["correct"], bool)
    for e in upcoming[0]["entries"]:
        assert e["settled"] is False
        assert e["actual"] is None
        assert e["correct"] is None


def test_overall_hit_rate_consistent() -> None:
    view = build_rounds(DummyDataProvider(), League.PREMIER_LEAGUE, SEASON)
    settled_bets = sum(r["bets"] for r in view.rounds if not r["upcoming"])
    settled_correct = sum(r["correct"] for r in view.rounds if not r["upcoming"])
    assert view.total_bets == settled_bets
    assert view.total_correct == settled_correct
    if view.total_bets:
        assert view.hit_rate == round(view.total_correct / view.total_bets * 100, 1)


def test_tracker_store_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    view = build_rounds(DummyDataProvider(), League.PREMIER_LEAGUE, SEASON)
    store = TrackerStore(tmp_path / "tracker.json")
    assert store.load() is None
    store.save(view)
    loaded = store.load()
    assert loaded is not None
    assert loaded.total_bets == view.total_bets
    assert len(loaded.rounds) == len(view.rounds)
