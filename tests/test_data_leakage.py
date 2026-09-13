"""Consolidated, explicit data-leakage test suite.

The single most important guardrail of QuantBot: no computation for a match may
use information created after that match's ``prediction_timestamp``. This file
verifies the guarantee at every layer that could break it:

    1. DataProvider ``as_of`` filtering (no future matches, odds, or results).
    2. FeatureExtractor snapshot stability (future matches never change features).
    3. Model ``fit_until`` boundaries and zero target-reading in ``predict``.
    4. Walk-forward loop isolation, proven by an in-the-loop spy model.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

import pytest

from quantbot.data import DummyDataProvider
from quantbot.features import FeatureExtractor
from quantbot.models import DixonColesModel, EloModel, LogisticRegressionModel
from quantbot.models.base import BaseModel, ModelPrediction
from quantbot.orchestrator import QuantBotOrchestrator
from quantbot.backtest import WalkForwardBacktester
from quantbot.schemas import League, Match, MatchStatus, Prediction

UTC = timezone.utc
SEASON = "2024-2025"
FAR_FUTURE = datetime(2026, 1, 1, tzinfo=UTC)
BEFORE_SEASON = datetime(2024, 1, 1, tzinfo=UTC)


def _all_finished() -> list[Match]:
    provider = DummyDataProvider()
    return provider.get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE) + provider.get_matches(
        League.BUNDESLIGA, SEASON, FAR_FUTURE
    )


# ---------------------------------------------------------------------------
# 1. DataProvider as_of filtering
# ---------------------------------------------------------------------------


class TestProviderAsOfFiltering:
    def test_no_result_visible_before_kickoff(self) -> None:
        provider = DummyDataProvider()
        matches = provider.get_matches(League.PREMIER_LEAGUE, SEASON, BEFORE_SEASON)
        assert matches
        for m in matches:
            assert m.result is None
            assert m.status is MatchStatus.SCHEDULED
            assert not m.is_finished

    def test_result_visible_only_after_kickoff(self) -> None:
        provider = DummyDataProvider()
        all_matches = provider.get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE)
        target = sorted(all_matches, key=lambda m: m.kickoff)[5]

        # One second before kickoff: still masked.
        just_before = provider.get_match(target.match_id, target.kickoff - timedelta(seconds=1))
        assert just_before is not None
        assert just_before.result is None

        # At kickoff: result becomes visible.
        at_kickoff = provider.get_match(target.match_id, target.kickoff)
        assert at_kickoff is not None
        assert at_kickoff.result is not None

    def test_odds_never_from_the_future(self) -> None:
        provider = DummyDataProvider()
        match = provider.get_matches(League.BUNDESLIGA, SEASON, FAR_FUTURE)[0]
        as_of = match.kickoff - timedelta(hours=24)
        for snapshot in provider.get_odds(match.match_id, as_of):
            assert snapshot.timestamp <= as_of

    def test_latest_odds_never_from_the_future(self) -> None:
        provider = DummyDataProvider()
        match = provider.get_matches(League.BUNDESLIGA, SEASON, FAR_FUTURE)[0]
        as_of = match.prediction_timestamp
        latest = provider.get_latest_odds(match.match_id, as_of)
        assert latest is not None
        assert latest.timestamp <= as_of

    def test_closing_line_hidden_before_close(self) -> None:
        provider = DummyDataProvider()
        match = provider.get_matches(League.BUNDESLIGA, SEASON, FAR_FUTURE)[0]
        early = provider.get_odds(match.match_id, match.kickoff - timedelta(hours=48))
        assert all(not o.is_closing for o in early)

    def test_finished_and_upcoming_partition_is_clean(self) -> None:
        provider = DummyDataProvider()
        all_matches = provider.get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE)
        as_of = sorted(m.kickoff for m in all_matches)[len(all_matches) // 2]
        finished = provider.get_finished_matches(League.PREMIER_LEAGUE, SEASON, as_of)
        upcoming = provider.get_upcoming_matches(League.PREMIER_LEAGUE, SEASON, as_of)
        assert all(m.kickoff <= as_of for m in finished)
        assert all(m.kickoff > as_of and m.result is None for m in upcoming)
        assert len(finished) + len(upcoming) == len(all_matches)


# ---------------------------------------------------------------------------
# 2. FeatureExtractor snapshot stability
# ---------------------------------------------------------------------------


class TestFeatureSnapshotStability:
    def test_future_matches_never_change_features(self) -> None:
        matches = sorted(_all_finished(), key=lambda m: m.kickoff)
        target = matches[15]
        extractor = FeatureExtractor()

        past_only = [m for m in matches if m.kickoff < target.prediction_timestamp]
        with_future = list(matches)  # includes matches after the target

        assert extractor.extract(target, past_only) == extractor.extract(target, with_future)

    def test_extract_equals_bulk_walk_snapshot(self) -> None:
        """A match's row in the chronological walk equals its as_of extraction."""

        matches = sorted(_all_finished(), key=lambda m: m.kickoff)
        extractor = FeatureExtractor()
        features, _ = extractor.build_training_set(matches)

        idx = 20
        target = matches[idx]
        standalone = extractor.extract(target, matches)  # full history, filtered internally
        # Compare each feature value.
        for name, value in standalone.items():
            assert features[idx][name] == pytest.approx(value)

    def test_shuffled_history_yields_same_features(self) -> None:
        import random

        matches = _all_finished()
        target = sorted(matches, key=lambda m: m.kickoff)[18]
        extractor = FeatureExtractor()

        ordered = extractor.extract(target, matches)
        shuffled_history = list(matches)
        random.Random(123).shuffle(shuffled_history)
        assert extractor.extract(target, shuffled_history) == ordered


