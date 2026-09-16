"""Tests for value, confidence, calibration, and the analysis engine."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from quantbot.analysis import (
    AnalysisEngine,
    ConfidenceEvaluator,
    ConfidenceLevel,
    DataQualitySignals,
    IsotonicCalibrator,
    PlattScaler,
    ValueCalculator,
    brier_score,
    edge,
    ensemble_agreement,
    expected_calibration_error,
    expected_value,
    log_loss,
)
from quantbot.schemas import MarginMethod, MarketData, MatchOutcome, Prediction

UTC = timezone.utc
TS = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)


def _prediction(match_id: str, h: float, d: float, a: float, conf: float = 60.0) -> Prediction:
    return Prediction(
        match_id=match_id,
        model_name="test",
        prediction_timestamp=TS,
        prob_home=h,
        prob_draw=d,
        prob_away=a,
        confidence=conf,
    )


def _market(match_id: str, h: float, d: float, a: float) -> MarketData:
    return MarketData(
        match_id=match_id,
        bookmaker="bk",
        timestamp=TS,
        method=MarginMethod.SHIN,
        fair_home=h,
        fair_draw=d,
        fair_away=a,
        overround=0.05,
    )


# --- Value: edge & EV ---


def test_edge_and_ev_formulas() -> None:
    assert edge(0.55, 0.50) == pytest.approx(0.05)
    assert expected_value(0.55, 2.0) == pytest.approx(0.10)
    # A fair bet (prob = 1/odds) has zero EV.
    assert expected_value(0.5, 2.0) == pytest.approx(0.0)


def test_value_calculator_metrics() -> None:
    pred = _prediction("m1", 0.55, 0.25, 0.20)
    market = _market("m1", 0.50, 0.25, 0.25)
    odds = {MatchOutcome.HOME: 2.1, MatchOutcome.DRAW: 3.6, MatchOutcome.AWAY: 4.2}
    calc = ValueCalculator()
    metrics = calc.metrics(pred, market, odds)
    assert len(metrics) == 3
    home = metrics[0]
    assert home.outcome is MatchOutcome.HOME
    assert home.edge == pytest.approx(0.05)
    assert home.expected_value == pytest.approx(0.55 * 2.1 - 1.0)
    best = calc.best_by_ev(metrics)
    assert best.outcome is MatchOutcome.HOME


def test_value_calculator_rejects_mismatched_ids() -> None:
    pred = _prediction("m1", 0.5, 0.3, 0.2)
    market = _market("m2", 0.5, 0.3, 0.2)
    with pytest.raises(ValueError, match="match_id mismatch"):
        ValueCalculator().metrics(pred, market, {o: 2.0 for o in MatchOutcome})


# --- Confidence ---


def test_ensemble_agreement_identical_is_one() -> None:
    preds = [_prediction("m1", 0.5, 0.3, 0.2) for _ in range(3)]
    assert ensemble_agreement(preds) == pytest.approx(1.0)


def test_ensemble_agreement_disagreement_lower() -> None:
    agree = [_prediction("m1", 0.5, 0.3, 0.2), _prediction("m1", 0.52, 0.28, 0.20)]
    disagree = [_prediction("m1", 0.8, 0.1, 0.1), _prediction("m1", 0.1, 0.1, 0.8)]
    assert ensemble_agreement(agree) > ensemble_agreement(disagree)
    assert ensemble_agreement(disagree) < 0.5


def test_data_quality_monotonic_in_history() -> None:
    ev = ConfidenceEvaluator()
    shallow = DataQualitySignals(home_matches=1, away_matches=1, n_bookmakers=1, injuries_known=False)
    deep = DataQualitySignals(home_matches=15, away_matches=15, n_bookmakers=5, injuries_known=True)
    q_shallow = ev.data_quality(shallow)
    q_deep = ev.data_quality(deep)
    assert 0.0 <= q_shallow < q_deep <= 100.0


def test_confidence_lower_on_ensemble_disagreement() -> None:
    ev = ConfidenceEvaluator()
    high_agreement = ensemble_agreement(
        [_prediction("m1", 0.5, 0.3, 0.2), _prediction("m1", 0.51, 0.29, 0.20)]
    )
    low_agreement = ensemble_agreement(
        [_prediction("m1", 0.8, 0.1, 0.1), _prediction("m1", 0.1, 0.1, 0.8)]
    )
    dq = 80.0
    score_high, level_high = ev.model_confidence(high_agreement, dq)
    score_low, level_low = ev.model_confidence(low_agreement, dq)
    assert score_high > score_low
    assert level_high is ConfidenceLevel.HIGH
    assert level_low in (ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM)


def test_confidence_level_thresholds() -> None:
    ev = ConfidenceEvaluator(medium_threshold=45.0, high_threshold=70.0)
    assert ev.model_confidence(0.0, 0.0)[1] is ConfidenceLevel.LOW
    assert ev.model_confidence(1.0, 100.0)[1] is ConfidenceLevel.HIGH


# --- Calibration metrics ---


def test_brier_score_perfect_and_known() -> None:
    perfect = brier_score(np.array([[1.0, 0.0, 0.0]]), np.array([0]))
    assert perfect == pytest.approx(0.0)
    half = brier_score(np.array([[0.5, 0.5, 0.0]]), np.array([0]))
    assert half == pytest.approx(0.5)


def test_log_loss_perfect_and_penalizes_wrong() -> None:
    good = log_loss(np.array([[0.99, 0.005, 0.005]]), np.array([0]))
    bad = log_loss(np.array([[0.01, 0.495, 0.495]]), np.array([0]))
    assert good < bad
    assert good >= 0.0


def test_expected_calibration_error_perfect_is_zero() -> None:
    # Confident and always correct -> zero calibration error.
    probs = np.array([[0.99, 0.005, 0.005], [0.005, 0.99, 0.005], [0.005, 0.005, 0.99]])
    labels = np.array([0, 1, 2])
    assert expected_calibration_error(probs, labels, n_bins=10) < 0.02


def test_expected_calibration_error_overconfident_positive() -> None:
    # Always predicts class 0 at 0.9 confidence but only right half the time.
    probs = np.array([[0.9, 0.05, 0.05]] * 10)
    labels = np.array([0, 1] * 5)
    ece = expected_calibration_error(probs, labels, n_bins=10)
    assert ece == pytest.approx(0.4, abs=1e-9)  # |0.9 - 0.5|


# --- Calibration post-processors ---


def _synthetic_calibration_data(n: int = 300, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    labels = rng.integers(0, 3, size=n)
    probs = np.full((n, 3), 0.2)
    probs[np.arange(n), labels] = 0.6
    # Add noise and renormalize.
    probs += rng.uniform(0.0, 0.1, size=(n, 3))
    probs /= probs.sum(axis=1, keepdims=True)
    return probs, labels


@pytest.mark.parametrize("calibrator_cls", [IsotonicCalibrator, PlattScaler])
def test_calibrator_outputs_valid_distribution(calibrator_cls) -> None:  # type: ignore[no-untyped-def]
    probs, labels = _synthetic_calibration_data()
    cal = calibrator_cls()
    out = cal.fit_transform(probs, labels)
    assert out.shape == probs.shape
    row_sums = out.sum(axis=1)
    assert np.allclose(row_sums, 1.0)
    assert np.all(out >= 0.0)


def test_isotonic_improves_brier_on_miscalibrated_probs() -> None:
    # Overconfident probabilities that isotonic can pull back.
    probs, labels = _synthetic_calibration_data(n=400, seed=3)
    sharp = probs**3
    sharp /= sharp.sum(axis=1, keepdims=True)
    before = brier_score(sharp, labels)
    cal = IsotonicCalibrator().fit(sharp, labels)
    after = brier_score(cal.transform(sharp), labels)
    assert after <= before + 1e-9


def test_calibrator_transform_before_fit_raises() -> None:
    with pytest.raises(RuntimeError, match="not fitted"):
        IsotonicCalibrator().transform(np.array([[0.5, 0.3, 0.2]]))


# --- Analysis engine ---


def test_analysis_engine_produces_result() -> None:
    pred = _prediction("m1", 0.55, 0.25, 0.20)
    market = _market("m1", 0.50, 0.25, 0.25)
    odds = {MatchOutcome.HOME: 2.1, MatchOutcome.DRAW: 3.6, MatchOutcome.AWAY: 4.2}
    engine = AnalysisEngine()
    result = engine.analyze(
        pred,
        market,
        odds,
        quality_signals=DataQualitySignals(
            home_matches=12, away_matches=10, n_bookmakers=4, injuries_known=True
        ),
    )
    assert result.match_id == "m1"
    assert result.best_ev.outcome is MatchOutcome.HOME
    assert 0.0 <= result.data_quality <= 100.0
    assert isinstance(result.confidence_level, ConfidenceLevel)
    assert result.metric_for(MatchOutcome.HOME).edge == pytest.approx(0.05)


def test_market_shrinkage_reduces_edge_when_data_thin() -> None:
    # Model is very bullish on HOME; market is neutral.
    pred = _prediction("m1", 0.80, 0.12, 0.08)
    market = _market("m1", 0.50, 0.27, 0.23)
    odds = {MatchOutcome.HOME: 2.1, MatchOutcome.DRAW: 3.6, MatchOutcome.AWAY: 4.2}
    thin = DataQualitySignals(home_matches=2, away_matches=2, n_bookmakers=1, injuries_known=False)

    plain = AnalysisEngine().analyze(pred, market, odds, thin)
    shrunk = AnalysisEngine(market_shrinkage=True).analyze(pred, market, odds, thin)

    plain_edge = plain.metric_for(MatchOutcome.HOME).edge
    shrunk_edge = shrunk.metric_for(MatchOutcome.HOME).edge
    assert shrunk_edge < plain_edge  # pulled toward the market
    assert shrunk_edge > 0.0  # but not erased entirely


def test_market_shrinkage_off_by_default() -> None:
    pred = _prediction("m1", 0.80, 0.12, 0.08)
    market = _market("m1", 0.50, 0.27, 0.23)
    odds = {MatchOutcome.HOME: 2.1, MatchOutcome.DRAW: 3.6, MatchOutcome.AWAY: 4.2}
    signals = DataQualitySignals(home_matches=2, away_matches=2, n_bookmakers=1, injuries_known=False)
    result = AnalysisEngine().analyze(pred, market, odds, signals)
    assert result.metric_for(MatchOutcome.HOME).model_prob == pytest.approx(0.80)


def test_analysis_engine_confidence_drops_with_disagreement() -> None:
    pred = _prediction("m1", 0.5, 0.3, 0.2)
    market = _market("m1", 0.5, 0.3, 0.2)
    odds = {o: 2.5 for o in MatchOutcome}
    engine = AnalysisEngine()
    signals = DataQualitySignals(home_matches=12, away_matches=12, n_bookmakers=4, injuries_known=True)

    agree_subs = [_prediction("m1", 0.5, 0.3, 0.2), _prediction("m1", 0.51, 0.29, 0.20)]
    disagree_subs = [_prediction("m1", 0.8, 0.1, 0.1), _prediction("m1", 0.1, 0.1, 0.8)]

    r_agree = engine.analyze(pred, market, odds, signals, sub_predictions=agree_subs)
    r_disagree = engine.analyze(pred, market, odds, signals, sub_predictions=disagree_subs)
    assert r_agree.model_confidence > r_disagree.model_confidence
    assert r_agree.ensemble_agreement > r_disagree.ensemble_agreement
