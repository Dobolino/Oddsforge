"""QuantBot Streamlit dashboard.

Run with ``quantbot dashboard`` (or ``streamlit run <this file>``). The UI is
executed only when the module runs as the Streamlit entry script, so importing
it for tests stays side-effect free.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from quantbot import __version__
from quantbot.dashboard.components import (
    clv_distribution_figure,
    ensemble_weights_figure,
    equity_curve_figure,
    metrics_dataframe,
    model_comparison_figure,
    scoreline_heatmap_figure,
    signals_dataframe,
)


def _render() -> None:  # pragma: no cover - requires Streamlit runtime
    # Imports kept local so module import stays cheap and side-effect free.
    from quantbot.models import DixonColesModel, EloModel, LogisticRegressionModel
    from quantbot.orchestrator import QuantBotOrchestrator
    from quantbot.schemas import League

    st.set_page_config(page_title="QuantBot", page_icon="⚽", layout="wide")
    st.sidebar.title(f"QuantBot v{__version__}")
    st.sidebar.caption("Decision support only. No automated betting.")

    page = st.sidebar.radio(
        "Page",
        ["Upcoming Value Signals", "Model Insights & Scorelines", "Backtest Performance"],
    )
    league = st.sidebar.selectbox("League", list(League), format_func=lambda lg: lg.value)
    season = st.sidebar.text_input("Season", "2024-2025")

    orchestrator = QuantBotOrchestrator()
    universe = orchestrator.universe(league, season)

    if page == "Upcoming Value Signals":
        st.header("Upcoming Value Signals")
        default_as_of = orchestrator.default_as_of(league, season).date()
        as_of_date = st.date_input("Prediction date (as of)", default_as_of)
        as_of = datetime(as_of_date.year, as_of_date.month, as_of_date.day, tzinfo=timezone.utc)
        reports = orchestrator.predict(league, season, as_of)
        n_bets = sum(1 for r in reports if r.signal.is_bet)
        col1, col2 = st.columns(2)
        col1.metric("Matches evaluated", len(reports))
        col2.metric("Value signals", n_bets)
        st.dataframe(signals_dataframe(reports), use_container_width=True)

    elif page == "Model Insights & Scorelines":
        st.header("Model Insights & Scorelines")
        as_of = orchestrator.default_as_of(league, season)
        upcoming = [m for m in universe if m.kickoff > as_of]
        if not upcoming:
            st.warning("No upcoming matches for this as-of date.")
            return
        match = st.selectbox(
            "Match",
            upcoming,
            format_func=lambda m: f"{m.home_team.name} vs {m.away_team.name}",
        )

        elo = EloModel()
        logistic = LogisticRegressionModel()
        dixon = DixonColesModel(min_matches=10)
        model_probs: dict[str, list[float]] = {}
        for name, model in (("Elo", elo), ("Logistic", logistic), ("Dixon-Coles", dixon)):
            try:
                model.fit_until(universe, as_of)
                pred = model.predict(match)
                model_probs[name] = [pred.prob_home, pred.prob_draw, pred.prob_away]
            except (ValueError, RuntimeError):
                st.info(f"{name}: insufficient history to fit.")

        if model_probs:
            st.plotly_chart(model_comparison_figure(model_probs), use_container_width=True)

        try:
            dixon.fit_until(universe, as_of)
            dc_pred = dixon.predict(match)
            if dc_pred.score_matrix is not None:
                st.plotly_chart(
                    scoreline_heatmap_figure(dc_pred.score_matrix.matrix),
                    use_container_width=True,
                )
        except (ValueError, RuntimeError):
            st.info("Dixon-Coles: insufficient history for a scoreline matrix.")

    else:  # Backtest Performance
        st.header("Backtest Performance")
        result = orchestrator.run_backtest(league, season)
        m = result.metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("ROI", f"{m.roi * 100:.2f}%")
        col2.metric("Sharpe", f"{m.sharpe:.3f}")
        col3.metric("Max drawdown", f"{m.max_drawdown * 100:.2f}%")
        col4.metric(
            "Beat-CLV rate",
            "-" if m.beat_clv_rate is None else f"{m.beat_clv_rate * 100:.1f}%",
        )
        st.plotly_chart(
            equity_curve_figure(result.bankroll_curve, result.initial_bankroll),
            use_container_width=True,
        )
        clvs = [b.clv for b in result.settled_bets if b.clv is not None]
        if clvs:
            st.plotly_chart(clv_distribution_figure(clvs), use_container_width=True)
        st.subheader("Metrics")
        st.table(metrics_dataframe(m))


if __name__ == "__main__":
    _render()
