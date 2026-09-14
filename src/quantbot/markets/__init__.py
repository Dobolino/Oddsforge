"""Market Engine (Layer 2)."""

from __future__ import annotations

from quantbot.markets.margin import (
    booksum,
    implied_probabilities,
    naive_normalization,
    power_method,
    remove_margin,
    shins_method,
    validate_odds,
)
from quantbot.markets.arbitrage import ArbitrageEngine, ArbitrageOpportunity
from quantbot.markets.odds import MarketEngine
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
    "actual_totals_label",
    "tip_label_for",
]
