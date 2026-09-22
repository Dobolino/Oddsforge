"""Live date-window reset must not wipe intentional future matchdays."""

from __future__ import annotations

from datetime import date, timedelta

from quantbot.dashboard.app import _live_committed_window_is_stale


def test_future_window_is_not_stale() -> None:
    today = date(2026, 9, 21)
    # Oct 9 is >14 days ahead — must NOT be treated as stale (Übernehmen bug).
    assert not _live_committed_window_is_stale(date(2026, 10, 9), today)
    assert not _live_committed_window_is_stale(today + timedelta(days=21), today)
    assert not _live_committed_window_is_stale(today + timedelta(days=2), today)


def test_past_window_is_stale() -> None:
    today = date(2026, 9, 21)
    assert _live_committed_window_is_stale(date(2024, 10, 1), today)
    assert _live_committed_window_is_stale(today - timedelta(days=15), today)
    assert not _live_committed_window_is_stale(today - timedelta(days=7), today)
