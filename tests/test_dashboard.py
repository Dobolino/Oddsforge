"""Tests for dashboard chart/table helpers, import stability, and the launcher."""

from __future__ import annotations

import importlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest
from typer.testing import CliRunner

from quantbot.cli import app
from quantbot.dashboard.components import charts, tables
from quantbot.orchestrator import QuantBotOrchestrator
from quantbot.schemas import League

runner = CliRunner()
SEASON = "2024-2025"


# --- Import stability ---


def test_dashboard_modules_import() -> None:
    for module in (
        "quantbot.dashboard",
        "quantbot.dashboard.app",
        "quantbot.dashboard.components",
        "quantbot.dashboard.components.charts",
        "quantbot.dashboard.components.tables",
    ):
        assert importlib.import_module(module) is not None


def test_app_path_points_to_app() -> None:
    from quantbot.dashboard import app_path

    path = app_path()
    assert path.name == "app.py"
    assert path.exists()


def test_resolve_season_falls_back_to_available() -> None:
    from quantbot.dashboard.app import _resolve_season

    class _Prov:
        def available_seasons(self) -> list[str]:
            return ["2025-2026", "2024-2025"]

    season, note = _resolve_season(_Prov(), "2026-2027", live=True)
    assert season == "2025-2026"
    assert note == "no_matches_season_fallback"

    season, note = _resolve_season(_Prov(), "2025-2026", live=True)
    assert season == "2025-2026"
    assert note is None

    season, note = _resolve_season(_Prov(), "2026-2027", live=False)
    assert season == "2026-2027"
    assert note is None


# --- Chart helpers ---


def test_equity_curve_figure() -> None:
    fig = charts.equity_curve_figure([1000.0, 1050.0, 990.0], initial_bankroll=1000.0)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 1
    assert list(fig.data[0].y) == [1000.0, 1050.0, 990.0]


def test_scoreline_heatmap_figure_trims() -> None:
    matrix = (np.ones((11, 11)) / 121.0).tolist()
    fig = charts.scoreline_heatmap_figure(matrix, max_display=5)
    assert isinstance(fig, go.Figure)
    z = np.asarray(fig.data[0].z)
    assert z.shape == (6, 6)  # max_display + 1


def test_scoreline_heatmap_rejects_non_2d() -> None:
    with pytest.raises(ValueError, match="2D"):
        charts.scoreline_heatmap_figure([0.1, 0.2, 0.3])


def test_ensemble_weights_figure() -> None:
    fig = charts.ensemble_weights_figure(["elo", "logistic"], [0.6, 0.4])
    assert isinstance(fig, go.Figure)
    assert list(fig.data[0].x) == ["elo", "logistic"]
    assert list(fig.data[0].y) == [0.6, 0.4]


def test_ensemble_weights_length_mismatch() -> None:
    with pytest.raises(ValueError, match="equal length"):
        charts.ensemble_weights_figure(["a", "b"], [1.0])


def test_clv_distribution_figure() -> None:
    fig = charts.clv_distribution_figure([0.05, -0.02, 0.10, None])
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1


def test_clv_distribution_empty() -> None:
    fig = charts.clv_distribution_figure([])
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def test_model_comparison_figure() -> None:
    fig = charts.model_comparison_figure({"Elo": [0.5, 0.3, 0.2], "DC": [0.45, 0.3, 0.25]})
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2


# --- Table helpers ---


def test_signals_dataframe_columns() -> None:
    from quantbot.dashboard.ux import UXMode, column_label

    orchestrator = QuantBotOrchestrator()
    reports = orchestrator.predict(League.PREMIER_LEAGUE, SEASON)
    df = tables.signals_dataframe(reports, lang="de")
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == [column_label(c, "de") for c in tables.SIGNAL_COLUMNS]
    assert len(df) == len(reports)

    beginner = tables.signals_dataframe(reports, mode=UXMode.BEGINNER, lang="de")
    assert list(beginner.columns) == ["Spiel", "Tipp", "Begründung"]
    assert len(beginner) == len(reports)

    en = tables.signals_dataframe(reports, mode=UXMode.ADVANCED, lang="en")
    assert "Odds" in list(en.columns)

    cards = tables.beginner_tip_cards(reports, lang="de", limit=3)
    assert len(cards) <= 3
    assert {"match", "tip", "why", "is_bet"} <= set(cards[0])

    colored = tables.colored_signals_table_html(reports, mode=UXMode.ADVANCED, lang="de")
    assert "<table" in colored
    assert "background:#" in colored  # tip badge
    assert "Edge (pp)" in colored or "Edge" in colored
    expert = tables.colored_signals_table_html(reports, mode=UXMode.EXPERT, lang="en")
    assert "Forecast quality" in expert
    assert "Data quality" in expert


def test_metrics_dataframe() -> None:
    from quantbot.dashboard.ux import UXMode

    orchestrator = QuantBotOrchestrator()
    result = orchestrator.run_backtest(League.PREMIER_LEAGUE, SEASON)
    df = tables.metrics_dataframe(result.metrics)
    assert list(df.columns) == ["Metric", "Value"]
    assert "ROI (yield)" in set(df["Metric"])
    assert "Sharpe" in set(df["Metric"])

    basic = tables.metrics_dataframe(result.metrics, mode=UXMode.BEGINNER)
    assert "Sharpe" not in set(basic["Metric"])
    assert "ROI (yield)" in set(basic["Metric"])


# --- CLI launcher ---


def test_dashboard_command_dry_run() -> None:
    result = runner.invoke(app, ["dashboard", "--dry-run", "--port", "9000"])
    assert result.exit_code == 0
    assert "streamlit" in result.stdout
    assert "run" in result.stdout
    assert "9000" in result.stdout
