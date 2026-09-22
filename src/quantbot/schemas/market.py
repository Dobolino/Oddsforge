"""Market schema: fair probabilities after margin removal.

Produced by the Market Engine (Layer 2). Holds the de-vigged fair
probabilities, the removed margin, and a liquidity proxy used later by the
Decision Engine.
"""

from __future__ import annotations

from datetime import datetime
from math import isfinite

from pydantic import Field, model_validator

from quantbot.schemas.base import PROB_SUM_TOLERANCE, QuantBotModel
from quantbot.schemas.enums import (
    MarginMethod,
    MarketKind,
    MatchOutcome,
    SettlementStatus,
    TotalsSide,
)


class MarketOutcome(QuantBotModel):
    """One quoted selection, with its own handicap or totals line when needed.

    ``name`` is the canonical key (home/draw/away/over/under). ``label`` is an
    optional display alias. ``fair_prob`` is set after margin removal when the
    caller materialises a demargined book.
    """

    name: str = Field(min_length=1)
    label: str | None = None
    line: float | None = None
    price: float = Field(gt=1.0)
    fair_prob: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _finite(self) -> MarketOutcome:
        if not isfinite(self.price) or (self.line is not None and not isfinite(self.line)):
            raise ValueError("market price and line must be finite")
        if self.fair_prob is not None and not isfinite(self.fair_prob):
            raise ValueError("fair_prob must be finite")
        return self

    @property
    def display_label(self) -> str:
        return self.label if self.label else self.name


