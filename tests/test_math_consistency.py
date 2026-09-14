"""Mathematical consistency of edge, EV, Kelly and displayed formats.

The dashboard must never show figures that disagree with
``edge = p_model - p_market`` and ``EV = p * odds - 1``.
"""

from __future__ import annotations

import pytest

from quantbot.analysis.value import (
    assert_metrics_consistent,
    edge,
    expected_value,
    format_edge_pp,
    format_ev_pct,
    format_model_prob,
    relative_edge,
)
from quantbot.decision.sizing import KellySizer
from quantbot.orchestrator import QuantBotOrchestrator
from quantbot.schemas import League, MatchOutcome, ValueMetrics


def test_chatgpt_review_example_ev_is_0_21_not_0_28() -> None:
    """P=56.3%, odds=2.15 → EV ≈ +0.210 (+21.0%), never +0.28."""

    p, odds = 0.563, 2.15
    ev = expected_value(p, odds)
    assert ev == pytest.approx(0.21045)
    assert format_ev_pct(ev) == "+21.0%"
    assert format_model_prob(p) == "56.3%"


def test_edge_absolute_vs_relative() -> None:
    p_model, p_market = 0.563, 0.50
    abs_edge = edge(p_model, p_market)
    assert abs_edge == pytest.approx(0.063)
    assert format_edge_pp(abs_edge) == "+6.3 pp"
    assert relative_edge(p_model, p_market) == pytest.approx(0.126)


def test_value_metrics_reject_inconsistent_ev() -> None:
    with pytest.raises(ValueError, match="expected_value"):
        ValueMetrics(
            outcome=MatchOutcome.HOME,
            model_prob=0.563,
            fair_market_prob=0.50,
            decimal_odds=2.15,
            edge=0.063,
            expected_value=0.28,  # wrong on purpose
        )


def test_value_metrics_reject_inconsistent_edge() -> None:
    with pytest.raises(ValueError, match="edge"):
        ValueMetrics(
            outcome=MatchOutcome.HOME,
            model_prob=0.563,
            fair_market_prob=0.50,
            decimal_odds=2.15,
            edge=0.10,
            expected_value=expected_value(0.563, 2.15),
        )


def test_kelly_matches_unrounded_inputs() -> None:
    p, odds = 0.563, 2.15
    full = (p * odds - 1.0) / (odds - 1.0)
    sizer = KellySizer(kelly_fraction=0.25, max_fraction=1.0)
    assert sizer.full_kelly(p, odds) == pytest.approx(full)
    assert sizer.stake_fraction(p, odds) == pytest.approx(0.25 * full)


def test_pipeline_signals_are_internally_consistent() -> None:
    orch = QuantBotOrchestrator()
    reports = orch.predict(League.PREMIER_LEAGUE, "2024-2025")
    assert reports
    for report in reports:
        for metric in report.signal.metrics:
            assert_metrics_consistent(metric)
            assert metric.edge_pp == pytest.approx(metric.edge * 100.0)
            assert metric.expected_return_pct == pytest.approx(metric.expected_value * 100.0)
        if report.signal.is_bet and report.signal.chosen_outcome is not None:
            chosen = next(
                m for m in report.signal.metrics if m.outcome is report.signal.chosen_outcome
            )
            assert report.signal.edge == pytest.approx(chosen.edge)
            assert report.signal.expected_value == pytest.approx(chosen.expected_value)
            assert report.signal.decimal_odds == pytest.approx(chosen.decimal_odds)
            assert report.signal.reason_codes
            assert "VALUE" in report.signal.reason_codes
        else:
            assert report.signal.reason_codes
            assert all(c.startswith("NO_BET_") or c == "VALUE" for c in report.signal.reason_codes)


def test_snapshot_from_signal_roundtrip() -> None:
    from datetime import datetime

    from quantbot.decision import DecisionEngine, KellySizer, NoBetRules
    from quantbot.schemas import SignalType, snapshot_from_signal

    orch = QuantBotOrchestrator(
        decision_engine=DecisionEngine(
            rules=NoBetRules(
                min_ev=-1.0,
                min_edge=-1.0,
                max_overround=1.0,
                min_data_quality=0.0,
                min_model_confidence=0.0,
                min_odds=1.01,
                max_odds=100.0,
            ),
            sizer=KellySizer(kelly_fraction=0.25, max_fraction=0.05),
        )
    )
    reports = orch.predict(League.PREMIER_LEAGUE, "2024-2025")
    report = next((r for r in reports if r.signal.is_bet), None) or reports[0]
    snap = snapshot_from_signal(
        report.signal,
        data_cutoff=report.match.prediction_timestamp,
        model_name="elo",
        odds_timestamp=report.signal.timestamp,
    )
    assert snap.match_id == report.signal.match_id
    assert snap.prediction_timestamp.tzinfo is not None
    assert isinstance(snap.data_cutoff, datetime)
    assert snap.data_cutoff.tzinfo is not None
    assert snap.reason_codes == report.signal.reason_codes
    if report.signal.is_bet:
        assert snap.signal is not SignalType.NO_BET
        assert snap.model_prob is not None
        assert snap.edge == pytest.approx(report.signal.edge)
        assert snap.expected_value == pytest.approx(report.signal.expected_value)
    else:
        assert snap.signal is SignalType.NO_BET
