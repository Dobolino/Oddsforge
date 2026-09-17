"""Regressions for temporal isolation, market settlement and hard risk limits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from quantbot.data.base import BaseDataProvider
from quantbot.data.basketball import BasketballDataProvider
from quantbot.dashboard.slip import cap_example_stake
from quantbot.decision import KellySizer, NoBetRules
from quantbot.features import FeatureExtractor
from quantbot.markets.odds import MarketEngine
from quantbot.markets.totals import TotalsMarketEngine, actual_totals_label
from quantbot.models import DixonColesModel, EloModel
from quantbot.schemas import (
    League,
    MarginMethod,
    Match,
    MatchOutcome,
    MatchResult,
    MatchStatus,
    ScoreMatrix,
    Team,
    TotalsOdds,
    ValueMetrics,
)

START = datetime(2025, 1, 1, 12, tzinfo=UTC)


def _match(
    match_id: str,
    home: str,
    away: str,
    kickoff: datetime,
    *,
    result_at: datetime | None = None,
    status: MatchStatus = MatchStatus.FINISHED,
) -> Match:
    return Match(
        match_id=match_id,
        league=League.PREMIER_LEAGUE,
        season="2024-2025",
        kickoff=kickoff,
        prediction_timestamp=kickoff - timedelta(hours=2),
        home_team=Team(team_id=home, name=home),
        away_team=Team(team_id=away, name=away),
        status=status,
        result=MatchResult(home_goals=2, away_goals=0) if status is MatchStatus.FINISHED else None,
        result_available_at=result_at,
        status_available_at=START if status is MatchStatus.POSTPONED else None,
    )


class _Provider(BaseDataProvider):
    def __init__(self, matches: list[Match]) -> None:
        self.matches = matches

    @property
    def provider_name(self) -> str:
        return "integrity_test"

    def _fetch_matches(self) -> list[Match]:
        return self.matches

    def _fetch_odds(self, match_id: str) -> list:
        return []


def test_result_remains_hidden_until_observed_and_fit_uses_publication() -> None:
    kickoff = START
    published = kickoff + timedelta(hours=3)
    match = _match("m1", "A", "B", kickoff, result_at=published)
    provider = _Provider([match])
    assert provider.get_match("m1", kickoff).result is None
    assert provider.get_match("m1", published - timedelta(seconds=1)).result is None
    assert provider.get_match("m1", published).result is not None

    model = EloModel()
    model.fit_until([match], published)
    assert model.rating("A") == 1500.0
    model.fit_until([match], published + timedelta(seconds=1))
    assert model.rating("A") > 1500.0


def test_bulk_features_exclude_result_published_after_target_prediction() -> None:
    first = _match("first", "A", "B", START, result_at=START + timedelta(hours=3))
    target = _match(
        "target", "A", "C", START + timedelta(hours=4),
        result_at=START + timedelta(hours=7),
    )
    # The target is predicted two hours after the first kickoff, one hour
    # before its result was published.
    extractor = FeatureExtractor()
    features, _ = extractor.build_training_set([first, target])
    assert features[1]["home_matches_played"] == 0.0
    assert extractor.extract(target, [first])["home_matches_played"] == 0.0
    assert extractor.extract(target, [first], as_of=START)["home_matches_played"] == 0.0


def test_known_postponement_is_not_upcoming() -> None:
    match = _match(
        "postponed", "A", "B", START + timedelta(days=1),
        status=MatchStatus.POSTPONED,
    )
    provider = _Provider([match])
    assert provider.get_upcoming_matches(League.PREMIER_LEAGUE, "2024-2025", START) == []


def test_integer_totals_rejected_before_pricing_or_settlement() -> None:
    with pytest.raises(ValidationError, match="half-point"):
        TotalsOdds(
            match_id="m1", bookmaker="book", timestamp=START,
            line=2.0, over=1.9, under=1.9,
        )
    with pytest.raises(ValueError, match="half-point"):
        ScoreMatrix(matrix=[[1.0]]).totals_probabilities(2.0)
    with pytest.raises(ValueError, match="half-point"):
        actual_totals_label(2, 2.0)


def test_hard_stake_cap_and_unrealistic_ev_gate() -> None:
    sizer = KellySizer(kelly_fraction=1.0, max_fraction=1.0)
    assert sizer.stake_fraction(0.9, 2.0) == 0.05
    assert cap_example_stake(1000.0, 100.0) == 5.0
    with pytest.raises(ValueError, match="finite"):
        sizer.stake_fraction(float("nan"), 2.0)
    metric = ValueMetrics(
        outcome=MatchOutcome.HOME,
        model_prob=0.8,
        fair_market_prob=0.5,
        decimal_odds=2.0,
        edge=0.3,
        expected_value=0.6,
    )
    result = NoBetRules().evaluate(metric, 0.05, 90.0, 90.0)
    assert not result.passed
    assert "NO_BET_UNREALISTIC_EV" in {reason.code for reason in result.reasons}


def test_basketball_spreads_respect_as_of() -> None:
    provider = BasketballDataProvider()
    match = provider._fetch_matches()[0]
    cutoff = match.prediction_timestamp
    assert all(o.timestamp <= cutoff for o in provider.get_spreads(match.match_id, cutoff))
    with pytest.raises(ValueError, match="timezone-aware"):
        provider.get_spreads(match.match_id, datetime(2025, 1, 1))


def test_market_method_policy_and_invalid_dixon_coles_rho() -> None:
    with pytest.raises(ValueError, match="two-way"):
        MarketEngine(MarginMethod.POWER)
    with pytest.raises(ValueError, match="two-way"):
        TotalsMarketEngine(MarginMethod.SHIN)

    model = DixonColesModel(max_goals=4)
    model._attack = {"A": 0.0, "B": 0.0}
    model._defense = {"A": 0.0, "B": 0.0}
    model._home_adv = 0.0
    model._rho = 0.9
    model._lambdas = lambda _h, _a: (4.0, 4.0)  # type: ignore[method-assign]
    invalid_grid = model.score_matrix("A", "B")
    model._rho = 0.0
    independent_grid = model.score_matrix("A", "B")
    assert (invalid_grid == independent_grid).all()
