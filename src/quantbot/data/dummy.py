"""Deterministic offline data provider for tests and development.

Generates a full, reproducible single-round-robin season for Premier League
and Bundesliga plus odds snapshots. No API keys or network access required.
Given the same ``seed``, the output is byte-for-byte identical.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from itertools import combinations
from random import Random

from quantbot.data.base import BaseDataProvider
from quantbot.data.basketball_demo import build_nba_matches, build_nba_odds, build_nba_totals
from quantbot.schemas import (
    DEFAULT_TOTALS_LINE,
    League,
    Match,
    MatchResult,
    MatchStatus,
    Odds,
    Team,
    TotalsOdds,
)

UTC = timezone.utc

# Season anchor: first kickoff. Matches are spread one week apart.
_SEASON = "2024-2025"
_SEASON_START = datetime(2024, 8, 17, 15, 0, tzinfo=UTC)
_PREDICTION_LEAD = timedelta(hours=2)
_HOME_ADVANTAGE = 0.20
_BASE_OVERROUND = 0.05

_TEAMS: dict[League, list[Team]] = {
    League.PREMIER_LEAGUE: [
        Team(team_id="pl_ars", name="Arsenal"),
        Team(team_id="pl_che", name="Chelsea"),
        Team(team_id="pl_liv", name="Liverpool"),
        Team(team_id="pl_mci", name="Manchester City"),
        Team(team_id="pl_mun", name="Manchester United"),
        Team(team_id="pl_tot", name="Tottenham"),
    ],
    League.BUNDESLIGA: [
        Team(team_id="bl_bay", name="Bayern Munich"),
        Team(team_id="bl_bvb", name="Borussia Dortmund"),
        Team(team_id="bl_rbl", name="RB Leipzig"),
        Team(team_id="bl_b04", name="Bayer Leverkusen"),
        Team(team_id="bl_sge", name="Eintracht Frankfurt"),
        Team(team_id="bl_wob", name="VfL Wolfsburg"),
    ],
}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _poisson(rng: Random, lam: float) -> int:
    """Knuth's algorithm; deterministic for a given ``rng`` state."""

    target = math.exp(-lam)
    k = 0
    product = 1.0
    while True:
        product *= rng.random()
        if product <= target:
            return k
        k += 1


