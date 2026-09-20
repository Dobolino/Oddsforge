"""Table helpers: turn pipeline objects into pandas DataFrames for display."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

import pandas as pd

from quantbot.analysis.value import format_edge_band_pp, format_ev_pct, format_model_prob
from quantbot.backtest.metrics import BacktestMetrics
from quantbot.dashboard.ux import (
    SIGNAL_COLUMNS_BY_MODE,
    UXMode,
    colored_text_html,
    column_label,
    market_stance,
    market_stance_label,
    plain_signal_label,
    reason_for_mode,
    signal_display_line,
    stake_display,
    tip_badge_html,
    tone_color_for_confidence,
    tone_color_for_signed,
    validation_label,
)
from quantbot.orchestrator import SignalReport

SIGNAL_COLUMNS = [
    "Match",
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
]


def _chosen_model_prob(signal) -> float | None:  # type: ignore[no-untyped-def]
    if signal.chosen_outcome is None:
        return None
    for metric in signal.metrics:
        if metric.outcome is signal.chosen_outcome:
            return float(metric.model_prob)
    return None


def signals_dataframe(
    reports: Sequence[SignalReport],
    *,
    mode: UXMode = UXMode.EXPERT,
    lang: str = "de",
) -> pd.DataFrame:
    """One row per signal. Column depth follows the UX mode."""

    rows: list[dict[str, object]] = []
    for report in reports:
        s = report.signal
        m = report.match
        tip = plain_signal_label(s.signal, lang, line=signal_display_line(s))
        if mode is UXMode.BEGINNER:
            # Emoji prefix so the table tip column is scannable without HTML.
            prefix = {
                "value_home": "🟢 ",
                "value_draw": "🟡 ",
                "value_away": "🔵 ",
                "value_over": "🟢 ",
                "value_under": "⚪ ",
                "value_ah_home": "🟢 ",
                "value_ah_away": "🔵 ",
                "no_bet": "⚪ ",
            }.get(s.signal.value, "")
            tip = f"{prefix}{tip}"
        why = reason_for_mode(s, mode, lang)
        rows.append(
            {
                "Match": f"{m.home_team.name} vs {m.away_team.name}",
                "Tipp": tip,
                "Markt": market_stance_label(s, lang),
                "Begründung": why,
                "Signal": tip if mode is not UXMode.EXPERT else s.signal.value,
                "Model P": format_model_prob(_chosen_model_prob(s)),
                "Odds": "—" if s.decimal_odds is None else f"{s.decimal_odds:.2f}",
                "Edge": format_edge_band_pp(
                    s.edge,
                    model_confidence=s.model_confidence,
                    ensemble_agreement=getattr(report.analysis, "ensemble_agreement", None),
                ),
                "EV": format_ev_pct(s.expected_value),
                "Stake %": stake_display(s, lang),
                "Confidence": f"◆ {s.model_confidence:.0f}",
                "Data quality": f"{s.data_quality:.0f}",
                "Validierung": validation_label(s, lang),
                "Spiele": (
                    f"{getattr(report.analysis, 'home_matches', 0)}"
                    f"/{getattr(report.analysis, 'away_matches', 0)}"
                ),
                "Reason": why,
            }
        )
    columns = list(SIGNAL_COLUMNS_BY_MODE[mode])
    df = pd.DataFrame(rows, columns=columns)
    return df.rename(columns={c: column_label(c, lang) for c in df.columns})


def render_signals_table(df: pd.DataFrame) -> None:  # pragma: no cover - Streamlit UI
    """Show the tips table with readable column widths and horizontal scroll."""

    import streamlit as st

    config: dict[str, object] = {}
    for col in df.columns:
        if col in {
            "Match",
            "Spiel",
            "Tipp",
            "Tip",
            "Signal",
            "Begründung",
            "Reason",
        }:
            config[col] = st.column_config.TextColumn(col, width="medium")
        elif col in {"Odds", "Quote"}:
            config[col] = st.column_config.TextColumn(col, width="small", help="Dezimalquote")
        else:
            config[col] = st.column_config.TextColumn(col, width="small")
    height = min(520, 38 * max(len(df), 1) + 40)
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config=config,
        height=height,
    )


def colored_signals_table_html(
    reports: Sequence[SignalReport],
    *,
    mode: UXMode = UXMode.ADVANCED,
    lang: str = "de",
) -> str:
    """HTML signal table with tip badges and tinted edge / EV / quality."""

    if mode is UXMode.BEGINNER:
        mode = UXMode.ADVANCED
    columns = list(SIGNAL_COLUMNS_BY_MODE[mode])
    headers = "".join(
        f'<th style="text-align:left;padding:0.45rem 0.55rem;border-bottom:2px solid #d1d5db;'
        f'font-size:0.8rem;opacity:0.85;white-space:nowrap;">{escape(column_label(c, lang))}</th>'
        for c in columns
    )
    body_rows: list[str] = []
    for report in reports:
        s = report.signal
        m = report.match
        tip_text = (
            s.signal.value
            if mode is UXMode.EXPERT
            else plain_signal_label(s.signal, lang, line=signal_display_line(s))
        )
        tip_cell = tip_badge_html(s.signal, lang, text=tip_text)
        why = reason_for_mode(s, mode, lang)
        edge_txt = format_edge_band_pp(
            s.edge,
            model_confidence=s.model_confidence,
            ensemble_agreement=getattr(report.analysis, "ensemble_agreement", None),
        )
        ev_txt = format_ev_pct(s.expected_value)
        stance = market_stance(s)
        stance_cell = escape(market_stance_label(s, lang))
        if stance is not None:
            stance_cell = colored_text_html(
                stance_cell, "#1a7f37" if stance == "with" else "#c47a00"
            )
        cells: dict[str, str] = {
            "Match": escape(f"{m.home_team.name} vs {m.away_team.name}"),
            "Signal": tip_cell,
            "Markt": stance_cell,
            "Model P": escape(format_model_prob(_chosen_model_prob(s))),
            "Odds": escape("—" if s.decimal_odds is None else f"{s.decimal_odds:.2f}"),
            "Edge": colored_text_html(edge_txt, tone_color_for_signed(s.edge)),
            "EV": colored_text_html(ev_txt, tone_color_for_signed(s.expected_value)),
            "Stake %": escape(stake_display(s, lang)),
            "Confidence": colored_text_html(
                f"◆ {s.model_confidence:.0f}",
                tone_color_for_confidence(s.model_confidence),
            ),
            "Data quality": escape(f"{s.data_quality:.0f}"),
            "Validierung": escape(validation_label(s, lang)),
            "Spiele": escape(
                f"{getattr(report.analysis, 'home_matches', 0)}"
                f"/{getattr(report.analysis, 'away_matches', 0)}"
            ),
            "Reason": escape(why),
        }
        tds = "".join(
            f'<td style="padding:0.5rem 0.55rem;border-bottom:1px solid #e5e7eb;'
            f'vertical-align:middle;font-size:0.9rem;">{cells[c]}</td>'
            for c in columns
        )
        body_rows.append(f"<tr>{tds}</tr>")
    if not body_rows:
        empty = "Keine Spiele." if lang.startswith("de") else "No matches."
        body_rows.append(
            f'<tr><td colspan="{len(columns)}" style="padding:0.75rem;opacity:0.7;">'
            f"{escape(empty)}</td></tr>"
        )
    return (
        '<div style="overflow-x:auto;max-width:100%;">'
        '<table style="border-collapse:collapse;width:100%;min-width:640px;">'
        f"<thead><tr>{headers}</tr></thead>"
        f'<tbody>{"".join(body_rows)}</tbody>'
        "</table></div>"
    )


def render_colored_signals_table(
    reports: Sequence[SignalReport],
    *,
    mode: UXMode = UXMode.ADVANCED,
    lang: str = "de",
) -> None:  # pragma: no cover - Streamlit UI
    """Render Advanced/Pro tips with color (badges + signed metrics)."""

    import streamlit as st

    st.html(colored_signals_table_html(reports, mode=mode, lang=lang))


def beginner_tip_cards(
    reports: Sequence[SignalReport],
    *,
    lang: str = "de",
    limit: int = 5,
) -> list[dict[str, str]]:
    """Top value tips for the beginner home view (bets first, then no-bets)."""

    from quantbot.analysis.value import format_edge_band_pp, format_model_prob

    bets = [r for r in reports if r.signal.is_bet]
    bets.sort(key=lambda r: (-float(r.signal.edge or 0.0), r.match.kickoff))
    others = [r for r in reports if not r.signal.is_bet]
    ordered = bets + others
    cards: list[dict[str, str]] = []
    for report in ordered[:limit]:
        s = report.signal
        m = report.match
        model_p = _chosen_model_prob(s)
        quality = report.analysis.confidence_level.value
        quality_lbl = {
            "high": "Hoch" if lang == "de" else "High",
            "medium": "Mittel" if lang == "de" else "Medium",
            "low": "Niedrig" if lang == "de" else "Low",
        }.get(quality, quality)
        cards.append(
            {
                "match": f"{m.home_team.name} vs {m.away_team.name}",
                "tip": plain_signal_label(s.signal, lang, line=signal_display_line(s)),
                "tip_html": tip_badge_html(
                    s.signal, lang, large=True, text=plain_signal_label(s.signal, lang, line=signal_display_line(s))
                ),
                "tip_html_small": tip_badge_html(
                    s.signal, lang, large=False, text=plain_signal_label(s.signal, lang, line=signal_display_line(s))
                ),
                "why": reason_for_mode(s, UXMode.BEGINNER, lang),
                "is_bet": "1" if s.is_bet else "0",
                "signal": s.signal.value,
                "model_p": format_model_prob(model_p, digits=0),
                "edge_pp": format_edge_band_pp(
                    s.edge,
                    model_confidence=s.model_confidence,
                    ensemble_agreement=getattr(report.analysis, "ensemble_agreement", None),
                    digits=1,
                ),
                "quality": quality_lbl,
                "validation": validation_label(s, lang),
                "reason_codes": ", ".join(s.reason_codes),
            }
        )
    return cards


def metrics_dataframe(
    metrics: BacktestMetrics,
    *,
    mode: UXMode = UXMode.EXPERT,
) -> pd.DataFrame:
    """Two-column (Metric, Value) frame of formatted backtest metrics."""

    def pct(x: float) -> str:
        return f"{x * 100:.2f}%"

    basic = [
        ("Bets placed", str(metrics.n_bets)),
        ("ROI (yield)", pct(metrics.roi)),
        ("Win rate", pct(metrics.win_rate)),
        ("Max drawdown", pct(metrics.max_drawdown)),
    ]
    advanced = [
        ("Total return", pct(metrics.total_return)),
        ("Profit factor", f"{metrics.profit_factor:.2f}"),
        (
            "Beat-CLV rate",
            "-" if metrics.beat_clv_rate is None else pct(metrics.beat_clv_rate),
        ),
    ]
    expert = [
        ("Total staked", f"{metrics.total_staked:.2f}"),
        ("Total PnL", f"{metrics.total_pnl:.2f}"),
        ("Sharpe", f"{metrics.sharpe:.3f}"),
        ("Sortino", f"{metrics.sortino:.3f}"),
        ("Avg CLV", "-" if metrics.avg_clv is None else f"{metrics.avg_clv:.4f}"),
    ]

    if mode is UXMode.BEGINNER:
        rows = basic
    elif mode is UXMode.ADVANCED:
        rows = basic + advanced
    else:
        rows = basic + advanced + expert
    return pd.DataFrame(rows, columns=["Metric", "Value"])
