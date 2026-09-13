"""Block A tests: calibration wiring, Dixon-Coles convergence fallback,
Sortino ratio, and Monte-Carlo bankroll simulation."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from quantbot.analysis import IsotonicCalibrator, PlattScaler
from quantbot.backtest import (
    BetSpec,
    WalkForwardBacktester,
    bet_specs_from_result,
    compute_metrics,
    monte_carlo_bankroll,
    sortino_ratio,
)
from quantbot.data import DummyDataProvider
from quantbot.decision import DecisionEngine, KellySizer, NoBetRules
from quantbot.models import CalibratedModel, DixonColesModel, EloModel, NotFittedError
from quantbot.orchestrator import QuantBotOrchestrator
from quantbot.schemas import League, Match, MatchOutcome

UTC = timezone.utc
SEASON = "2024-2025"
FAR_FUTURE = datetime(2026, 1, 1, tzinfo=UTC)


def _all_finished() -> list[Match]:
    provider = DummyDataProvider()
    return provider.get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE) + provider.get_matches(
        League.BUNDESLIGA, SEASON, FAR_FUTURE
    )


# --- 1. Calibration wiring ---


@pytest.mark.parametrize("calibrator_cls", [IsotonicCalibrator, PlattScaler])
def test_calibrated_model_outputs_valid_distribution(calibrator_cls) -> None:  # type: ignore[no-untyped-def]
    matches = _all_finished()
    model = CalibratedModel(EloModel(), calibrator_cls())
    model.fit(matches)
    pred = model.predict(matches[0])
    total = pred.prob_home + pred.prob_draw + pred.prob_away
    assert abs(total - 1.0) < 1e-6
    assert pred.model_name.endswith("_calibrated")


def test_calibrated_model_marks_calibration_active() -> None:
    matches = _all_finished()
    model = CalibratedModel(EloModel(), IsotonicCalibrator())
    model.fit(matches)
    assert model._calibrated is True


def test_calibrated_predict_before_fit_raises() -> None:
    with pytest.raises(NotFittedError):
        CalibratedModel(EloModel(), IsotonicCalibrator()).predict(_all_finished()[0])


def test_orchestrator_uses_calibrated_model() -> None:
    orchestrator = QuantBotOrchestrator(model=EloModel(), calibrator=IsotonicCalibrator())
    assert orchestrator.model.name.endswith("_calibrated")
    reports = orchestrator.predict(League.PREMIER_LEAGUE, SEASON)
    assert reports
    for report in reports:
        m = report.analysis.metric_for(MatchOutcome.HOME)
        assert 0.0 <= m.model_prob <= 1.0


# --- 2. Dixon-Coles convergence fallback ---


def test_dixon_coles_fallback_on_non_convergence(monkeypatch, caplog) -> None:  # type: ignore[no-untyped-def]
    matches = _all_finished()

    def fake_minimize(*args, **kwargs):  # type: ignore[no-untyped-def]
        x0 = args[1]
        return SimpleNamespace(x=x0, success=False, message="forced non-convergence")

    monkeypatch.setattr("quantbot.models.dixon_coles.minimize", fake_minimize)

    model = DixonColesModel(min_matches=10)
    with caplog.at_level(logging.WARNING):
        model.fit(matches)

    assert model.is_fitted
    assert "did not converge" in caplog.text
    # Fallback still yields a valid probability distribution.
    pred = model.predict(matches[0])
    assert abs(pred.prob_home + pred.prob_draw + pred.prob_away - 1.0) < 1e-6
    # mean-centered attack ~ 0
    assert abs(sum(model._attack.values())) < 1e-9
    assert model.rho == 0.0


def test_dixon_coles_converges_normally() -> None:
    model = DixonColesModel(min_matches=10)
    model.fit(_all_finished())
    assert model.is_fitted
    # A real fit produces a non-degenerate rho or home advantage.
    assert model.home_advantage != 0.0


# --- 3. Sortino ratio ---


def test_sortino_all_positive_is_infinite() -> None:
    assert math.isinf(sortino_ratio([0.1, 0.2, 0.15]))


def test_sortino_zero_without_bets() -> None:
    assert sortino_ratio([0.1]) == 0.0


def test_sortino_finite_with_downside() -> None:
    s = sortino_ratio([0.1, -0.05, 0.2, -0.1])
    assert math.isfinite(s)


def test_sortino_matches_manual_formula() -> None:
    returns = [0.2, 0.2, 0.2, -0.4]
    # mean = 0.05; downside dev = sqrt(mean(min(0, r)^2)) = sqrt(0.16/4) = 0.2.
    expected = 0.05 / 0.2
    assert sortino_ratio(returns) == pytest.approx(expected)


def test_sortino_only_counts_downside() -> None:
    from quantbot.backtest import sharpe_ratio

    # Upside volatility but no downside -> Sortino infinite, Sharpe finite.
    returns = [0.0, 0.3, 0.0, 0.3]
    assert math.isinf(sortino_ratio(returns))
    assert math.isfinite(sharpe_ratio(returns))


def test_compute_metrics_includes_sortino() -> None:
    from quantbot.backtest import SettledBet

    def bet(pnl: float) -> SettledBet:
        return SettledBet(
            match_id="m",
            outcome=MatchOutcome.HOME,
            stake=50.0,
            entry_odds=2.0,
            closing_odds=None,
            actual_outcome=MatchOutcome.HOME,
            won=pnl > 0,
            pnl=pnl,
            model_prob=0.5,
            clv=None,
            beat_closing=None,
        )

    bets = [bet(50.0), bet(-50.0), bet(100.0)]
    m = compute_metrics(bets, [1000.0, 1050.0, 1000.0, 1100.0], 1000.0)
    assert hasattr(m, "sortino")
    assert math.isfinite(m.sortino)


# --- 4. Monte-Carlo bankroll simulation ---


def test_monte_carlo_all_winning_no_ruin() -> None:
    specs = [BetSpec(stake_fraction=0.05, decimal_odds=2.0, win_prob=1.0)] * 10
    result = monte_carlo_bankroll(specs, initial_bankroll=1000.0, n_sims=500, seed=1)
    assert result.risk_of_ruin == 0.0
    assert result.final_median > 1000.0


def test_monte_carlo_all_losing_ruin() -> None:
    specs = [BetSpec(stake_fraction=0.5, decimal_odds=2.0, win_prob=0.0)] * 5
    result = monte_carlo_bankroll(specs, initial_bankroll=1000.0, n_sims=500, ruin_fraction=0.5, seed=1)
    # First loss halves the bankroll to the ruin threshold.
    assert result.risk_of_ruin == pytest.approx(1.0)
    assert result.final_median < 1000.0


def test_monte_carlo_empty_specs() -> None:
    result = monte_carlo_bankroll([], initial_bankroll=1000.0, n_sims=100)
    assert result.risk_of_ruin == 0.0
    assert result.final_mean == 1000.0
    assert result.n_bets == 0


def test_monte_carlo_is_deterministic_with_seed() -> None:
    specs = [BetSpec(stake_fraction=0.05, decimal_odds=2.1, win_prob=0.5)] * 8
    a = monte_carlo_bankroll(specs, n_sims=300, seed=42)
    b = monte_carlo_bankroll(specs, n_sims=300, seed=42)
    assert a.risk_of_ruin == b.risk_of_ruin
    assert a.final_mean == b.final_mean


def test_monte_carlo_from_backtest_result() -> None:
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
        sizer=KellySizer(kelly_fraction=0.2, max_fraction=0.05),
    )

    class HomeBias(EloModel):
        def predict(self, match):  # type: ignore[no-untyped-def]
            from quantbot.schemas import Prediction

            return Prediction(
                match_id=match.match_id,
                model_name="home_bias",
                prediction_timestamp=match.prediction_timestamp,
                prob_home=0.6,
                prob_draw=0.2,
                prob_away=0.2,
                confidence=80.0,
            )

    result = WalkForwardBacktester(HomeBias(), decision_engine=lenient).run(matches, provider)
    specs = bet_specs_from_result(result)
    assert len(specs) == result.n_bets
    assert all(0.0 <= s.stake_fraction <= 1.0 for s in specs)

    mc = monte_carlo_bankroll(specs, initial_bankroll=result.initial_bankroll, n_sims=500, seed=3)
    assert 0.0 <= mc.risk_of_ruin <= 1.0
    assert 0.0 <= mc.drawdown_median <= 1.0
    assert mc.n_bets == result.n_bets
