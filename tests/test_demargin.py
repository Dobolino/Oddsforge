"""Demargin router: Shin for 1X2, Power for two-way books."""

from __future__ import annotations

import pytest

from quantbot.markets.demargin import demargin_prices, method_for_market, method_for_n_ways
from quantbot.schemas.enums import MarginMethod, MarketKind


def test_method_routing() -> None:
    assert method_for_market(MarketKind.ONE_X_TWO) is MarginMethod.SHIN
    assert method_for_market(MarketKind.TOTALS) is MarginMethod.POWER
    assert method_for_market(MarketKind.SPREAD) is MarginMethod.POWER
    assert method_for_market(MarketKind.MONEYLINE) is MarginMethod.POWER
    assert method_for_n_ways(3) is MarginMethod.SHIN
    assert method_for_n_ways(2) is MarginMethod.POWER


def test_demargin_prices_1x2_and_totals() -> None:
    fair_1x2 = demargin_prices([2.0, 3.4, 3.5], kind=MarketKind.ONE_X_TWO)
    assert len(fair_1x2) == 3
    assert sum(fair_1x2) == pytest.approx(1.0)
    fair_2way = demargin_prices([1.9, 1.95], kind=MarketKind.TOTALS)
    assert len(fair_2way) == 2
    assert sum(fair_2way) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        demargin_prices([2.0, 3.0], method=MarginMethod.SHIN)
    with pytest.raises(ValueError):
        demargin_prices([2.0, 3.0, 4.0], method=MarginMethod.POWER)
