"""Dixon-Coles adaptive score grid and rest-mass tests."""

from __future__ import annotations

import numpy as np
import pytest

from quantbot.models.dixon_coles import (
    DEFAULT_REST_MASS_TOL,
    DixonColesModel,
    ScoreGridStatus,
    choose_max_goals,
    independent_rest_mass,
)


def _fitted_params(model: DixonColesModel, *, rho: float = 0.0) -> None:
    model._attack = {"A": 0.0, "B": 0.0}
    model._defense = {"A": 0.0, "B": 0.0}
    model._home_adv = 0.0
    model._rho = rho
    model._is_fitted = True


def test_independent_rest_mass_fixed_grid_hides_tail() -> None:
    # λ=12 with max_goals=10 truncates a large independent mass.
    rest = independent_rest_mass(12.0, 12.0, 10)
    assert rest > 0.05


def test_choose_max_goals_meets_tolerance_near_lambda_max() -> None:
    g, rest, status = choose_max_goals(
        12.0,
        12.0,
        min_goals=10,
        max_goals_cap=50,
        rest_mass_tol=DEFAULT_REST_MASS_TOL,
    )
    assert status is ScoreGridStatus.OK
    assert g > 10
    assert rest <= DEFAULT_REST_MASS_TOL


def test_choose_max_goals_reports_grid_limit() -> None:
    g, rest, status = choose_max_goals(
        12.0,
        12.0,
        min_goals=10,
        max_goals_cap=12,
        rest_mass_tol=DEFAULT_REST_MASS_TOL,
    )
    assert status is ScoreGridStatus.GRID_LIMIT
    assert g == 12
    assert rest > DEFAULT_REST_MASS_TOL


def test_adaptive_grid_grows_for_high_lambda() -> None:
    model = DixonColesModel(max_goals=10, adaptive_grid=True, max_goals_cap=50)
    _fitted_params(model)
    model._lambdas = lambda _h, _a: (12.0, 12.0)  # type: ignore[method-assign]
    built = model.build_score_grid("A", "B")
    assert built.status is ScoreGridStatus.OK
    assert built.max_goals > 10
    assert built.independent_rest_mass <= model.rest_mass_tol
    assert built.mass_conserved
    assert built.cells_valid
    assert built.grid.shape == (built.max_goals + 1, built.max_goals + 1)


def test_grid_limit_status_and_optional_raise() -> None:
    model = DixonColesModel(
        max_goals=10,
        adaptive_grid=True,
        max_goals_cap=12,
        rest_mass_tol=1e-8,
        raise_on_grid_limit=False,
    )
    _fitted_params(model)
    model._lambdas = lambda _h, _a: (12.0, 12.0)  # type: ignore[method-assign]
    built = model.build_score_grid("A", "B")
    assert built.status is ScoreGridStatus.GRID_LIMIT
    assert built.independent_rest_mass > 1e-8
    # Still a usable normalized grid — truncation is audited, not hidden.
    assert built.mass_conserved
    assert built.cells_valid

    strict = DixonColesModel(
        max_goals=10,
        adaptive_grid=True,
        max_goals_cap=12,
        raise_on_grid_limit=True,
    )
    _fitted_params(strict)
    strict._lambdas = lambda _h, _a: (12.0, 12.0)  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="rest mass"):
        strict.build_score_grid("A", "B")


def test_non_adaptive_reports_rest_mass_without_growing() -> None:
    model = DixonColesModel(max_goals=10, adaptive_grid=False)
    _fitted_params(model)
    model._lambdas = lambda _h, _a: (12.0, 12.0)  # type: ignore[method-assign]
    built = model.build_score_grid("A", "B")
    assert built.max_goals == 10
    assert built.status is ScoreGridStatus.GRID_LIMIT
    assert built.independent_rest_mass == pytest.approx(independent_rest_mass(12.0, 12.0, 10))


def test_invalid_tau_falls_back_to_independent() -> None:
    model = DixonColesModel(max_goals=4, adaptive_grid=False)
    _fitted_params(model, rho=0.9)
    model._lambdas = lambda _h, _a: (4.0, 4.0)  # type: ignore[method-assign]
    invalid = model.build_score_grid("A", "B")
    assert invalid.status is ScoreGridStatus.TAU_INVALID
    assert invalid.tau_applied is False

    model._rho = 0.0
    independent = model.build_score_grid("A", "B")
    assert independent.tau_applied is False
    assert np.allclose(invalid.grid, independent.grid)


def test_valid_negative_rho_applies_tau() -> None:
    model = DixonColesModel(max_goals=8, adaptive_grid=True)
    _fitted_params(model, rho=-0.1)
    built = model.build_score_grid("A", "B")
    assert built.status is ScoreGridStatus.OK
    assert built.tau_applied is True
    assert built.cells_valid
    assert built.mass_conserved
    # Negative rho boosts 0-0 relative to the independent product share.
    model._rho = 0.0
    naive = model.build_score_grid("A", "B")
    assert built.grid[0, 0] > naive.grid[0, 0]