# ---------------------------------------------------------------------------
# 3. Model fit_until boundaries and predict isolation
# ---------------------------------------------------------------------------


class TestModelBoundaries:
    def test_fit_until_excludes_target_and_later(self) -> None:
        matches = _all_finished()
        target = sorted(matches, key=lambda m: m.kickoff)[12]
        model = EloModel()
        model.fit_until(matches, target.prediction_timestamp)

        trainable = [m for m in matches if m.kickoff < target.prediction_timestamp]
        assert sum(model._games_played.values()) == 2 * len(trainable)
        assert target not in trainable  # kickoff is after its own prediction time

    def test_fit_until_empty_history_before_season(self) -> None:
        matches = _all_finished()
        model = EloModel()
        model.fit_until(matches, BEFORE_SEASON)
        assert sum(model._games_played.values()) == 0

    @pytest.mark.parametrize(
        "model_factory",
        [lambda: EloModel(), lambda: DixonColesModel(min_matches=10), lambda: LogisticRegressionModel()],
    )
    def test_predict_ignores_target_result(self, model_factory) -> None:  # type: ignore[no-untyped-def]
        matches = _all_finished()
        model = model_factory()
        model.fit(matches)
        target = matches[0]

        baseline = model.predict(target)
        # Mutate the target's result drastically; predictions must not move.
        altered = target.model_copy(
            update={"result": target.result.model_copy(update={"home_goals": 9, "away_goals": 0})}
        )
        after = model.predict(altered)
        assert (baseline.prob_home, baseline.prob_draw, baseline.prob_away) == (
            after.prob_home,
            after.prob_draw,
            after.prob_away,
        )

    def test_predict_ignores_masked_vs_unmasked_target(self) -> None:
        matches = _all_finished()
        model = EloModel()
        model.fit(matches)
        target = matches[3]
        masked = target.model_copy(update={"status": MatchStatus.SCHEDULED, "result": None})
        p_full = model.predict(target)
        p_masked = model.predict(masked)
        assert (p_full.prob_home, p_full.prob_draw, p_full.prob_away) == (
            p_masked.prob_home,
            p_masked.prob_draw,
            p_masked.prob_away,
        )


# ---------------------------------------------------------------------------
# 4. Walk-forward loop isolation via an in-the-loop spy model
# ---------------------------------------------------------------------------


class StrictLeakSpyModel(BaseModel):
    """Fails loudly if any leak occurs during the walk-forward loop.

    On every fit it verifies each training match is finished and kicked off
    before the next prediction; on every predict it verifies the target is
    masked (no result) and that no training match reaches its prediction time.
    """

    name = "strict_leak_spy"

    def __init__(self) -> None:
        super().__init__()
        self._train: list[Match] = []
        self.predicted: list[Match] = []

    def fit(self, matches: Sequence[Match]) -> None:
        for m in matches:
            assert m.is_finished and m.result is not None, "trained on an unresolved match"
        self._train = list(matches)
        self._is_fitted = True

    def predict(self, match: Match) -> ModelPrediction:
        # The backtester must hand us a masked target.
        assert match.result is None, "target result leaked into predict"
        assert match.status is MatchStatus.SCHEDULED
        # No training match may have kicked off at/after the target's decision time.
        for m in self._train:
            assert m.kickoff < match.prediction_timestamp, "future training data leaked"
        self.predicted.append(match)
        return Prediction(
            match_id=match.match_id,
            model_name=self.name,
            prediction_timestamp=match.prediction_timestamp,
            prob_home=1 / 3,
            prob_draw=1 / 3,
            prob_away=1 / 3,
        )


class TestWalkForwardIsolation:
    def test_backtest_loop_is_leak_free(self) -> None:
        provider = DummyDataProvider()
        matches = _all_finished()
        spy = StrictLeakSpyModel()
        result = WalkForwardBacktester(spy).run(matches, provider)

        # Every match with entry odds was evaluated and its spy asserts held.
        assert len(spy.predicted) == len(matches)
        assert result.n_evaluated == len(matches)
        # Predictions are strictly chronological (the loop never jumps ahead).
        kickoffs = [m.kickoff for m in spy.predicted]
        assert kickoffs == sorted(kickoffs)

    def test_orchestrator_backtest_is_leak_free(self) -> None:
        orchestrator = QuantBotOrchestrator(model=StrictLeakSpyModel())
        result = orchestrator.run_backtest(League.PREMIER_LEAGUE, SEASON)
        assert result.n_evaluated > 0

    def test_orchestrator_predict_uses_no_future_odds(self) -> None:
        orchestrator = QuantBotOrchestrator()
        as_of = orchestrator.default_as_of(League.PREMIER_LEAGUE, SEASON)
        reports = orchestrator.predict(League.PREMIER_LEAGUE, SEASON, as_of)
        provider = orchestrator.provider
        for report in reports:
            latest = provider.get_latest_odds(report.match.match_id, as_of)
            assert latest is not None
            assert latest.timestamp <= as_of
