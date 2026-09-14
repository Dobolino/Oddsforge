"""QuantBot domain schemas (Pydantic v2)."""

from __future__ import annotations

from quantbot.schemas.base import PROB_SUM_TOLERANCE, QuantBotModel
from quantbot.schemas.enums import (
    DEFAULT_TOTALS_LINE,
    OUTCOME_ORDER,
    TOTALS_ORDER,
    InjuryStatus,
    League,
    MarginMethod,
    MatchOutcome,
    MatchStatus,
    SignalType,
    TotalsSide,
)
from quantbot.schemas.market import MarketData, TotalsMarketData
from quantbot.schemas.match import Match, MatchResult, Team
from quantbot.schemas.odds import Odds, TotalsOdds
from quantbot.schemas.prediction import Prediction, ScoreMatrix
from quantbot.schemas.signal import ValueMetrics, ValueSignal

__all__ = [
    "PROB_SUM_TOLERANCE",
    "QuantBotModel",
    "DEFAULT_TOTALS_LINE",
    "OUTCOME_ORDER",
    "TOTALS_ORDER",
    "InjuryStatus",
    "League",
    "MarginMethod",
    "MatchOutcome",
    "MatchStatus",
    "SignalType",
    "TotalsSide",
    "MarketData",
    "TotalsMarketData",
    "Match",
    "MatchResult",
    "Team",
    "Odds",
    "TotalsOdds",
    "Prediction",
    "ScoreMatrix",
    "ValueMetrics",
    "ValueSignal",
]
