"""Tests for UX depth modes and plain-language helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from quantbot.dashboard.ux import (
    PAGES_BY_MODE,
    UXMode,
    pages_for,
    plain_reason,
    plain_signal_label,
    reason_for_mode,
)
from quantbot.schemas import SignalType, ValueSignal


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


def test_tip_kind_from_label_totals() -> None:
    from quantbot.dashboard.ux import tip_kind_from_label
    from quantbot.schemas import SignalType

    assert tip_kind_from_label("Tipp: Über 2,5 Tore") is SignalType.VALUE_OVER
    assert tip_kind_from_label("Tip: under 2.5 goals") is SignalType.VALUE_UNDER
    assert tip_kind_from_label("Tipp: Heimsieg") is SignalType.VALUE_HOME


def test_plain_reason_uses_signal_fields() -> None:
    signal = ValueSignal(
        match_id="m1",
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        signal=SignalType.NO_BET,
        model_confidence=50.0,
        data_quality=40.0,
        rationale="data quality 40.0 below minimum 60.0",
        rationale_de="Zu wenig verlässliche Daten für dieses Spiel.",
        rationale_en="Not enough reliable data for this match.",
    )
    assert "Daten" in plain_reason(signal, "de")
    assert "reliable" in plain_reason(signal, "en").lower()
    assert "data quality" in reason_for_mode(signal, UXMode.EXPERT, "de")
    assert "Daten" in reason_for_mode(signal, UXMode.BEGINNER, "de")
    assert plain_reason("", "de")
