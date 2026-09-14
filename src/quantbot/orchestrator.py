"""High-level orchestration of the full QuantBot pipeline.

Wires provider -> model -> market -> analysis -> decision, and drives the
walk-forward backtester. Keeps leakage guarantees intact: predictions fit the
model only on matches finished before the ``as_of`` instant, and use only odds
recorded on or before it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from quantbot.analysis.calibration import BaseCalibrator
from quantbot.analysis.confidence import DataQualitySignals
from quantbot.analysis.engine import AnalysisEngine, AnalysisResult
from quantbot.backtest.engine import BacktestResult, WalkForwardBacktester
from quantbot.data.base import BaseDataProvider
from quantbot.data.dummy import DummyDataProvider
from quantbot.decision.engine import DecisionEngine
from quantbot.logging import get_logger
from quantbot.markets.odds import MarketEngine
from quantbot.models.base import BaseModel
from quantbot.models.calibrated import CalibratedModel
from quantbot.models.elo import EloModel
from quantbot.schemas import InjuryStatus, League, Match, ValueSignal

logger = get_logger(__name__)

_FAR_FUTURE = datetime(2100, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class SignalReport:
    """A prediction for one match: the match, its signal, and the analysis."""

    match: Match
    signal: ValueSignal
    analysis: AnalysisResult


class QuantBotOrchestrator:
    """Connects pipeline components for prediction and backtesting.

    Args:
        provider: Data source (defaults to the deterministic dummy provider).
        model: Prediction model refit per as_of (defaults to Elo).
        market_engine / analysis_engine / decision_engine: Pipeline stages.
        initial_bankroll: Starting bankroll for backtests.
    """

    def __init__(
        self,
        provider: BaseDataProvider | None = None,
        model: BaseModel | None = None,
        market_engine: MarketEngine | None = None,
        analysis_engine: AnalysisEngine | None = None,
        decision_engine: DecisionEngine | None = None,
        initial_bankroll: float = 1000.0,
        calibrator: BaseCalibrator | None = None,
    ) -> None:
        self.provider = provider or DummyDataProvider()
        base_model = model or EloModel()
        # Optionally wrap the model so calibrated probabilities reach the
        # Value Engine.
        self.model = (
            CalibratedModel(base_model, calibrator) if calibrator is not None else base_model
        )
        self.market_engine = market_engine or MarketEngine()
        self.analysis_engine = analysis_engine or AnalysisEngine()
        self.decision_engine = decision_engine or DecisionEngine()
        self.initial_bankroll = initial_bankroll

    # --- Universe helpers ---

    def universe(self, league: League, season: str) -> list[Match]:
        """All matches (ground truth, results included) for a league/season."""

        return self.provider.get_matches(league, season, _FAR_FUTURE)

    def default_as_of(self, league: League, season: str) -> datetime:
        """A mid-season instant: the prediction time of the median fixture.

        Using the fixture's ``prediction_timestamp`` (kickoff minus lead) means
        that match's entry odds are already available at ``as_of``, so it is
        predictable rather than filtered out for lack of a quote.
        """

        matches = sorted(self.universe(league, season), key=lambda m: m.kickoff)
        if not matches:
            raise ValueError(f"no matches for {league.value} {season}")
        return matches[len(matches) // 2].prediction_timestamp

    # --- Prediction ---

    def predict(
        self,
        league: League,
        season: str,
        as_of: datetime | None = None,
    ) -> list[SignalReport]:
        """Predict all upcoming matches as of ``as_of`` (default mid-season)."""

        as_of = as_of or self.default_as_of(league, season)
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")

        universe = self.universe(league, season)
        self.model.fit_until(universe, as_of)
        counts = self._team_counts(universe, as_of)

        reports: list[SignalReport] = []
        for match in self.provider.get_upcoming_matches(league, season, as_of):
            entry = self.provider.get_latest_odds(match.match_id, as_of)
            if entry is None:
                continue
            prediction = self.model.predict(match)
            market = self.market_engine.to_market_data(entry)
            snapshots = self.provider.get_odds(match.match_id, as_of)
            quality = DataQualitySignals(
                home_matches=counts.get(match.home_team.team_id, 0),
                away_matches=counts.get(match.away_team.team_id, 0),
                n_bookmakers=len({o.bookmaker for o in snapshots}),
                injuries_known=(
                    match.home_injury_status is not InjuryStatus.UNKNOWN
                    and match.away_injury_status is not InjuryStatus.UNKNOWN
                ),
            )
            analysis = self.analysis_engine.analyze(
                prediction, market, entry.decimal_odds(), quality
            )
            signal = self.decision_engine.decide(analysis, market)
            reports.append(SignalReport(match=match, signal=signal, analysis=analysis))

        n_bets = sum(1 for r in reports if r.signal.is_bet)
        logger.info(
            "Predicted %s %s as of %s: %d matches, %d value signals",
            league.value,
            season,
            as_of.isoformat(),
            len(reports),
            n_bets,
        )
        return reports

    # --- Match cards (full transparent analysis per fixture) ---

    def build_match_cards(
        self,
        league: League,
        season: str,
        as_of: datetime | None = None,
    ) -> list:
        """Build a MatchCard per upcoming match: consensus, uncertainty,
        fair odds, divergence, data quality, reliability and explanation."""

        from quantbot.analysis.confidence import DataQualitySignals
        from quantbot.analysis.matchcard import build_match_card
        from quantbot.features import FeatureExtractor
        from quantbot.models import (
            DixonColesModel,
            EloModel,
            EnsembleModel,
            LogisticRegressionModel,
        )

        as_of = as_of or self.default_as_of(league, season)
        universe = self.universe(league, season)

        ensemble = EnsembleModel(
            [EloModel(), DixonColesModel(min_matches=5), LogisticRegressionModel()]
        )
        try:
            ensemble.fit_until(universe, as_of)
        except (ValueError, RuntimeError):
            ensemble = EnsembleModel([EloModel()])
            ensemble.fit_until(universe, as_of)

        extractor = FeatureExtractor()
        counts = self._team_counts(universe, as_of)
        cards = []
        for match in self.provider.get_upcoming_matches(league, season, as_of):
            entry = self.provider.get_latest_odds(match.match_id, as_of)
            if entry is None:
                continue
            sub_preds = {m.name: m.predict(match) for m in ensemble.models}
            ens_pred = ensemble.predict(match)
            market = self.market_engine.to_market_data(entry)
            snapshots = self.provider.get_odds(match.match_id, as_of)
            quality = DataQualitySignals(
                home_matches=counts.get(match.home_team.team_id, 0),
                away_matches=counts.get(match.away_team.team_id, 0),
                n_bookmakers=len({o.bookmaker for o in snapshots}),
                injuries_known=(
                    match.home_injury_status is not InjuryStatus.UNKNOWN
                    and match.away_injury_status is not InjuryStatus.UNKNOWN
                ),
            )
            analysis = self.analysis_engine.analyze(
                ens_pred, market, entry.decimal_odds(), quality,
                sub_predictions=list(sub_preds.values()),
            )
            signal = self.decision_engine.decide(analysis, market)
            cards.append(
                build_match_card(
                    match, sub_preds, ens_pred, market, entry.decimal_odds(),
                    signal, extractor.extract(match, universe), quality,
                )
            )
        logger.info("Built %d match cards for %s %s", len(cards), league.value, season)
        return cards

    # --- Backtest ---

    def run_backtest(self, league: League, season: str) -> BacktestResult:
        backtester = WalkForwardBacktester(
            self.model,
            market_engine=self.market_engine,
            analysis_engine=self.analysis_engine,
            decision_engine=self.decision_engine,
            initial_bankroll=self.initial_bankroll,
        )
        return backtester.run(self.universe(league, season), self.provider)

    # --- Info ---

    def info(self) -> dict[str, object]:
        """System and model specification."""

        return {
            "model": self.model.name,
            "provider": self.provider.provider_name,
            "market_method": self.market_engine.method.value,
            "initial_bankroll": self.initial_bankroll,
            "automated_betting": False,
        }

    @staticmethod
    def _team_counts(matches: Sequence[Match], as_of: datetime) -> dict[str, int]:
        counts: dict[str, int] = {}
        for m in matches:
            if m.is_finished and m.kickoff < as_of:
                counts[m.home_team.team_id] = counts.get(m.home_team.team_id, 0) + 1
                counts[m.away_team.team_id] = counts.get(m.away_team.team_id, 0) + 1
        return counts
