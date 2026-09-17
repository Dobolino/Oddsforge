"""QuantBot domain schemas (Pydantic v2)."""

from __future__ import annotations

from quantbot.schemas.base import PROB_SUM_TOLERANCE, QuantBotModel
from quantbot.schemas.enums import (
    DEFAULT_NBA_TOTALS_LINE,
    DEFAULT_TOTALS_LINE,
    OUTCOME_ORDER,
    TOTALS_ORDER,
    InjuryStatus,
    League,
    MarginMethod,
    MarketKind,
    MatchOutcome,
    MatchStatus,
    SettlementStatus,
    SignalType,
    Sport,
    TotalsSide,
    leagues_for_sport,
    sport_for_league,
)
from quantbot.schemas.market import Market, MarketData, MarketOutcome, TotalsMarketData
from quantbot.schemas.match import Match, MatchResult, Team
from quantbot.schemas.odds import MoneylineOdds, Odds, SpreadOdds, TotalsOdds
from quantbot.schemas.prediction import Prediction, ScoreMatrix
from quantbot.schemas.signal import ValueMetrics, ValueSignal
from quantbot.schemas.snapshot import PredictionSnapshot, snapshot_from_signal

__all__ = [
    "PROB_SUM_TOLERANCE",
    "QuantBotModel",
    "DEFAULT_NBA_TOTALS_LINE",
    "DEFAULT_TOTALS_LINE",
    "OUTCOME_ORDER",
    "TOTALS_ORDER",
    "InjuryStatus",
    "League",
    "MarginMethod",
    "MarketKind",
    "SettlementStatus",
    "Sport",
    "MatchOutcome",
    "MatchStatus",
    "SignalType",
    "TotalsSide",
    "leagues_for_sport",
    "sport_for_league",
    "MarketData",
    "Market",
    "MarketOutcome",
    "TotalsMarketData",
    "Match",
    "MatchResult",
    "Team",
    "MoneylineOdds",
    "Odds",
    "SpreadOdds",
    "TotalsOdds",
    "Prediction",
    "ScoreMatrix",
    "ValueMetrics",
    "ValueSignal",
    "PredictionSnapshot",
    "snapshot_from_signal",
]
