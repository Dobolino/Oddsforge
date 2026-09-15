"""Deterministic offline NBA fixtures for demo / tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from random import Random

from quantbot.schemas import (
    InjuryStatus,
    League,
    Match,
    MatchResult,
    MatchStatus,
    Odds,
    Team,
    TotalsOdds,
)
from quantbot.schemas.enums import DEFAULT_NBA_TOTALS_LINE, Sport
from quantbot.schemas.odds import MoneylineOdds, SpreadOdds

UTC = timezone.utc
_SEASON = "2024-2025"
_SEASON_START = datetime(2024, 10, 22, 23, 0, tzinfo=UTC)
_PREDICTION_LEAD = timedelta(hours=2)

# Same lead schedule as football dummy so mid-season as_of sees upcoming quotes.
_ODDS_OFFSETS: tuple[tuple[timedelta, bool], ...] = (
    (timedelta(hours=72), False),
    (timedelta(hours=24), False),
    (timedelta(hours=2), False),
    (timedelta(minutes=10), True),
)

_BOOKS = ("demo_nba", "demo_nba_b", "demo_nba_c")

NBA_TEAMS: list[Team] = [
    Team(team_id="nba_bos", name="Boston Celtics", short_name="BOS"),
    Team(team_id="nba_nyk", name="New York Knicks", short_name="NYK"),
    Team(team_id="nba_mil", name="Milwaukee Bucks", short_name="MIL"),
    Team(team_id="nba_cle", name="Cleveland Cavaliers", short_name="CLE"),
    Team(team_id="nba_den", name="Denver Nuggets", short_name="DEN"),
    Team(team_id="nba_okc", name="Oklahoma City Thunder", short_name="OKC"),
]


def build_nba_matches(*, seed: int = 7) -> list[Match]:
    """Round-robin NBA demo season with finished + upcoming games."""

    rng = Random(seed + 99)
    teams = list(NBA_TEAMS)
    strength = {t.team_id: rng.uniform(-4.0, 4.0) for t in teams}
    matches: list[Match] = []
    week = 0
    pairs = [(a, b) for i, a in enumerate(teams) for b in teams[i + 1 :]]
    # Home-and-away so every franchise builds enough history for quality gates.
    schedule = pairs + [(b, a) for a, b in pairs]
    # Leave the last 8 fixtures upcoming at mid-season.
    finish_before = len(schedule) - 8
    for home, away in schedule:
        kickoff = _SEASON_START + timedelta(days=3 * week)
        week += 1
        match_id = f"nba_{home.team_id}_{away.team_id}_{kickoff.date().isoformat()}"
        finished = week <= finish_before
        result = None
        status = MatchStatus.SCHEDULED
        if finished:
            status = MatchStatus.FINISHED
            home_mu = 112.0 + 2.5 * strength[home.team_id] - 1.5 * strength[away.team_id]
            away_mu = 110.0 + 2.5 * strength[away.team_id] - 1.5 * strength[home.team_id]
            result = MatchResult(
                home_goals=max(80, int(rng.gauss(home_mu, 10))),
                away_goals=max(80, int(rng.gauss(away_mu, 10))),
            )
        matches.append(
            Match(
                match_id=match_id,
                league=League.NBA,
                season=_SEASON,
                kickoff=kickoff,
                prediction_timestamp=kickoff - _PREDICTION_LEAD,
                home_team=home,
                away_team=away,
                status=status,
                result=result,
                sport=Sport.BASKETBALL,
                home_injury_status=InjuryStatus.AVAILABLE,
                away_injury_status=InjuryStatus.AVAILABLE,
            )
        )
    return matches


def build_nba_odds(matches: list[Match], *, seed: int = 7) -> dict[str, list[Odds]]:
    rng = Random(seed + 123)
    out: dict[str, list[Odds]] = {}
    for m in matches:
        edge = rng.uniform(-0.08, 0.08)
        p_home = min(0.85, max(0.15, 0.52 + edge))
        overround = 1.05
        snapshots: list[Odds] = []
        for lead, is_closing in _ODDS_OFFSETS:
            for book in _BOOKS:
                jitter = rng.uniform(-0.03, 0.03)
                ph = min(0.88, max(0.12, p_home * (1.0 + jitter)))
                pa = 1.0 - ph
                ml = MoneylineOdds(
                    match_id=m.match_id,
                    bookmaker=book,
                    timestamp=m.kickoff - lead,
                    home=overround / ph,
                    away=overround / pa,
                    is_closing=is_closing,
                )
                snapshots.append(ml.to_three_way())
        out[m.match_id] = snapshots
    return out


def build_nba_totals(
    matches: list[Match],
    *,
    seed: int = 7,
    line: float = DEFAULT_NBA_TOTALS_LINE,
) -> dict[str, list[TotalsOdds]]:
    rng = Random(seed + 321)
    out: dict[str, list[TotalsOdds]] = {}
    for m in matches:
        p_over = min(0.75, max(0.25, 0.5 + rng.uniform(-0.1, 0.1)))
        overround = 1.04
        snapshots: list[TotalsOdds] = []
        for lead, is_closing in _ODDS_OFFSETS:
            for book in _BOOKS:
                noisy = min(0.8, max(0.2, p_over * (1.0 + rng.uniform(-0.05, 0.05))))
                snapshots.append(
                    TotalsOdds(
                        match_id=m.match_id,
                        bookmaker=book,
                        timestamp=m.kickoff - lead,
                        line=line,
                        over=overround / noisy,
                        under=overround / (1.0 - noisy),
                        is_closing=is_closing,
                    )
                )
        out[m.match_id] = snapshots
    return out


def build_nba_spreads(
    matches: list[Match], *, seed: int = 7
) -> dict[str, list[SpreadOdds]]:
    rng = Random(seed + 444)
    out: dict[str, list[SpreadOdds]] = {}
    for m in matches:
        line = rng.choice([-6.5, -3.5, -1.5, 1.5, 3.5, 5.5])
        p_home = min(0.7, max(0.3, 0.5 + rng.uniform(-0.08, 0.08)))
        overround = 1.04
        snapshots: list[SpreadOdds] = []
        for lead, is_closing in _ODDS_OFFSETS:
            for book in _BOOKS:
                noisy = min(0.75, max(0.25, p_home * (1.0 + rng.uniform(-0.04, 0.04))))
                snapshots.append(
                    SpreadOdds(
                        match_id=m.match_id,
                        bookmaker=book,
                        timestamp=m.kickoff - lead,
                        line=line,
                        home=overround / noisy,
                        away=overround / (1.0 - noisy),
                        is_closing=is_closing,
                    )
                )
        out[m.match_id] = snapshots
    return out
