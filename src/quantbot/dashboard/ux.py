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
    UXMode.BEGINNER: ("signals", "slip", "tracker", "glossary"),
    UXMode.ADVANCED: ("signals", "slip", "card", "tracker", "backtest", "glossary"),
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
        "glossary",
    ),
}

# Signal table columns by depth (keys match tables.signals_dataframe output).
SIGNAL_COLUMNS_BY_MODE: dict[UXMode, tuple[str, ...]] = {
    UXMode.BEGINNER: ("Match", "Tipp", "Begründung"),
    UXMode.ADVANCED: ("Match", "Signal", "Odds", "Edge", "EV", "Stake %", "Reason"),
    UXMode.EXPERT: (
        "Match",
        "Signal",
        "Odds",
        "Edge",
        "EV",
        "Stake %",
        "Confidence",
        "Data quality",
        "Reason",
    ),
}

_SIGNAL_PLAIN: dict[SignalType, dict[str, str]] = {
    SignalType.VALUE_HOME: {"de": "Tipp: Heimsieg", "en": "Tip: home win"},
    SignalType.VALUE_DRAW: {"de": "Tipp: Unentschieden", "en": "Tip: draw"},
    SignalType.VALUE_AWAY: {"de": "Tipp: Auswärtssieg", "en": "Tip: away win"},
    SignalType.NO_BET: {"de": "Kein Tipp", "en": "No tip"},
}


def plain_signal_label(signal: SignalType, lang: str = "de") -> str:
    """Human tip label instead of VALUE_HOME / NO_BET."""

    entry = _SIGNAL_PLAIN[signal]
    return entry.get(lang) or entry["de"]


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
