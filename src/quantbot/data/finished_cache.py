"""Permanent local archive of finished matches (results never change).

Finished fixtures are written once under the project's ``data/`` directory
(gitignored). Later runs read them from disk and only ask the network for
matches that are still open or missing from the archive.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from quantbot.config import DATA_DIR
from quantbot.logging import get_logger
from quantbot.schemas import League, Match

logger = get_logger(__name__)

# Football-Data status filter: everything that can still change.
_OPEN_STATUSES = "SCHEDULED,TIMED,IN_PLAY,PAUSED,POSTPONED,SUSPENDED,CANCELLED"

_COMPETITION_TO_LEAGUE: dict[str, League] = {
    "PL": League.PREMIER_LEAGUE,
    "BL1": League.BUNDESLIGA,
    "PD": League.LA_LIGA,
    "SA": League.SERIE_A,
    "FL1": League.LIGUE_1,
    "CL": League.CHAMPIONS_LEAGUE,
}


def finished_cache_path(*, base: Path | None = None) -> Path:
    root = Path(base) if base is not None else DATA_DIR / "finished"
    return root / "matches.json"


class MatchFetcher(Protocol):
    """Minimal interface for competition match fetches."""

    def fetch_matches(
        self, competition: str, *, status: str | None = None
    ) -> list[Match]: ...


class FinishedMatchCache:
    """Disk store for finished matches; entries do not expire."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else finished_cache_path()
        self._by_id: dict[str, Match] = {}
        self._last_updated: datetime | None = None
        self._load()

    def _load(self) -> None:
        self._by_id = {}
        self._last_updated = None
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        if raw.get("last_updated"):
            try:
                self._last_updated = datetime.fromisoformat(str(raw["last_updated"]))
            except ValueError:
                self._last_updated = None
        for item in raw.get("matches", []):
            try:
                match = Match.model_validate(item)
            except Exception:  # noqa: BLE001 - skip corrupt rows
                continue
            if match.is_finished:
                self._by_id[match.match_id] = match

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_updated": (self._last_updated or datetime.now(timezone.utc)).isoformat(),
            "matches": [m.model_dump(mode="json") for m in self._by_id.values()],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def last_updated(self) -> datetime | None:
        return self._last_updated

    def get(self, match_id: str) -> Match | None:
        return self._by_id.get(match_id)

    def all_finished(self) -> list[Match]:
        return list(self._by_id.values())

    def for_league(self, league: League) -> list[Match]:
        return [m for m in self._by_id.values() if m.league is league]

    def put_finished(self, matches: Sequence[Match]) -> int:
        """Archive finished matches. Returns how many new ids were stored."""

        added = 0
        changed = False
        for match in matches:
            if not match.is_finished:
                continue
            if match.match_id not in self._by_id:
                added += 1
                changed = True
            elif self._by_id[match.match_id] != match:
                changed = True
            self._by_id[match.match_id] = match
        if changed:
            self._last_updated = datetime.now(timezone.utc)
            self.save()
        return added


class CachingMatchProvider:
    """Wraps a competition match fetcher; finished games live on disk forever.

    After the first successful full fetch, finished matches are answered from
    the archive. Subsequent refreshes only ask the network for open fixtures.
    Looking up a finished match by id never hits the network again.
    """

    def __init__(
        self,
        inner: MatchFetcher | Callable[[str], list[Match]],
        cache: FinishedMatchCache | None = None,
    ) -> None:
        self._inner = inner
        self.cache = cache or FinishedMatchCache()
        self.network_calls = 0

    @property
    def provider_name(self) -> str:
        inner_name = getattr(self._inner, "provider_name", type(self._inner).__name__)
        return f"caching({inner_name})"

    @property
    def last_updated(self) -> datetime | None:
        return self.cache.last_updated

    def _league_for(self, competition: str) -> League | None:
        return _COMPETITION_TO_LEAGUE.get(competition)

    def _call_inner(
        self,
        competition: str,
        *,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        season: int | None = None,
        allow_unfiltered_fallback: bool = True,
    ) -> list[Match]:
        self.network_calls += 1
        if callable(self._inner) and not hasattr(self._inner, "fetch_matches"):
            return list(self._inner(competition))
        kwargs: dict[str, object] = {}
        if status is not None:
            kwargs["status"] = status
        if date_from is not None:
            kwargs["date_from"] = date_from
        if date_to is not None:
            kwargs["date_to"] = date_to
        if season is not None:
            kwargs["season"] = season
        try:
            if kwargs:
                return list(self._inner.fetch_matches(competition, **kwargs))
            return list(self._inner.fetch_matches(competition))
        except TypeError:
            if kwargs and not allow_unfiltered_fallback:
                return []
            return list(self._inner.fetch_matches(competition))

    def fetch_matches(self, competition: str, *, season: int | None = None) -> list[Match]:
        """Merge permanent finished archive with a live competition refresh.

        Cold start (no finished rows for this league): one full network fetch,
        archive finished. Warm start: only request open fixtures (plus recently
        finished via date filter when supported); finished rows come from disk.

        ``season`` is the Football-Data start year (e.g. 2026 for 2026-2027).
        On cold start we also try the previous year and an unfiltered fetch if
        the preferred season returns nothing.
        """

        from datetime import timedelta

        league = self._league_for(competition)
        archived = self.cache.for_league(league) if league is not None else []

        if not archived:
            network: list[Match] = []
            years: list[int | None]
            if season is not None:
                years = [season, season - 1, None]
            else:
                years = [None]
            for year in years:
                network = self._call_inner(competition, season=year)
                if network:
                    break
            self.cache.put_finished([m for m in network if m.is_finished])
            return list(network)

        open_or_all = self._call_inner(
            competition,
            status=_OPEN_STATUSES,
            season=season,
            allow_unfiltered_fallback=True,
        )
        # If a preferred season returned nothing, try without season filter
        # (Football-Data "current") then the previous year.
        if not open_or_all and season is not None:
            open_or_all = self._call_inner(
                competition,
                status=_OPEN_STATUSES,
                allow_unfiltered_fallback=True,
            )
        if not open_or_all and season is not None:
            open_or_all = self._call_inner(
                competition,
                status=_OPEN_STATUSES,
                season=season - 1,
                allow_unfiltered_fallback=True,
            )
        recent_finished: list[Match] = []
        if self.cache.last_updated is not None:
            since = self.cache.last_updated.astimezone(timezone.utc).date()
            date_from = (since - timedelta(days=3)).isoformat()
            recent_finished = self._call_inner(
                competition,
                status="FINISHED",
                date_from=date_from,
                season=season,
                allow_unfiltered_fallback=False,
            )

        newly_finished = [m for m in open_or_all + recent_finished if m.is_finished]
        if newly_finished:
            self.cache.put_finished(newly_finished)

        open_matches = [m for m in open_or_all if not m.is_finished]
        open_ids = {m.match_id for m in open_matches}
        finished = [
            m
            for m in self.cache.for_league(league)  # type: ignore[arg-type]
            if m.match_id not in open_ids
        ]
        return finished + open_matches

    def get_finished_cached(self, match_id: str) -> Match | None:
        """Return a finished match from disk only — never hits the network."""

        match = self.cache.get(match_id)
        if match is not None and match.is_finished:
            return match
        return None

    def ensure_finished(self, competition: str, match_id: str) -> Match | None:
        """Load one finished match: disk first, else one competition fetch."""

        hit = self.get_finished_cached(match_id)
        if hit is not None:
            return hit
        self.fetch_matches(competition)
        return self.get_finished_cached(match_id)
