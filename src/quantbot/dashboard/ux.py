"""User-experience depth modes for the dashboard.

Three levels so a complete beginner can open the app without drowning in
metrics, while experts still get the full toolkit.

- beginner: one tip, one reason, safety first. Few pages.
- advanced: probabilities, edge, stake, match card, backtest.
- expert: every page and every metric.
"""

from __future__ import annotations

from enum import Enum

from quantbot.schemas import SignalType


class UXMode(str, Enum):
    BEGINNER = "beginner"
    ADVANCED = "advanced"
    EXPERT = "expert"


# Pages visible in the sidebar, in display order.
PAGES_BY_MODE: dict[UXMode, tuple[str, ...]] = {
    UXMode.BEGINNER: ("signals", "tracker", "glossary"),
    UXMode.ADVANCED: ("signals", "card", "tracker", "backtest", "glossary"),
    UXMode.EXPERT: (
        "signals",
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

# Ordered checks: more specific needles first, then fall through.
_REASON_MAP: tuple[tuple[str, dict[str, str]], ...] = (
    ("data quality", {
        "de": "Zu wenig verlässliche Daten für dieses Spiel.",
        "en": "Not enough reliable data for this match.",
    }),
    ("model confidence", {
        "de": "Das Modell ist sich hier zu unsicher.",
        "en": "The model is too uncertain here.",
    }),
    ("overround", {
        "de": "Die Buchmacher-Marge ist zu hoch.",
        "en": "The bookmaker margin is too high.",
    }),
    ("edge ", {
        "de": "Der Vorteil gegenüber dem Markt ist zu gering.",
        "en": "The edge versus the market is too small.",
    }),
    ("ev ", {
        "de": "Der erwartete Gewinn ist zu gering.",
        "en": "The expected value is too low.",
    }),
    ("odds ", {
        "de": "Die Quote liegt ausserhalb des sinnvollen Bereichs.",
        "en": "The odds are outside a sensible range.",
    }),
    ("kelly stake rounds to zero", {
        "de": "Der sinnvolle Einsatz wäre praktisch null.",
        "en": "A sensible stake would be practically zero.",
    }),
    ("value on", {
        "de": "Das Modell sieht hier einen Vorteil gegenüber dem Markt.",
        "en": "The model sees an advantage versus the market here.",
    }),
)


def plain_signal_label(signal: SignalType, lang: str = "de") -> str:
    """Human tip label instead of VALUE_HOME / NO_BET."""

    entry = _SIGNAL_PLAIN[signal]
    return entry.get(lang) or entry["de"]


def plain_reason(rationale: str, lang: str = "de") -> str:
    """Turn a technical decision rationale into one short sentence."""

    text = (rationale or "").lower()
    if not text:
        return (
            "Keine nähere Begründung."
            if lang == "de"
            else "No further explanation."
        )

    # Prefer the value-on phrasing for positive tips.
    if text.startswith("value on"):
        mapped = _REASON_MAP[-1][1]
        return mapped.get(lang) or mapped["de"]

    for needle, mapped in _REASON_MAP:
        if needle in text:
            return mapped.get(lang) or mapped["de"]

    # Fallback: keep first clause, truncated.
    first = rationale.split(";")[0].strip()
    if len(first) > 120:
        first = first[:117] + "…"
    return first


def pages_for(mode: UXMode) -> tuple[str, ...]:
    return PAGES_BY_MODE[mode]
