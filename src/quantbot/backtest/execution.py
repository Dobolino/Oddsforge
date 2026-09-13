"""Execution simulation: settle paper bets, compute PnL and CLV (Layer 5).

Guardrail: this is paper trading only. No orders are placed. A bet is settled
against the known match result to compute profit/loss, and against the closing
line to compute Closing Line Value (CLV) -- the standard measure of whether an
entry price beat the market's final price.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantbot.schemas import MatchOutcome


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


class ExecutionSimulator:
    """Settles bets and computes PnL and CLV."""

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
        )
