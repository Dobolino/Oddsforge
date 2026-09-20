"""Asian-handicap (spread) market: model probs, value, decision, orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quantbot.analysis.value import handicap_metrics_from_prediction
from quantbot.decision.engine import DecisionEngine
from quantbot.decision.rules import NoBetRules
from quantbot.markets.spread import SpreadMarketEngine
from quantbot.schemas import (
    DEFAULT_HANDICAP_LINE,
    HandicapSide,
    MarginMethod,
    Prediction,
    ScoreMatrix,
    SignalType,
    SpreadMarketData,
    SpreadOdds,
    ValueSignal,
)

UTC = timezone.utc
TS = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def _home_leaning_matrix() -> ScoreMatrix:
    """3x3 grid with most mass on home-win scorelines (i > j)."""

    raw = [
        [0.06, 0.04, 0.02],  # home 0: draw, away by1, away by2
        [0.20, 0.06, 0.03],  # home 1: home by1, draw, away by1
        [0.28, 0.18, 0.05],  # home 2: home by2, home by1, draw
    ]
    total = sum(sum(r) for r in raw)
    return ScoreMatrix(matrix=[[c / total for c in row] for row in raw])


def _prediction(matrix: ScoreMatrix) -> Prediction:
    return Prediction(
        match_id="m1",
        model_name="test",
        prediction_timestamp=TS,
        prob_home=0.55,
        prob_draw=0.25,
        prob_away=0.20,
        confidence=80.0,
        score_matrix=matrix,
    )


# --- Market engine ---


def test_spread_market_fair_probs_sum_to_one() -> None:
    odds = SpreadOdds(
        match_id="m1", bookmaker="bk", timestamp=TS, line=-0.5, home=1.78, away=2.02
    )
    market = SpreadMarketEngine(method=MarginMethod.POWER).to_market_data(odds)
    assert isinstance(market, SpreadMarketData)
    assert abs(market.fair_home + market.fair_away - 1.0) < 1e-9
    assert market.line == -0.5
    assert market.overround > 0.0


def test_spread_market_rejects_shin() -> None:
    with pytest.raises(ValueError, match="Power"):
        SpreadMarketEngine(method=MarginMethod.SHIN)


def test_spread_best_odds_picks_highest() -> None:
    a = SpreadOdds(match_id="m1", bookmaker="a", timestamp=TS, line=-0.5, home=1.8, away=2.0)
    b = SpreadOdds(match_id="m1", bookmaker="b", timestamp=TS, line=-0.5, home=1.9, away=1.95)
    best = SpreadMarketEngine().best_odds([a, b])
    assert best[HandicapSide.HOME] == (1.9, "b")
    assert best[HandicapSide.AWAY] == (2.0, "a")


# --- Value metrics ---


def test_handicap_metrics_from_prediction() -> None:
    matrix = _home_leaning_matrix()
    prediction = _prediction(matrix)
    odds = SpreadOdds(
        match_id="m1", bookmaker="bk", timestamp=TS, line=-0.5, home=2.10, away=1.80
    )
    market = SpreadMarketEngine(method=MarginMethod.POWER).to_market_data(odds)
    metrics = handicap_metrics_from_prediction(prediction, odds, market)
    assert {m.outcome for m in metrics} == {HandicapSide.HOME, HandicapSide.AWAY}
    home = next(m for m in metrics if m.outcome is HandicapSide.HOME)
    # Model cover prob equals matrix home cover for -0.5.
    home_cover, _ = matrix.handicap_probabilities(-0.5)
    assert home.model_prob == pytest.approx(home_cover)
    assert home.edge == pytest.approx(home.model_prob - home.fair_market_prob)


def test_handicap_metrics_reject_whole_line() -> None:
    prediction = _prediction(_home_leaning_matrix())
    odds = SpreadOdds(match_id="m1", bookmaker="bk", timestamp=TS, line=-1.0, home=2.0, away=1.8)
    market = SpreadMarketEngine().to_market_data(odds)
    with pytest.raises(ValueError):
        handicap_metrics_from_prediction(prediction, odds, market)


# --- Decision engine ---


def test_decide_spread_emits_handicap_signal() -> None:
    matrix = _home_leaning_matrix()
    prediction = _prediction(matrix)
    # Near-fair odds (low overround) with the home cover underpriced -> value.
    odds = SpreadOdds(
        match_id="m1", bookmaker="bk", timestamp=TS, line=-0.5, home=1.85, away=2.15
    )
    market = SpreadMarketEngine(method=MarginMethod.POWER).to_market_data(odds)
    metrics = handicap_metrics_from_prediction(prediction, odds, market)
    engine = DecisionEngine(rules=NoBetRules(min_edge=0.03, min_data_quality=0.0, min_model_confidence=0.0))
    signal = engine.decide_spread(
        match_id="m1", market=market, metrics=metrics, data_quality=80.0, model_confidence=70.0
    )
    assert signal.signal is SignalType.VALUE_HANDICAP_HOME
    assert signal.chosen_outcome is HandicapSide.HOME
    assert signal.handicap_line == -0.5
    assert signal.totals_line is None
    assert signal.tip_label == "handicap_home_-0.5"


def test_decide_spread_no_bet_when_no_edge() -> None:
    matrix = _home_leaning_matrix()
    prediction = _prediction(matrix)
    # Home cover (0.72) is over-priced at 1.35; neither side beats fair.
    odds = SpreadOdds(match_id="m1", bookmaker="bk", timestamp=TS, line=-0.5, home=1.35, away=3.20)
    market = SpreadMarketEngine().to_market_data(odds)
    metrics = handicap_metrics_from_prediction(prediction, odds, market)
    engine = DecisionEngine(rules=NoBetRules(min_edge=0.03, min_data_quality=0.0, min_model_confidence=0.0))
    signal = engine.decide_spread(
        match_id="m1", market=market, metrics=metrics, data_quality=80.0, model_confidence=70.0
    )
    assert signal.signal is SignalType.NO_BET


# --- Signal schema guards ---


def test_handicap_signal_requires_line() -> None:
    with pytest.raises(ValueError, match="handicap_line"):
        ValueSignal(
            match_id="m1",
            timestamp=TS,
            signal=SignalType.VALUE_HANDICAP_HOME,
            chosen_outcome=HandicapSide.HOME,
            model_confidence=60.0,
            data_quality=70.0,
            stake_fraction=0.01,
        )


def test_handicap_signal_rejects_totals_line() -> None:
    with pytest.raises(ValueError, match="must not set totals_line"):
        ValueSignal(
            match_id="m1",
            timestamp=TS,
            signal=SignalType.VALUE_HANDICAP_HOME,
            chosen_outcome=HandicapSide.HOME,
            model_confidence=60.0,
            data_quality=70.0,
            stake_fraction=0.01,
            handicap_line=-0.5,
            totals_line=2.5,
        )


def test_1x2_still_rejects_handicap_line() -> None:
    with pytest.raises(ValueError, match="must not set handicap_line"):
        ValueSignal(
            match_id="m1",
            timestamp=TS,
            signal=SignalType.VALUE_HOME,
            chosen_outcome=__import__("quantbot.schemas", fromlist=["MatchOutcome"]).MatchOutcome.HOME,
            model_confidence=60.0,
            data_quality=70.0,
            stake_fraction=0.01,
            handicap_line=-0.5,
        )


def test_default_handicap_line_is_half() -> None:
    assert DEFAULT_HANDICAP_LINE == -0.5


# --- Orchestrator wiring ---


def _orchestrator():
    from quantbot.analysis.engine import AnalysisEngine
    from quantbot.orchestrator import QuantBotOrchestrator

    return QuantBotOrchestrator(analysis_engine=AnalysisEngine(market_shrinkage=False))


class _Match:
    match_id = "m1"


def test_prefer_handicap_upgrades_no_bet(monkeypatch) -> None:
    orch = _orchestrator()
    matrix = _home_leaning_matrix()
    prediction = _prediction(matrix)
    odds = SpreadOdds(match_id="m1", bookmaker="bk", timestamp=TS, line=-0.5, home=1.85, away=2.15)
    monkeypatch.setattr(
        orch.provider, "get_latest_spread_odds", lambda *a, **k: odds
    )
    no_bet = ValueSignal(
        match_id="m1", timestamp=TS, signal=SignalType.NO_BET,
        model_confidence=70.0, data_quality=80.0,
    )
    out = orch._maybe_prefer_handicap(
        match=_Match(), as_of=TS, prediction=prediction,
        data_quality=80.0, model_confidence=70.0, current=no_bet, quality=None,
    )
    assert out.signal is SignalType.VALUE_HANDICAP_HOME
    assert out.handicap_line == -0.5


def test_prefer_handicap_noop_without_odds(monkeypatch) -> None:
    orch = _orchestrator()
    prediction = _prediction(_home_leaning_matrix())
    monkeypatch.setattr(orch.provider, "get_latest_spread_odds", lambda *a, **k: None)
    no_bet = ValueSignal(
        match_id="m1", timestamp=TS, signal=SignalType.NO_BET,
        model_confidence=70.0, data_quality=80.0,
    )
    out = orch._maybe_prefer_handicap(
        match=_Match(), as_of=TS, prediction=prediction,
        data_quality=80.0, model_confidence=70.0, current=no_bet, quality=None,
    )
    assert out is no_bet
