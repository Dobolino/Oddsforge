"""Tests for margin removal and the Market Engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quantbot.markets import (
    MarketEngine,
    booksum,
    implied_probabilities,
    naive_normalization,
    power_method,
    remove_margin,
    shins_method,
    validate_odds,
)
from quantbot.schemas import MarginMethod, MatchOutcome, Odds

UTC = timezone.utc
TS = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
PROB_TOL = 1e-9


def _odds(match_id: str, bookmaker: str, home: float, draw: float, away: float) -> Odds:
    return Odds(match_id=match_id, bookmaker=bookmaker, timestamp=TS, home=home, draw=draw, away=away)


# --- Margin math ---


def test_booksum_and_overround() -> None:
    odds = [2.0, 4.0, 4.0]  # implied 0.5 + 0.25 + 0.25 = 1.0 exactly
    assert booksum(odds) == pytest.approx(1.0)
    odds2 = [1.9, 3.8, 3.8]
    assert booksum(odds2) > 1.0


@pytest.mark.parametrize(
    "fn",
    [naive_normalization, lambda o: power_method(o)[0], lambda o: shins_method(o)[0]],
)
def test_fair_probabilities_sum_to_one(fn) -> None:  # type: ignore[no-untyped-def]
    odds = [1.8, 3.6, 4.5]
    fair = fn(odds)
    assert sum(fair) == pytest.approx(1.0, abs=1e-9)
    assert all(0.0 < p < 1.0 for p in fair)


def test_naive_normalization_matches_definition() -> None:
    odds = [2.0, 4.0, 5.0]
    implied = implied_probabilities(odds)
    total = sum(implied)
    expected = [p / total for p in implied]
    assert naive_normalization(odds) == pytest.approx(expected)


def test_power_method_exponent_above_one_with_margin() -> None:
    _, k = power_method([1.8, 3.6, 4.5])
    assert k > 1.0


def test_shin_z_is_positive_with_margin() -> None:
    _, z = shins_method([1.8, 3.6, 4.5])
    assert z > 0.0


def test_shin_corrects_favorite_longshot_bias() -> None:
    """Shin lifts the favorite and lowers the longshot vs naive normalization."""

    odds = [1.5, 4.0, 8.0]  # clear favorite / longshot spread
    naive = naive_normalization(odds)
    shin, _ = shins_method(odds)
    # Favorite is index 0, longshot index 2.
    assert shin[0] > naive[0]
    assert shin[2] < naive[2]


def test_methods_agree_when_no_margin() -> None:
    """With booksum == 1 there is no margin, so all methods coincide."""

    odds = [2.0, 4.0, 4.0]  # booksum exactly 1.0
    naive = naive_normalization(odds)
    power, k = power_method(odds)
    shin, z = shins_method(odds)
    assert power == pytest.approx(naive)
    assert shin == pytest.approx(naive)
    assert k == pytest.approx(1.0)
    assert z == pytest.approx(0.0)


# --- Faulty odds handling ---


@pytest.mark.parametrize("bad", [[1.0, 4.0, 4.0], [0.5, 4.0, 4.0], [-2.0, 4.0, 4.0]])
def test_validate_rejects_non_positive_margin_odds(bad) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="> 1.0"):
        validate_odds(bad)


def test_validate_rejects_single_outcome() -> None:
    with pytest.raises(ValueError, match="at least two"):
        validate_odds([2.0])


def test_validate_rejects_non_finite() -> None:
    with pytest.raises(ValueError, match="finite"):
        validate_odds([float("inf"), 3.0])


def test_remove_margin_unknown_method() -> None:
    with pytest.raises(ValueError, match="unknown margin method"):
        remove_margin([2.0, 4.0, 4.0], "bogus")


# --- Market Engine ---


def test_to_market_data_sums_to_one_and_has_overround() -> None:
    engine = MarketEngine(method=MarginMethod.SHIN)
    market = engine.to_market_data(_odds("m1", "bk", 1.9, 3.6, 4.2))
    total = market.fair_home + market.fair_draw + market.fair_away
    assert abs(total - 1.0) < 1e-6
    assert market.overround > 0.0
    assert market.method is MarginMethod.SHIN
    assert market.bookmaker == "bk"


def test_engine_respects_method_override() -> None:
    engine = MarketEngine(method=MarginMethod.SHIN)
    odds = _odds("m1", "bk", 1.5, 4.0, 8.0)
    shin = engine.fair_probabilities(odds, MarginMethod.SHIN)
    naive = engine.fair_probabilities(odds, MarginMethod.MULTIPLICATIVE)
    assert shin[MatchOutcome.HOME] > naive[MatchOutcome.HOME]


def test_best_odds_picks_highest_per_outcome() -> None:
    engine = MarketEngine()
    books = [
        _odds("m1", "bookA", 2.0, 3.5, 4.0),
        _odds("m1", "bookB", 1.9, 3.8, 4.5),
    ]
    best = engine.best_odds(books)
    assert best[MatchOutcome.HOME] == (2.0, "bookA")
    assert best[MatchOutcome.DRAW] == (3.8, "bookB")
    assert best[MatchOutcome.AWAY] == (4.5, "bookB")


def test_best_odds_market_normalizes_low_booksum() -> None:
    engine = MarketEngine()
    # Two generous books; best odds combined can push booksum below 1.
    books = [
        _odds("m1", "bookA", 2.2, 3.9, 4.3),
        _odds("m1", "bookB", 2.3, 4.1, 4.6),
    ]
    market = engine.best_odds_market(books)
    total = market.fair_home + market.fair_draw + market.fair_away
    assert abs(total - 1.0) < 1e-6
    assert market.bookmaker == "best"
    assert market.overround >= 0.0


def test_consensus_averages_books() -> None:
    engine = MarketEngine(method=MarginMethod.MULTIPLICATIVE)
    books = [
        _odds("m1", "bookA", 2.0, 3.5, 4.0),
        _odds("m1", "bookB", 1.8, 3.8, 4.5),
    ]
    market = engine.consensus(books)
    total = market.fair_home + market.fair_draw + market.fair_away
    assert abs(total - 1.0) < 1e-6
    assert market.bookmaker == "consensus"
    # Consensus home prob lies between the two books' fair home probs.
    fa = engine.fair_probabilities(books[0])[MatchOutcome.HOME]
    fb = engine.fair_probabilities(books[1])[MatchOutcome.HOME]
    assert min(fa, fb) <= market.fair_home <= max(fa, fb)


def test_aggregation_rejects_mixed_match_ids() -> None:
    engine = MarketEngine()
    books = [_odds("m1", "bookA", 2.0, 3.5, 4.0), _odds("m2", "bookB", 1.9, 3.8, 4.5)]
    with pytest.raises(ValueError, match="one match_id"):
        engine.consensus(books)


def test_aggregation_rejects_empty() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        MarketEngine().best_odds([])
