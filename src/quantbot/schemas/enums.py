"""Shared enumerations for QuantBot schemas."""

from __future__ import annotations

from enum import Enum


class Sport(str, Enum):
    """Top-level sport family. Football remains the default everywhere."""

    FOOTBALL = "football"
    BASKETBALL = "basketball"


class MatchOutcome(str, Enum):
    """Match outcome from the home team's perspective.

    Football uses the full 1X2 set. Basketball moneyline uses HOME/AWAY only
    (DRAW probability is carried near zero when a 3-way schema is reused).
    """

    HOME = "home"
    DRAW = "draw"
    AWAY = "away"


class TotalsSide(str, Enum):
    """Over/Under side of a totals market (goals or points)."""

    OVER = "over"
    UNDER = "under"


class HandicapSide(str, Enum):
    """Side backed on an Asian-handicap (spread) market.

    Values are deliberately prefixed so a handicap side never equals a 1X2
    :class:`MatchOutcome` (both are string enums): equal string values would
    collide in signal maps and misparse when reloaded from history. ``team``
    gives the plain "home"/"away" side for display and settlement.
    """

    HOME = "handicap_home"
    AWAY = "handicap_away"

    @property
    def team(self) -> str:
        """The plain side ("home" or "away") without the handicap prefix."""

        return "home" if self is HandicapSide.HOME else "away"


class MarketKind(str, Enum):
    """Settlement and pricing rules for a bookmaker market."""

    ONE_X_TWO = "1x2"
    MONEYLINE = "moneyline"
    TOTALS = "totals"
    SPREAD = "spread"


class SettlementStatus(str, Enum):
    WON = "won"
    LOST = "lost"
    VOID = "void"


class League(str, Enum):
    """Supported competitions. Extend as new ones are added."""

    PREMIER_LEAGUE = "premier_league"
    BUNDESLIGA = "bundesliga"
    LA_LIGA = "la_liga"
    SERIE_A = "serie_a"
    LIGUE_1 = "ligue_1"
    CHAMPIONS_LEAGUE = "champions_league"
    NBA = "nba"


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
    VALUE_HANDICAP_HOME = "value_handicap_home"
    VALUE_HANDICAP_AWAY = "value_handicap_away"
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

MONEYLINE_ORDER: tuple[MatchOutcome, ...] = (
    MatchOutcome.HOME,
    MatchOutcome.AWAY,
)

TOTALS_ORDER: tuple[TotalsSide, ...] = (
    TotalsSide.OVER,
    TotalsSide.UNDER,
)

HANDICAP_ORDER: tuple[HandicapSide, ...] = (
    HandicapSide.HOME,
    HandicapSide.AWAY,
)

# Default totals lines by sport.
DEFAULT_TOTALS_LINE = 2.5
DEFAULT_NBA_TOTALS_LINE = 225.5
# Default Asian-handicap line (home slightly favored). Negative = home gives
# a start; positive = home receives one.
DEFAULT_HANDICAP_LINE = -0.5

# League → sport mapping (football leagues default when omitted).
LEAGUE_SPORT: dict[League, Sport] = {
    League.PREMIER_LEAGUE: Sport.FOOTBALL,
    League.BUNDESLIGA: Sport.FOOTBALL,
    League.LA_LIGA: Sport.FOOTBALL,
    League.SERIE_A: Sport.FOOTBALL,
    League.LIGUE_1: Sport.FOOTBALL,
    League.CHAMPIONS_LEAGUE: Sport.FOOTBALL,
    League.NBA: Sport.BASKETBALL,
}


def sport_for_league(league: League) -> Sport:
    return LEAGUE_SPORT.get(league, Sport.FOOTBALL)


def leagues_for_sport(sport: Sport | None) -> tuple[League, ...]:
    """Leagues in a sport; ``None`` means every league."""

    if sport is None:
        return tuple(League)
    return tuple(lg for lg in League if sport_for_league(lg) is sport)
