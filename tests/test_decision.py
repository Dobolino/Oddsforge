"""Tests for Kelly sizing, no-bet rules, and the Decision Engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quantbot.analysis.engine import AnalysisResult
from quantbot.analysis.confidence import ConfidenceLevel
from quantbot.decision import DecisionEngine, KellySizer, NoBetRules
from quantbot.schemas import MarginMethod, MarketData, MatchOutcome, SignalType, ValueMetrics

UTC = timezone.utc
TS = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)


def _metric(
    outcome: MatchOutcome,
    model_prob: float,
    fair: float,
    odds: float,
) -> ValueMetrics:
    return ValueMetrics(
        outcome=outcome,
        model_prob=model_prob,
        fair_market_prob=fair,
        decimal_odds=odds,
        edge=model_prob - fair,
        expected_value=model_prob * odds - 1.0,
    )


def _market(match_id: str = "m1", overround: float = 0.05) -> MarketData:
    return MarketData(
        match_id=match_id,
        bookmaker="bk",
        timestamp=TS,
        method=MarginMethod.SHIN,
        fair_home=0.5,
        fair_draw=0.25,
        fair_away=0.25,
        overround=overround,
    )


def _analysis(
    metric: ValueMetrics,
    data_quality: float = 80.0,
    model_confidence: float = 75.0,
    match_id: str = "m1",
) -> AnalysisResult:
    return AnalysisResult(
        match_id=match_id,
        metrics=(metric,),
        best_ev=metric,
        data_quality=data_quality,
        model_confidence=model_confidence,
        confidence_level=ConfidenceLevel.HIGH,
        ensemble_agreement=0.9,
    )


# --- Kelly sizing ---


def test_full_kelly_formula() -> None:
    sizer = KellySizer()
    # p=0.6, odds=2.0 -> (0.6*2 - 1)/(2 - 1) = 0.2
    assert sizer.full_kelly(0.6, 2.0) == pytest.approx(0.2)
    # Fair bet -> zero edge.
    assert sizer.full_kelly(0.5, 2.0) == pytest.approx(0.0)
    # No edge -> negative full Kelly.
    assert sizer.full_kelly(0.4, 2.0) < 0.0


def test_fractional_kelly_and_cap() -> None:
    sizer = KellySizer(kelly_fraction=0.5, max_fraction=0.05)
    # Full Kelly 0.2, half -> 0.1, capped to 0.05.
    assert sizer.stake_fraction(0.6, 2.0) == pytest.approx(0.05)


def test_fractional_kelly_below_cap() -> None:
    sizer = KellySizer(kelly_fraction=0.25, max_fraction=0.5)
    # Full 0.2 * 0.25 = 0.05, below the 0.5 cap.
    assert sizer.stake_fraction(0.6, 2.0) == pytest.approx(0.05)


def test_no_edge_gives_zero_stake() -> None:
    sizer = KellySizer()
    assert sizer.stake_fraction(0.45, 2.0) == 0.0


def test_min_fraction_rounds_small_stake_to_zero() -> None:
    sizer = KellySizer(kelly_fraction=0.25, max_fraction=0.5, min_fraction=0.06)
    # Stake would be 0.05, below min_fraction 0.06 -> 0.
    assert sizer.stake_fraction(0.6, 2.0) == 0.0


def test_stake_amount_scales_with_bankroll() -> None:
    sizer = KellySizer(kelly_fraction=0.5, max_fraction=0.5)
    frac = sizer.stake_fraction(0.6, 2.0)
    assert sizer.stake_amount(0.6, 2.0, 1000.0) == pytest.approx(frac * 1000.0)


def test_invalid_sizer_config() -> None:
    with pytest.raises(ValueError):
        KellySizer(kelly_fraction=1.5)
    with pytest.raises(ValueError):
        KellySizer(max_fraction=0.0)


# --- No-bet rules ---


def test_rules_pass_on_good_candidate() -> None:
    rules = NoBetRules(min_ev=0.0, min_edge=0.03, min_data_quality=60.0, min_model_confidence=55.0)
    metric = _metric(MatchOutcome.HOME, 0.60, 0.50, 2.1)  # ev 0.26, edge 0.10
    result = rules.evaluate(metric, overround=0.05, data_quality=80.0, model_confidence=75.0)
    assert result.passed
    assert result.reasons == ()


def test_rules_reject_low_ev() -> None:
    rules = NoBetRules(min_ev=0.05, min_edge=0.0)
    metric = _metric(MatchOutcome.HOME, 0.50, 0.50, 2.0)  # ev 0.0
    result = rules.evaluate(metric, overround=0.05, data_quality=80.0, model_confidence=75.0)
    assert not result.passed
    assert any("ev" in r for r in result.reasons)


def test_rules_reject_low_confidence() -> None:
    rules = NoBetRules(min_model_confidence=70.0)
    metric = _metric(MatchOutcome.HOME, 0.60, 0.50, 2.1)
    result = rules.evaluate(metric, overround=0.05, data_quality=80.0, model_confidence=50.0)
    assert not result.passed
    assert any("model confidence" in r for r in result.reasons)


def test_rules_reject_low_data_quality() -> None:
    rules = NoBetRules(min_data_quality=70.0)
    metric = _metric(MatchOutcome.HOME, 0.60, 0.50, 2.1)
    result = rules.evaluate(metric, overround=0.05, data_quality=40.0, model_confidence=75.0)
    assert not result.passed
    assert any("data quality" in r for r in result.reasons)


def test_rules_reject_high_overround() -> None:
    rules = NoBetRules(max_overround=0.08)
    metric = _metric(MatchOutcome.HOME, 0.60, 0.50, 2.1)
    result = rules.evaluate(metric, overround=0.20, data_quality=80.0, model_confidence=75.0)
    assert not result.passed
    assert any("overround" in r for r in result.reasons)


def test_rules_reject_extreme_odds() -> None:
    rules = NoBetRules(min_odds=1.2, max_odds=15.0, min_edge=0.0, min_ev=-1.0)
    high = _metric(MatchOutcome.AWAY, 0.10, 0.05, 20.0)
    low = _metric(MatchOutcome.HOME, 0.95, 0.90, 1.05)
    assert any("above maximum" in r for r in rules.evaluate(high, 0.05, 80.0, 75.0).reasons)
    assert any("below minimum" in r for r in rules.evaluate(low, 0.05, 80.0, 75.0).reasons)


def test_rules_collect_multiple_reasons() -> None:
    rules = NoBetRules(min_ev=0.10, min_edge=0.10, min_model_confidence=80.0)
    metric = _metric(MatchOutcome.HOME, 0.50, 0.50, 1.9)  # ev negative, edge 0
    result = rules.evaluate(metric, overround=0.05, data_quality=80.0, model_confidence=50.0)
    assert not result.passed
    assert len(result.reasons) >= 3


# --- Decision engine ---


def test_decision_engine_value_signal() -> None:
    engine = DecisionEngine(
        rules=NoBetRules(min_ev=0.0, min_edge=0.03, min_data_quality=60.0, min_model_confidence=55.0),
        sizer=KellySizer(kelly_fraction=0.25, max_fraction=0.1),
    )
    metric = _metric(MatchOutcome.HOME, 0.60, 0.50, 2.1)  # edge 0.10, ev 0.26
    signal = engine.decide(_analysis(metric), _market())
    assert signal.signal is SignalType.VALUE_HOME
    assert signal.chosen_outcome is MatchOutcome.HOME
    assert signal.stake_fraction > 0.0
    assert signal.edge == pytest.approx(0.10)
    assert "value on home" in signal.rationale


def test_decision_engine_no_bet_low_ev() -> None:
    engine = DecisionEngine(rules=NoBetRules(min_ev=0.10, min_edge=0.0))
    metric = _metric(MatchOutcome.HOME, 0.50, 0.50, 2.0)  # ev 0.0
    signal = engine.decide(_analysis(metric), _market())
    assert signal.signal is SignalType.NO_BET
    assert signal.chosen_outcome is None
    assert signal.stake_fraction == 0.0
    assert "ev" in signal.rationale


def test_decision_engine_no_bet_low_confidence() -> None:
    engine = DecisionEngine(rules=NoBetRules(min_model_confidence=90.0))
    metric = _metric(MatchOutcome.HOME, 0.60, 0.50, 2.1)
    signal = engine.decide(_analysis(metric, model_confidence=60.0), _market())
    assert signal.signal is SignalType.NO_BET
    assert "model confidence" in signal.rationale


def test_decision_engine_rejects_mismatched_ids() -> None:
    engine = DecisionEngine()
    metric = _metric(MatchOutcome.HOME, 0.60, 0.50, 2.1)
    with pytest.raises(ValueError, match="match_id mismatch"):
        engine.decide(_analysis(metric, match_id="m1"), _market(match_id="m2"))
