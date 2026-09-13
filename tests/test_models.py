"""Tests for prediction models: probability sums, Dixon-Coles tau effect,
Elo updates, and data-leakage handling at fit time."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from quantbot.data import DummyDataProvider
from quantbot.models import DixonColesModel, EloModel, NotFittedError
from quantbot.schemas import (
    League,
    Match,
    MatchResult,
    MatchStatus,
    Team,
)

UTC = timezone.utc
SEASON = "2024-2025"
FAR_FUTURE = datetime(2026, 1, 1, tzinfo=UTC)
PROB_TOL = 1e-6


def _all_finished() -> list[Match]:
    provider = DummyDataProvider()
    return provider.get_matches(League.PREMIER_LEAGUE, SEASON, FAR_FUTURE) + provider.get_matches(
        League.BUNDESLIGA, SEASON, FAR_FUTURE
    )


def _match(home: str, away: str, kickoff: datetime, result: MatchResult | None = None) -> Match:
    return Match(
        match_id=f"{home}:{away}",
        league=League.PREMIER_LEAGUE,
        season=SEASON,
        kickoff=kickoff,
        prediction_timestamp=kickoff - timedelta(hours=2),
        home_team=Team(team_id=home, name=home),
        away_team=Team(team_id=away, name=away),
        status=MatchStatus.FINISHED if result else MatchStatus.SCHEDULED,
        result=result,
    )


# --- Shared prediction sanity ---


def test_dixon_coles_probabilities_sum_to_one() -> None:
    model = DixonColesModel(max_goals=8)
    model.fit(_all_finished())
    match = _all_finished()[0]
    pred = model.predict(match)
    total = pred.prob_home + pred.prob_draw + pred.prob_away
    assert abs(total - 1.0) < PROB_TOL
    assert pred.score_matrix is not None


def test_dixon_coles_score_matrix_sums_to_one() -> None:
    model = DixonColesModel(max_goals=8)
    model.fit(_all_finished())
    grid = model.score_matrix(
        _all_finished()[0].home_team.team_id, _all_finished()[0].away_team.team_id
    )
    assert grid.sum() == pytest.approx(1.0)


def test_elo_probabilities_sum_to_one() -> None:
    model = EloModel()
    model.fit(_all_finished())
    pred = model.predict(_all_finished()[0])
    total = pred.prob_home + pred.prob_draw + pred.prob_away
    assert abs(total - 1.0) < PROB_TOL


# --- Dixon-Coles tau effect vs naive Poisson ---


def test_tau_effect_shifts_low_scores() -> None:
    """Negative rho boosts 0:0 and 1:1, damps 1:0 and 0:1 vs independent Poisson."""

    model = DixonColesModel(max_goals=6)
    model._attack = {"A": 0.0, "B": 0.0}
    model._defense = {"A": 0.0, "B": 0.0}
    model._home_adv = 0.0
    model._is_fitted = True

    model._rho = 0.0
    naive = model.score_matrix("A", "B")
    model._rho = -0.1
    adjusted = model.score_matrix("A", "B")

    assert adjusted[0, 0] > naive[0, 0]
    assert adjusted[1, 1] > naive[1, 1]
    assert adjusted[0, 1] < naive[0, 1]
    assert adjusted[1, 0] < naive[1, 0]
    # A cell outside the tau-adjusted set keeps roughly its naive share.
    assert adjusted[2, 2] == pytest.approx(naive[2, 2], rel=0.05)


def test_negative_rho_increases_draw_probability() -> None:
    model = DixonColesModel(max_goals=6)
    model._attack = {"A": 0.0, "B": 0.0}
    model._defense = {"A": 0.0, "B": 0.0}
    model._home_adv = 0.0
    model._is_fitted = True

    model._rho = 0.0
    naive_draw = float(model.score_matrix("A", "B").trace())
    model._rho = -0.1
    adj_draw = float(model.score_matrix("A", "B").trace())
    assert adj_draw > naive_draw


# --- Elo rating updates ---


def test_elo_winner_gains_loser_loses() -> None:
    model = EloModel(use_mov=False, home_advantage=0.0)
    match = _match("A", "B", datetime(2024, 8, 1, 15, tzinfo=UTC), MatchResult(home_goals=2, away_goals=0))
    model.fit([match])
    assert model.rating("A") > 1500.0
    assert model.rating("B") < 1500.0
    # Zero-sum update: gains equal losses.
    assert (model.rating("A") - 1500.0) == pytest.approx(-(model.rating("B") - 1500.0))


def test_elo_mov_scales_update() -> None:
    big = EloModel(use_mov=True, home_advantage=0.0)
    small = EloModel(use_mov=True, home_advantage=0.0)
    kickoff = datetime(2024, 8, 1, 15, tzinfo=UTC)
    big.fit([_match("A", "B", kickoff, MatchResult(home_goals=5, away_goals=0))])
    small.fit([_match("A", "B", kickoff, MatchResult(home_goals=1, away_goals=0))])
    assert big.rating("A") > small.rating("A") > 1500.0


def test_elo_home_advantage_gives_edge_at_equal_rating() -> None:
    model = EloModel()
    model.fit(_all_finished())
    # Fresh, unrated teams: only home advantage separates them.
    match = _match("X", "Y", datetime(2025, 6, 1, 15, tzinfo=UTC))
    pred = model.predict(match)
    assert pred.prob_home > pred.prob_away


# --- Data leakage handling at fit ---


def test_fit_rejects_unfinished_matches() -> None:
    scheduled = _match("A", "B", datetime(2025, 6, 1, 15, tzinfo=UTC))  # no result
    with pytest.raises(ValueError, match="not finished"):
        EloModel().fit([scheduled])
    with pytest.raises(ValueError, match="not finished"):
        DixonColesModel(min_matches=1).fit([scheduled])


def test_predict_before_fit_raises() -> None:
    with pytest.raises(NotFittedError):
        EloModel().predict(_all_finished()[0])
    with pytest.raises(NotFittedError):
        DixonColesModel().predict(_all_finished()[0])


def test_fit_until_excludes_target_and_later_matches() -> None:
    matches = _all_finished()
    ordered = sorted(matches, key=lambda m: m.kickoff)
    target = ordered[10]

    model = EloModel()
    model.fit_until(matches, target.prediction_timestamp)

    trainable = [m for m in matches if m.kickoff < target.prediction_timestamp]
    total_games = sum(model._games_played.values())
    assert total_games == 2 * len(trainable)
    # The target match kicks off after its own prediction timestamp, so it is
    # never part of the training slice: no leakage of the outcome we predict.
    assert target not in trainable


def test_fit_until_empty_history_still_predicts() -> None:
    matches = _all_finished()
    earliest = min(m.kickoff for m in matches)
    model = EloModel()
    model.fit_until(matches, earliest)  # strictly-before => empty training set
    assert sum(model._games_played.values()) == 0
    pred = model.predict(matches[0])
    assert pred.confidence == 40.0
    assert abs(pred.prob_home + pred.prob_draw + pred.prob_away - 1.0) < PROB_TOL


def test_fit_until_requires_aware_as_of() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EloModel().fit_until(_all_finished(), datetime(2025, 1, 1))
