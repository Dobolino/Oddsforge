"""Backward-compatible alias for the Dixon-Coles model.

The implementation now lives in :mod:`quantbot.models.dixon_coles`. This module
re-exports it so existing imports (``quantbot.models.poisson``) keep working.
"""

from __future__ import annotations

from quantbot.models.dixon_coles import (
    DixonColesModel,
    _dixon_coles_tau,
    _poisson_pmf,
    time_decay_weights,
)

__all__ = ["DixonColesModel", "_dixon_coles_tau", "_poisson_pmf", "time_decay_weights"]
