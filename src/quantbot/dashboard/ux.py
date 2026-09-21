"""User-experience depth modes for the dashboard.

Three levels so a complete beginner can open the app without drowning in
metrics, while experts still get the full toolkit.

- beginner: one model signal, one reason, safety first. Few pages.
- advanced: probabilities, edge, stake (when released), match card, backtest.
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
    UXMode.ADVANCED: (
        "signals",
        "slip",
        "paper",
        "card",
        "tracker",
        "calibration",
        "backtest",
        "settings",
        "glossary",
    ),
    UXMode.EXPERT: (
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
    ),
}

# Signal table columns by depth (keys match tables.signals_dataframe output).
# Internal keys stay English; display labels are localized in the table builder.
SIGNAL_COLUMNS_BY_MODE: dict[UXMode, tuple[str, ...]] = {
    UXMode.BEGINNER: ("Match", "Kickoff", "Tipp", "Markt", "Spiele", "Validierung", "Begründung"),
    UXMode.ADVANCED: (
        "Match",
        "Kickoff",
        "Signal",
        "Markt",
        "Model P",
        "Odds",
        "Edge",
        "EV",
        "Stake %",
        "Validierung",
        "Spiele",
        "Reason",
    ),
    UXMode.EXPERT: (
        "Match",
        "Kickoff",
        "Signal",
        "Markt",
        "Model P",
        "Odds",
        "Edge",
        "EV",
        "Stake %",
        "Confidence",
        "Data quality",
        "Validierung",
        "Spiele",
        "Reason",
    ),
}

_COLUMN_LABELS: dict[str, dict[str, str]] = {
    "Match": {"de": "Spiel", "en": "Match"},
    "Kickoff": {"de": "Anstoß", "en": "Kickoff"},
    "Tipp": {"de": "Modell-Signal", "en": "Model signal"},
    "Begründung": {"de": "Begründung", "en": "Reason"},
    "Signal": {"de": "Modell-Signal", "en": "Model signal"},
    "Model P": {"de": "Modell-P", "en": "Model P"},
    "Odds": {"de": "Quote", "en": "Odds"},
    "Edge": {"de": "Statistische Abweichung (pp)", "en": "Model-market gap (pp)"},
    "EV": {"de": "Geschätzter Nettoertrag", "en": "Estimated net return"},
    "Stake %": {"de": "Papier-Einsatz %", "en": "Paper stake %"},
    "Confidence": {"de": "Modellübereinstimmung", "en": "Model agreement"},
    "Data quality": {"de": "Datenabdeckung", "en": "Data coverage"},
    "Validierung": {"de": "Validierung", "en": "Validation"},
    "Spiele": {"de": "Spiele (H/A)", "en": "Games (H/A)"},
    "Markt": {"de": "Marktbezug", "en": "Market stance"},
    "Reason": {"de": "Begründung", "en": "Reason"},
}


def column_label(key: str, lang: str = "de") -> str:
    entry = _COLUMN_LABELS.get(key, {})
    if lang.startswith("de"):
        return entry.get("de", key)
    return entry.get("en", key)


_STANCE_LABELS: dict[str, dict[str, str]] = {
    "with": {"de": "Näher am Markt", "en": "Closer to market"},
    "against": {
        "de": "Größere Abweichung (kein Vorteil)",
        "en": "Larger deviation (not an edge)",
    },
}


def market_stance(signal: ValueSignal) -> str | None:
    """Is the tipped side the market favorite, or a pick against the market?

    Returns ``"with"`` when the chosen outcome has the highest fair market
    probability of the market's options (betting the favorite), ``"against"``
    when the model backs a less likely side (a contrarian value pick), or
    ``None`` for a no-bet.
    """

    if not signal.is_bet or signal.chosen_outcome is None or not signal.metrics:
        return None
    chosen = next(
        (m for m in signal.metrics if m.outcome is signal.chosen_outcome), None
    )
    if chosen is None:
        return None
    top_fp = max(m.fair_market_prob for m in signal.metrics)
    return "with" if chosen.fair_market_prob >= top_fp - 1e-9 else "against"


def market_stance_label(signal: ValueSignal, lang: str = "de") -> str:
    """Human label for the market stance, or ``—`` for no-bet."""

    stance = market_stance(signal)
    if stance is None:
        return "—"
    entry = _STANCE_LABELS[stance]
    return entry.get(lang) or entry["de"]


def validation_label(signal: ValueSignal, lang: str = "de") -> str:
    """Short validation / decision-status label for tables and cards."""

    status = (signal.validation_status or "unvalidated").lower()
    decision = (signal.decision_status or "").lower()
    if decision == "value_exploratory" or (
        signal.is_bet and not signal.sizing_allowed
    ):
        return "explorativ" if lang.startswith("de") else "exploratory"
    labels = {
        "unvalidated": ("unvalidiert", "unvalidated"),
        "valid": ("freigegeben", "released"),
        "degraded": ("eingeschränkt", "degraded"),
        "expired": ("abgelaufen", "expired"),
    }
    de, en = labels.get(status, (status, status))
    return de if lang.startswith("de") else en


def stake_display(signal: ValueSignal, lang: str = "de") -> str:
    """Stake % only when sizing is released; otherwise an honest placeholder."""

    if signal.sizing_allowed and signal.stake_fraction > 0.0:
        return f"{signal.stake_fraction * 100.0:.2f}"
    if signal.is_bet:
        return "—" if lang.startswith("de") else "—"
    return "0.00"


_SIGNAL_PLAIN: dict[SignalType, dict[str, str]] = {
    # Claude review: avoid “Empfehlung”; prefer neutral value language.
    SignalType.VALUE_HOME: {"de": "Value erkannt: Heimsieg", "en": "Value spotted: home win"},
    SignalType.VALUE_DRAW: {"de": "Value erkannt: Unentschieden", "en": "Value spotted: draw"},
    SignalType.VALUE_AWAY: {"de": "Value erkannt: Auswärtssieg", "en": "Value spotted: away win"},
    SignalType.VALUE_OVER: {"de": "Value erkannt: Über 2,5 Tore", "en": "Value spotted: over 2.5 goals"},
    SignalType.VALUE_UNDER: {"de": "Value erkannt: Unter 2,5 Tore", "en": "Value spotted: under 2.5 goals"},
    SignalType.VALUE_AH_HOME: {"de": "Value erkannt: AH Heim", "en": "Value spotted: AH home"},
    SignalType.VALUE_AH_AWAY: {"de": "Value erkannt: AH Auswärts", "en": "Value spotted: AH away"},
    SignalType.NO_BET: {"de": "Kein Signal", "en": "No signal"},
}

# Clear beginner colors: home = green, draw = amber, away = blue,
# over = teal, under = slate, no tip = gray.
_TIP_COLORS: dict[SignalType, dict[str, str]] = {
    SignalType.VALUE_HOME: {"bg": "#1b7f4a", "fg": "#ffffff"},
    SignalType.VALUE_DRAW: {"bg": "#c47a00", "fg": "#ffffff"},
    SignalType.VALUE_AWAY: {"bg": "#1f5fbf", "fg": "#ffffff"},
    SignalType.VALUE_OVER: {"bg": "#0f766e", "fg": "#ffffff"},
    SignalType.VALUE_UNDER: {"bg": "#475569", "fg": "#ffffff"},
    SignalType.VALUE_AH_HOME: {"bg": "#047857", "fg": "#ffffff"},
    SignalType.VALUE_AH_AWAY: {"bg": "#1d4ed8", "fg": "#ffffff"},
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

    if line is not None and signal in (SignalType.VALUE_AH_HOME, SignalType.VALUE_AH_AWAY):
        line_s = str(line).replace(".", ",") if lang == "de" else str(line)
        if lang == "de":
            side = "Heim" if signal is SignalType.VALUE_AH_HOME else "Auswärts"
            return f"Value erkannt: AH {side} {line_s}"
        side = "home" if signal is SignalType.VALUE_AH_HOME else "away"
        return f"Value spotted: AH {side} {line_s}"

    return label


def signal_display_line(signal) -> float | None:  # type: ignore[no-untyped-def]
    """Totals or AH line for plain labels / badges."""

    if getattr(signal, "totals_line", None) is not None:
        return float(signal.totals_line)
    if getattr(signal, "handicap_line", None) is not None:
        return float(signal.handicap_line)
    return None


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
    if low.startswith("ah_home") or "ah heim" in low or ("ah" in low and "home" in low):
        return SignalType.VALUE_AH_HOME
    if low.startswith("ah_away") or "ah auswärts" in low or ("ah" in low and "away" in low):
        return SignalType.VALUE_AH_AWAY
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
