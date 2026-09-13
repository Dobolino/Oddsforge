"""Prediction models (Layer 1)."""

from __future__ import annotations

from quantbot.models.base import BaseModel, ModelPrediction, NotFittedError
from quantbot.models.elo import EloModel
from quantbot.models.poisson import DixonColesModel

__all__ = [
    "BaseModel",
    "ModelPrediction",
    "NotFittedError",
    "EloModel",
    "DixonColesModel",
]
