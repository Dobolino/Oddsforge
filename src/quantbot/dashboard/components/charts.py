"""Plotly chart helpers for the dashboard.

Pure functions: each takes plain data and returns a ``plotly.graph_objects``
Figure. They do not import Streamlit, so they are unit-testable in isolation.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import plotly.graph_objects as go


def equity_curve_figure(
    bankroll_curve: Sequence[float], initial_bankroll: float | None = None
) -> go.Figure:
    """Line chart of bankroll over settled bets."""

    y = list(bankroll_curve)
    x = list(range(len(y)))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers", name="Bankroll"))
    baseline = initial_bankroll if initial_bankroll is not None else (y[0] if y else 0.0)
    if y:
        fig.add_hline(y=baseline, line_dash="dash", line_color="gray")
    fig.update_layout(
        title="Bankroll Equity Curve",
        xaxis_title="Settled bet #",
        yaxis_title="Bankroll",
        template="plotly_white",
    )
    return fig


def scoreline_heatmap_figure(matrix: Sequence[Sequence[float]], max_display: int = 6) -> go.Figure:
    """Heatmap of the Dixon-Coles scoreline probability matrix.

    Rows are home goals, columns away goals. Trimmed to ``max_display`` per
    side for readability.
    """

    grid = np.asarray(matrix, dtype=float)
    if grid.ndim != 2:
        raise ValueError("matrix must be 2D")
    n = min(max_display + 1, grid.shape[0], grid.shape[1])
    grid = grid[:n, :n]
    labels = [str(i) for i in range(n)]
    fig = go.Figure(
        data=go.Heatmap(
            z=grid,
            x=labels,
            y=labels,
            colorscale="Blues",
            colorbar={"title": "P"},
        )
    )
    fig.update_layout(
        title="Scoreline Probabilities (Dixon-Coles)",
        xaxis_title="Away goals",
        yaxis_title="Home goals",
        template="plotly_white",
    )
    return fig


def ensemble_weights_figure(names: Sequence[str], weights: Sequence[float]) -> go.Figure:
    """Bar chart of ensemble sub-model weights."""

    if len(names) != len(weights):
        raise ValueError("names and weights must have equal length")
    fig = go.Figure(data=go.Bar(x=list(names), y=list(weights), marker_color="#2a6fdb"))
    fig.update_layout(
        title="Ensemble Model Weights",
        xaxis_title="Model",
        yaxis_title="Weight",
        yaxis_range=[0, 1],
        template="plotly_white",
    )
    return fig


def clv_distribution_figure(clvs: Sequence[float]) -> go.Figure:
    """Histogram of Closing Line Value across settled bets."""

    values = [c for c in clvs if c is not None]
    fig = go.Figure()
    if values:
        fig.add_trace(go.Histogram(x=values, nbinsx=20, marker_color="#2a6fdb"))
        fig.add_vline(x=0.0, line_dash="dash", line_color="red")
    fig.update_layout(
        title="Closing Line Value Distribution",
        xaxis_title="CLV (entry / closing - 1)",
        yaxis_title="Count",
        template="plotly_white",
    )
    return fig


def model_comparison_figure(
    model_probs: dict[str, Sequence[float]], outcome_labels: Sequence[str] = ("Home", "Draw", "Away")
) -> go.Figure:
    """Grouped bar chart comparing 1X2 probabilities across models."""

    fig = go.Figure()
    for name, probs in model_probs.items():
        fig.add_trace(go.Bar(name=name, x=list(outcome_labels), y=list(probs)))
    fig.update_layout(
        title="Model Probability Comparison",
        barmode="group",
        yaxis_title="Probability",
        yaxis_range=[0, 1],
        template="plotly_white",
    )
    return fig
