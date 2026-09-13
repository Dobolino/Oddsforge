"""Base model and shared constants for all QuantBot schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# Probabilities must sum to 1 within this absolute tolerance.
PROB_SUM_TOLERANCE: float = 1e-6


class QuantBotModel(BaseModel):
    """Base for all domain models.

    Immutable and strict by default so that data flowing through the pipeline
    cannot be mutated in place, which keeps backtests reproducible.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=False,
        validate_assignment=True,
    )
