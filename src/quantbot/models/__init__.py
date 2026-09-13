"""Prediction models (Layer 1)."""

from __future__ import annotations

from quantbot.models.base import BaseModel, ModelPrediction, NotFittedError
from quantbot.models.calibrated import CalibratedModel
from quantbot.models.elo import EloModel
from quantbot.models.ensemble import EnsembleModel, multiclass_brier
from quantbot.models.dixon_coles import DixonColesModel, time_decay_weights
from quantbot.models.ml import GradientBoostingModel, LogisticRegressionModel

__all__ = [
    "BaseModel",
    "ModelPrediction",
    "NotFittedError",
    "EloModel",
    "DixonColesModel",
    "LogisticRegressionModel",
    "GradientBoostingModel",
    "EnsembleModel",
    "CalibratedModel",
    "time_decay_weights",
    "multiclass_brier",
]
