"""Tracking of weekly suggestions and their results (paper trading log).

Groups a season's matches into rounds (by ISO calendar week), records the
bot's tip per match, and marks it right or wrong once the result is known.
The last rounds can be held out as "upcoming" (results hidden) to show next
week's tips.

``TipHistoryStore`` persists individual tips to JSON under the project's
``data/`` directory (gitignored) so history survives restarts and accumulates
over time. Demo and live modes use separate files and are never mixed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from quantbot.analysis.confidence import DataQualitySignals
from quantbot.analysis.engine import AnalysisEngine
from quantbot.config import DATA_DIR
from quantbot.data.base import BaseDataProvider
from quantbot.decision.engine import DecisionEngine
from quantbot.decision.rules import NoBetRules
from quantbot.decision.sizing import KellySizer
from quantbot.logging import get_logger
from quantbot.markets.odds import MarketEngine
from quantbot.models.base import BaseModel, NotFittedError
from quantbot.models.elo import EloModel
from quantbot.schemas import InjuryStatus, League, Match, MatchOutcome, MatchStatus

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


@dataclass(frozen=True)
class TipRecord:
    """One tip locked at prediction time (before kickoff).

    Optional audit fields form a lightweight prediction snapshot so later
    reviews can reconstruct probabilities, market view, and reason codes.
    """

    tip_id: str
    match_id: str
    kickoff: str
    league: str
    home: str
    away: str
    tip: str
    odds: float | None
    model_prob: float | None
    as_of: str
    mode: str
    settled: bool = False
    actual: str | None = None
    correct: bool | None = None
    # Snapshot / audit trail (optional for backward-compatible JSON loads)
    fair_market_prob: float | None = None
    edge: float | None = None
    expected_value: float | None = None
    model_confidence: float | None = None
    data_quality: float | None = None
    reason_codes: tuple[str, ...] = ()
    model_name: str | None = None
    odds_timestamp: str | None = None
    decision: str | None = None

    @property
    def match_label(self) -> str:
        return f"{self.home} vs {self.away}"


def tracker_path(mode: str, *, base: Path | None = None) -> Path:
    """JSON path for tip history; demo and live stay separate."""

    root = Path(base) if base is not None else DATA_DIR / "tracker"
    safe = "live" if mode == "live" else "demo"
    return root / f"{safe}.json"


def _mask(match: Match) -> Match:
    return match.model_copy(update={"status": MatchStatus.SCHEDULED, "result": None})


def _model_prob_for_signal(signal) -> float | None:  # type: ignore[no-untyped-def]
    if not signal.is_bet or signal.chosen_outcome is None:
        return None
    for metric in signal.metrics:
        if metric.outcome is signal.chosen_outcome:
            return float(metric.model_prob)
    return None


def _fair_prob_for_signal(signal) -> float | None:  # type: ignore[no-untyped-def]
    if signal.chosen_outcome is None:
        return None
    for metric in signal.metrics:
        if metric.outcome is signal.chosen_outcome:
            return float(metric.fair_market_prob)
    return None


def tip_record_from_match_signal(
    match: Match,
    signal,
    *,
    mode: str,
    as_of: datetime,
    model_name: str | None = None,
    odds_timestamp: datetime | None = None,
) -> TipRecord | None:
    """Build a TipRecord from a leak-free prediction; None if NO_BET."""

    if not signal.is_bet or signal.chosen_outcome is None:
        return None
    tip_id = f"{match.match_id}::{as_of.isoformat()}"
    tip_value = getattr(signal, "tip_label", None) or signal.chosen_outcome.value
    codes = tuple(getattr(signal, "reason_codes", ()) or ())
    return TipRecord(
        tip_id=tip_id,
        match_id=match.match_id,
        kickoff=match.kickoff.isoformat(),
        league=match.league.value,
        home=match.home_team.name,
        away=match.away_team.name,
        tip=tip_value,
        odds=round(float(signal.decimal_odds), 2) if signal.decimal_odds else None,
        model_prob=(
            None
            if _model_prob_for_signal(signal) is None
            else round(float(_model_prob_for_signal(signal)), 4)
        ),
        as_of=as_of.isoformat(),
        mode="live" if mode == "live" else "demo",
        settled=False,
        actual=None,
        correct=None,
        fair_market_prob=(
            None
            if _fair_prob_for_signal(signal) is None
            else round(float(_fair_prob_for_signal(signal)), 4)
        ),
        edge=None if signal.edge is None else round(float(signal.edge), 6),
        expected_value=(
            None if signal.expected_value is None else round(float(signal.expected_value), 6)
        ),
        model_confidence=round(float(signal.model_confidence), 1),
        data_quality=round(float(signal.data_quality), 1),
        reason_codes=codes,
        model_name=model_name,
        odds_timestamp=odds_timestamp.isoformat() if odds_timestamp is not None else None,
        decision=signal.signal.value,
    )


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
            tip_value = getattr(signal, "tip_label", None) or signal.chosen_outcome.value
            if upcoming:
                actual_label = None
                is_correct = None
            elif signal.totals_line is not None and match.result is not None:
                from quantbot.markets.totals import actual_totals_label

                actual_label = actual_totals_label(
                    match.result.total_goals, signal.totals_line
                )
                is_correct = tip_value == actual_label
            else:
                actual = match.result.outcome  # type: ignore[union-attr]
                actual_label = actual.value
                is_correct = signal.chosen_outcome is actual
            if not upcoming:
                bets += 1
                if is_correct:
                    correct += 1
            entries.append(
                {
                    "match": name,
                    "tip": tip_value,
                    "odds": round(signal.decimal_odds, 2) if signal.decimal_odds else None,
                    "stake": round(signal.stake_fraction * 100, 2),
                    "model_prob": _model_prob_for_signal(signal),
                    "as_of": match.prediction_timestamp.isoformat(),
                    "league": match.league.value,
                    "kickoff": match.kickoff.isoformat(),
                    "actual": actual_label,
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


def collect_tip_records(
    provider: BaseDataProvider,
    league: League,
    season: str,
    *,
    mode: str,
    model: BaseModel | None = None,
    decision_engine: DecisionEngine | None = None,
    hold_out_last: int = 1,
) -> list[TipRecord]:
    """Produce tip records for a league/season without mutating any store."""

    model = model or EloModel()
    decision = decision_engine or _lenient_decision()
    market_engine = MarketEngine()
    analysis_engine = AnalysisEngine()
    universe = sorted(
        (m for m in provider.get_matches(league, season, _FAR_FUTURE) if m.is_finished),
        key=lambda m: m.kickoff,
    )
    week_of = {m.match_id: m.kickoff.isocalendar()[:2] for m in universe}
    weeks = sorted({week_of[m.match_id] for m in universe})
    upcoming_weeks = set(weeks[-hold_out_last:]) if hold_out_last > 0 else set()

    counts: dict[str, int] = {}
    records: list[TipRecord] = []
    for match in universe:
        as_of = match.prediction_timestamp
        try:
            model.fit_until(universe, as_of)
            prediction = model.predict(_mask(match))
        except (ValueError, NotFittedError):
            _bump(counts, match)
            continue
        entry = provider.get_latest_odds(match.match_id, as_of)
        if entry is None:
            _bump(counts, match)
            continue
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
        analysis = analysis_engine.analyze(prediction, market, entry.decimal_odds(), quality)
        signal = decision.decide(analysis, market)
        record = tip_record_from_match_signal(
            match,
            signal,
            mode=mode,
            as_of=as_of,
            model_name=getattr(model, "name", None) or prediction.model_name,
            odds_timestamp=entry.timestamp,
        )
        if record is not None:
            upcoming = week_of[match.match_id] in upcoming_weeks
            if not upcoming and match.result is not None:
                tip_value = record.tip
                if signal.totals_line is not None:
                    from quantbot.markets.totals import actual_totals_label

                    actual_label = actual_totals_label(
                        match.result.total_goals, signal.totals_line
                    )
                    is_correct = tip_value == actual_label
                else:
                    actual_label = match.result.outcome.value
                    is_correct = signal.chosen_outcome is match.result.outcome
                record = TipRecord(
                    **{
                        **asdict(record),
                        "settled": True,
                        "actual": actual_label,
                        "correct": is_correct,
                    }
                )
            records.append(record)
        _bump(counts, match)
    return records


def _bump(counts: dict[str, int], match: Match) -> None:
    counts[match.home_team.team_id] = counts.get(match.home_team.team_id, 0) + 1
    counts[match.away_team.team_id] = counts.get(match.away_team.team_id, 0) + 1


class TrackerStore:
    """Persists tracker rounds to a JSON file (legacy round-blob API)."""

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


class TipHistoryStore:
    """Append-only tip ledger with settle-on-result updates.

    Existing tip_ids are never overwritten. Settlement only fills
    ``actual`` / ``correct`` / ``settled`` on pending rows.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._tips: list[TipRecord] = []
        self._by_id: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        self._tips = []
        self._by_id = {}
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        fields = set(TipRecord.__dataclass_fields__)
        for raw in data.get("tips", []):
            payload = {k: v for k, v in raw.items() if k in fields}
            if "reason_codes" in payload and isinstance(payload["reason_codes"], list):
                payload["reason_codes"] = tuple(payload["reason_codes"])
            tip = TipRecord(**payload)
            self._by_id[tip.tip_id] = len(self._tips)
            self._tips.append(tip)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"tips": [asdict(t) for t in self._tips]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def all_tips(self) -> list[TipRecord]:
        return list(self._tips)

    def append_new(self, records: Sequence[TipRecord]) -> int:
        """Add tips whose tip_id is not yet known. Returns how many were added."""

        added = 0
        for record in records:
            if record.tip_id in self._by_id:
                continue
            self._by_id[record.tip_id] = len(self._tips)
            self._tips.append(record)
            added += 1
        if added:
            self.save()
        return added

    def settle(self, match_id: str, actual: MatchOutcome | str) -> int:
        """Mark pending 1X2 tips for ``match_id`` using the real outcome.

        Totals tips (``over_*`` / ``under_*``) are left untouched here; use
        :meth:`settle_from_matches` which routes by tip shape.
        """

        actual_value = actual.value if isinstance(actual, MatchOutcome) else str(actual)
        updated = 0
        for i, tip in enumerate(self._tips):
            if tip.match_id != match_id or tip.settled:
                continue
            if tip.tip.startswith("over_") or tip.tip.startswith("under_"):
                continue
            is_correct = tip.tip == actual_value
            self._tips[i] = TipRecord(
                **{
                    **asdict(tip),
                    "settled": True,
                    "actual": actual_value,
                    "correct": is_correct,
                }
            )
            updated += 1
        if updated:
            self.save()
        return updated

    def settle_totals(self, match_id: str, actual: str) -> int:
        """Mark pending totals tips for ``match_id`` (e.g. ``over_2.5``)."""

        updated = 0
        for i, tip in enumerate(self._tips):
            if tip.match_id != match_id or tip.settled:
                continue
            if not (tip.tip.startswith("over_") or tip.tip.startswith("under_")):
                continue
            is_correct = tip.tip == actual
            self._tips[i] = TipRecord(
                **{
                    **asdict(tip),
                    "settled": True,
                    "actual": actual,
                    "correct": is_correct,
                }
            )
            updated += 1
        if updated:
            self.save()
        return updated

    def settle_from_matches(self, matches: Sequence[Match]) -> int:
        """Settle any pending tips whose matches now have a finished result."""

        from quantbot.markets.totals import actual_totals_label
        from quantbot.schemas.enums import DEFAULT_TOTALS_LINE

        n = 0
        for match in matches:
            if match.result is None or not match.is_finished:
                continue
            n += self.settle(match.match_id, match.result.outcome)
            # Settle each pending totals tip with its own line.
            pending_totals = [
                t
                for t in self._tips
                if t.match_id == match.match_id
                and not t.settled
                and (t.tip.startswith("over_") or t.tip.startswith("under_"))
            ]
            for tip in pending_totals:
                try:
                    line = float(tip.tip.split("_", 1)[1])
                except ValueError:
                    line = DEFAULT_TOTALS_LINE
                actual = actual_totals_label(match.result.total_goals, line)
                n += self.settle_totals(match.match_id, actual)
        return n

    def hit_rate(self) -> float | None:
        settled = [t for t in self._tips if t.settled]
        if not settled:
            return None
        correct = sum(1 for t in settled if t.correct)
        return round(correct / len(settled) * 100, 1)

    def totals(self) -> tuple[int, int]:
        settled = [t for t in self._tips if t.settled]
        correct = sum(1 for t in settled if t.correct)
        return len(settled), correct

    def to_view(self) -> TrackerView:
        """Group stored tips into week rounds for the dashboard."""

        if not self._tips:
            return TrackerView(rounds=[], total_bets=0, total_correct=0, hit_rate=None)

        def week_key(tip: TipRecord) -> tuple[int, int]:
            return datetime.fromisoformat(tip.kickoff).isocalendar()[:2]

        weeks = sorted({week_key(t) for t in self._tips})
        rounds: list[dict] = []
        total_bets = total_correct = 0
        for wi, week in enumerate(weeks, start=1):
            entries = []
            bets = correct = 0
            for tip in self._tips:
                if week_key(tip) != week:
                    continue
                if tip.settled:
                    bets += 1
                    if tip.correct:
                        correct += 1
                entries.append(
                    {
                        "match": tip.match_label,
                        "tip": tip.tip,
                        "odds": tip.odds,
                        "stake": None,
                        "model_prob": tip.model_prob,
                        "as_of": tip.as_of,
                        "league": tip.league,
                        "kickoff": tip.kickoff,
                        "actual": tip.actual,
                        "correct": tip.correct,
                        "settled": tip.settled,
                    }
                )
            upcoming = bets == 0 and any(not e["settled"] for e in entries)
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
        return TrackerView(
            rounds=rounds,
            total_bets=total_bets,
            total_correct=total_correct,
            hit_rate=hit,
        )


def sync_tip_history(
    store: TipHistoryStore,
    provider: BaseDataProvider,
    leagues: Sequence[League],
    season: str,
    *,
    mode: str,
) -> TrackerView:
    """Append new tips and settle finished ones, then return a view for the UI."""

    new_records: list[TipRecord] = []
    all_matches: list[Match] = []
    for league in leagues:
        new_records.extend(collect_tip_records(provider, league, season, mode=mode))
        all_matches.extend(provider.get_matches(league, season, _FAR_FUTURE))
    store.append_new(new_records)
    store.settle_from_matches(all_matches)
    return store.to_view()
