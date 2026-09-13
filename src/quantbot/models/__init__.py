"""Prediction models (Layer 1)."""

from __future__ import annotations

from quantbot.models.base import BaseModel, ModelPrediction, NotFittedError
from quantbot.models.elo import EloModel
from quantbot.models.ensemble import EnsembleModel, multiclass_brier
from quantbot.models.ml import GradientBoostingModel, LogisticRegressionModel
from quantbot.models.poisson import DixonColesModel

__all__ = [
    "BaseModel",
    "ModelPrediction",
    "NotFittedError",
    "EloModel",
    "DixonColesModel",
    "LogisticRegressionModel",
    "GradientBoostingModel",
    "EnsembleModel",
    "multiclass_brier",
]
