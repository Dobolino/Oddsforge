"""Batch 2 tests: calibration curve, model comparison, backtest breakdowns."""

from __future__ import annotations

import numpy as np

from quantbot.analysis.evaluation import (
    calibration_report,
    model_comparison,
    reliability_curve,
    walk_forward_probabilities,
)
from quantbot.backtest import by_edge, by_league, by_month, by_odds
from quantbot.backtest.execution import SettledBet
from quantbot.data import DummyDataProvider
from quantbot.models import DixonColesModel, EloModel, LogisticRegressionModel
from quantbot.schemas import League, MatchOutcome

SEASON = "2024-2025"
FAR = __import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc)


def _universe() -> list:
    p = DummyDataProvider()
    return p.get_matches(League.PREMIER_LEAGUE, SEASON, FAR) + p.get_matches(League.BUNDESLIGA, SEASON, FAR)


# --- Walk-forward evaluation ---


def test_walk_forward_probabilities_leak_free_shape() -> None:
    probs, labels = walk_forward_probabilities(_universe(), EloModel())
    assert probs.shape[0] == labels.shape[0]
    assert probs.shape[1] == 3
    # Each row is a valid distribution.
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-6)
    assert set(np.unique(labels)).issubset({0, 1, 2})


def test_reliability_curve_bins() -> None:
    probs, labels = walk_forward_probabilities(_universe(), EloModel())
    curve = reliability_curve(probs, labels, n_bins=5)
    assert curve
    for b in curve:
        assert 0.0 <= b["confidence"] <= 1.0
        assert 0.0 <= b["accuracy"] <= 1.0
        assert b["count"] >= 1


def test_reliability_curve_empty() -> None:
    assert reliability_curve(np.empty((0, 3)), np.empty((0,), dtype=int)) == []


def test_model_comparison_sorted_by_brier() -> None:
    rows = model_comparison(
        {
            "elo": EloModel(),
            "dixon_coles": DixonColesModel(min_matches=5),
            "logistic": LogisticRegressionModel(),
        },
        _universe(),
    )
    assert {r["model"] for r in rows} == {"elo", "dixon_coles", "logistic"}
    briers = [r["brier"] for r in rows if r["brier"] is not None]
    assert briers == sorted(briers)  # best (lowest) first


def test_calibration_report_has_curve_and_metrics() -> None:
    report = calibration_report(_universe(), EloModel())
    assert report["n"] > 0
    assert report["curve"]
    assert report["brier"] is not None and report["log_loss"] is not None


# --- Backtest breakdowns ---


def _bet(odds: float, edge: float, pnl: float, won: bool, league: str, month: str) -> SettledBet:
    return SettledBet(
        match_id="m",
        outcome=MatchOutcome.HOME,
        stake=50.0,
        entry_odds=odds,
        closing_odds=None,
        actual_outcome=MatchOutcome.HOME if won else MatchOutcome.AWAY,
        won=won,
        pnl=pnl,
        model_prob=0.5,
        clv=None,
        beat_closing=None,
        edge=edge,
        league=league,
        kickoff=f"{month}-15",
    )


def test_breakdown_by_odds_and_edge() -> None:
    bets = [
        _bet(1.4, 0.01, -50.0, False, "premier_league", "2024-08"),
        _bet(1.8, 0.04, 40.0, True, "premier_league", "2024-08"),
        _bet(2.5, 0.09, 75.0, True, "bundesliga", "2024-09"),
        _bet(3.5, 0.15, -50.0, False, "bundesliga", "2024-09"),
    ]
    odds_rows = by_odds(bets)
    assert odds_rows and all("roi" in r for r in odds_rows)
    assert sum(r["n"] for r in odds_rows) == 4

    edge_rows = by_edge(bets)
    assert sum(r["n"] for r in edge_rows) == 4


def test_breakdown_by_league_and_month() -> None:
    bets = [
        _bet(2.0, 0.05, 50.0, True, "premier_league", "2024-08"),
        _bet(2.0, 0.05, -50.0, False, "bundesliga", "2024-09"),
    ]
    leagues = by_league(bets)
    assert {r["label"] for r in leagues} == {"premier_league", "bundesliga"}
    months = by_month(bets)
    assert {r["label"] for r in months} == {"2024-08", "2024-09"}
    for r in leagues:
        assert 0.0 <= r["hit_rate"] <= 100.0
