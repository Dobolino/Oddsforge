"""Shared enumerations for QuantBot schemas."""

from __future__ import annotations

from enum import Enum


class MatchOutcome(str, Enum):
    """1X2 outcome of a football match from the home team's perspective."""

    HOME = "home"
    DRAW = "draw"
    AWAY = "away"


class TotalsSide(str, Enum):
    """Over/Under side of a totals (goals) market."""

    OVER = "over"
    UNDER = "under"


class League(str, Enum):
    """Supported competitions. Extend as new ones are added."""

    PREMIER_LEAGUE = "premier_league"
    BUNDESLIGA = "bundesliga"
    LA_LIGA = "la_liga"
    SERIE_A = "serie_a"
    LIGUE_1 = "ligue_1"
    CHAMPIONS_LEAGUE = "champions_league"


class MatchStatus(str, Enum):
    """Lifecycle state of a match."""

    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class InjuryStatus(str, Enum):
    """Injury data availability.

    Guardrail: missing injury data is ``UNKNOWN``, never silently treated as
    "no injuries". This prevents an optimistic bias when data is absent.
    """

    UNKNOWN = "unknown"
    AVAILABLE = "available"
    DOUBTFUL = "doubtful"
    OUT = "out"


class SignalType(str, Enum):
    """Decision engine output."""

    VALUE_HOME = "value_home"
    VALUE_DRAW = "value_draw"
    VALUE_AWAY = "value_away"
    VALUE_OVER = "value_over"
    VALUE_UNDER = "value_under"
    NO_BET = "no_bet"


class MarginMethod(str, Enum):
    """Method used to strip the bookmaker overround."""

    SHIN = "shin"
    POWER = "power"
    MULTIPLICATIVE = "multiplicative"


# Ordered outcome tuple used wherever probabilities are stored positionally.
OUTCOME_ORDER: tuple[MatchOutcome, ...] = (
    MatchOutcome.HOME,
    MatchOutcome.DRAW,
    MatchOutcome.AWAY,
)

TOTALS_ORDER: tuple[TotalsSide, ...] = (
    TotalsSide.OVER,
    TotalsSide.UNDER,
)

# Default totals line (goals); configurable where scores are derived.
DEFAULT_TOTALS_LINE = 2.5
