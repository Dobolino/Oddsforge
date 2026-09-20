"""Prediction models (Layer 1)."""

from __future__ import annotations

from quantbot.models.base import BaseModel, ModelPrediction, NotFittedError
from quantbot.models.calibrated import CalibratedModel
from quantbot.models.basketball import BasketballModel
from quantbot.models.elo import EloModel
from quantbot.models.ensemble import EnsembleModel, multiclass_brier
from quantbot.models.dixon_coles import (
    DixonColesModel,
    ScoreGridResult,
    ScoreGridStatus,
    choose_max_goals,
    independent_rest_mass,
    time_decay_weights,
)
from quantbot.models.ml import GradientBoostingModel, LogisticRegressionModel

__all__ = [
    "BaseModel",
    "ModelPrediction",
    "NotFittedError",
    "BasketballModel",
    "EloModel",
    "DixonColesModel",
    "ScoreGridResult",
    "ScoreGridStatus",
    "choose_max_goals",
    "independent_rest_mass",
    "LogisticRegressionModel",
    "GradientBoostingModel",
    "EnsembleModel",
    "CalibratedModel",
    "time_decay_weights",
    "multiclass_brier",
]
