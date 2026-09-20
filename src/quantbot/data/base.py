"""Data provider abstraction (Layer 0: ingestion).

Every read is parameterized by ``as_of`` (a timezone-aware instant). The base
class centralizes the temporal-isolation guardrail: no returned object may
carry information created after ``as_of``. Concrete providers implement only
the raw fetch methods and never touch ``as_of`` themselves, so the leakage
guarantee holds for every provider by construction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime

from quantbot.schemas import League, Match, MatchStatus, Odds, SpreadOdds, TotalsOdds


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


class BaseDataProvider(ABC):
    """Abstract interface for match and odds data.

    Subclasses implement the ``_fetch_*`` methods returning the full ground
    truth. Public ``get_*`` methods apply the ``as_of`` temporal filter.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Stable identifier of the provider (used in logging and caching)."""

    # --- Raw fetch hooks (subclass responsibility) ---

    @abstractmethod
    def _fetch_matches(self) -> Sequence[Match]:
        """Return all known matches (ground truth, results included)."""

    @abstractmethod
    def _fetch_odds(self, match_id: str) -> Sequence[Odds]:
        """Return all odds snapshots ever recorded for ``match_id``."""

    def _fetch_totals_odds(self, match_id: str) -> Sequence[TotalsOdds]:
        """Return totals (Over/Under) snapshots for ``match_id`` (optional)."""

        return ()

    def _fetch_spread_odds(self, match_id: str) -> Sequence[SpreadOdds]:
        """Return Asian-handicap snapshots for ``match_id`` (optional)."""

        return ()

    # --- Temporal masking ---

    @staticmethod
    def _mask_match(match: Match, as_of: datetime) -> Match:
        """Strip post-``as_of`` information from a match.

        A final score remains hidden until its publication timestamp. A
        postponed/cancelled status is visible only after its observation time.
        """

        if match.is_finished and match.result_available_at is not None and match.result_available_at <= as_of:
            return match
        if (
            match.status in (MatchStatus.POSTPONED, MatchStatus.CANCELLED)
            and match.status_available_at is not None
            and match.status_available_at <= as_of
        ):
            return match.model_copy(update={"result": None})
        return match.model_copy(update={"status": MatchStatus.SCHEDULED, "result": None})

    # --- Public, as-of-safe queries ---

    def get_matches(
        self,
        league: League,
        season: str,
        as_of: datetime,
    ) -> list[Match]:
        """Return all matches for a league/season with results masked by ``as_of``."""

        _require_aware("as_of", as_of)
        return [
            self._mask_match(m, as_of)
            for m in self._fetch_matches()
            if m.league is league and m.season == season
        ]

    def get_match(self, match_id: str, as_of: datetime) -> Match | None:
        """Return a single match by id, masked by ``as_of``, or ``None``."""

        _require_aware("as_of", as_of)
        for m in self._fetch_matches():
            if m.match_id == match_id:
                return self._mask_match(m, as_of)
        return None

    def get_finished_matches(
        self,
        league: League,
        season: str,
        as_of: datetime,
    ) -> list[Match]:
        """Return only matches already played before ``as_of`` (training data)."""

        return [
            m
            for m in self.get_matches(league, season, as_of)
            if m.result_known_before(as_of)
        ]

    def get_upcoming_matches(
        self,
        league: League,
        season: str,
        as_of: datetime,
    ) -> list[Match]:
        """Return only matches with kickoff after ``as_of`` (prediction targets)."""

        return [
            m
            for m in self.get_matches(league, season, as_of)
            if m.kickoff > as_of and m.status is MatchStatus.SCHEDULED
        ]

    def get_odds(self, match_id: str, as_of: datetime) -> list[Odds]:
        """Return odds snapshots recorded on or before ``as_of``, oldest first."""

        _require_aware("as_of", as_of)
        snapshots = [o for o in self._fetch_odds(match_id) if o.timestamp <= as_of]
        return sorted(snapshots, key=lambda o: o.timestamp)

    def get_latest_odds(self, match_id: str, as_of: datetime) -> Odds | None:
        """Return the most recent odds snapshot on or before ``as_of``."""

        snapshots = self.get_odds(match_id, as_of)
        return snapshots[-1] if snapshots else None

    def get_totals_odds(self, match_id: str, as_of: datetime) -> list[TotalsOdds]:
        """Return totals snapshots recorded on or before ``as_of``, oldest first."""

        _require_aware("as_of", as_of)
        snapshots = [o for o in self._fetch_totals_odds(match_id) if o.timestamp <= as_of]
        return sorted(snapshots, key=lambda o: o.timestamp)

    def get_latest_totals_odds(
        self, match_id: str, as_of: datetime, *, line: float | None = None
    ) -> TotalsOdds | None:
        """Most recent totals quote on or before ``as_of`` (optional line filter)."""

        snapshots = self.get_totals_odds(match_id, as_of)
        if line is not None:
            snapshots = [o for o in snapshots if abs(o.line - line) < 1e-9]
        return snapshots[-1] if snapshots else None

    def get_spread_odds(self, match_id: str, as_of: datetime) -> list[SpreadOdds]:
        """Return spread snapshots recorded on or before ``as_of``, oldest first."""

        _require_aware("as_of", as_of)
        snapshots = [o for o in self._fetch_spread_odds(match_id) if o.timestamp <= as_of]
        return sorted(snapshots, key=lambda o: o.timestamp)

    def get_latest_spread_odds(
        self, match_id: str, as_of: datetime, *, line: float | None = None
    ) -> SpreadOdds | None:
        """Most recent spread quote on or before ``as_of`` (optional line filter)."""

        snapshots = self.get_spread_odds(match_id, as_of)
        if line is not None:
            snapshots = [o for o in snapshots if abs(o.line - line) < 1e-9]
        return snapshots[-1] if snapshots else None

    def get_closing_odds(self, match_id: str) -> Odds | None:
        """Return the closing line for a match.

        Post-settlement data used only for Closing Line Value (CLV) analysis
        after an event has resolved. Never feed this into features.
        """

        closing = [o for o in self._fetch_odds(match_id) if o.is_closing]
        if not closing:
            return None
        return max(closing, key=lambda o: o.timestamp)
