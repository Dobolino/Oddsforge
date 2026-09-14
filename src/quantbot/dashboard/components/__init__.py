"""Reusable dashboard components (charts and tables)."""

from __future__ import annotations

from quantbot.dashboard.components.charts import (
    clv_distribution_figure,
    ensemble_weights_figure,
    equity_curve_figure,
    model_comparison_figure,
    reliability_diagram_figure,
    scoreline_heatmap_figure,
)
from quantbot.dashboard.components.tables import (
    beginner_tip_cards,
    colored_signals_table_html,
    metrics_dataframe,
    render_colored_signals_table,
    render_signals_table,
    signals_dataframe,
)

__all__ = [
    "clv_distribution_figure",
    "ensemble_weights_figure",
    "equity_curve_figure",
    "model_comparison_figure",
    "reliability_diagram_figure",
    "scoreline_heatmap_figure",
    "beginner_tip_cards",
    "colored_signals_table_html",
    "metrics_dataframe",
    "render_colored_signals_table",
    "render_signals_table",
    "signals_dataframe",
]
