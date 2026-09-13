"""Leak-free feature extraction for matches (Layer 1 input).

Every feature for a target match is computed only from matches finished
strictly before that match's ``prediction_timestamp``. Two entry points:

* :meth:`FeatureExtractor.extract` -- features for one match given a history.
* :meth:`FeatureExtractor.build_training_set` -- an efficient chronological
  walk that snapshots pre-match state as features, so training data is
  leak-free by construction.

Labels use the shared outcome order: home=0, draw=1, away=2.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from quantbot.schemas import Match, MatchOutcome, MatchResult

if TYPE_CHECKING:
    from quantbot.models.elo import EloModel

# Label encoding, aligned with OUTCOME_ORDER.
OUTCOME_TO_LABEL: dict[MatchOutcome, int] = {
    MatchOutcome.HOME: 0,
    MatchOutcome.DRAW: 1,
    MatchOutcome.AWAY: 2,
}
LABEL_TO_OUTCOME: dict[int, MatchOutcome] = {v: k for k, v in OUTCOME_TO_LABEL.items()}

FEATURE_NAMES: tuple[str, ...] = (
    "elo_diff",
    "home_form_points",
    "away_form_points",
    "home_goals_for_avg",
    "home_goals_against_avg",
    "away_goals_for_avg",
    "away_goals_against_avg",
    "home_xg_for_avg",
    "home_xg_against_avg",
    "away_xg_for_avg",
    "away_xg_against_avg",
    "home_rest_days",
    "away_rest_days",
    "home_matches_played",
    "away_matches_played",
)

_DEFAULT_REST_DAYS = 7.0


@dataclass
class _TeamRecord:
    """Rolling per-team state used while walking the history."""

    goals_for: list[int] = field(default_factory=list)
    goals_against: list[int] = field(default_factory=list)
    xg_for: list[float] = field(default_factory=list)
    xg_against: list[float] = field(default_factory=list)
    points: list[int] = field(default_factory=list)
    last_kickoff: object | None = None  # datetime | None
    matches_played: int = 0


def _avg(values: Sequence[float], window: int) -> float:
    recent = values[-window:]
    return sum(recent) / len(recent) if recent else 0.0


class FeatureExtractor:
    """Builds numeric feature vectors from match history.

    Args:
        form_window: Number of recent matches used for rolling averages.
        elo_factory: Callable producing a fresh ``EloModel`` for Elo diffs.
    """

    def __init__(
        self,
        form_window: int = 5,
        elo_factory: Callable[[], EloModel] | None = None,
    ) -> None:
        self.form_window = form_window
        self._elo_factory = elo_factory

    def _make_elo(self) -> EloModel:
        if self._elo_factory is not None:
            return self._elo_factory()
        # Lazy import breaks the features <-> models import cycle.
        from quantbot.models.elo import EloModel

        return EloModel()

    # --- Single-match extraction ---

    def extract(self, match: Match, history: Sequence[Match]) -> dict[str, float]:
        """Return the feature vector for ``match`` using only prior matches."""

        as_of = match.prediction_timestamp
        past = sorted(
            (m for m in history if m.is_finished and m.kickoff < as_of),
            key=lambda m: m.kickoff,
        )

        elo = self._make_elo()
        if past:
            elo.fit(past)

        records: dict[str, _TeamRecord] = {}
        for m in past:
            self._absorb(records, m)

        return self._assemble(match, elo, records)

    # --- Bulk training-set construction (chronological, leak-free) ---

    def build_training_set(
        self, matches: Sequence[Match]
    ) -> tuple[list[dict[str, float]], list[int]]:
        """Return (feature dicts, labels) built from a chronological walk.

        Each match's features reflect only the state before it was played.
        Matches without enough history still produce a row (zero-filled),
        which keeps early-season fixtures in the training set.
        """

        finished = sorted(
            (m for m in matches if m.is_finished and m.result is not None),
            key=lambda m: m.kickoff,
        )
        elo = self._make_elo()
        records: dict[str, _TeamRecord] = {}
        features: list[dict[str, float]] = []
        labels: list[int] = []

        for m in finished:
            features.append(self._assemble(m, elo, records))
            assert m.result is not None
            labels.append(OUTCOME_TO_LABEL[m.result.outcome])
            # Update state AFTER snapshotting features.
            elo._update(m)  # noqa: SLF001 - intentional incremental update
            self._absorb(records, m)

        return features, labels

    # --- Internals ---

    @staticmethod
    def _xg(goals: int, xg: float | None) -> float:
        """Expected goals, falling back to actual goals when xG is absent."""

        return float(goals) if xg is None else float(xg)

    def _absorb(self, records: dict[str, _TeamRecord], match: Match) -> None:
        result: MatchResult | None = match.result
        if result is None:
            return
        home_id = match.home_team.team_id
        away_id = match.away_team.team_id
        home = records.setdefault(home_id, _TeamRecord())
        away = records.setdefault(away_id, _TeamRecord())

        home.goals_for.append(result.home_goals)
        home.goals_against.append(result.away_goals)
        away.goals_for.append(result.away_goals)
        away.goals_against.append(result.home_goals)

        home.xg_for.append(self._xg(result.home_goals, result.home_xg))
        home.xg_against.append(self._xg(result.away_goals, result.away_xg))
        away.xg_for.append(self._xg(result.away_goals, result.away_xg))
        away.xg_against.append(self._xg(result.home_goals, result.home_xg))

        outcome = result.outcome
        home.points.append(3 if outcome is MatchOutcome.HOME else 1 if outcome is MatchOutcome.DRAW else 0)
        away.points.append(3 if outcome is MatchOutcome.AWAY else 1 if outcome is MatchOutcome.DRAW else 0)

        home.last_kickoff = match.kickoff
        away.last_kickoff = match.kickoff
        home.matches_played += 1
        away.matches_played += 1

    def _rest_days(self, record: _TeamRecord | None, match: Match) -> float:
        if record is None or record.last_kickoff is None:
            return _DEFAULT_REST_DAYS
        delta = match.kickoff - record.last_kickoff  # type: ignore[operator]
        return delta.total_seconds() / 86400.0

    def _assemble(
        self,
        match: Match,
        elo: EloModel,
        records: dict[str, _TeamRecord],
    ) -> dict[str, float]:
        home_id = match.home_team.team_id
        away_id = match.away_team.team_id
        home = records.get(home_id)
        away = records.get(away_id)
        w = self.form_window

        return {
            "elo_diff": elo.rating(home_id) - elo.rating(away_id),
            "home_form_points": _avg(home.points, w) if home else 0.0,
            "away_form_points": _avg(away.points, w) if away else 0.0,
            "home_goals_for_avg": _avg(home.goals_for, w) if home else 0.0,
            "home_goals_against_avg": _avg(home.goals_against, w) if home else 0.0,
            "away_goals_for_avg": _avg(away.goals_for, w) if away else 0.0,
            "away_goals_against_avg": _avg(away.goals_against, w) if away else 0.0,
            "home_xg_for_avg": _avg(home.xg_for, w) if home else 0.0,
            "home_xg_against_avg": _avg(home.xg_against, w) if home else 0.0,
            "away_xg_for_avg": _avg(away.xg_for, w) if away else 0.0,
            "away_xg_against_avg": _avg(away.xg_against, w) if away else 0.0,
            "home_rest_days": self._rest_days(home, match),
            "away_rest_days": self._rest_days(away, match),
            "home_matches_played": float(home.matches_played) if home else 0.0,
            "away_matches_played": float(away.matches_played) if away else 0.0,
        }

    def to_vector(self, features: dict[str, float]) -> list[float]:
        """Order a feature dict into the canonical FEATURE_NAMES sequence."""

        return [features[name] for name in FEATURE_NAMES]
