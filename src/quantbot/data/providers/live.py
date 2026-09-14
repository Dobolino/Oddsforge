"""Live data provider: fixtures/results from Football-Data, odds from The Odds API.

Composes the two API clients into a single :class:`BaseDataProvider`, so the
whole QuantBot pipeline (orchestrator, backtester) runs on real current-season
matches. The base class enforces the ``as_of`` leakage guarantee; this class
only supplies the raw ground truth.

The hard part is matching an odds event (identified by team names) to a
Football-Data fixture (identified by numeric ids). Matching is by normalized
team-name pair within the same league. Names are normalized (lowercased,
accent- and suffix-stripped) with a small alias table for known mismatches.
Near-matches (fuzzy) are accepted but flagged as uncertain so the UI can warn.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from quantbot.data.base import BaseDataProvider
from quantbot.data.finished_cache import CachingMatchProvider, FinishedMatchCache
from quantbot.data.providers.football_data import FootballDataProvider
from quantbot.data.providers.leagues import football_data_code, odds_api_key
from quantbot.data.providers.the_odds_api import TheOddsAPIProvider
from quantbot.logging import get_logger
from quantbot.schemas import League, Match, Odds, TotalsOdds

logger = get_logger(__name__)

# Common club-name tokens dropped during normalization.
_DROP_TOKENS = {
    "fc", "cf", "afc", "sc", "ac", "as", "ssc", "rc", "cd", "ud", "fk", "bk",
    "calcio", "club", "de", "the", "1", "1899", "1846", "1900", "1904", "1909",
}

# Known cross-API aliases (normalized Football-Data name -> normalized Odds name).
_ALIASES: dict[str, str] = {
    "brighton hove albion": "brighton and hove albion",
    "wolverhampton wanderers": "wolves",
    "tottenham hotspur": "tottenham",
    "internazionale": "inter milan",
    "borussia monchengladbach": "monchengladbach",
    "paris saint germain": "paris saint germain",
}

# Fuzzy pair score below this is rejected; at/above is accepted but uncertain.
_FUZZY_THRESHOLD = 0.86


def normalize_team(name: str) -> str:
    """Normalize a club name for cross-API matching."""

    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)
    )
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in stripped.lower()).split()]
    kept = [t for t in tokens if t not in _DROP_TOKENS]
    key = " ".join(kept or tokens)
    return _ALIASES.get(key, key)


def _pair_score(a: tuple[str, str], b: tuple[str, str]) -> float:
    """Similarity of two (home, away) normalized name pairs."""

    home = SequenceMatcher(None, a[0], b[0]).ratio()
    away = SequenceMatcher(None, a[1], b[1]).ratio()
    return (home + away) / 2.0


@dataclass(frozen=True)
class NameMatchIssue:
    """One uncertain or failed team-name mapping between the two APIs."""

    kind: str  # "fuzzy" | "unmatched_odds"
    odds_home: str
    odds_away: str
    fixture_home: str | None = None
    fixture_away: str | None = None
    match_id: str | None = None
    score: float | None = None


@dataclass
class NameMatchReport:
    """Summary of how odds events mapped onto fixtures for one league."""

    league: str
    matched_exact: int = 0
    matched_fuzzy: int = 0
    unmatched_odds: int = 0
    issues: list[NameMatchIssue] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        return self.matched_fuzzy > 0 or self.unmatched_odds > 0

    def to_dict(self) -> dict:
        return asdict(self)


class LiveDataProvider(BaseDataProvider):
    """Real-data provider combining Football-Data and The Odds API.

    Args:
        football: Football-Data client (fixtures and results).
        odds: The Odds API client (bookmaker odds).
        leagues: Competitions to load.
        regions: The Odds API bookmaker regions (e.g. "eu,uk").
    """

    def __init__(
        self,
        football: FootballDataProvider | CachingMatchProvider,
        odds: TheOddsAPIProvider,
        leagues: Sequence[League],
        regions: str = "eu,uk",
    ) -> None:
        if not leagues:
            raise ValueError("at least one league is required")
        self._football = football
        self._odds = odds
        self._leagues = list(leagues)
        self._regions = regions
        self._matches_cache: list[Match] | None = None
        self._match_league: dict[str, League] = {}
        self._odds_cache: dict[League, dict[str, list[Odds]]] = {}
        self._totals_cache: dict[League, dict[str, list[TotalsOdds]]] = {}
        self._match_reports: dict[League, NameMatchReport] = {}

    @property
    def provider_name(self) -> str:
        codes = ",".join(lg.value for lg in self._leagues)
        return f"live(football_data+the_odds_api; {codes})"

    @property
    def finished_last_updated(self) -> datetime | None:
        """When finished match results were last written to the local archive."""

        football = self._football
        if isinstance(football, CachingMatchProvider):
            return football.last_updated
        cache = getattr(football, "cache", None)
        return getattr(cache, "last_updated", None)

    def name_match_report(self, league: League | None = None) -> NameMatchReport | None:
        """Return the latest name-matching report (builds odds cache if needed)."""

        target = league or self._leagues[0]
        if target not in self._match_reports:
            self._odds_for_league(target)
        return self._match_reports.get(target)

    # --- Matches / fixtures (Football-Data) ---

    def _fetch_matches(self) -> Sequence[Match]:
        if self._matches_cache is not None:
            return self._matches_cache

        matches: list[Match] = []
        for league in self._leagues:
            try:
                league_matches = self._football.fetch_matches(football_data_code(league))
            except Exception as exc:  # noqa: BLE001 - one league must not break the rest
                logger.warning("Could not load %s fixtures: %s", league.value, exc)
                continue
            for m in league_matches:
                self._match_league[m.match_id] = league
            matches.extend(league_matches)
        self._matches_cache = matches
        logger.info("Loaded %d fixtures across %d leagues", len(matches), len(self._leagues))
        return matches

    # --- Odds (The Odds API), matched to fixtures by team names ---

    def _odds_for_league(self, league: League) -> dict[str, list[Odds]]:
        if league in self._odds_cache:
            return self._odds_cache[league]

        self._fetch_matches()  # ensure fixtures and league index are populated
        index: dict[tuple[str, str], tuple[str, str, str]] = {}
        for m in self._matches_cache or []:
            if m.league is league:
                key = (normalize_team(m.home_team.name), normalize_team(m.away_team.name))
                index[key] = (m.match_id, m.home_team.name, m.away_team.name)

        mapped: dict[str, list[Odds]] = {}
        totals_mapped: dict[str, list[TotalsOdds]] = {}
        report = NameMatchReport(league=league.value)
        try:
            events = self._odds.fetch_events(odds_api_key(league), regions=self._regions)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load %s odds: %s", league.value, exc)
            events = []

        used_fixture_ids: set[str] = set()
        for event in events:
            odds_home_raw = event.get("home_team", "")
            odds_away_raw = event.get("away_team", "")
            key = (normalize_team(odds_home_raw), normalize_team(odds_away_raw))
            hit = index.get(key)
            uncertain = False
            score: float | None = None

            if hit is None:
                # Fuzzy fallback: best unused fixture pair above threshold.
                best_key = None
                best_score = 0.0
                for fixture_key in index:
                    if index[fixture_key][0] in used_fixture_ids:
                        continue
                    s = _pair_score(key, fixture_key)
                    if s > best_score:
                        best_score = s
                        best_key = fixture_key
                if best_key is not None and best_score >= _FUZZY_THRESHOLD:
                    hit = index[best_key]
                    uncertain = True
                    score = best_score
                else:
                    report.unmatched_odds += 1
                    report.issues.append(
                        NameMatchIssue(
                            kind="unmatched_odds",
                            odds_home=str(odds_home_raw),
                            odds_away=str(odds_away_raw),
                            score=best_score if best_key is not None else None,
                        )
                    )
                    continue

            fd_id, fixture_home, fixture_away = hit
            if fd_id in used_fixture_ids:
                report.unmatched_odds += 1
                report.issues.append(
                    NameMatchIssue(
                        kind="unmatched_odds",
                        odds_home=str(odds_home_raw),
                        odds_away=str(odds_away_raw),
                    )
                )
                continue

            odds = [o.model_copy(update={"match_id": fd_id}) for o in self._odds.event_to_odds(event)]
            totals = [
                t.model_copy(update={"match_id": fd_id})
                for t in self._odds.event_to_totals(event)
            ]
            if not odds and not totals:
                continue
            if odds:
                mapped[fd_id] = odds
            if totals:
                totals_mapped[fd_id] = totals
            used_fixture_ids.add(fd_id)
            if uncertain:
                report.matched_fuzzy += 1
                report.issues.append(
                    NameMatchIssue(
                        kind="fuzzy",
                        odds_home=str(odds_home_raw),
                        odds_away=str(odds_away_raw),
                        fixture_home=fixture_home,
                        fixture_away=fixture_away,
                        match_id=fd_id,
                        score=score,
                    )
                )
            else:
                report.matched_exact += 1

        logger.info(
            "%s: matched odds exact=%d fuzzy=%d unmatched=%d / %d events",
            league.value,
            report.matched_exact,
            report.matched_fuzzy,
            report.unmatched_odds,
            len(events),
        )
        self._match_reports[league] = report
        self._odds_cache[league] = mapped
        self._totals_cache[league] = totals_mapped
        return mapped

    def _totals_for_league(self, league: League) -> dict[str, list[TotalsOdds]]:
        if league not in self._totals_cache:
            self._odds_for_league(league)
        return self._totals_cache.get(league, {})

    def _fetch_odds(self, match_id: str) -> Sequence[Odds]:
        league = self._match_league.get(match_id)
        if league is None:
            self._fetch_matches()
            league = self._match_league.get(match_id)
        if league is None:
            return ()
        return self._odds_for_league(league).get(match_id, ())

    def _fetch_totals_odds(self, match_id: str) -> Sequence[TotalsOdds]:
        league = self._match_league.get(match_id)
        if league is None:
            self._fetch_matches()
            league = self._match_league.get(match_id)
        if league is None:
            return ()
        return self._totals_for_league(league).get(match_id, ())


def build_live_provider(
    football_api_key: str,
    the_odds_api_key: str,
    leagues: Sequence[League],
    cache_dir: Path,
    ttl_seconds: float = 1800.0,
    min_interval: float = 1.0,
    regions: str = "eu,uk",
) -> LiveDataProvider:
    """Build a :class:`LiveDataProvider` from API keys and a cache directory."""

    cache_dir = Path(cache_dir)
    football_inner = FootballDataProvider(
        football_api_key,
        cache_dir=cache_dir / "football_data",
        ttl_seconds=ttl_seconds,
        min_interval=min_interval,
    )
    football = CachingMatchProvider(
        football_inner,
        FinishedMatchCache(),
    )
    odds = TheOddsAPIProvider(
        the_odds_api_key,
        cache_dir=cache_dir / "the_odds_api",
        ttl_seconds=ttl_seconds,
        min_interval=min_interval,
    )
    return LiveDataProvider(football, odds, leagues, regions=regions)
