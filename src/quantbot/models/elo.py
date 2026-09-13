"""Dynamic Elo rating model.

Sequential fit: ratings update match by match in chronological order, so a
team's rating before a given match reflects only earlier results. Elo expected
score is mapped to 1X2 probabilities via a distance-dependent draw model that
keeps E[points] = P(home) + 0.5 * P(draw) exact.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from quantbot.models.base import BaseModel, ModelPrediction
from quantbot.schemas import Match, MatchResult, Prediction


class EloModel(BaseModel):
    """Elo with home advantage and margin-of-victory scaling.

    Args:
        k_factor: Base update step.
        home_advantage: Rating points added to the home side pre-match.
        initial_rating: Rating assigned to a team's first appearance.
        draw_max: Maximum draw probability (at equal strength).
        draw_scale: Rating gap over which draw probability decays.
        use_mov: Scale the update by margin of victory.
    """

    name = "elo"

    def __init__(
        self,
        k_factor: float = 20.0,
        home_advantage: float = 65.0,
        initial_rating: float = 1500.0,
        draw_max: float = 0.28,
        draw_scale: float = 200.0,
        use_mov: bool = True,
    ) -> None:
        super().__init__()
        if k_factor <= 0:
            raise ValueError("k_factor must be positive")
        if not 0.0 < draw_max < 1.0:
            raise ValueError("draw_max must be in (0, 1)")
        if draw_scale <= 0:
            raise ValueError("draw_scale must be positive")
        self.k_factor = k_factor
        self.home_advantage = home_advantage
        self.initial_rating = initial_rating
        self.draw_max = draw_max
        self.draw_scale = draw_scale
        self.use_mov = use_mov
        self._ratings: dict[str, float] = {}
        self._games_played: dict[str, int] = {}

    # --- Rating access ---

    def rating(self, team_id: str) -> float:
        return self._ratings.get(team_id, self.initial_rating)

    def _expected_home_score(self, home_id: str, away_id: str) -> float:
        """Expected points fraction for the home team (win=1, draw=0.5)."""

        d = self.rating(home_id) + self.home_advantage - self.rating(away_id)
        return 1.0 / (1.0 + math.pow(10.0, -d / 400.0))

    def _mov_multiplier(self, goal_diff: int, rating_diff: float) -> float:
        """538-style margin-of-victory multiplier."""

        if not self.use_mov or goal_diff == 0:
            return 1.0
        return math.log(abs(goal_diff) + 1.0) * (2.2 / ((rating_diff * 0.001) + 2.2))

    # --- Fit ---

    def fit(self, matches: Sequence[Match]) -> None:
        ordered = self._validate_training_matches(matches)
        self._ratings.clear()
        self._games_played.clear()
        for match in ordered:
            self._update(match)
        self._is_fitted = True

    def _update(self, match: Match) -> None:
        result: MatchResult = match.result  # validated finished by caller
        home_id = match.home_team.team_id
        away_id = match.away_team.team_id

        expected = self._expected_home_score(home_id, away_id)
        if result.home_goals > result.away_goals:
            actual = 1.0
        elif result.home_goals < result.away_goals:
            actual = 0.0
        else:
            actual = 0.5

        rating_diff_winner = (
            self.rating(home_id) + self.home_advantage - self.rating(away_id)
            if actual >= 0.5
            else self.rating(away_id) - self.rating(home_id) - self.home_advantage
        )
        goal_diff = result.home_goals - result.away_goals
        mult = self._mov_multiplier(goal_diff, rating_diff_winner)

        change = self.k_factor * mult * (actual - expected)
        self._ratings[home_id] = self.rating(home_id) + change
        self._ratings[away_id] = self.rating(away_id) - change
        self._games_played[home_id] = self._games_played.get(home_id, 0) + 1
        self._games_played[away_id] = self._games_played.get(away_id, 0) + 1

    # --- Predict ---

    def _outcome_probabilities(self, home_id: str, away_id: str) -> tuple[float, float, float]:
        expected = self._expected_home_score(home_id, away_id)
        d = self.rating(home_id) + self.home_advantage - self.rating(away_id)
        p_draw = self.draw_max * math.exp(-((d / self.draw_scale) ** 2))
        # E[points] = p_home + 0.5 * p_draw  =>  p_home = expected - 0.5 * p_draw.
        p_home = expected - 0.5 * p_draw
        p_away = 1.0 - p_draw - p_home
        # Guard against tiny negatives at extreme rating gaps, then renormalize.
        p_home = max(p_home, 1e-6)
        p_away = max(p_away, 1e-6)
        total = p_home + p_draw + p_away
        return p_home / total, p_draw / total, p_away / total

    def predict(self, match: Match) -> ModelPrediction:
        self._check_fitted()
        p_home, p_draw, p_away = self._outcome_probabilities(
            match.home_team.team_id, match.away_team.team_id
        )
        games = min(
            self._games_played.get(match.home_team.team_id, 0),
            self._games_played.get(match.away_team.team_id, 0),
        )
        # Confidence grows with the number of observed games, capped at 90.
        confidence = min(90.0, 40.0 + 5.0 * games)
        return Prediction(
            match_id=match.match_id,
            model_name=self.name,
            prediction_timestamp=match.prediction_timestamp,
            prob_home=p_home,
            prob_draw=p_draw,
            prob_away=p_away,
            confidence=confidence,
        )
