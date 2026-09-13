"""Dixon-Coles bivariate Poisson model.

Estimates per-team attack/defense strengths, a home-advantage term, and the
Dixon-Coles low-score dependence parameter ``rho`` via maximum likelihood
(``scipy.optimize.minimize``). Produces an ``N x N`` scoreline matrix and
marginalizes it to 1X2 probabilities.

The ``rho`` correction (tau) reweights the four low-scoring outcomes
(0:0, 1:0, 0:1, 1:1) relative to independent Poisson marginals, which the
data show are mispriced by a naive double-Poisson.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.optimize import minimize

from quantbot.logging import get_logger
from quantbot.models.base import BaseModel, ModelPrediction
from quantbot.schemas import Match, Prediction, ScoreMatrix

logger = get_logger(__name__)


def _dixon_coles_tau(
    x: np.ndarray, y: np.ndarray, lam_home: float, lam_away: float, rho: float
) -> np.ndarray:
    """Vectorized low-score dependence factor tau(x, y)."""

    tau = np.ones_like(x, dtype=float)
    tau[(x == 0) & (y == 0)] = 1.0 - lam_home * lam_away * rho
    tau[(x == 0) & (y == 1)] = 1.0 + lam_home * rho
    tau[(x == 1) & (y == 0)] = 1.0 + lam_away * rho
    tau[(x == 1) & (y == 1)] = 1.0 - rho
    return tau


def _poisson_pmf(k: np.ndarray, lam: float) -> np.ndarray:
    """Poisson pmf; numerically stable via log-space."""

    from scipy.special import gammaln

    log_pmf = -lam + k * math.log(lam) - gammaln(k + 1.0)
    return np.exp(log_pmf)


class DixonColesModel(BaseModel):
    """Dixon-Coles Poisson goal model.

    Args:
        max_goals: Grid size for the scoreline matrix (0..max_goals per side).
        min_matches: Minimum finished matches required to fit.
        rho_init: Initial value for the dependence parameter.
    """

    name = "dixon_coles"

    def __init__(
        self,
        max_goals: int = 10,
        min_matches: int = 20,
        rho_init: float = -0.05,
    ) -> None:
        super().__init__()
        if max_goals < 1:
            raise ValueError("max_goals must be >= 1")
        self.max_goals = max_goals
        self.min_matches = min_matches
        self.rho_init = rho_init
        self._teams: list[str] = []
        self._team_index: dict[str, int] = {}
        self._attack: dict[str, float] = {}
        self._defense: dict[str, float] = {}
        self._home_adv: float = 0.0
        self._rho: float = rho_init

    @property
    def rho(self) -> float:
        return self._rho

    @property
    def home_advantage(self) -> float:
        return self._home_adv

    def attack(self, team_id: str) -> float:
        return self._attack.get(team_id, 0.0)

    def defense(self, team_id: str) -> float:
        return self._defense.get(team_id, 0.0)

    # --- Fit ---

    def fit(self, matches: Sequence[Match]) -> None:
        ordered = self._validate_training_matches(matches)
        if len(ordered) < self.min_matches:
            raise ValueError(
                f"need at least {self.min_matches} matches to fit, got {len(ordered)}"
            )

        teams = sorted({t for m in ordered for t in (m.home_team.team_id, m.away_team.team_id)})
        self._teams = teams
        self._team_index = {t: i for i, t in enumerate(teams)}
        n = len(teams)

        home_idx = np.array([self._team_index[m.home_team.team_id] for m in ordered])
        away_idx = np.array([self._team_index[m.away_team.team_id] for m in ordered])
        home_goals = np.array([m.result.home_goals for m in ordered], dtype=float)  # type: ignore[union-attr]
        away_goals = np.array([m.result.away_goals for m in ordered], dtype=float)  # type: ignore[union-attr]

        # Parameter vector: [attack(n), defense(n), home_adv, rho].
        # Identifiability: mean(attack) constrained to 0 (SLSQP equality).
        x0 = np.concatenate(
            [np.zeros(n), np.zeros(n), np.array([0.25]), np.array([self.rho_init])]
        )

        hx = (home_goals == 0) & (away_goals == 0)
        h01 = (home_goals == 0) & (away_goals == 1)
        h10 = (home_goals == 1) & (away_goals == 0)
        h11 = (home_goals == 1) & (away_goals == 1)

        def neg_log_likelihood(params: np.ndarray) -> float:
            attack = params[:n]
            defense = params[n : 2 * n]
            home_adv = params[2 * n]
            rho = params[2 * n + 1]

            lam_home = np.exp(attack[home_idx] + defense[away_idx] + home_adv)
            lam_away = np.exp(attack[away_idx] + defense[home_idx])

            # Base independent-Poisson log-likelihood.
            ll = (
                -lam_home
                + home_goals * np.log(lam_home)
                - lam_away
                + away_goals * np.log(lam_away)
            )
            # Dixon-Coles tau only affects the four low-score cells.
            tau = np.ones_like(lam_home)
            tau = np.where(hx, 1.0 - lam_home * lam_away * rho, tau)
            tau = np.where(h01, 1.0 + lam_home * rho, tau)
            tau = np.where(h10, 1.0 + lam_away * rho, tau)
            tau = np.where(h11, 1.0 - rho, tau)
            # Keep tau strictly positive so the log is defined.
            tau = np.clip(tau, 1e-10, None)
            ll = ll + np.log(tau)
            return float(-np.sum(ll))

        constraints = [{"type": "eq", "fun": lambda p: float(np.sum(p[:n]))}]
        bounds = (
            [(-3.0, 3.0)] * n  # attack
            + [(-3.0, 3.0)] * n  # defense
            + [(-1.0, 1.5)]  # home advantage
            + [(-0.9, 0.9)]  # rho
        )

        result = minimize(
            neg_log_likelihood,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 500, "ftol": 1e-8},
        )

        if getattr(result, "success", False):
            self._apply_params(result.x, n)
        else:
            message = getattr(result, "message", "unknown reason")
            logger.warning(
                "DixonColes SLSQP did not converge (%s); using moment-based fallback.",
                message,
            )
            self._apply_moment_fallback(ordered)
        self._is_fitted = True

    def _apply_params(self, params: np.ndarray, n: int) -> None:
        self._attack = {t: float(params[i]) for t, i in self._team_index.items()}
        self._defense = {t: float(params[n + i]) for t, i in self._team_index.items()}
        self._home_adv = float(params[2 * n])
        self._rho = float(params[2 * n + 1])

    def _apply_moment_fallback(self, ordered: Sequence[Match]) -> None:
        """Stable closed-form fallback when the MLE fails to converge.

        Uses log goal rates relative to the league average as attack/defense,
        mean-centered attack for identifiability, zero low-score dependence.
        """

        scored: dict[str, list[int]] = {t: [] for t in self._teams}
        conceded: dict[str, list[int]] = {t: [] for t in self._teams}
        home_goals_total = 0
        away_goals_total = 0
        for m in ordered:
            assert m.result is not None
            h, a = m.home_team.team_id, m.away_team.team_id
            scored[h].append(m.result.home_goals)
            conceded[h].append(m.result.away_goals)
            scored[a].append(m.result.away_goals)
            conceded[a].append(m.result.home_goals)
            home_goals_total += m.result.home_goals
            away_goals_total += m.result.away_goals

        all_goals = [g for goals in scored.values() for g in goals]
        league_mean = max(sum(all_goals) / len(all_goals), 0.1) if all_goals else 1.0

        def _log_rate(values: list[int]) -> float:
            avg = sum(values) / len(values) if values else league_mean
            return math.log(max(avg, 0.1) / league_mean)

        raw_attack = {t: _log_rate(scored[t]) for t in self._teams}
        mean_attack = sum(raw_attack.values()) / len(raw_attack) if raw_attack else 0.0
        self._attack = {t: raw_attack[t] - mean_attack for t in self._teams}
        self._defense = {t: _log_rate(conceded[t]) for t in self._teams}
        mean_defense = sum(self._defense.values()) / len(self._defense) if self._defense else 0.0
        self._defense = {t: self._defense[t] - mean_defense for t in self._teams}
        n_matches = max(len(ordered), 1)
        self._home_adv = math.log(
            max(home_goals_total / n_matches, 0.1) / max(away_goals_total / n_matches, 0.1)
        )
        self._rho = 0.0

    # --- Predict ---

    def _lambdas(self, home_id: str, away_id: str) -> tuple[float, float]:
        lam_home = math.exp(self.attack(home_id) + self.defense(away_id) + self._home_adv)
        lam_away = math.exp(self.attack(away_id) + self.defense(home_id))
        return lam_home, lam_away

    def score_matrix(self, home_id: str, away_id: str) -> np.ndarray:
        """Normalized ``(max_goals+1) x (max_goals+1)`` scoreline probability grid."""

        lam_home, lam_away = self._lambdas(home_id, away_id)
        size = self.max_goals + 1
        goals = np.arange(size)
        p_home = _poisson_pmf(goals, lam_home)
        p_away = _poisson_pmf(goals, lam_away)
        grid = np.outer(p_home, p_away)  # rows = home goals, cols = away goals

        x = np.repeat(goals, size).reshape(size, size)
        y = np.tile(goals, size).reshape(size, size)
        grid = grid * _dixon_coles_tau(x, y, lam_home, lam_away, self._rho)

        grid = np.clip(grid, 0.0, None)
        grid /= grid.sum()
        return grid

    def predict(self, match: Match) -> ModelPrediction:
        self._check_fitted()
        grid = self.score_matrix(match.home_team.team_id, match.away_team.team_id)

        p_home = float(np.tril(grid, -1).sum())  # home goals > away goals
        p_draw = float(np.trace(grid))
        p_away = float(np.triu(grid, 1).sum())
        total = p_home + p_draw + p_away
        p_home, p_draw, p_away = p_home / total, p_draw / total, p_away / total

        return Prediction(
            match_id=match.match_id,
            model_name=self.name,
            prediction_timestamp=match.prediction_timestamp,
            prob_home=p_home,
            prob_draw=p_draw,
            prob_away=p_away,
            confidence=70.0,
            score_matrix=ScoreMatrix(matrix=grid.tolist()),
        )
