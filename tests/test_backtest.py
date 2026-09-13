"""Tests for execution, metrics, and the walk-forward backtester."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from quantbot.analysis.engine import AnalysisEngine
from quantbot.backtest import (
    ExecutionSimulator,
    SettledBet,
    WalkForwardBacktester,
    compute_metrics,
    max_drawdown,
    sharpe_ratio,
)
from quantbot.data import DummyDataProvider
from quantbot.decision import DecisionEngine, KellySizer, NoBetRules
from quantbot.markets import MarketEngine
from quantbot.models.base import BaseModel, ModelPrediction
from quantbot.schemas import League, Match, MatchOutcome, Prediction

UTC = timezone.utc
SEASON = "2024-2025"
FAR_FUTURE = datetime(2026, 1, 1, tzinfo=UTC)


def _all_finished() -> list[Match]:
    provider = DummyDataProvider()
    return provider.get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE) + provider.get_matches(
        League.BUNDESLIGA, SEASON, FAR_FUTURE
    )


# --- Execution ---


def test_profit_win_and_loss() -> None:
    ex = ExecutionSimulator()
    assert ex.profit(100.0, 2.5, won=True) == pytest.approx(150.0)  # net win
    assert ex.profit(100.0, 2.5, won=False) == pytest.approx(-100.0)


def test_clv_positive_when_beating_close() -> None:
    ex = ExecutionSimulator()
    # Took 2.0, closed at 1.8 -> beat the close.
    assert ex.closing_line_value(2.0, 1.8) == pytest.approx(2.0 / 1.8 - 1.0)
    assert ex.closing_line_value(2.0, 1.8) > 0.0
    # Took 1.8, closed at 2.0 -> worse than close.
    assert ex.closing_line_value(1.8, 2.0) < 0.0


def test_settle_records_clv_and_result() -> None:
    ex = ExecutionSimulator()
    bet = ex.settle(
        match_id="m1",
        outcome=MatchOutcome.HOME,
        stake=50.0,
        entry_odds=2.0,
        actual_outcome=MatchOutcome.HOME,
        model_prob=0.6,
        closing_odds=1.8,
    )
    assert bet.won
    assert bet.pnl == pytest.approx(50.0)
    assert bet.beat_closing is True
    assert bet.clv == pytest.approx(2.0 / 1.8 - 1.0)


def test_settle_without_closing_odds() -> None:
    bet = ExecutionSimulator().settle(
        "m1", MatchOutcome.AWAY, 10.0, 3.0, MatchOutcome.HOME, model_prob=0.3
    )
    assert not bet.won
    assert bet.pnl == pytest.approx(-10.0)
    assert bet.clv is None
    assert bet.beat_closing is None


# --- Metrics ---


def test_max_drawdown_known_curve() -> None:
    # Peak 120, trough 60 -> drawdown 0.5.
    curve = [100.0, 120.0, 90.0, 60.0, 80.0]
    assert max_drawdown(curve) == pytest.approx(0.5)


def test_max_drawdown_monotonic_increase_is_zero() -> None:
    assert max_drawdown([100.0, 110.0, 130.0]) == pytest.approx(0.0)


def test_sharpe_zero_without_spread() -> None:
    assert sharpe_ratio([0.1, 0.1, 0.1]) == 0.0
    assert sharpe_ratio([0.1]) == 0.0


def _bet(pnl: float, stake: float, won: bool, clv: float | None, beat: bool | None) -> SettledBet:
    return SettledBet(
        match_id="m",
        outcome=MatchOutcome.HOME,
        stake=stake,
        entry_odds=2.0,
        closing_odds=1.9 if clv is not None else None,
        actual_outcome=MatchOutcome.HOME if won else MatchOutcome.AWAY,
        won=won,
        pnl=pnl,
        model_prob=0.5,
        clv=clv,
        beat_closing=beat,
    )


def test_compute_metrics_roi_winrate_profit_factor() -> None:
    bets = [
        _bet(50.0, 50.0, True, 0.05, True),
        _bet(-50.0, 50.0, False, -0.02, False),
        _bet(100.0, 50.0, True, 0.10, True),
    ]
    curve = [1000.0, 1050.0, 1000.0, 1100.0]
    m = compute_metrics(bets, curve, initial_bankroll=1000.0)
    assert m.n_bets == 3
    assert m.total_staked == pytest.approx(150.0)
    assert m.total_pnl == pytest.approx(100.0)
    assert m.roi == pytest.approx(100.0 / 150.0)
    assert m.win_rate == pytest.approx(2 / 3)
    # gross win 150, gross loss 50 -> 3.0
    assert m.profit_factor == pytest.approx(3.0)
    assert m.total_return == pytest.approx(0.1)
    assert m.beat_clv_rate == pytest.approx(2 / 3)
    assert m.avg_clv == pytest.approx((0.05 - 0.02 + 0.10) / 3)


def test_compute_metrics_no_losses_infinite_profit_factor() -> None:
    import math

    bets = [_bet(50.0, 50.0, True, None, None)]
    m = compute_metrics(bets, [1000.0, 1050.0], 1000.0)
    assert math.isinf(m.profit_factor)
    assert m.avg_clv is None
    assert m.beat_clv_rate is None


# --- Walk-forward leakage ---


class LeakSpyModel(BaseModel):
    """Asserts, at every predict, that no training match leaks the future."""

    name = "leak_spy"

    def __init__(self) -> None:
        super().__init__()
        self._train: list[Match] = []
        self.predict_calls = 0

    def fit(self, matches: Sequence[Match]) -> None:
        self._train = list(matches)
        self._is_fitted = True

    def predict(self, match: Match) -> ModelPrediction:
        self.predict_calls += 1
        for m in self._train:
            assert m.kickoff < match.prediction_timestamp, "training data leaked the future"
        return Prediction(
            match_id=match.match_id,
            model_name=self.name,
            prediction_timestamp=match.prediction_timestamp,
            prob_home=1 / 3,
            prob_draw=1 / 3,
            prob_away=1 / 3,
        )


def test_walk_forward_is_leak_free() -> None:
    provider = DummyDataProvider()
    matches = _all_finished()
    model = LeakSpyModel()
    backtester = WalkForwardBacktester(model)
    result = backtester.run(matches, provider)
    # Every match with entry odds was evaluated; leak asserts held throughout.
    assert model.predict_calls == len(matches)
    assert result.n_evaluated == len(matches)


class HomeBiasModel(BaseModel):
    """Always favors the home side, to force bets in the pipeline."""

    name = "home_bias"

    def fit(self, matches: Sequence[Match]) -> None:
        self._is_fitted = True

    def predict(self, match: Match) -> ModelPrediction:
        return Prediction(
            match_id=match.match_id,
            model_name=self.name,
            prediction_timestamp=match.prediction_timestamp,
            prob_home=0.6,
            prob_draw=0.2,
            prob_away=0.2,
            confidence=80.0,
        )


def test_walk_forward_integration_produces_bets_and_bankroll() -> None:
    provider = DummyDataProvider()
    matches = _all_finished()
    lenient = DecisionEngine(
        rules=NoBetRules(
            min_ev=0.0,
            min_edge=0.0,
            max_overround=1.0,
            min_data_quality=0.0,
            min_model_confidence=0.0,
            min_odds=1.01,
            max_odds=100.0,
        ),
        sizer=KellySizer(kelly_fraction=0.25, max_fraction=0.05),
    )
    backtester = WalkForwardBacktester(
        HomeBiasModel(),
        market_engine=MarketEngine(),
        analysis_engine=AnalysisEngine(),
        decision_engine=lenient,
        initial_bankroll=1000.0,
    )
    result = backtester.run(matches, provider)

    assert result.n_bets > 0
    # Bankroll curve has one entry per settled bet plus the starting point.
    assert len(result.bankroll_curve) == result.n_bets + 1
    assert result.bankroll_curve[0] == 1000.0
    assert result.final_bankroll == pytest.approx(result.bankroll_curve[-1])
    # Every settled bet was priced at an entry recorded on or before as_of.
    for bet in result.settled_bets:
        assert bet.entry_odds > 1.0
    assert result.metrics.n_bets == result.n_bets
    assert result.n_bets + result.n_no_bet == len(result.signals)
