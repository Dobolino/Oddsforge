"""Block B tests: time-decay weighting, xG Dixon-Coles, and xi tuning."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from quantbot.data import DummyDataProvider
from quantbot.features import FeatureExtractor
from quantbot.models import DixonColesModel, time_decay_weights
from quantbot.models.tuning import tune_time_decay
from quantbot.schemas import League, Match, MatchResult, MatchStatus, Team

UTC = timezone.utc
SEASON = "2024-2025"
FAR_FUTURE = datetime(2026, 1, 1, tzinfo=UTC)
BASE = datetime(2024, 8, 1, 15, 0, tzinfo=UTC)


def _all_finished() -> list[Match]:
    provider = DummyDataProvider()
    return provider.get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE) + provider.get_matches(
        League.BUNDESLIGA, SEASON, FAR_FUTURE
    )


def _match(
    idx: int,
    home: str,
    away: str,
    hg: int,
    ag: int,
    week: int,
    hxg: float | None = None,
    axg: float | None = None,
) -> Match:
    kickoff = BASE + timedelta(days=7 * week)
    return Match(
        match_id=f"m{idx}",
        league=League.PREMIER_LEAGUE,
        season=SEASON,
        kickoff=kickoff,
        prediction_timestamp=kickoff - timedelta(hours=2),
        home_team=Team(team_id=home, name=home),
        away_team=Team(team_id=away, name=away),
        status=MatchStatus.FINISHED,
        result=MatchResult(home_goals=hg, away_goals=ag, home_xg=hxg, away_xg=axg),
    )


# --- 1. Time-decay weighting math ---


def test_time_decay_weights_zero_xi_is_uniform() -> None:
    kickoffs = [BASE + timedelta(days=7 * i) for i in range(5)]
    weights = time_decay_weights(kickoffs, xi=0.0)
    assert np.allclose(weights, 1.0)


def test_time_decay_weights_newer_heavier() -> None:
    kickoffs = [BASE + timedelta(days=7 * i) for i in range(5)]
    weights = time_decay_weights(kickoffs, xi=0.05)
    # Strictly increasing: later kickoffs weigh more.
    assert all(weights[i] < weights[i + 1] for i in range(len(weights) - 1))
    # The most recent match has weight 1.0 (age 0).
    assert weights[-1] == pytest.approx(1.0)


def test_time_decay_weights_empty() -> None:
    assert time_decay_weights([], xi=0.05).size == 0


def test_feature_decay_favors_recent_form() -> None:
    # Team A: old wins, recent losses. Decay should pull form points down.
    history = [
        _match(1, "A", "B", 2, 0, week=0),
        _match(2, "A", "C", 2, 0, week=1),
        _match(3, "A", "D", 0, 2, week=2),
        _match(4, "A", "E", 0, 2, week=3),
        _match(5, "A", "F", 0, 2, week=4),
    ]
    target = _match(6, "A", "G", 0, 0, week=5)

    plain = FeatureExtractor(time_decay_xi=0.0).extract(target, history)
    decayed = FeatureExtractor(time_decay_xi=0.1).extract(target, history)
    # Recent matches are losses (0 points), so decay lowers the form average.
    assert decayed["home_form_points"] < plain["home_form_points"]


def test_feature_decay_identity_when_xi_zero() -> None:
    matches = _all_finished()
    target = sorted(matches, key=lambda m: m.kickoff)[20]
    a = FeatureExtractor(time_decay_xi=0.0).extract(target, matches)
    b = FeatureExtractor().extract(target, matches)  # default xi=0
    assert a == b


# --- 2. xG-adjusted Dixon-Coles ---


def _xg_dataset() -> list[Match]:
    teams = ["A", "B", "C", "D"]
    matches: list[Match] = []
    idx = 0
    week = 0
    for home in teams:
        for away in teams:
            if home == away:
                continue
            idx += 1
            week += 1
            # Goals say the away side scores; xG says the home side dominates.
            matches.append(
                _match(idx, home, away, hg=0, ag=1, week=week, hxg=2.5, axg=0.5)
            )
    return matches


def test_xg_dixon_coles_fits_and_predicts() -> None:
    matches = _xg_dataset()
    model = DixonColesModel(min_matches=8, use_xg=True)
    model.fit(matches)
    assert model.is_fitted
    assert model.rho == 0.0  # low-score correction disabled in xG mode
    pred = model.predict(matches[0])
    assert abs(pred.prob_home + pred.prob_draw + pred.prob_away - 1.0) < 1e-6


def test_xg_and_goals_fits_differ() -> None:
    matches = _xg_dataset()
    goals_model = DixonColesModel(min_matches=8, use_xg=False)
    xg_model = DixonColesModel(min_matches=8, use_xg=True)
    goals_model.fit(matches)
    xg_model.fit(matches)

    target = matches[0]
    p_goals = goals_model.predict(target)
    p_xg = xg_model.predict(target)
    # xG favors the home side; goals favor the away side.
    assert p_xg.prob_home > p_goals.prob_home


def test_xg_falls_back_to_goals_when_missing() -> None:
    # No xG provided: xG mode must still fit using actual goals.
    matches = [
        _match(i, h, a, hg=2, ag=1, week=i)
        for i, (h, a) in enumerate(
            [("A", "B"), ("B", "C"), ("C", "A"), ("A", "C"), ("B", "A"), ("C", "B"),
             ("A", "D"), ("D", "B"), ("C", "D"), ("D", "A")]
        )
    ]
    model = DixonColesModel(min_matches=8, use_xg=True)
    model.fit(matches)
    pred = model.predict(matches[0])
    assert abs(pred.prob_home + pred.prob_draw + pred.prob_away - 1.0) < 1e-6


# --- 3. Xi tuning ---


def test_tune_time_decay_selects_from_grid() -> None:
    matches = _all_finished()
    grid = [0.0, 0.005, 0.05]
    result = tune_time_decay(
        matches,
        grid,
        build_model=lambda xi: DixonColesModel(min_matches=5, time_decay_xi=xi),
        n_splits=3,
    )
    assert result.best_xi in grid
    assert set(result.scores) == set(grid)
    assert result.best_score == min(result.scores.values())
    assert all(np.isfinite(v) for v in result.scores.values())


def test_tune_time_decay_rejects_empty_grid() -> None:
    with pytest.raises(ValueError, match="xi_grid must not be empty"):
        tune_time_decay(_all_finished(), [], build_model=lambda xi: DixonColesModel())


def test_tune_time_decay_rejects_too_few_matches() -> None:
    matches = _all_finished()[:2]
    with pytest.raises(ValueError, match="more matches than folds"):
        tune_time_decay(matches, [0.0], build_model=lambda xi: DixonColesModel(), n_splits=3)