class DummyDataProvider(BaseDataProvider):
    """Reproducible in-memory provider.

    Args:
        seed: Master seed. Team strengths, results, and odds all derive from
            it. Identical seeds yield identical data.
    """

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed

    @property
    def provider_name(self) -> str:
        return f"dummy(seed={self._seed})"

    # --- Deterministic generation ---

    @lru_cache(maxsize=1)  # noqa: B019 - bound to instance lifetime, small object
    def _team_strength(self) -> dict[str, float]:
        """Assign each team a fixed strength in roughly [-1, 1]."""

        rng = Random(self._seed)
        strengths: dict[str, float] = {}
        # Sort leagues/teams for a stable assignment order.
        for league in sorted(_TEAMS, key=lambda lg: lg.value):
            for team in _TEAMS[league]:
                strengths[team.team_id] = rng.uniform(-1.0, 1.0)
        return strengths

    def _fair_probabilities(self, home_id: str, away_id: str) -> tuple[float, float, float]:
        """Model fair 1X2 probabilities from team strengths (no margin)."""

        strengths = self._team_strength()
        diff = strengths[home_id] - strengths[away_id] + _HOME_ADVANTAGE
        p_draw = 0.24
        remaining = 1.0 - p_draw
        p_home = remaining * _sigmoid(1.6 * diff)
        p_away = remaining - p_home
        return p_home, p_draw, p_away

    @lru_cache(maxsize=1)  # noqa: B019
    def _fetch_matches(self) -> Sequence[Match]:
        matches: list[Match] = []
        for league in sorted(_TEAMS, key=lambda lg: lg.value):
            teams = _TEAMS[league]
            week = 0
            for home, away in combinations(teams, 2):
                kickoff = _SEASON_START + timedelta(days=7 * week)
                week += 1
                match_id = f"{league.value}:{home.team_id}:{away.team_id}"
                result = self._generate_result(match_id, home.team_id, away.team_id)
                matches.append(
                    Match(
                        match_id=match_id,
                        league=league,
                        season=_SEASON,
                        kickoff=kickoff,
                        prediction_timestamp=kickoff - _PREDICTION_LEAD,
                        home_team=home,
                        away_team=away,
                        status=MatchStatus.FINISHED,
                        result=result,
                        result_available_at=kickoff + timedelta(hours=2),
                        status_available_at=kickoff + timedelta(hours=2),
                    )
                )
        matches.extend(build_nba_matches(seed=self._seed))
        return tuple(matches)

    def _match_rng(self, match_id: str, salt: str) -> Random:
        """A per-match RNG independent of query order."""

        return Random(f"{self._seed}:{match_id}:{salt}")

    def _generate_result(self, match_id: str, home_id: str, away_id: str) -> MatchResult:
        strengths = self._team_strength()
        rng = self._match_rng(match_id, "result")
        # Expected goals scaled by strength around a base rate of 1.35.
        home_lambda = max(0.2, 1.35 + 0.6 * strengths[home_id] + _HOME_ADVANTAGE)
        away_lambda = max(0.2, 1.35 + 0.6 * strengths[away_id])
        return MatchResult(
            home_goals=_poisson(rng, home_lambda),
            away_goals=_poisson(rng, away_lambda),
        )

    def _fetch_odds(self, match_id: str) -> Sequence[Odds]:
        match = next((m for m in self._fetch_matches() if m.match_id == match_id), None)
        if match is None:
            return ()
        if match.league is League.NBA:
            return tuple(build_nba_odds([match], seed=self._seed).get(match_id, []))

        p_home, p_draw, p_away = self._fair_probabilities(
            match.home_team.team_id, match.away_team.team_id
        )
        # Snapshots relative to kickoff: opening, mid, near-close, closing.
        offsets = [
            (timedelta(hours=72), False),
            (timedelta(hours=24), False),
            (timedelta(hours=2), False),
            (timedelta(minutes=10), True),
        ]
        snapshots: list[Odds] = []
        for idx, (lead, is_closing) in enumerate(offsets):
            rng = self._match_rng(match_id, f"odds:{idx}")
            # Small multiplicative noise on fair probs, then add margin.
            noisy = [
                max(0.01, p * (1.0 + rng.uniform(-0.04, 0.04)))
                for p in (p_home, p_draw, p_away)
            ]
            total = sum(noisy)
            margin_factor = (1.0 + _BASE_OVERROUND) / total
            book = [p * margin_factor for p in noisy]
            snapshots.append(
                Odds(
                    match_id=match_id,
                    bookmaker="dummy_book",
                    timestamp=match.kickoff - lead,
                    home=round(1.0 / book[0], 3),
                    draw=round(1.0 / book[1], 3),
                    away=round(1.0 / book[2], 3),
                    is_closing=is_closing,
                )
            )
        return tuple(snapshots)

    def _fetch_totals_odds(self, match_id: str) -> Sequence[TotalsOdds]:
        match = next((m for m in self._fetch_matches() if m.match_id == match_id), None)
        if match is None:
            return ()
        if match.league is League.NBA:
            return tuple(build_nba_totals([match], seed=self._seed).get(match_id, []))

        strengths = self._team_strength()
        # Rough expected total goals from the same strength model as results.
        home_lambda = max(
            0.2, 1.35 + 0.6 * strengths[match.home_team.team_id] + _HOME_ADVANTAGE
        )
        away_lambda = max(0.2, 1.35 + 0.6 * strengths[match.away_team.team_id])
        # Soft Poisson P(total > 2.5) approximation via expected goals.
        expected = home_lambda + away_lambda
        # Map expected goals around 2.5 into an over probability in (0.25, 0.75).
        p_over = 1.0 / (1.0 + math.exp(-(expected - DEFAULT_TOTALS_LINE)))
        p_over = min(0.75, max(0.25, p_over))
        p_under = 1.0 - p_over

        offsets = [
            (timedelta(hours=72), False),
            (timedelta(hours=24), False),
            (timedelta(hours=2), False),
            (timedelta(minutes=10), True),
        ]
        snapshots: list[TotalsOdds] = []
        for idx, (lead, is_closing) in enumerate(offsets):
            rng = self._match_rng(match_id, f"totals:{idx}")
            noisy_over = max(0.05, p_over * (1.0 + rng.uniform(-0.05, 0.05)))
            noisy_under = max(0.05, p_under * (1.0 + rng.uniform(-0.05, 0.05)))
            total = noisy_over + noisy_under
            margin_factor = (1.0 + _BASE_OVERROUND) / total
            book_over = noisy_over * margin_factor
            book_under = noisy_under * margin_factor
            snapshots.append(
                TotalsOdds(
                    match_id=match_id,
                    bookmaker="dummy_book",
                    timestamp=match.kickoff - lead,
                    line=DEFAULT_TOTALS_LINE,
                    over=round(1.0 / book_over, 3),
                    under=round(1.0 / book_under, 3),
                    is_closing=is_closing,
                )
            )
        return tuple(snapshots)
