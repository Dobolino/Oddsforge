"""QuantBot domain schemas (Pydantic v2)."""

from __future__ import annotations

from quantbot.schemas.base import PROB_SUM_TOLERANCE, QuantBotModel
from quantbot.schemas.enums import (
    OUTCOME_ORDER,
    InjuryStatus,
    League,
    MarginMethod,
    MatchOutcome,
    MatchStatus,
    SignalType,
)
from quantbot.schemas.market import MarketData
from quantbot.schemas.match import Match, MatchResult, Team
from quantbot.schemas.odds import Odds
from quantbot.schemas.prediction import Prediction, ScoreMatrix
from quantbot.schemas.signal import ValueMetrics, ValueSignal

__all__ = [
    "PROB_SUM_TOLERANCE",
    "QuantBotModel",
    "OUTCOME_ORDER",
    "InjuryStatus",
    "League",
    "MarginMethod",
    "MatchOutcome",
    "MatchStatus",
    "SignalType",
    "MarketData",
    "Match",
    "MatchResult",
    "Team",
    "Odds",
    "Prediction",
    "ScoreMatrix",
    "ValueMetrics",
    "ValueSignal",
]
