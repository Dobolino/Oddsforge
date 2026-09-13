"""CLI tests via Typer's CliRunner."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from quantbot.cli import app

runner = CliRunner()


def test_info_command() -> None:
    result = runner.invoke(app, ["info", "--lang", "en"])
    assert result.exit_code == 0
    assert "QuantBot" in result.stdout
    assert "disabled" in result.stdout  # automated betting guardrail


def test_status_alias() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "QuantBot" in result.stdout


def test_predict_command_default() -> None:
    result = runner.invoke(app, ["predict", "--lang", "en"])
    assert result.exit_code == 0
    assert "Signals" in result.stdout
    assert "evaluated" in result.stdout


def test_predict_command_with_options() -> None:
    result = runner.invoke(
        app,
        ["predict", "--league", "bundesliga", "--season", "2024-2025", "--as-of", "2024-10-15"],
    )
    assert result.exit_code == 0
    assert "bundesliga" in result.stdout


def test_predict_rejects_bad_date() -> None:
    result = runner.invoke(app, ["predict", "--as-of", "15-10-2024"])
    assert result.exit_code != 0


def test_backtest_command() -> None:
    result = runner.invoke(app, ["backtest", "--league", "premier_league", "--lang", "en"])
    assert result.exit_code == 0
    assert "Backtest" in result.stdout
    assert "ROI" in result.stdout
    assert "Max drawdown" in result.stdout


def test_backtest_custom_bankroll() -> None:
    result = runner.invoke(app, ["backtest", "--bankroll", "5000"])
    assert result.exit_code == 0
    assert "5000" in result.stdout


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    # no_args_is_help exits with code 0 or 2 depending on version; output has usage.
    assert "Usage" in result.stdout or "Commands" in result.stdout
