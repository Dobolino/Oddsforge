"""Market schema: fair probabilities after margin removal.

Produced by the Market Engine (Layer 2). Holds the de-vigged fair
probabilities, the removed margin, and a liquidity proxy used later by the
Decision Engine.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from quantbot.schemas.base import PROB_SUM_TOLERANCE, QuantBotModel
from quantbot.schemas.enums import MarginMethod, MatchOutcome


class MarketData(QuantBotModel):
    """Fair market probabilities derived from bookmaker odds.

    Attributes:
        fair_home/draw/away: Margin-free probabilities, summing to 1.0.
        overround: The margin removed to obtain the fair probabilities.
        method: The margin-removal method applied.
        liquidity: Optional liquidity/volume proxy (>= 0). Higher is better.
    """

    match_id: str = Field(min_length=1)
    bookmaker: str = Field(min_length=1)
    timestamp: datetime
    method: MarginMethod
    fair_home: float = Field(gt=0.0, lt=1.0)
    fair_draw: float = Field(gt=0.0, lt=1.0)
    fair_away: float = Field(gt=0.0, lt=1.0)
    overround: float = Field(ge=0.0)
    liquidity: float | None = Field(default=None, ge=0.0)
    is_closing: bool = False

    @model_validator(mode="after")
    def _validate(self) -> MarketData:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        total = self.fair_home + self.fair_draw + self.fair_away
        if abs(total - 1.0) > PROB_SUM_TOLERANCE:
            raise ValueError(f"fair probabilities must sum to 1.0, got {total}")
        return self

    def fair_probabilities(self) -> dict[MatchOutcome, float]:
        return {
            MatchOutcome.HOME: self.fair_home,
            MatchOutcome.DRAW: self.fair_draw,
            MatchOutcome.AWAY: self.fair_away,
        }

    def fair_odds(self) -> dict[MatchOutcome, float]:
        """Fair decimal odds implied by the margin-free probabilities."""

        return {
            MatchOutcome.HOME: 1.0 / self.fair_home,
            MatchOutcome.DRAW: 1.0 / self.fair_draw,
            MatchOutcome.AWAY: 1.0 / self.fair_away,
        }
