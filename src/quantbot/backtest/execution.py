"""Execution simulation: settle paper bets, compute PnL and CLV (Layer 5).

Guardrail: this is paper trading only. No orders are placed. A bet is settled
against the known match result to compute profit/loss, and against the closing
line to compute Closing Line Value (CLV) -- the standard measure of whether an
entry price beat the market's final price.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from quantbot.schemas import Market, MatchOutcome, SettlementStatus


@dataclass(frozen=True)
class MarketSettlement:
    status: SettlementStatus
    stake: float
    payoff: float
    pnl: float


@dataclass(frozen=True)
class SettledBet:
    """A resolved paper bet.

    Attributes:
        stake: Amount staked (currency units).
        entry_odds: Decimal odds taken when the bet was recorded.
        closing_odds: Decimal odds at market close (None if unavailable).
        won: Whether the chosen outcome occurred.
        pnl: Profit/loss in currency units.
        clv: entry_odds / closing_odds - 1 (positive means beat the close).
        beat_closing: Whether entry odds exceeded closing odds.
    """

    match_id: str
    outcome: MatchOutcome
    stake: float
    entry_odds: float
    closing_odds: float | None
    actual_outcome: MatchOutcome
    won: bool
    pnl: float
    model_prob: float
    clv: float | None
    beat_closing: bool | None
    edge: float | None = None
    league: str | None = None
    kickoff: str | None = None  # ISO date, for period breakdowns


class ExecutionSimulator:
    """Settles bets and computes PnL and CLV."""

    @staticmethod
    def settle_market(
        market: Market, selection: str, stake: float, home_score: int, away_score: int
    ) -> MarketSettlement:
        """Settle any market, refunding the full stake on a push."""

        if not isfinite(stake) or stake < 0.0:
            raise ValueError("stake must be finite and non-negative")
        status = market.settle(selection, home_score, away_score)
        payoff = market.payoff(selection, home_score, away_score)
        return MarketSettlement(
            status=status, stake=stake, payoff=payoff, pnl=stake * (payoff - 1.0)
        )

    @staticmethod
    def profit(stake: float, decimal_odds: float, won: bool) -> float:
        """PnL for a unit-priced bet: net win on success, full stake lost otherwise."""

        if stake < 0.0:
            raise ValueError("stake must be non-negative")
        if decimal_odds <= 1.0:
            raise ValueError("decimal_odds must be > 1.0")
        return stake * (decimal_odds - 1.0) if won else -stake

    @staticmethod
    def closing_line_value(entry_odds: float, closing_odds: float) -> float:
        """CLV as an odds ratio: ``entry_odds / closing_odds - 1``.

        Positive means the entry price was better (higher) than the close.
        """

        if entry_odds <= 1.0 or closing_odds <= 1.0:
            raise ValueError("odds must be > 1.0")
        return entry_odds / closing_odds - 1.0

    def settle(
        self,
        match_id: str,
        outcome: MatchOutcome,
        stake: float,
        entry_odds: float,
        actual_outcome: MatchOutcome,
        model_prob: float,
        closing_odds: float | None = None,
        edge: float | None = None,
        league: str | None = None,
        kickoff: str | None = None,
    ) -> SettledBet:
        won = outcome is actual_outcome
        pnl = self.profit(stake, entry_odds, won)

        clv: float | None = None
        beat: bool | None = None
        if closing_odds is not None:
            clv = self.closing_line_value(entry_odds, closing_odds)
            beat = entry_odds > closing_odds

        return SettledBet(
            match_id=match_id,
            outcome=outcome,
            stake=stake,
            entry_odds=entry_odds,
            closing_odds=closing_odds,
            actual_outcome=actual_outcome,
            won=won,
            pnl=pnl,
            model_prob=model_prob,
            clv=clv,
            beat_closing=beat,
            edge=edge,
            league=league,
            kickoff=kickoff,
        )
