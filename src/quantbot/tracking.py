"""Tracking of weekly suggestions and their results (paper trading log).

Groups a season's matches into rounds (by ISO calendar week), records the
bot's tip per match, and marks it right or wrong once the result is known.
The last rounds can be held out as "upcoming" (results hidden) to show next
week's tips. ``TrackerStore`` persists rounds to a JSON file so a live run can
accumulate history across sessions.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from quantbot.analysis.confidence import DataQualitySignals
from quantbot.analysis.engine import AnalysisEngine
from quantbot.data.base import BaseDataProvider
from quantbot.decision.engine import DecisionEngine
from quantbot.decision.rules import NoBetRules
from quantbot.decision.sizing import KellySizer
from quantbot.logging import get_logger
from quantbot.markets.odds import MarketEngine
from quantbot.models.base import BaseModel, NotFittedError
from quantbot.models.elo import EloModel
from quantbot.schemas import InjuryStatus, League, Match, MatchStatus

logger = get_logger(__name__)

_FAR_FUTURE = datetime(2100, 1, 1, tzinfo=timezone.utc)


def _lenient_decision() -> DecisionEngine:
    """A permissive decision engine so the demo tracker shows tips."""

    return DecisionEngine(
        rules=NoBetRules(
            min_ev=0.02,
            min_edge=0.0,
            max_overround=1.0,
            min_data_quality=0.0,
            min_model_confidence=0.0,
            min_odds=1.01,
            max_odds=100.0,
        ),
        sizer=KellySizer(kelly_fraction=0.25, max_fraction=0.05),
    )


@dataclass(frozen=True)
class TrackerView:
    """Full tracker output: rounds plus overall settled-bet stats."""

    rounds: list[dict]
    total_bets: int
    total_correct: int
    hit_rate: float | None


def _mask(match: Match) -> Match:
    return match.model_copy(update={"status": MatchStatus.SCHEDULED, "result": None})


def build_rounds(
    provider: BaseDataProvider,
    league: League,
    season: str,
    *,
    model: BaseModel | None = None,
    decision_engine: DecisionEngine | None = None,
    hold_out_last: int = 1,
) -> TrackerView:
    """Build weekly rounds of tips with right/wrong marks (leak-free).

    ``hold_out_last`` rounds are shown as upcoming (results hidden), the rest
    as settled history.
    """

    model = model or EloModel()
    decision = decision_engine or _lenient_decision()
    market_engine = MarketEngine()
    analysis_engine = AnalysisEngine()

    universe = sorted(
        (m for m in provider.get_matches(league, season, _FAR_FUTURE) if m.is_finished),
        key=lambda m: m.kickoff,
    )
    if not universe:
        return TrackerView(rounds=[], total_bets=0, total_correct=0, hit_rate=None)

    # Order distinct calendar weeks; the last few are "upcoming".
    week_of = {m.match_id: m.kickoff.isocalendar()[:2] for m in universe}
    weeks = sorted({week_of[m.match_id] for m in universe})
    upcoming_weeks = set(weeks[-hold_out_last:]) if hold_out_last > 0 else set()

    counts: dict[str, int] = {}
    suggestions: dict[str, tuple[Match, object]] = {}
    for match in universe:
        as_of = match.prediction_timestamp
        try:
            model.fit_until(universe, as_of)
            prediction = model.predict(_mask(match))
        except (ValueError, NotFittedError):
            _bump(counts, match)
            continue
        entry = provider.get_latest_odds(match.match_id, as_of)
        if entry is not None:
            market = market_engine.to_market_data(entry)
            quality = DataQualitySignals(
                home_matches=counts.get(match.home_team.team_id, 0),
                away_matches=counts.get(match.away_team.team_id, 0),
                n_bookmakers=len({o.bookmaker for o in provider.get_odds(match.match_id, as_of)}),
                injuries_known=(
                    match.home_injury_status is not InjuryStatus.UNKNOWN
                    and match.away_injury_status is not InjuryStatus.UNKNOWN
                ),
            )
            result = analysis_engine.analyze(prediction, market, entry.decimal_odds(), quality)
            suggestions[match.match_id] = (match, decision.decide(result, market))
        _bump(counts, match)

    # Group tips into rounds.
    rounds: list[dict] = []
    total_bets = total_correct = 0
    for wi, week in enumerate(weeks, start=1):
        upcoming = week in upcoming_weeks
        entries: list[dict] = []
        bets = correct = 0
        for match in universe:
            if week_of[match.match_id] != week or match.match_id not in suggestions:
                continue
            _, signal = suggestions[match.match_id]
            if not signal.is_bet or signal.chosen_outcome is None:
                continue
            name = f"{match.home_team.name} vs {match.away_team.name}"
            actual = None if upcoming else match.result.outcome  # type: ignore[union-attr]
            is_correct = None if upcoming else (signal.chosen_outcome is actual)
            if not upcoming:
                bets += 1
                if is_correct:
                    correct += 1
            entries.append(
                {
                    "match": name,
                    "tip": signal.chosen_outcome.value,
                    "odds": round(signal.decimal_odds, 2) if signal.decimal_odds else None,
                    "stake": round(signal.stake_fraction * 100, 2),
                    "actual": None if actual is None else actual.value,
                    "correct": is_correct,
                    "settled": not upcoming,
                }
            )
        total_bets += bets
        total_correct += correct
        rounds.append(
            {
                "label": f"Woche {wi}",
                "upcoming": upcoming,
                "entries": entries,
                "bets": bets,
                "correct": correct,
                "hit_rate": round(correct / bets * 100, 1) if bets else None,
            }
        )

    hit = round(total_correct / total_bets * 100, 1) if total_bets else None
    logger.info("Tracker: %d rounds, %d settled bets, hit rate %s", len(rounds), total_bets, hit)
    return TrackerView(rounds=rounds, total_bets=total_bets, total_correct=total_correct, hit_rate=hit)


def _bump(counts: dict[str, int], match: Match) -> None:
    counts[match.home_team.team_id] = counts.get(match.home_team.team_id, 0) + 1
    counts[match.away_team.team_id] = counts.get(match.away_team.team_id, 0) + 1


class TrackerStore:
    """Persists tracker rounds to a JSON file (for live accumulation)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def save(self, view: TrackerView) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "total_bets": view.total_bets,
            "total_correct": view.total_correct,
            "hit_rate": view.hit_rate,
            "rounds": view.rounds,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> TrackerView | None:
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return TrackerView(
            rounds=data.get("rounds", []),
            total_bets=data.get("total_bets", 0),
            total_correct=data.get("total_correct", 0),
            hit_rate=data.get("hit_rate"),
        )
