"""End-to-end system test: ingestion -> prediction -> decision -> backtest."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quantbot.analysis.engine import AnalysisEngine
from quantbot.data import DummyDataProvider
from quantbot.decision import DecisionEngine, KellySizer, NoBetRules
from quantbot.markets import MarketEngine
from quantbot.models import EloModel, EnsembleModel, LogisticRegressionModel
from quantbot.orchestrator import QuantBotOrchestrator
from quantbot.schemas import League, MatchOutcome, SignalType, ValueSignal

UTC = timezone.utc
SEASON = "2024-2025"


def test_manual_pipeline_produces_value_signal() -> None:
    """Exercise every layer explicitly for one match."""

    provider = DummyDataProvider()
    universe = provider.get_matches(League.PREMIER_LEAGUE, SEASON, datetime(2026, 1, 1, tzinfo=UTC))
    ordered = sorted(universe, key=lambda m: m.kickoff)
    target = ordered[-1]  # last match: maximal history
    as_of = target.prediction_timestamp

    model = EloModel()
    model.fit_until(universe, as_of)
    masked = target.model_copy(update={"result": None})
    prediction = model.predict(masked)
    assert abs(sum(prediction.probabilities().values()) - 1.0) < 1e-6

    entry = provider.get_latest_odds(target.match_id, as_of)
    assert entry is not None
    market = MarketEngine().to_market_data(entry)

    analysis = AnalysisEngine().analyze(prediction, market, entry.decimal_odds())
    signal = DecisionEngine().decide(analysis, market)
    assert isinstance(signal, ValueSignal)
    assert signal.signal in set(SignalType)


def test_orchestrator_predict_reports() -> None:
    orchestrator = QuantBotOrchestrator()
    reports = orchestrator.predict(League.PREMIER_LEAGUE, SEASON)
    assert reports  # mid-season -> some upcoming matches
    for report in reports:
        total = (
            report.analysis.metric_for(MatchOutcome.HOME).model_prob
            + report.analysis.metric_for(MatchOutcome.DRAW).model_prob
            + report.analysis.metric_for(MatchOutcome.AWAY).model_prob
        )
        assert abs(total - 1.0) < 1e-6
        assert 0.0 <= report.signal.stake_fraction <= 1.0


def test_min_team_matches_blocks_low_data_tips() -> None:
    """With a high per-team threshold, no tips are issued; a clear reason shows."""

    orchestrator = QuantBotOrchestrator(min_team_matches=1000)
    reports = orchestrator.predict(League.PREMIER_LEAGUE, SEASON)
    assert reports  # matches still listed
    for report in reports:
        assert report.signal.signal is SignalType.NO_BET
        assert report.signal.rationale_de
        assert "pro team" in report.signal.rationale_de.lower()


def test_min_team_matches_default_off() -> None:
    """Default threshold (0) never triggers the low-data no-bet path."""

    default = QuantBotOrchestrator().predict(League.PREMIER_LEAGUE, SEASON)
    assert default
    assert not any(
        "pro team" in (r.signal.rationale_de or "").lower() for r in default
    )


def test_orchestrator_predict_with_calibrator() -> None:
    """The calibrated live-style pipeline runs and stays a valid distribution."""

    from quantbot.analysis.calibration import PlattScaler
    from quantbot.analysis.engine import AnalysisEngine

    orchestrator = QuantBotOrchestrator(
        calibrator=PlattScaler(),
        analysis_engine=AnalysisEngine(market_shrinkage=True),
    )
    reports = orchestrator.predict(League.PREMIER_LEAGUE, SEASON)
    assert reports
    for report in reports:
        total = sum(
            report.analysis.metric_for(o).model_prob for o in MatchOutcome
        )
        assert abs(total - 1.0) < 1e-6


def test_orchestrator_backtest_end_to_end() -> None:
    orchestrator = QuantBotOrchestrator(
        model=EloModel(),
        decision_engine=DecisionEngine(
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
        ),
        initial_bankroll=1000.0,
    )
    result = orchestrator.run_backtest(League.PREMIER_LEAGUE, SEASON)

    assert result.n_evaluated > 0
    assert result.n_bets > 0
    assert len(result.bankroll_curve) == result.n_bets + 1
    assert result.bankroll_curve[0] == 1000.0
    assert result.final_bankroll == pytest.approx(result.bankroll_curve[-1])
    # Metrics are internally consistent.
    assert result.metrics.n_bets == result.n_bets
    assert 0.0 <= result.metrics.win_rate <= 1.0
    assert result.metrics.max_drawdown >= 0.0
    # CLV was tracked from the closing line.
    assert result.metrics.avg_clv is not None


def test_ensemble_backtest_runs() -> None:
    """The heavier ensemble path also runs end to end."""

    orchestrator = QuantBotOrchestrator(
        model=EnsembleModel([EloModel(), LogisticRegressionModel()]),
    )
    result = orchestrator.run_backtest(League.BUNDESLIGA, SEASON)
    assert result.n_evaluated >= 0
    assert result.metrics.n_bets == result.n_bets
