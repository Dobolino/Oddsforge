"""User-experience depth modes for the dashboard.

Three levels so a complete beginner can open the app without drowning in
metrics, while experts still get the full toolkit.

- beginner: one tip, one reason, safety first. Few pages.
- advanced: probabilities, edge, stake, match card, backtest.
- expert: every page and every metric.
"""

from __future__ import annotations

from enum import Enum

from quantbot.schemas import SignalType, ValueSignal


class UXMode(str, Enum):
    BEGINNER = "beginner"
    ADVANCED = "advanced"
    EXPERT = "expert"


# Pages visible in the sidebar, in display order.
PAGES_BY_MODE: dict[UXMode, tuple[str, ...]] = {
    # Beginner: no tip slip / accumulators — Gemini+Claude: kombis raise risk for newcomers.
    UXMode.BEGINNER: ("signals", "tracker", "settings", "glossary"),
    # Advanced: calibration is a must-have signal-quality view (Claude review).
    UXMode.ADVANCED: ("signals", "slip", "card", "tracker", "calibration", "backtest", "settings", "glossary"),
    UXMode.EXPERT: (
        "signals",
        "slip",
        "card",
        "tracker",
        "insights",
        "calibration",
        "models",
        "diagnostics",
        "backtest",
        "settings",
        "glossary",
    ),
}

# Signal table columns by depth (keys match tables.signals_dataframe output).
# Internal keys stay English; display labels are localized in the table builder.
SIGNAL_COLUMNS_BY_MODE: dict[UXMode, tuple[str, ...]] = {
    UXMode.BEGINNER: ("Match", "Tipp", "Begründung"),
    UXMode.ADVANCED: ("Match", "Signal", "Model P", "Odds", "Edge", "EV", "Stake %", "Reason"),
    UXMode.EXPERT: (
        "Match",
        "Signal",
        "Model P",
        "Odds",
        "Edge",
        "EV",
        "Stake %",
        "Confidence",
        "Data quality",
        "Reason",
    ),
}

_COLUMN_LABELS: dict[str, dict[str, str]] = {
    "Match": {"de": "Spiel", "en": "Match"},
    "Tipp": {"de": "Tipp", "en": "Tip"},
    "Begründung": {"de": "Begründung", "en": "Reason"},
    "Signal": {"de": "Tipp", "en": "Signal"},
    "Model P": {"de": "Modell-P", "en": "Model P"},
    "Odds": {"de": "Quote", "en": "Odds"},
    "Edge": {"de": "Edge (pp)", "en": "Edge (pp)"},
    "EV": {"de": "Erwartete Rendite", "en": "Expected return"},
    "Stake %": {"de": "Einsatz %", "en": "Stake %"},
    "Confidence": {"de": "Prognosequalität", "en": "Forecast quality"},
    "Data quality": {"de": "Datenqualität", "en": "Data quality"},
    "Reason": {"de": "Begründung", "en": "Reason"},
}


def column_label(key: str, lang: str = "de") -> str:
    entry = _COLUMN_LABELS.get(key, {})
    if lang.startswith("de"):
        return entry.get("de", key)
    return entry.get("en", key)

_SIGNAL_PLAIN: dict[SignalType, dict[str, str]] = {
    # Claude review: avoid “Empfehlung”; prefer neutral value language.
    SignalType.VALUE_HOME: {"de": "Value erkannt: Heimsieg", "en": "Value spotted: home win"},
    SignalType.VALUE_DRAW: {"de": "Value erkannt: Unentschieden", "en": "Value spotted: draw"},
    SignalType.VALUE_AWAY: {"de": "Value erkannt: Auswärtssieg", "en": "Value spotted: away win"},
    SignalType.VALUE_OVER: {"de": "Value erkannt: Über 2,5 Tore", "en": "Value spotted: over 2.5 goals"},
    SignalType.VALUE_UNDER: {"de": "Value erkannt: Unter 2,5 Tore", "en": "Value spotted: under 2.5 goals"},
    SignalType.NO_BET: {"de": "Kein Value", "en": "No value"},
}

# Clear beginner colors: home = green, draw = amber, away = blue,
# over = teal, under = slate, no tip = gray.
_TIP_COLORS: dict[SignalType, dict[str, str]] = {
    SignalType.VALUE_HOME: {"bg": "#1b7f4a", "fg": "#ffffff"},
    SignalType.VALUE_DRAW: {"bg": "#c47a00", "fg": "#ffffff"},
    SignalType.VALUE_AWAY: {"bg": "#1f5fbf", "fg": "#ffffff"},
    SignalType.VALUE_OVER: {"bg": "#0f766e", "fg": "#ffffff"},
    SignalType.VALUE_UNDER: {"bg": "#475569", "fg": "#ffffff"},
    SignalType.NO_BET: {"bg": "#6b7280", "fg": "#ffffff"},
}


