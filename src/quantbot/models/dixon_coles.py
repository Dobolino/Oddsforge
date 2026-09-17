"""Dixon-Coles bivariate Poisson model with time decay and optional xG.

Estimates per-team attack/defense strengths, a home-advantage term, and the
Dixon-Coles low-score dependence ``rho`` via weighted maximum likelihood
(``scipy.optimize.minimize``). Two extensions over the textbook model:

* Time decay: each match contributes with weight ``w_i = exp(-xi * age_i)``
  where ``age_i`` is the age in days relative to the most recent training
  match. Larger ``xi`` down-weights old matches. ``xi = 0`` is the classic
  equal-weight fit.
* xG mode: when ``use_xg`` is set, the goal expectations are fitted to
  ``home_xg``/``away_xg`` (falling back to actual goals when xG is missing)
  via a quasi-Poisson likelihood, with the discrete low-score correction
  disabled (``rho = 0``) since it is meaningless on continuous xG.
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

# Sane bounds for expected goals per team. Keeps the Poisson grid finite even
# when a sparse-data fit returns extreme or non-finite team parameters.
_LAM_MIN = 0.02
_LAM_MAX = 12.0


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


def time_decay_weights(kickoffs: Sequence[object], xi: float) -> np.ndarray:
    """Weights ``exp(-xi * age_days)`` relative to the most recent kickoff.

    ``xi = 0`` yields all-ones (no decay). Newer matches always weigh at least
    as much as older ones.
    """

    if not kickoffs:
        return np.array([], dtype=float)
    times = np.array([k.timestamp() for k in kickoffs], dtype=float)  # type: ignore[attr-defined]
    t_now = times.max()
    age_days = (t_now - times) / 86400.0
    return np.exp(-xi * age_days)


class DixonColesModel(BaseModel):
    """Dixon-Coles Poisson goal model.

    Args:
        max_goals: Grid size for the scoreline matrix (0..max_goals per side).
        min_matches: Minimum finished matches required to fit.
        rho_init: Initial value for the dependence parameter.
        time_decay_xi: Daily decay rate for match weights (0 = equal weight).
        use_xg: Fit goal expectations to xG instead of actual goals.
    """

    name = "dixon_coles"

    def __init__(
        self,
        max_goals: int = 10,
        min_matches: int = 20,
        rho_init: float = -0.05,
        time_decay_xi: float = 0.0,
        use_xg: bool = False,
    ) -> None:
        super().__init__()
        if max_goals < 1:
            raise ValueError("max_goals must be >= 1")
        if time_decay_xi < 0.0:
            raise ValueError("time_decay_xi must be non-negative")
        self.max_goals = max_goals
        self.min_matches = min_matches
        self.rho_init = rho_init
        self.time_decay_xi = time_decay_xi
        self.use_xg = use_xg
        self._teams: list[str] = []
        self._team_index: dict[str, int] = {}
        self._attack: dict[str, float] = {}
        self._defense: dict[str, float] = {}
        self._home_adv: float = 0.0
        self._rho: float = 0.0 if use_xg else rho_init

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

    # --- Response extraction (goals or xG) ---

    def _response(self, match: Match) -> tuple[float, float]:
        assert match.result is not None
        r = match.result
        if self.use_xg:
            home = float(r.home_xg) if r.home_xg is not None else float(r.home_goals)
            away = float(r.away_xg) if r.away_xg is not None else float(r.away_goals)
            return home, away
        return float(r.home_goals), float(r.away_goals)

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
        responses = [self._response(m) for m in ordered]
        home_resp = np.array([r[0] for r in responses], dtype=float)
        away_resp = np.array([r[1] for r in responses], dtype=float)
        weights = time_decay_weights([m.kickoff for m in ordered], self.time_decay_xi)

        estimate_rho = not self.use_xg
        x0 = np.concatenate(
            [np.zeros(n), np.zeros(n), np.array([0.25]), np.array([self.rho_init if estimate_rho else 0.0])]
        )

        # Low-score cell masks for the tau correction (goals mode only).
        hx = (home_resp == 0) & (away_resp == 0)
        h01 = (home_resp == 0) & (away_resp == 1)
        h10 = (home_resp == 1) & (away_resp == 0)
        h11 = (home_resp == 1) & (away_resp == 1)

        def neg_log_likelihood(params: np.ndarray) -> float:
            attack = params[:n]
            defense = params[n : 2 * n]
            home_adv = params[2 * n]
            rho = params[2 * n + 1]

            lam_home = np.exp(attack[home_idx] + defense[away_idx] + home_adv)
            lam_away = np.exp(attack[away_idx] + defense[home_idx])

            # Quasi-Poisson log-likelihood (valid for continuous xG too).
            ll = (
                -lam_home
                + home_resp * np.log(lam_home)
                - lam_away
                + away_resp * np.log(lam_away)
            )
            if estimate_rho:
                tau = np.ones_like(lam_home)
                tau = np.where(hx, 1.0 - lam_home * lam_away * rho, tau)
                tau = np.where(h01, 1.0 + lam_home * rho, tau)
                tau = np.where(h10, 1.0 + lam_away * rho, tau)
                tau = np.where(h11, 1.0 - rho, tau)
                if np.any(tau <= 0.0) or not np.all(np.isfinite(tau)):
                    return 1e12
                ll = ll + np.log(tau)
            # Time-decay weighting.
            return float(-np.sum(weights * ll))

        constraints = [{"type": "eq", "fun": lambda p: float(np.sum(p[:n]))}]
        rho_bounds = (-0.9, 0.9) if estimate_rho else (0.0, 0.0)
        bounds = (
            [(-3.0, 3.0)] * n  # attack
            + [(-3.0, 3.0)] * n  # defense
            + [(-1.0, 1.5)]  # home advantage
            + [rho_bounds]  # rho (fixed to 0 in xG mode)
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
            self._apply_moment_fallback(home_idx, away_idx, home_resp, away_resp, n)
        self._is_fitted = True

    def _apply_params(self, params: np.ndarray, n: int) -> None:
        self._attack = {t: float(params[i]) for t, i in self._team_index.items()}
        self._defense = {t: float(params[n + i]) for t, i in self._team_index.items()}
        self._home_adv = float(params[2 * n])
        self._rho = float(params[2 * n + 1])

    def _apply_moment_fallback(
        self,
        home_idx: np.ndarray,
        away_idx: np.ndarray,
        home_resp: np.ndarray,
        away_resp: np.ndarray,
        n: int,
    ) -> None:
        """Stable closed-form fallback: log rates relative to the league mean."""

        scored = np.bincount(home_idx, weights=home_resp, minlength=n) + np.bincount(
            away_idx, weights=away_resp, minlength=n
        )
        conceded = np.bincount(home_idx, weights=away_resp, minlength=n) + np.bincount(
            away_idx, weights=home_resp, minlength=n
        )
        counts = np.bincount(home_idx, minlength=n) + np.bincount(away_idx, minlength=n)
        counts = np.clip(counts, 1, None)
        avg_scored = scored / counts
        avg_conceded = conceded / counts
        league_mean = max(float((home_resp.sum() + away_resp.sum()) / (2 * len(home_resp))), 0.1)

        raw_attack = np.log(np.clip(avg_scored, 0.1, None) / league_mean)
        raw_attack = raw_attack - raw_attack.mean()
        raw_defense = np.log(np.clip(avg_conceded, 0.1, None) / league_mean)
        raw_defense = raw_defense - raw_defense.mean()

        self._attack = {t: float(raw_attack[i]) for t, i in self._team_index.items()}
        self._defense = {t: float(raw_defense[i]) for t, i in self._team_index.items()}
        self._home_adv = math.log(
            max(float(home_resp.mean()), 0.1) / max(float(away_resp.mean()), 0.1)
        )
        self._rho = 0.0

    # --- Predict ---

    def _lambdas(self, home_id: str, away_id: str) -> tuple[float, float]:
        # Clamp the expected goals to a sane, finite range. A degenerate fit
        # (sparse early-season data) can return non-finite or extreme
        # attack/defense values; without this the Poisson grid overflows to
        # NaN and the whole prediction — and calibration — breaks.
        def _f(x: float) -> float:
            return x if math.isfinite(x) else 0.0

        lo, hi = math.log(_LAM_MIN), math.log(_LAM_MAX)
        e_home = _f(self.attack(home_id)) + _f(self.defense(away_id)) + _f(self._home_adv)
        e_away = _f(self.attack(away_id)) + _f(self.defense(home_id))
        lam_home = math.exp(min(max(e_home, lo), hi))
        lam_away = math.exp(min(max(e_away, lo), hi))
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
        tau = _dixon_coles_tau(x, y, lam_home, lam_away, self._rho)
        if np.all(np.isfinite(tau)) and np.all(tau >= 0.0):
            grid = grid * tau
        else:
            logger.warning("Invalid Dixon-Coles correction; using independent Poisson grid")

        total = grid.sum()
        if not np.isfinite(total) or total <= 0.0:
            # Degenerate grid: fall back to the independent Poisson product,
            # and to a uniform grid only if that is still unusable.
            grid = np.outer(p_home, p_away)
            total = grid.sum()
            if not np.isfinite(total) or total <= 0.0:
                return np.full((size, size), 1.0 / (size * size))
        grid /= total
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
