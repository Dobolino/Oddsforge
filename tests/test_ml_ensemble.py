"""Tests for feature extraction, ML baselines, and the ensemble layer."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from quantbot.data import DummyDataProvider
from quantbot.features import FEATURE_NAMES, FeatureExtractor
from quantbot.models import (
    EloModel,
    EnsembleModel,
    GradientBoostingModel,
    LogisticRegressionModel,
    NotFittedError,
    multiclass_brier,
)
from quantbot.models.base import BaseModel, ModelPrediction
from quantbot.schemas import League, Match, Prediction

UTC = timezone.utc
SEASON = "2024-2025"
FAR_FUTURE = datetime(2026, 1, 1, tzinfo=UTC)


def _all_finished() -> list[Match]:
    provider = DummyDataProvider()
    return provider.get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE) + provider.get_matches(
        League.BUNDESLIGA, SEASON, FAR_FUTURE
    )


class ConstantModel(BaseModel):
    """Test double returning fixed probabilities."""

    def __init__(self, name: str, probs: tuple[float, float, float]) -> None:
        super().__init__()
        self.name = name
        self.probs = probs

    def fit(self, matches):  # type: ignore[no-untyped-def]
        self._is_fitted = True

    def predict(self, match: Match) -> ModelPrediction:
        self._check_fitted()
        return Prediction(
            match_id=match.match_id,
            model_name=self.name,
            prediction_timestamp=match.prediction_timestamp,
            prob_home=self.probs[0],
            prob_draw=self.probs[1],
            prob_away=self.probs[2],
        )


# --- Feature extractor: leak freedom ---


def test_extract_ignores_matches_at_or_after_as_of() -> None:
    matches = sorted(_all_finished(), key=lambda m: m.kickoff)
    target = matches[12]
    extractor = FeatureExtractor()

    past_only = [m for m in matches if m.kickoff < target.prediction_timestamp]
    with_future = matches  # includes matches after the target

    f_past = extractor.extract(target, past_only)
    f_all = extractor.extract(target, with_future)
    assert f_past == f_all


def test_extract_returns_all_feature_names() -> None:
    matches = _all_finished()
    feats = FeatureExtractor().extract(matches[0], matches)
    assert set(feats) == set(FEATURE_NAMES)


def test_build_training_set_first_match_has_no_history() -> None:
    matches = _all_finished()
    features, labels = FeatureExtractor().build_training_set(matches)
    assert len(features) == len(labels) == len(matches)
    first = features[0]
    assert first["elo_diff"] == 0.0
    assert first["home_matches_played"] == 0.0
    assert first["away_matches_played"] == 0.0
    assert all(label in (0, 1, 2) for label in labels)


def test_build_training_set_accumulates_history() -> None:
    matches = _all_finished()
    features, _ = FeatureExtractor().build_training_set(matches)
    # Later matches should show non-zero accumulated match counts.
    assert features[-1]["home_matches_played"] > 0.0


# --- ML models ---


@pytest.mark.parametrize("model_cls", [LogisticRegressionModel, GradientBoostingModel])
def test_ml_model_predicts_valid_distribution(model_cls) -> None:  # type: ignore[no-untyped-def]
    matches = _all_finished()
    model = model_cls()
    model.fit(matches)
    pred = model.predict(matches[0])
    total = pred.prob_home + pred.prob_draw + pred.prob_away
    assert abs(total - 1.0) < 1e-6
    assert 0.0 <= pred.prob_home <= 1.0
    assert 0.0 <= pred.confidence <= 100.0


def test_ml_predict_before_fit_raises() -> None:
    with pytest.raises(NotFittedError):
        LogisticRegressionModel().predict(_all_finished()[0])


def test_ml_fit_rejects_unfinished() -> None:
    provider = DummyDataProvider()
    before = datetime(2024, 1, 1, tzinfo=UTC)
    scheduled = provider.get_matches(League.PREMIER_LEAGUE, SEASON, before)
    with pytest.raises(ValueError, match="not finished"):
        LogisticRegressionModel().fit(scheduled)


def test_ml_fit_requires_minimum_samples() -> None:
    matches = _all_finished()[:5]
    with pytest.raises(ValueError, match="at least"):
        LogisticRegressionModel().fit(matches)


def test_ml_predict_is_leak_free_ignores_target_result() -> None:
    """Predicting the same fixture yields the same probs regardless of its result."""

    matches = _all_finished()
    model = LogisticRegressionModel()
    model.fit(matches)
    target = matches[0]
    p1 = model.predict(target)
    # A hypothetical, differently-scored version of the same fixture.
    altered = target.model_copy(update={"result": None})
    altered = altered.model_copy(
        update={"result": target.result.model_copy(update={"home_goals": 9, "away_goals": 0})}
    )
    p2 = model.predict(altered)
    assert (p1.prob_home, p1.prob_draw, p1.prob_away) == (
        p2.prob_home,
        p2.prob_draw,
        p2.prob_away,
    )


# --- Ensemble aggregation ---


def test_multiclass_brier_values() -> None:
    perfect = multiclass_brier(np.array([[1.0, 0.0, 0.0]]), np.array([0]))
    assert perfect == pytest.approx(0.0)
    half = multiclass_brier(np.array([[0.5, 0.5, 0.0]]), np.array([0]))
    assert half == pytest.approx(0.5)


def test_ensemble_configured_weights_aggregation() -> None:
    a = ConstantModel("a", (0.6, 0.2, 0.2))
    b = ConstantModel("b", (0.2, 0.2, 0.6))
    ensemble = EnsembleModel([a, b], weights=[0.25, 0.75])
    ensemble.fit(_all_finished())
    pred = ensemble.predict(_all_finished()[0])
    assert pred.prob_home == pytest.approx(0.30)
    assert pred.prob_draw == pytest.approx(0.20)
    assert pred.prob_away == pytest.approx(0.50)


def test_ensemble_weights_are_normalized() -> None:
    ensemble = EnsembleModel(
        [ConstantModel("a", (0.5, 0.3, 0.2)), ConstantModel("b", (0.2, 0.3, 0.5))],
        weights=[3.0, 1.0],
    )
    assert sum(ensemble.weights) == pytest.approx(1.0)
    assert ensemble.weights[0] == pytest.approx(0.75)


def test_ensemble_prediction_sums_to_one() -> None:
    ensemble = EnsembleModel(
        [EloModel(), LogisticRegressionModel(), GradientBoostingModel()],
    )
    ensemble.fit(_all_finished())
    pred = ensemble.predict(_all_finished()[0])
    total = pred.prob_home + pred.prob_draw + pred.prob_away
    assert abs(total - 1.0) < 1e-6


def test_ensemble_weight_optimization() -> None:
    ensemble = EnsembleModel(
        [EloModel(), LogisticRegressionModel(), GradientBoostingModel()],
        optimize_weights=True,
        val_fraction=0.3,
    )
    ensemble.fit(_all_finished())
    weights = ensemble.weights
    assert len(weights) == 3
    assert sum(weights) == pytest.approx(1.0)
    assert all(w >= 0.0 for w in weights)
    pred = ensemble.predict(_all_finished()[0])
    assert abs(pred.prob_home + pred.prob_draw + pred.prob_away - 1.0) < 1e-6


def test_ensemble_requires_at_least_one_model() -> None:
    with pytest.raises(ValueError, match="at least one model"):
        EnsembleModel([])