def plain_signal_label(signal: SignalType, lang: str = "de", *, line: float | None = None) -> str:
    """Human tip label instead of VALUE_HOME / NO_BET."""

    entry = _SIGNAL_PLAIN[signal]
    label = entry.get(lang) or entry["de"]
    if line is not None and signal in (SignalType.VALUE_OVER, SignalType.VALUE_UNDER):
        line_s = str(line).replace(".", ",") if lang == "de" else str(line)
        # Basketball totals use large point lines; football stays on goals.
        points = float(line) >= 100.0
        if lang == "de":
            unit = "Punkte" if points else "Tore"
            prefix = "Über" if signal is SignalType.VALUE_OVER else "Unter"
            return f"Value erkannt: {prefix} {line_s} {unit}"
        unit = "points" if points else "goals"
        side = "over" if signal is SignalType.VALUE_OVER else "under"
        return f"Value spotted: {side} {line_s} {unit}"

    return label


def tip_badge_html(signal: SignalType, lang: str = "de", *, large: bool = False, text: str | None = None) -> str:
    """Colored HTML badge for beginner-friendly tip labels."""

    from html import escape

    colors = _TIP_COLORS.get(signal, _TIP_COLORS[SignalType.NO_BET])
    label = escape(text if text is not None else plain_signal_label(signal, lang))
    size = "1.15rem" if large else "0.95rem"
    pad = "0.45rem 0.85rem" if large else "0.25rem 0.65rem"
    return (
        f'<span style="display:inline-block;background:{colors["bg"]};color:{colors["fg"]};'
        f"font-weight:700;font-size:{size};padding:{pad};border-radius:999px;"
        f'letter-spacing:0.02em;">{label}</span>'
    )


# Signed metrics (edge / EV): green = favourable, red = unfavourable.
_TONE_POSITIVE = "#1b7f4a"
_TONE_NEGATIVE = "#b91c1c"
_TONE_NEUTRAL = "#6b7280"
_TONE_AMBER = "#c47a00"


def tone_color_for_signed(value: float | None, *, eps: float = 1e-9) -> str:
    """CSS color for a signed metric (edge, expected return)."""

    if value is None:
        return _TONE_NEUTRAL
    if value > eps:
        return _TONE_POSITIVE
    if value < -eps:
        return _TONE_NEGATIVE
    return _TONE_NEUTRAL


def tone_color_for_confidence(score: float) -> str:
    """CSS color for forecast-quality score 0–100."""

    if score >= 70.0:
        return _TONE_POSITIVE
    if score >= 40.0:
        return _TONE_AMBER
    return _TONE_NEUTRAL


def colored_text_html(text: str, color: str, *, bold: bool = True) -> str:
    """Inline colored span for table cells."""

    from html import escape

    weight = "700" if bold else "500"
    return (
        f'<span style="color:{color};font-weight:{weight};'
        f'white-space:nowrap;">{escape(text)}</span>'
    )


def tip_kind_from_label(label: str) -> SignalType:
    """Best-effort map of a tip label back to SignalType (for slip coloring)."""

    low = label.lower()
    if "über" in low or "over" in low:
        return SignalType.VALUE_OVER
    if "unter" in low or "under" in low:
        return SignalType.VALUE_UNDER
    if "heim" in low or "home" in low:
        return SignalType.VALUE_HOME
    if "unentschieden" in low or "draw" in low:
        return SignalType.VALUE_DRAW
    if "auswärts" in low or "away" in low:
        return SignalType.VALUE_AWAY
    return SignalType.NO_BET


def plain_reason(signal_or_text: ValueSignal | str, lang: str = "de") -> str:
    """Prefer bilingual reasons from the Decision Engine; fall back gracefully."""

    if isinstance(signal_or_text, ValueSignal):
        text = signal_or_text.plain_rationale(lang)
        if text:
            return text.split(";")[0].strip()
        signal_or_text = signal_or_text.rationale

    text = (signal_or_text or "").strip()
    if not text:
        return (
            "Keine nähere Begründung."
            if lang == "de"
            else "No further explanation."
        )
    first = text.split(";")[0].strip()
    if len(first) > 120:
        first = first[:117] + "…"
    return first


def reason_for_mode(signal: ValueSignal, mode: UXMode, lang: str = "de") -> str:
    """Expert sees technical English; others see plain language."""

    if mode is UXMode.EXPERT:
        return signal.rationale or plain_reason(signal, lang)
    return plain_reason(signal, lang)


def pages_for(mode: UXMode) -> tuple[str, ...]:
    return PAGES_BY_MODE[mode]
