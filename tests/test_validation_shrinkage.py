"""P0 validation artifact + EFF_SAMPLE shrinkage tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from quantbot.analysis.confidence import ConfidenceLevel, DataQualitySignals
from quantbot.analysis.engine import (
    AnalysisEngine,
    AnalysisResult,
    ShrinkageMode,
    eff_sample_weight,
    effective_sample_size,
)
from quantbot.analysis.validation import (
    ValidationCriteria,
    ValidationMetrics,
    build_artifact,
    evaluate_artifact,
    load_latest_artifact,
    pipeline_hash,
    policy_content_hash,
    policy_from_artifact,
    save_artifact,
)
from quantbot.decision.engine import DecisionEngine
from quantbot.decision.policy import (
    DecisionStatus,
    PolicyProfile,
    ValidationStatus,
    live_policy,
)
from quantbot.markets.odds import MarketEngine
from quantbot.schemas import (
    MarginMethod,
    MarketData,
    MatchOutcome,
    Odds,
    Prediction,
    ValueMetrics,
)

UTC = timezone.utc
TS = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)


def _ts(y: int = 2024, m: int = 6, d: int = 1) -> datetime:
    return datetime(y, m, d, tzinfo=UTC)


def _prediction(h: float, d: float, a: float) -> Prediction:
    return Prediction(
        match_id="m1",
        model_name="test",
        prediction_timestamp=TS,
        prob_home=h,
        prob_draw=d,
        prob_away=a,
        confidence=70.0,
    )


def _market(h: float, d: float, a: float) -> MarketData:
    return MarketData(
        match_id="m1",
        bookmaker="bk",
        timestamp=TS,
        method=MarginMethod.SHIN,
        fair_home=h,
        fair_draw=d,
        fair_away=a,
        overround=0.05,
    )


def test_evaluate_without_criteria_stays_unvalidated() -> None:
    status = evaluate_artifact(
        criteria=None,
        metrics=ValidationMetrics(n=500, brier=0.1, ece=0.02),
    )
    assert status is ValidationStatus.UNVALIDATED
    empty = ValidationCriteria()
    assert empty.has_bounds() is False
    assert (
        evaluate_artifact(criteria=empty, metrics=ValidationMetrics(n=500))
        is ValidationStatus.UNVALIDATED
    )


def test_evaluate_passes_only_when_all_bounds_met() -> None:
    criteria = ValidationCriteria(min_n=100, max_brier=0.25, max_ece=0.08)
    ok = ValidationMetrics(n=120, brier=0.20, ece=0.05)
    assert evaluate_artifact(criteria=criteria, metrics=ok) is ValidationStatus.VALID
    fail_n = ValidationMetrics(n=50, brier=0.20, ece=0.05)
    assert evaluate_artifact(criteria=criteria, metrics=fail_n) is ValidationStatus.UNVALIDATED
    fail_ece = ValidationMetrics(n=120, brier=0.20, ece=0.20)
    assert evaluate_artifact(criteria=criteria, metrics=fail_ece) is ValidationStatus.UNVALIDATED


def test_evaluate_expired() -> None:
    criteria = ValidationCriteria(min_n=10)
    metrics = ValidationMetrics(n=50)
    assert (
        evaluate_artifact(
            criteria=criteria,
            metrics=metrics,
            expires_at=_ts(2020, 1, 1),
            now=_ts(2024, 1, 1),
        )
        is ValidationStatus.EXPIRED
    )


def test_demo_artifact_does_not_validate_live(tmp_path: Path) -> None:
    art = build_artifact(
        scope="football:1x2:demo",
        profile="demo",
        train_end=_ts(2023, 12, 31),
        test_start=_ts(2024, 1, 1),
        test_end=_ts(2024, 6, 1),
        pipeline_hash="abc",
        policy_hash="def",
        policy_version="1.0.0",
        n_train=200,
        n_test=100,
        criteria=ValidationCriteria(min_n=50),
        metrics=ValidationMetrics(n=100),
    )
    assert art.status is ValidationStatus.VALID
    path = save_artifact(art, directory=tmp_path)
    assert path.exists()
    loaded = load_latest_artifact(scope="football:1x2:demo", directory=tmp_path)
    assert loaded is not None
    assert loaded.status is ValidationStatus.VALID

    gated = policy_from_artifact(art, base=live_policy())
    assert gated.profile is PolicyProfile.LIVE
    assert gated.validation_status is ValidationStatus.UNVALIDATED
    assert gated.sizing_released is False


def test_valid_live_artifact_releases_sizing() -> None:
    art = build_artifact(
        scope="football:1x2:bl",
        profile="live",
        train_end=_ts(2023, 12, 31),
        test_start=_ts(2024, 1, 1),
        test_end=_ts(2024, 6, 1),
        pipeline_hash=pipeline_hash(model_name="elo", shrinkage_mode="legacy_depth"),
        policy_hash=policy_content_hash(live_policy()),
        policy_version="1.0.0",
        n_train=400,
        n_test=150,
        criteria=ValidationCriteria(min_n=100, max_brier=0.30),
        metrics=ValidationMetrics(n=150, brier=0.22),
        expires_at=_ts(2030, 1, 1),
    )
    assert art.status is ValidationStatus.VALID
    policy = policy_from_artifact(art, base=live_policy())
    assert policy.validation_status is ValidationStatus.VALID
    assert policy.sizing_released is True

    locked = policy_from_artifact(
        art, base=live_policy(), expected_pipeline_hash="not-the-hash"
    )
    assert locked.validation_status is ValidationStatus.UNVALIDATED


def test_expired_artifact_blocks_sizing_via_policy() -> None:
    art = build_artifact(
        scope="football:1x2:bl",
        profile="live",
        train_end=_ts(2022, 1, 1),
        test_start=_ts(2022, 2, 1),
        test_end=_ts(2022, 6, 1),
        pipeline_hash="p",
        policy_hash="q",
        policy_version="1.0.0",
        n_train=100,
        n_test=80,
        criteria=ValidationCriteria(min_n=10),
        metrics=ValidationMetrics(n=80),
        expires_at=_ts(2023, 1, 1),
        evaluate=False,
        status=ValidationStatus.VALID,
    )
    policy = policy_from_artifact(art, base=live_policy(), now=_ts(2024, 1, 1))
    assert policy.validation_status is ValidationStatus.EXPIRED
    assert policy.sizing_released is False

    metric = ValueMetrics(
        outcome=MatchOutcome.HOME,
        model_prob=0.60,
        fair_market_prob=0.50,
        decimal_odds=2.10,
        edge=0.10,
        expected_value=0.60 * 2.10 - 1.0,
    )
    analysis = AnalysisResult(
        match_id="m1",
        metrics=(metric,),
        best_ev=metric,
        data_quality=80.0,
        model_confidence=70.0,
        confidence_level=ConfidenceLevel.MEDIUM,
        ensemble_agreement=1.0,
        home_matches=8,
        away_matches=8,
    )
    entry = Odds(
        match_id="m1",
        bookmaker="x",
        timestamp=_ts(2024, 12, 1),
        home=2.10,
        draw=3.40,
        away=3.50,
    )
    market = MarketEngine().to_market_data(entry)
    signal = DecisionEngine.from_policy(policy).decide(
        analysis, market, home_matches=8, away_matches=8
    )
    assert signal.stake_fraction == 0.0
    assert signal.decision_status == DecisionStatus.VALUE_EXPLORATORY.value


def test_effective_sample_size_weighted_and_conservative() -> None:
    assert effective_sample_size([1.0, 1.0, 1.0, 1.0]) == pytest.approx(4.0)
    assert effective_sample_size([10.0, 0.1, 0.1]) < 1.5
    assert effective_sample_size(home_matches=12, away_matches=5) == pytest.approx(5.0)
    assert eff_sample_weight(10.0, 10.0) == pytest.approx(0.5)
    assert eff_sample_weight(0.0, 10.0) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        eff_sample_weight(5.0, 0.0)


def test_eff_sample_shrinkage_pulls_toward_market() -> None:
    pred = _prediction(0.80, 0.12, 0.08)
    market = _market(0.50, 0.27, 0.23)
    odds = {MatchOutcome.HOME: 2.1, MatchOutcome.DRAW: 3.6, MatchOutcome.AWAY: 4.2}
    thin = DataQualitySignals(
        home_matches=2, away_matches=2, n_bookmakers=1, injuries_known=False
    )

    plain = AnalysisEngine().analyze(pred, market, odds, thin)
    legacy = AnalysisEngine(market_shrinkage=True).analyze(pred, market, odds, thin)
    eff = AnalysisEngine(
        shrinkage_mode=ShrinkageMode.EFF_SAMPLE, shrinkage_k=10.0
    ).analyze(pred, market, odds, thin)

    assert plain.shrinkage_mode == ShrinkageMode.OFF.value
    assert legacy.shrinkage_mode == ShrinkageMode.LEGACY_DEPTH.value
    assert eff.shrinkage_mode == ShrinkageMode.EFF_SAMPLE.value
    assert eff.p_raw_home == pytest.approx(0.80)
    assert eff.shrinkage_weight == pytest.approx(eff_sample_weight(2.0, 10.0))

    plain_edge = plain.metric_for(MatchOutcome.HOME).edge
    eff_edge = eff.metric_for(MatchOutcome.HOME).edge
    assert eff_edge < plain_edge
    assert eff_edge > 0.0
    # With n_eff=2 and k=10, EFF_SAMPLE trusts the model less than LEGACY
    # depth/target=2/10 when both use the same depth — same formula here for
    # min matches; still ensure audit fields are populated.
    assert legacy.shrinkage_weight == pytest.approx(0.2)


def test_legacy_bool_still_maps_to_legacy_depth() -> None:
    engine = AnalysisEngine(market_shrinkage=True)
    assert engine.shrinkage_mode is ShrinkageMode.LEGACY_DEPTH
    engine_off = AnalysisEngine()
    assert engine_off.shrinkage_mode is ShrinkageMode.OFF


def test_orchestrator_applies_validation_artifact() -> None:
    from quantbot.orchestrator import QuantBotOrchestrator

    art = build_artifact(
        scope="football:1x2:bl",
        profile="live",
        train_end=_ts(2023, 1, 1),
        test_start=_ts(2023, 2, 1),
        test_end=_ts(2023, 6, 1),
        pipeline_hash="pipe",
        policy_hash="pol",
        policy_version="1.0.0",
        n_train=100,
        n_test=80,
        criteria=ValidationCriteria(min_n=10),
        metrics=ValidationMetrics(n=80),
    )
    orch = QuantBotOrchestrator(live=True, validation_artifact=art)
    assert orch.policy.validation_status is ValidationStatus.VALID
    assert orch.policy.sizing_released is True
