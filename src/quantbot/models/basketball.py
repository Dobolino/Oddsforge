"""Basketball (NBA) Gaussian prediction model (Layer 1).

Expected home/away points are modelled as Normals fit from finished games.
Moneyline and totals probabilities use the Gaussian CDF — a solid first-order
fit for high-scoring basketball.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import erf, sqrt

from quantbot.models.base import BaseModel, ModelPrediction
from quantbot.schemas import Match, Prediction
from quantbot.schemas.enums import DEFAULT_NBA_TOTALS_LINE, Sport


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


class BasketballModel(BaseModel):
    """Gaussian team-strength model for basketball moneyline + totals."""

    name: str = "basketball_gaussian"

    def __init__(self, *, default_total: float = DEFAULT_NBA_TOTALS_LINE) -> None:
        super().__init__()
        self.default_total = float(default_total)
        self._offence: dict[str, float] = {}
        self._defence: dict[str, float] = {}
        self._league_avg_home: float = default_total / 2.0
        self._league_avg_away: float = default_total / 2.0
        self._residual_sigma: float = 12.0

    def fit(self, matches: Sequence[Match]) -> None:
        finished = self._validate_training_matches(matches)
        bb = [
            m
            for m in finished
            if m.sport is Sport.BASKETBALL or m.league.value == "nba"
        ]
        if not bb:
            self._is_fitted = True
            return

        home_pts = [float(m.result.home_goals) for m in bb]  # type: ignore[union-attr]
        away_pts = [float(m.result.away_goals) for m in bb]  # type: ignore[union-attr]
        self._league_avg_home = sum(home_pts) / len(home_pts)
        self._league_avg_away = sum(away_pts) / len(away_pts)

        scored: dict[str, list[float]] = {}
        allowed: dict[str, list[float]] = {}
        for m in bb:
            assert m.result is not None
            scored.setdefault(m.home_team.team_id, []).append(float(m.result.home_goals))
            scored.setdefault(m.away_team.team_id, []).append(float(m.result.away_goals))
            allowed.setdefault(m.home_team.team_id, []).append(float(m.result.away_goals))
            allowed.setdefault(m.away_team.team_id, []).append(float(m.result.home_goals))

        self._offence = {tid: sum(v) / len(v) for tid, v in scored.items()}
        self._defence = {tid: sum(v) / len(v) for tid, v in allowed.items()}

        residuals: list[float] = []
        for m in bb:
            assert m.result is not None
            mu_h, mu_a = self._expected_points(m)
            residuals.append(float(m.result.home_goals) - mu_h)
            residuals.append(float(m.result.away_goals) - mu_a)
        if residuals:
            var = sum(r * r for r in residuals) / len(residuals)
            self._residual_sigma = max(6.0, sqrt(var))
        self._is_fitted = True

    def _expected_points(self, match: Match) -> tuple[float, float]:
        home_off = self._offence.get(match.home_team.team_id, self._league_avg_home)
        away_off = self._offence.get(match.away_team.team_id, self._league_avg_away)
        home_def = self._defence.get(match.home_team.team_id, self._league_avg_away)
        away_def = self._defence.get(match.away_team.team_id, self._league_avg_home)
        mu_home = 0.5 * (home_off + away_def) + 1.25
        mu_away = 0.5 * (away_off + home_def) - 1.25
        return mu_home, mu_away

    def predict(self, match: Match) -> ModelPrediction:
        self._check_fitted()
        mu_h, mu_a = self._expected_points(match)
        margin_mu = mu_h - mu_a
        margin_sigma = self._residual_sigma * sqrt(2.0)
        p_home = 1.0 - _norm_cdf((0.0 - margin_mu) / margin_sigma)
        p_away = 1.0 - p_home
        draw_eps = 1e-6
        p_home = max(0.0, p_home - draw_eps / 2.0)
        p_away = max(0.0, p_away - draw_eps / 2.0)
        total = p_home + p_away + draw_eps
        return Prediction(
            match_id=match.match_id,
            model_name=self.name,
            prediction_timestamp=match.prediction_timestamp,
            prob_home=p_home / total,
            prob_draw=draw_eps / total,
            prob_away=p_away / total,
            confidence=min(90.0, 40.0 + abs(margin_mu)),
        )

    def totals_probabilities(
        self, match: Match, *, line: float | None = None
    ) -> tuple[float, float]:
        self._check_fitted()
        mu_h, mu_a = self._expected_points(match)
        total_mu = mu_h + mu_a
        total_sigma = self._residual_sigma * sqrt(2.0)
        used = self.default_total if line is None else float(line)
        p_under = _norm_cdf((used - total_mu) / total_sigma)
        return 1.0 - p_under, p_under

    def spread_probabilities(
        self, match: Match, *, line: float
    ) -> tuple[float, float]:
        self._check_fitted()
        mu_h, mu_a = self._expected_points(match)
        margin_mu = mu_h - mu_a
        margin_sigma = self._residual_sigma * sqrt(2.0)
        threshold = -float(line)
        p_home_cover = 1.0 - _norm_cdf((threshold - margin_mu) / margin_sigma)
        return p_home_cover, 1.0 - p_home_cover