class Market(QuantBotModel):
    """Sport-neutral bookmaker quote with explicit settlement rules.

    Totals use the same positive line for both sides. Spread lines are from
    each selected team's perspective and must be opposites.
    """

    match_id: str = Field(min_length=1)
    bookmaker: str = Field(min_length=1)
    timestamp: datetime
    kind: MarketKind
    outcomes: tuple[MarketOutcome, ...]
    is_closing: bool = False

    @classmethod
    def from_quote(cls, quote: object) -> Market:
        """Adapt existing provider quotes to the common market representation."""

        from quantbot.schemas.odds import MoneylineOdds, Odds, SpreadOdds, TotalsOdds

        if isinstance(quote, Odds):
            if quote.kind is MarketKind.MONEYLINE:
                kind = MarketKind.MONEYLINE
                selections = (("home", None, quote.home), ("away", None, quote.away))
            else:
                kind = MarketKind.ONE_X_TWO
                selections = (
                    ("home", None, quote.home),
                    ("draw", None, quote.draw),
                    ("away", None, quote.away),
                )
        elif isinstance(quote, MoneylineOdds):
            kind = MarketKind.MONEYLINE
            selections = (("home", None, quote.home), ("away", None, quote.away))
        elif isinstance(quote, TotalsOdds):
            kind = MarketKind.TOTALS
            selections = (("over", quote.line, quote.over), ("under", quote.line, quote.under))
        elif isinstance(quote, SpreadOdds):
            kind = MarketKind.SPREAD
            selections = (("home", quote.line, quote.home), ("away", -quote.line, quote.away))
        else:
            raise TypeError(f"unsupported quote type: {type(quote).__name__}")
        return cls(
            match_id=quote.match_id,
            bookmaker=quote.bookmaker,
            timestamp=quote.timestamp,
            kind=kind,
            outcomes=tuple(
                MarketOutcome(name=name, line=line, price=price) for name, line, price in selections
            ),
            is_closing=quote.is_closing,
        )

    @model_validator(mode="after")
    def _validate_market(self) -> Market:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        expected = {
            MarketKind.ONE_X_TWO: {"home", "draw", "away"},
            MarketKind.MONEYLINE: {"home", "away"},
            MarketKind.TOTALS: {"over", "under"},
            MarketKind.SPREAD: {"home", "away"},
        }[self.kind]
        by_name = {outcome.name: outcome for outcome in self.outcomes}
        if len(by_name) != len(self.outcomes) or set(by_name) != expected:
            raise ValueError(f"{self.kind.value} requires exactly {sorted(expected)}")
        if self.kind in (MarketKind.ONE_X_TWO, MarketKind.MONEYLINE):
            if any(outcome.line is not None for outcome in self.outcomes):
                raise ValueError("result markets must not have a line")
        elif self.kind is MarketKind.TOTALS:
            over, under = by_name["over"], by_name["under"]
            if over.line is None or over.line <= 0 or over.line != under.line:
                raise ValueError("totals require one shared positive line")
        else:
            home, away = by_name["home"], by_name["away"]
            if home.line is None or away.line is None or home.line != -away.line:
                raise ValueError("spread handicap lines must be opposites")
        return self

    @property
    def margin_method(self) -> MarginMethod:
        from quantbot.markets.demargin import method_for_market

        return method_for_market(self.kind)

    def fair_probabilities(self) -> dict[str, float]:
        """Remove the margin with Shin for 1X2 and Power for every two-way market."""

        from quantbot.markets.demargin import demargin_prices

        fair = demargin_prices([item.price for item in self.outcomes], kind=self.kind)
        return dict(zip((item.name for item in self.outcomes), fair, strict=True))

    def with_fair_probs(self) -> Market:
        """Return a copy whose outcomes carry demargined ``fair_prob`` values."""

        fair = self.fair_probabilities()
        return self.model_copy(
            update={
                "outcomes": tuple(
                    outcome.model_copy(update={"fair_prob": fair[outcome.name]})
                    for outcome in self.outcomes
                )
            }
        )

    def settle(self, selection: str, home_score: int, away_score: int) -> SettlementStatus:
        """Resolve a selection with typed push / half outcomes for line markets.

        Integer-line exact hits refund the stake as :attr:`SettlementStatus.VOID`
        (same payoff factor 1.0 as PUSH) so multi-sport callers share one name.
        """

        if home_score < 0 or away_score < 0:
            raise ValueError("scores must be non-negative")
        outcome = next((item for item in self.outcomes if item.name == selection), None)
        if outcome is None:
            raise ValueError(f"unknown selection: {selection!r}")
        if self.kind is MarketKind.ONE_X_TWO:
            actual = (
                "home" if home_score > away_score else "away" if away_score > home_score else "draw"
            )
            return SettlementStatus.WON if selection == actual else SettlementStatus.LOST
        if self.kind is MarketKind.MONEYLINE:
            if home_score == away_score:
                return SettlementStatus.VOID  # unfinished / no overtime result
            actual = "home" if home_score > away_score else "away"
            return SettlementStatus.WON if selection == actual else SettlementStatus.LOST
        assert outcome.line is not None
        from quantbot.markets.settlement import LineMarketKind, settle_line_market

        kind = (
            LineMarketKind.TOTALS
            if self.kind is MarketKind.TOTALS
            else LineMarketKind.SPREAD
        )
        result = settle_line_market(
            kind=kind,
            selection=selection,
            line=outcome.line,
            home_score=home_score,
            away_score=away_score,
            decimal_odds=outcome.price,
        )
        # Exact integer-line hit: expose VOID (full refund) at the Market API.
        if result.status is SettlementStatus.PUSH:
            return SettlementStatus.VOID
        return result.status

    def payoff(self, selection: str, home_score: int, away_score: int) -> float:
        """Gross decimal return per unit stake (incl. half-win / half-loss)."""

        from quantbot.markets.settlement import payoff_factor

        status = self.settle(selection, home_score, away_score)
        if status in (SettlementStatus.PENDING, SettlementStatus.UNSUPPORTED):
            raise ValueError(f"cannot compute payoff for {status.value}")
        price = next(item.price for item in self.outcomes if item.name == selection)
        # Map legacy VOID (moneyline unfinished) to full refund like PUSH.
        if status is SettlementStatus.VOID:
            return 1.0
        return payoff_factor(status, price)


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
    kind: MarketKind = MarketKind.ONE_X_TWO
    fair_home: float = Field(gt=0.0, lt=1.0)
    fair_draw: float = Field(ge=0.0, lt=1.0)
    fair_away: float = Field(gt=0.0, lt=1.0)
    overround: float = Field(ge=0.0)
    liquidity: float | None = Field(default=None, ge=0.0)
    is_closing: bool = False

    @model_validator(mode="after")
    def _validate(self) -> MarketData:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.kind is MarketKind.MONEYLINE:
            if self.method is not MarginMethod.POWER or self.fair_draw != 0.0:
                raise ValueError("moneyline requires Power and zero draw probability")
        elif self.kind is MarketKind.ONE_X_TWO:
            if self.fair_draw <= 0.0:
                raise ValueError("1X2 requires a positive draw probability")
            if self.method is MarginMethod.POWER:
                raise ValueError("Power margin removal is reserved for two-way markets")
        else:
            raise ValueError("MarketData supports only 1X2 and moneyline")
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

        prices = {
            MatchOutcome.HOME: 1.0 / self.fair_home,
            MatchOutcome.AWAY: 1.0 / self.fair_away,
        }
        if self.kind is MarketKind.ONE_X_TWO:
            prices[MatchOutcome.DRAW] = 1.0 / self.fair_draw
        return prices


class TotalsMarketData(QuantBotModel):
    """Fair Over/Under probabilities for one totals line (margin removed)."""

    match_id: str = Field(min_length=1)
    bookmaker: str = Field(min_length=1)
    timestamp: datetime
    method: MarginMethod
    line: float = Field(gt=0.0)
    fair_over: float = Field(gt=0.0, lt=1.0)
    fair_under: float = Field(gt=0.0, lt=1.0)
    overround: float = Field(ge=0.0)
    is_closing: bool = False

    @model_validator(mode="after")
    def _validate(self) -> TotalsMarketData:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.method is not MarginMethod.POWER:
            raise ValueError("two-way totals require Power margin removal")
        total = self.fair_over + self.fair_under
        if abs(total - 1.0) > PROB_SUM_TOLERANCE:
            raise ValueError(f"fair totals probabilities must sum to 1.0, got {total}")
        return self

    def fair_probabilities(self) -> dict[TotalsSide, float]:
        return {
            TotalsSide.OVER: self.fair_over,
            TotalsSide.UNDER: self.fair_under,
        }

    def fair_odds(self) -> dict[TotalsSide, float]:
        return {
            TotalsSide.OVER: 1.0 / self.fair_over,
            TotalsSide.UNDER: 1.0 / self.fair_under,
        }
