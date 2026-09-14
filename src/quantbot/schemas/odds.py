"""Bookmaker odds schemas (raw market input, margin still included)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from quantbot.schemas.base import QuantBotModel
from quantbot.schemas.enums import MatchOutcome, TotalsSide


class Odds(QuantBotModel):
    """A single 1X2 decimal-odds quote from one bookmaker at one instant.

    Decimal odds are strictly greater than 1.0. The implied probabilities
    (``1 / odds``) sum to more than 1.0 by the bookmaker margin (overround).
    """

    match_id: str = Field(min_length=1)
    bookmaker: str = Field(min_length=1)
    timestamp: datetime
    home: float = Field(gt=1.0)
    draw: float = Field(gt=1.0)
    away: float = Field(gt=1.0)
    is_closing: bool = Field(
        default=False, description="True if this is the closing line before kickoff."
    )

    @model_validator(mode="after")
    def _validate_timestamp(self) -> Odds:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return self

    @property
    def overround(self) -> float:
        """Bookmaker margin: sum of implied probabilities minus 1."""

        return (1.0 / self.home) + (1.0 / self.draw) + (1.0 / self.away) - 1.0

    def implied_probabilities(self) -> dict[MatchOutcome, float]:
        """Raw implied probabilities (not normalized; still contain margin)."""

        return {
            MatchOutcome.HOME: 1.0 / self.home,
            MatchOutcome.DRAW: 1.0 / self.draw,
            MatchOutcome.AWAY: 1.0 / self.away,
        }

    def decimal_odds(self) -> dict[MatchOutcome, float]:
        return {
            MatchOutcome.HOME: self.home,
            MatchOutcome.DRAW: self.draw,
            MatchOutcome.AWAY: self.away,
        }


class TotalsOdds(QuantBotModel):
    """Over/Under totals quote for one line from one bookmaker.

    Kept separate from :class:`Odds` so the 1X2 market stays cleanly isolated
    from the goals market.
    """

    match_id: str = Field(min_length=1)
    bookmaker: str = Field(min_length=1)
    timestamp: datetime
    line: float = Field(gt=0.0, description="Totals line, e.g. 2.5")
    over: float = Field(gt=1.0)
    under: float = Field(gt=1.0)
    is_closing: bool = False

    @model_validator(mode="after")
    def _validate(self) -> TotalsOdds:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return self

    @property
    def overround(self) -> float:
        return (1.0 / self.over) + (1.0 / self.under) - 1.0

    def implied_probabilities(self) -> dict[TotalsSide, float]:
        return {
            TotalsSide.OVER: 1.0 / self.over,
            TotalsSide.UNDER: 1.0 / self.under,
        }

    def decimal_odds(self) -> dict[TotalsSide, float]:
        return {
            TotalsSide.OVER: self.over,
            TotalsSide.UNDER: self.under,
        }
