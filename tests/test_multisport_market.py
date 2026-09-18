"""Contract tests for sport-neutral pricing and push settlement."""

from datetime import datetime, timezone

import pytest

from quantbot.backtest.execution import ExecutionSimulator
from quantbot.dashboard.slip import BettingSlip, SlipLeg
from quantbot.markets.odds import MarketEngine
from quantbot.markets.totals import TotalsMarketEngine
from quantbot.schemas import (
    MarginMethod,
    Market,
    MarketKind,
    MarketOutcome,
    MatchOutcome,
    MoneylineOdds,
    SettlementStatus,
    SpreadOdds,
    TotalsMarketData,
    TotalsOdds,
)

NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _leg(index: int, *, odds: float, prob: float) -> SlipLeg:
    return SlipLeg(
        match_id=str(index),
        match="A–B",
        tip="home",
        outcome=MatchOutcome.HOME,
        odds=odds,
        model_prob=prob,
        edge=0.0,
        role="core",
    )


def test_slip_multiplies_probs_and_flags_required_thresholds() -> None:
    slip = BettingSlip((_leg(1, odds=2.0, prob=0.6), _leg(2, odds=2.0, prob=0.5)), "safe")
    assert slip.combined_prob == pytest.approx(0.3)
    assert slip.geschaetzte_chance == "n/a"
    assert slip.independence_scenario_pct == pytest.approx(30.0)
    inflated = BettingSlip((_leg(1, odds=4.0, prob=0.4), _leg(2, odds=4.0, prob=0.4)), "safe")
    assert inflated.combined_prob * inflated.combined_odds > 2.5
    assert inflated.independence_scenario_pct is None
    longshot = BettingSlip((_leg(1, odds=8.01, prob=0.15),), "safe")
    assert longshot.independence_scenario_pct is None


def test_moneyline_uses_two_way_power_without_phantom_draw() -> None:
    quote = MoneylineOdds(match_id="m", bookmaker="b", timestamp=NOW, home=1.4, away=3.2)
    market = MarketEngine().to_market_data(quote.to_three_way())
    assert market.kind is MarketKind.MONEYLINE
    assert market.method is MarginMethod.POWER
    assert market.fair_draw == 0.0
    assert MatchOutcome.DRAW not in market.fair_odds()
    assert market.fair_home + market.fair_away == pytest.approx(1.0)
    generic = Market.from_quote(quote)
    assert generic.margin_method is MarginMethod.POWER
    assert generic.fair_probabilities()["home"] == pytest.approx(market.fair_home)


def test_two_way_totals_cannot_override_power() -> None:
    quote = TotalsOdds(match_id="m", bookmaker="b", timestamp=NOW, line=2.5, over=1.8, under=2.1)
    assert TotalsMarketEngine().to_market_data(quote).method is MarginMethod.POWER
    for method in (MarginMethod.SHIN, MarginMethod.MULTIPLICATIVE):
        with pytest.raises(ValueError):
            TotalsMarketEngine(method)
        with pytest.raises(ValueError):
            TotalsMarketEngine().to_market_data(quote, method)
        with pytest.raises(ValueError):
            TotalsMarketData(
                match_id="m",
                bookmaker="b",
                timestamp=NOW,
                method=method,
                line=2.5,
                fair_over=0.5,
                fair_under=0.5,
                overround=0.05,
            )


def test_integer_totals_and_spreads_refund_on_push() -> None:
    totals = Market(
        match_id="m",
        bookmaker="b",
        timestamp=NOW,
        kind=MarketKind.TOTALS,
        outcomes=(
            MarketOutcome(name="over", line=2.0, price=1.9),
            MarketOutcome(name="under", line=2.0, price=1.9),
        ),
    )
    spread = Market.from_quote(
        SpreadOdds(match_id="m", bookmaker="b", timestamp=NOW, line=-3.0, home=1.95, away=1.95)
    )
    for market, selection, home, away in (
        (totals, "over", 1, 1),
        (spread, "home", 103, 100),
        (spread, "away", 103, 100),
    ):
        result = ExecutionSimulator.settle_market(market, selection, 100.0, home, away)
        assert result.status is SettlementStatus.PUSH
        assert result.payoff == 1.0
        assert result.pnl == 0.0
    assert totals.settle("over", 2, 1) is SettlementStatus.WON
    assert totals.settle("under", 2, 1) is SettlementStatus.LOST
    assert spread.margin_method is MarginMethod.POWER
    assert sum(spread.fair_probabilities().values()) == pytest.approx(1.0)


def test_market_rejects_inconsistent_lines_and_outcomes() -> None:
    with pytest.raises(ValueError):
        Market(
            match_id="m",
            bookmaker="b",
            timestamp=NOW,
            kind=MarketKind.SPREAD,
            outcomes=(
                MarketOutcome(name="home", line=-3.0, price=1.9),
                MarketOutcome(name="away", line=-3.0, price=1.9),
            ),
        )
    with pytest.raises(ValueError):
        Market(
            match_id="m",
            bookmaker="b",
            timestamp=NOW,
            kind=MarketKind.TOTALS,
            outcomes=(
                MarketOutcome(name="over", line=2.0, price=1.9),
                MarketOutcome(name="under", line=3.0, price=1.9),
            ),
        )
