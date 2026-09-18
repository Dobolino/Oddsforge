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
    assert "slip" not in beginner
    assert "paper" not in beginner
    assert "paper" in advanced and "paper" in expert
    assert "calibration" in advanced
    assert "diagnostics" in expert and "diagnostics" not in advanced
    assert "backtest" in advanced and "backtest" not in beginner


def test_all_modes_have_pages() -> None:
    for mode in UXMode:
        assert mode in PAGES_BY_MODE
        assert PAGES_BY_MODE[mode]


def test_tip_kind_from_label_totals() -> None:
    from quantbot.dashboard.ux import tip_kind_from_label

    assert tip_kind_from_label("Value erkannt: Über 2,5 Tore") is SignalType.VALUE_OVER
    assert tip_kind_from_label("Tip: under 2.5 goals") is SignalType.VALUE_UNDER
    assert tip_kind_from_label("Value erkannt: Heimsieg") is SignalType.VALUE_HOME


def test_plain_signal_labels() -> None:
    assert "Heim" in plain_signal_label(SignalType.VALUE_HOME, "de")
    assert plain_signal_label(SignalType.VALUE_HOME, "de").startswith("Value erkannt")
    assert "Value spotted" in plain_signal_label(SignalType.VALUE_HOME, "en")
    assert "home" in plain_signal_label(SignalType.VALUE_HOME, "en").lower()
    assert "Kein Signal" in plain_signal_label(SignalType.NO_BET, "de")
    assert "No signal" in plain_signal_label(SignalType.NO_BET, "en")


def test_tone_colors_for_signed_and_confidence() -> None:
    from quantbot.dashboard.ux import (
        colored_text_html,
        tone_color_for_confidence,
        tone_color_for_signed,
    )

    assert tone_color_for_signed(0.05) == "#1b7f4a"
    assert tone_color_for_signed(-0.02) == "#b91c1c"
    assert tone_color_for_signed(0.0) == "#6b7280"
    assert tone_color_for_signed(None) == "#6b7280"
    assert tone_color_for_confidence(80) == "#1b7f4a"
    assert tone_color_for_confidence(50) == "#c47a00"
    assert tone_color_for_confidence(20) == "#6b7280"
    html = colored_text_html("+6.3 pp", "#1b7f4a")
    assert "#1b7f4a" in html
    assert "+6.3 pp" in html


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


def test_all_visible_pages_have_labels() -> None:
    """Every page id from UX modes must exist in the dashboard label map."""

    from quantbot.i18n import t

    # Mirrors app.py all_pages keys — keep in sync when adding pages.
    label_keys = {
        "signals",
        "slip",
        "paper",
        "card",
        "tracker",
        "insights",
        "calibration",
        "models",
        "diagnostics",
        "backtest",
        "settings",
        "glossary",
    }
    for mode in UXMode:
        missing = set(pages_for(mode)) - label_keys
        assert not missing, f"{mode}: missing page labels {missing}"
        assert t("page.settings", "de")
