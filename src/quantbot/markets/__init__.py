"""Market Engine (Layer 2)."""

from __future__ import annotations

from quantbot.markets.arbitrage import ArbitrageEngine, ArbitrageOpportunity
from quantbot.markets.integrity import check_1x2_odds, check_totals_odds
from quantbot.markets.margin import (
    booksum,
    implied_probabilities,
    naive_normalization,
    power_method,
    remove_margin,
    shins_method,
    validate_odds,
)
from quantbot.markets.odds import MarketEngine
from quantbot.markets.clv import (
    ClvResult,
    ClvStatus,
    ClosingQuoteRef,
    EntryQuoteRef,
    closing_line_value_odds_ratio,
    closing_reference_ev,
    evaluate_clv,
)
from quantbot.markets.settlement import (
    LineMarketKind,
    SettlementResult,
    multi_state_ev,
    payoff_factor,
    settle_line_market,
)
from quantbot.markets.totals import TotalsMarketEngine, actual_totals_label, tip_label_for

__all__ = [
    "MarketEngine",
    "TotalsMarketEngine",
    "ArbitrageEngine",
    "ArbitrageOpportunity",
    "booksum",
    "implied_probabilities",
    "naive_normalization",
    "power_method",
    "remove_margin",
    "shins_method",
    "validate_odds",
    "check_1x2_odds",
    "check_totals_odds",
    "actual_totals_label",
    "tip_label_for",
    "ClvResult",
    "ClvStatus",
    "ClosingQuoteRef",
    "EntryQuoteRef",
    "closing_line_value_odds_ratio",
    "closing_reference_ev",
    "evaluate_clv",
    "LineMarketKind",
    "SettlementResult",
    "multi_state_ev",
    "payoff_factor",
    "settle_line_market",
]
