"""QuantBot: probabilistic market analysis for sports and prediction markets.

Pipeline: Probability -> Market Price -> Edge -> Expected Value -> Backtest ->
Decision Support. Version 1 is decision support only and never places bets.
"""

from __future__ import annotations

__version__ = "0.2.0"

from quantbot.config import Settings, get_settings

__all__ = ["__version__", "Settings", "get_settings"]
