"""Tests for the core domain schemas, including temporal-isolation guardrails."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from quantbot.schemas import (
    League,
    Match,
    MatchOutcome,
    MatchResult,
    MatchStatus,
    Odds,
    Prediction,
    ScoreMatrix,
    SignalType,
    Team,
    ValueMetrics,
    ValueSignal,
)
from quantbot.schemas.enums import MarginMethod
from quantbot.schemas.market import MarketData

UTC = timezone.utc
KICKOFF = datetime(2025, 1, 1, 15, 0, tzinfo=UTC)
PREDICT = KICKOFF - timedelta(hours=2)


def _teams() -> tuple[Team, Team]:
    return Team(team_id="h", name="Home FC"), Team(team_id="a", name="Away FC")


def _match(**overrides: object) -> Match:
    home, away = _teams()
    base: dict[str, object] = dict(
        match_id="m1",
        league=League.PREMIER_LEAGUE,
        season="2024-2025",
        kickoff=KICKOFF,
        prediction_timestamp=PREDICT,
        home_team=home,
        away_team=away,
    )
    base.update(overrides)
    return Match(**base)  # type: ignore[arg-type]


def test_match_valid() -> None:
    match = _match()
    assert match.home_team.team_id == "h"
    assert not match.is_finished


def test_match_rejects_prediction_after_kickoff() -> None:
    with pytest.raises(ValidationError, match="prediction_timestamp must not be after"):
        _match(prediction_timestamp=KICKOFF + timedelta(minutes=1))


def test_match_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _match(kickoff=datetime(2025, 1, 1, 15, 0))


def test_match_rejects_same_team() -> None:
    home, _ = _teams()
    with pytest.raises(ValidationError, match="must differ"):
        _match(away_team=home)


def test_match_result_requires_finished_status() -> None:
    with pytest.raises(ValidationError, match="status is FINISHED"):
        _match(result=MatchResult(home_goals=2, away_goals=1))


def test_match_result_outcome() -> None:
    match = _match(status=MatchStatus.FINISHED, result=MatchResult(home_goals=2, away_goals=1))
    assert match.is_finished
    assert match.result is not None
    assert match.result.outcome is MatchOutcome.HOME
    assert match.result.total_goals == 3


def test_odds_overround_and_implied() -> None:
    odds = Odds(match_id="m1", bookmaker="bk", timestamp=PREDICT, home=2.0, draw=4.0, away=4.0)
    assert odds.overround == pytest.approx(0.0)  # 0.5 + 0.25 + 0.25 - 1
    implied = odds.implied_probabilities()
    assert implied[MatchOutcome.HOME] == pytest.approx(0.5)


def test_odds_rejects_non_positive_margin_odds() -> None:
    with pytest.raises(ValidationError):
        Odds(match_id="m1", bookmaker="bk", timestamp=PREDICT, home=1.0, draw=4.0, away=4.0)


def test_market_data_probs_must_sum_to_one() -> None:
    with pytest.raises(ValidationError, match="must sum to 1.0"):
        MarketData(
            match_id="m1",
            bookmaker="bk",
            timestamp=PREDICT,
            method=MarginMethod.SHIN,
            fair_home=0.5,
            fair_draw=0.3,
            fair_away=0.3,
            overround=0.05,
        )


def test_market_fair_odds() -> None:
    market = MarketData(
        match_id="m1",
        bookmaker="bk",
        timestamp=PREDICT,
        method=MarginMethod.SHIN,
        fair_home=0.5,
        fair_draw=0.25,
        fair_away=0.25,
        overround=0.05,
    )
    assert market.fair_odds()[MatchOutcome.HOME] == pytest.approx(2.0)


def test_prediction_probs_must_sum_to_one() -> None:
    with pytest.raises(ValidationError, match="must sum to 1.0"):
        Prediction(
            match_id="m1",
            model_name="dixon_coles",
            prediction_timestamp=PREDICT,
            prob_home=0.5,
            prob_draw=0.3,
            prob_away=0.3,
        )


def test_score_matrix_marginalization() -> None:
    matrix = ScoreMatrix(matrix=[[0.4, 0.1], [0.1, 0.4]])
    probs = matrix.outcome_probabilities()
    assert probs[MatchOutcome.HOME] == pytest.approx(0.1)
    assert probs[MatchOutcome.DRAW] == pytest.approx(0.8)
    assert probs[MatchOutcome.AWAY] == pytest.approx(0.1)


def test_value_metrics_derived_fields_checked() -> None:
    with pytest.raises(ValidationError, match="edge must equal"):
        ValueMetrics(
            outcome=MatchOutcome.HOME,
            model_prob=0.55,
            fair_market_prob=0.5,
            decimal_odds=2.0,
            edge=0.10,  # wrong; should be 0.05
            expected_value=0.10,
        )


def test_value_signal_no_bet_rules() -> None:
    with pytest.raises(ValidationError, match="NO_BET must not set"):
        ValueSignal(
            match_id="m1",
            timestamp=PREDICT,
            signal=SignalType.NO_BET,
            chosen_outcome=MatchOutcome.HOME,
            model_confidence=60.0,
            data_quality=70.0,
        )


def test_value_signal_bet_requires_matching_outcome() -> None:
    with pytest.raises(ValidationError, match="must choose home"):
        ValueSignal(
            match_id="m1",
            timestamp=PREDICT,
            signal=SignalType.VALUE_HOME,
            chosen_outcome=MatchOutcome.AWAY,
            model_confidence=60.0,
            data_quality=70.0,
            stake_fraction=0.02,
        )


def test_value_signal_valid_bet() -> None:
    signal = ValueSignal(
        match_id="m1",
        timestamp=PREDICT,
        signal=SignalType.VALUE_HOME,
        chosen_outcome=MatchOutcome.HOME,
        edge=0.05,
        expected_value=0.1,
        decimal_odds=2.0,
        model_confidence=60.0,
        data_quality=70.0,
        stake_fraction=0.02,
    )
    assert signal.is_bet
