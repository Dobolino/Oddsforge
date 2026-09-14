"""Over/Under totals from the score matrix and value market path."""

from __future__ import annotations

from datetime import datetime, timezone

from quantbot.analysis.value import totals_metrics_from_prediction
from quantbot.decision.engine import DecisionEngine
from quantbot.markets.totals import TotalsMarketEngine
from quantbot.schemas import (
    DEFAULT_TOTALS_LINE,
    MarginMethod,
    Prediction,
    ScoreMatrix,
    TotalsOdds,
    TotalsSide,
)


def _matrix_with_known_totals() -> ScoreMatrix:
    """3x3 grid: mass mostly on high-scoring cells (over 2.5)."""

    # rows = home goals 0..2, cols = away goals 0..2
    # totals: 0+0=0, 0+1=1, 0+2=2, 1+0=1, 1+1=2, 1+2=3, 2+0=2, 2+1=3, 2+2=4
    raw = [
        [0.02, 0.03, 0.05],  # totals 0,1,2
        [0.03, 0.05, 0.20],  # totals 1,2,3
        [0.05, 0.22, 0.35],  # totals 2,3,4
    ]
    total = sum(sum(r) for r in raw)
    return ScoreMatrix(matrix=[[c / total for c in row] for row in raw])


def test_totals_probabilities_sum_to_one() -> None:
    matrix = _matrix_with_known_totals()
    probs = matrix.totals_probabilities(2.5)
    assert abs(probs[TotalsSide.OVER] + probs[TotalsSide.UNDER] - 1.0) < 1e-9
    assert probs[TotalsSide.OVER] > probs[TotalsSide.UNDER]

    # Configurable line: 1.5 should also partition cleanly.
    probs_15 = matrix.totals_probabilities(1.5)
    assert abs(probs_15[TotalsSide.OVER] + probs_15[TotalsSide.UNDER] - 1.0) < 1e-9


def test_totals_market_emits_value_tip_when_edge_exists() -> None:
    ts = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    matrix = _matrix_with_known_totals()
    model_probs = matrix.totals_probabilities(DEFAULT_TOTALS_LINE)
    # Book prices under heavily — model likes over → clear edge on over.
    totals = TotalsOdds(
        match_id="m1",
        bookmaker="test_book",
        timestamp=ts,
        line=DEFAULT_TOTALS_LINE,
        over=2.80,
        under=1.35,
    )
    market = TotalsMarketEngine(method=MarginMethod.MULTIPLICATIVE).to_market_data(totals)
    prediction = Prediction(
        match_id="m1",
        model_name="test",
        prediction_timestamp=ts,
        prob_home=0.4,
        prob_draw=0.3,
        prob_away=0.3,
        confidence=80.0,
        score_matrix=matrix,
    )
    metrics = totals_metrics_from_prediction(prediction, totals, market)
    over_metric = next(m for m in metrics if m.outcome is TotalsSide.OVER)
    assert over_metric.edge > 0.03
    assert over_metric.model_prob == model_probs[TotalsSide.OVER]

    signal = DecisionEngine().decide_totals(
        match_id="m1",
        market=market,
        metrics=metrics,
        data_quality=80.0,
        model_confidence=80.0,
    )
    assert signal.is_bet
    assert signal.signal.value == "value_over"
    assert signal.totals_line == DEFAULT_TOTALS_LINE
    assert signal.tip_label == "over_2.5"
