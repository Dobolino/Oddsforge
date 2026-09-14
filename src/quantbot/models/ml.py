"""Machine-learning baseline models (Layer 1).

Both models follow the standard BaseModel contract. At ``fit`` they build a
leak-free training set from the supplied matches (features snapshot pre-match
state) and store that history. At ``predict`` they recompute features for the
target match using only the stored history filtered to before the target's
``prediction_timestamp``.

``LogisticRegressionModel`` is the linear baseline; ``GradientBoostingModel``
wraps scikit-learn's HistGradientBoosting classifier.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from quantbot.features.extractor import FEATURE_NAMES, LABEL_TO_OUTCOME, FeatureExtractor
from quantbot.models.base import BaseModel, ModelPrediction
from quantbot.schemas import Match, MatchOutcome, Prediction

# Full label space so predictions always have three columns.
_ALL_LABELS: tuple[int, ...] = (0, 1, 2)


class _SklearnClassifierModel(BaseModel):
    """Shared training/prediction machinery for sklearn-based models."""

    name = "sklearn"
    _min_samples = 10

    def __init__(
        self,
        extractor: FeatureExtractor | None = None,
        exclude_features: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._extractor = extractor or FeatureExtractor()
        self._history: list[Match] = []
        self._pipeline: Pipeline | None = None
        self.exclude_features = set(exclude_features or ())
        self._active = [n for n in FEATURE_NAMES if n not in self.exclude_features]

    def _build_pipeline(self) -> Pipeline:  # pragma: no cover - overridden
        raise NotImplementedError

    def _vec(self, features: dict[str, float]) -> list[float]:
        """Feature vector limited to the active (non-excluded) features."""

        return [features[n] for n in self._active]

    def fit(self, matches: Sequence[Match]) -> None:
        ordered = self._validate_training_matches(matches)
        features, labels = self._extractor.build_training_set(ordered)
        if len(features) < self._min_samples:
            raise ValueError(
                f"{self.name} needs at least {self._min_samples} samples, got {len(features)}"
            )
        if len(set(labels)) < 2:
            raise ValueError(f"{self.name} needs at least two outcome classes in training data")

        x = np.array([self._vec(f) for f in features], dtype=float)
        y = np.array(labels, dtype=int)

        pipeline = self._build_pipeline()
        pipeline.fit(x, y)
        self._pipeline = pipeline
        self._history = ordered
        self._is_fitted = True

    def _probabilities(self, match: Match) -> tuple[float, float, float]:
        assert self._pipeline is not None
        features = self._extractor.extract(match, self._history)
        x = np.array([self._vec(features)], dtype=float)
        proba = self._pipeline.predict_proba(x)[0]
        classes = list(self._pipeline.classes_)

        full = np.zeros(len(_ALL_LABELS), dtype=float)
        for label, p in zip(classes, proba, strict=True):
            full[int(label)] = p
        total = full.sum()
        if total <= 0.0:
            full = np.ones(len(_ALL_LABELS)) / len(_ALL_LABELS)
        else:
            full = full / total
        return float(full[0]), float(full[1]), float(full[2])

    def predict(self, match: Match) -> ModelPrediction:
        self._check_fitted()
        p_home, p_draw, p_away = self._probabilities(match)
        confidence = 40.0 + 50.0 * float(max(p_home, p_draw, p_away))
        return Prediction(
            match_id=match.match_id,
            model_name=self.name,
            prediction_timestamp=match.prediction_timestamp,
            prob_home=p_home,
            prob_draw=p_draw,
            prob_away=p_away,
            confidence=min(confidence, 95.0),
        )


class LogisticRegressionModel(_SklearnClassifierModel):
    """Multinomial logistic regression baseline with feature standardization."""

    name = "logistic_regression"

    def __init__(
        self,
        extractor: FeatureExtractor | None = None,
        c: float = 1.0,
        max_iter: int = 1000,
        random_state: int = 42,
        exclude_features: set[str] | None = None,
    ) -> None:
        super().__init__(extractor, exclude_features)
        self.c = c
        self.max_iter = max_iter
        self.random_state = random_state

    def _build_pipeline(self) -> Pipeline:
        return Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        C=self.c,
                        max_iter=self.max_iter,
                        random_state=self.random_state,
                    ),
                ),
            ]
        )


class GradientBoostingModel(_SklearnClassifierModel):
    """Histogram-based gradient boosting classifier."""

    name = "gradient_boosting"

    def __init__(
        self,
        extractor: FeatureExtractor | None = None,
        max_depth: int | None = 3,
        learning_rate: float = 0.1,
        max_iter: int = 200,
        random_state: int = 42,
        exclude_features: set[str] | None = None,
    ) -> None:
        super().__init__(extractor, exclude_features)
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.random_state = random_state

    def _build_pipeline(self) -> Pipeline:
        return Pipeline(
            [
                (
                    "clf",
                    HistGradientBoostingClassifier(
                        max_depth=self.max_depth,
                        learning_rate=self.learning_rate,
                        max_iter=self.max_iter,
                        random_state=self.random_state,
                    ),
                ),
            ]
        )


# Re-exported for callers that map labels back to outcomes.
__all__ = [
    "LogisticRegressionModel",
    "GradientBoostingModel",
    "LABEL_TO_OUTCOME",
    "MatchOutcome",
    "FEATURE_NAMES",
]
