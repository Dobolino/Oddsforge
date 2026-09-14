"""Tests for UX depth modes and plain-language helpers."""

from __future__ import annotations

from quantbot.dashboard.ux import (
    PAGES_BY_MODE,
    UXMode,
    pages_for,
    plain_reason,
    plain_signal_label,
)
from quantbot.schemas import SignalType


def test_pages_nested_by_depth() -> None:
    beginner = set(pages_for(UXMode.BEGINNER))
    advanced = set(pages_for(UXMode.ADVANCED))
    expert = set(pages_for(UXMode.EXPERT))
    assert beginner <= advanced <= expert
    assert "signals" in beginner and "glossary" in beginner
    assert "diagnostics" in expert and "diagnostics" not in advanced
    assert "backtest" in advanced and "backtest" not in beginner


def test_all_modes_have_pages() -> None:
    for mode in UXMode:
        assert mode in PAGES_BY_MODE
        assert PAGES_BY_MODE[mode]


def test_plain_signal_labels() -> None:
    assert "Heim" in plain_signal_label(SignalType.VALUE_HOME, "de")
    assert "home" in plain_signal_label(SignalType.VALUE_HOME, "en").lower()
    assert "Kein" in plain_signal_label(SignalType.NO_BET, "de")


def test_plain_reason_maps_common_cases() -> None:
    assert "Daten" in plain_reason("data quality 40.0 below minimum 60.0", "de")
    assert "edge" in plain_reason("edge 0.01 below minimum 0.03", "en").lower()
    assert "Vorteil" in plain_reason("value on home: edge 0.05, ev 0.08, stake 0.02", "de")
    assert plain_reason("", "de")
