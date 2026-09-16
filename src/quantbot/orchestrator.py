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
from quantbot.config import get_settings
from quantbot.data.base import BaseDataProvider
from quantbot.data.dummy import DummyDataProvider
from quantbot.decision.engine import DecisionEngine
from quantbot.decision.rules import NoBetRules
from quantbot.decision.sizing import KellySizer
from quantbot.logging import get_logger
from quantbot.markets.odds import MarketEngine
from quantbot.models.base import BaseModel, NotFittedError
from quantbot.models.calibrated import CalibratedModel
from quantbot.models.elo import EloModel
from quantbot.schemas import InjuryStatus, League, Match, SignalType, ValueSignal

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
        min_team_matches: int = 0,
    ) -> None:
        # Below this many finished matches for either team, issue no tip: a
        # goals model fit on a handful of games per team is overconfident
        # (extreme probabilities), so early-season data is not trustworthy.
        self.min_team_matches = max(0, int(min_team_matches))
        self.provider = provider or DummyDataProvider()
        base_model = model or EloModel()
        # Optionally wrap the model so calibrated probabilities reach the
        # Value Engine.
        self.model = (
            CalibratedModel(base_model, calibrator) if calibrator is not None else base_model
        )
        settings = get_settings()
        self.market_engine = market_engine or MarketEngine(method=settings.margin_method)
        self.analysis_engine = analysis_engine or AnalysisEngine()
        if decision_engine is None:
            decision_engine = DecisionEngine(
                rules=NoBetRules(
                    min_edge=settings.min_edge,
                    min_data_quality=settings.min_data_quality,
                    min_model_confidence=settings.min_model_confidence,
                ),
                sizer=KellySizer(
                    kelly_fraction=settings.kelly_fraction,
                    max_fraction=0.05,
                ),
            )
        self.decision_engine = decision_engine
        self.initial_bankroll = initial_bankroll
        self._totals_margin_method = settings.totals_margin_method

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

    def suggested_as_of(self, league: League, season: str, *, live: bool) -> datetime:
        """Default prediction clock for the UI.

        Live mode jumps to "now" so upcoming fixtures are the next real games.
        Demo mode keeps the mid-season instant so historical dummy data still
        has upcoming matches to score.
        """

        if live:
            return datetime.now(timezone.utc)
        return self.default_as_of(league, season)

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

        from quantbot.models.basketball import BasketballModel
        from quantbot.schemas.enums import DEFAULT_NBA_TOTALS_LINE, Sport, sport_for_league

        universe = self.universe(league, season)
        use_basketball = sport_for_league(league) is Sport.BASKETBALL
        model = BasketballModel() if use_basketball else self.model
        try:
            model.fit_until(universe, as_of)
        except (ValueError, NotFittedError) as exc:
            # Not enough finished matches to fit at all (very early season).
            logger.warning("Model not fitted for %s %s: %s", league.value, season, exc)
            return []
        counts = self._team_counts(universe, as_of)

        reports: list[SignalReport] = []
        for match in self.provider.get_upcoming_matches(league, season, as_of):
            entry = self.provider.get_latest_odds(match.match_id, as_of)
            if entry is None:
                continue
            prediction = model.predict(match)
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
            if min(quality.home_matches, quality.away_matches) < self.min_team_matches:
                # Too little history for this pairing: no reliable tip.
                reports.append(
                    SignalReport(
                        match=match,
                        signal=self._insufficient_data_signal(market, analysis),
                        analysis=analysis,
                    )
                )
                continue
            signal = self.decision_engine.decide(analysis, market)
            if use_basketball and isinstance(model, BasketballModel):
                signal = self._maybe_prefer_nba_totals(
                    match=match,
                    as_of=as_of,
                    model=model,
                    data_quality=analysis.data_quality,
                    model_confidence=analysis.model_confidence,
                    signal_ml=signal,
                    quality=quality,
                )
            else:
                signal = self._maybe_prefer_totals(
                    match=match,
                    as_of=as_of,
                    prediction=prediction,
                    data_quality=analysis.data_quality,
                    model_confidence=analysis.model_confidence,
                    signal_1x2=signal,
                    quality=quality,
                )
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

    def _insufficient_data_signal(
        self, market, analysis: AnalysisResult
    ) -> ValueSignal:
        """A NO_BET signal used when a team has too little match history."""

        return ValueSignal(
            match_id=analysis.match_id,
            timestamp=market.timestamp,
            signal=SignalType.NO_BET,
            model_confidence=analysis.model_confidence,
            data_quality=analysis.data_quality,
            stake_fraction=0.0,
            rationale="insufficient team match history",
            rationale_de="Zu wenig Spiele pro Team für einen verlässlichen Tipp.",
            rationale_en="Too few matches per team for a reliable tip.",
            metrics=analysis.metrics,
        )

    def _maybe_prefer_totals(
        self,
        *,
        match: Match,
        as_of: datetime,
        prediction,
        data_quality: float,
        model_confidence: float,
        signal_1x2: ValueSignal,
        quality: DataQualitySignals | None = None,
    ) -> ValueSignal:
        """If a totals tip clears the same rules with better EV, prefer it."""

        from quantbot.analysis.value import totals_metrics_from_prediction
        from quantbot.markets.totals import TotalsMarketEngine
        from quantbot.schemas.enums import DEFAULT_TOTALS_LINE

        if prediction.score_matrix is None:
            return signal_1x2
        totals_entry = self.provider.get_latest_totals_odds(
            match.match_id, as_of, line=DEFAULT_TOTALS_LINE
        )
        if totals_entry is None:
            return signal_1x2
        totals_engine = TotalsMarketEngine(method=self._totals_margin_method)
        totals_market = totals_engine.to_market_data(totals_entry)
        try:
            totals_metrics = totals_metrics_from_prediction(
                prediction, totals_entry, totals_market
            )
        except ValueError:
            return signal_1x2
        # Same market-shrinkage discipline as 1X2: without it every goals
        # market looks like value on thin early-season data.
        totals_metrics = self.analysis_engine.shrink_totals_metrics(totals_metrics, quality)
        totals_signal = self.decision_engine.decide_totals(
            match_id=match.match_id,
            market=totals_market,
            metrics=totals_metrics,
            data_quality=data_quality,
            model_confidence=model_confidence,
        )
        if not totals_signal.is_bet:
            return signal_1x2
        if not signal_1x2.is_bet:
            return totals_signal
        if (totals_signal.expected_value or 0.0) > (signal_1x2.expected_value or 0.0):
            return totals_signal
        return signal_1x2

    def _maybe_prefer_nba_totals(
        self,
        *,
        match: Match,
        as_of: datetime,
        model,
        data_quality: float,
        model_confidence: float,
        signal_ml: ValueSignal,
        quality: DataQualitySignals | None = None,
    ) -> ValueSignal:
        """Prefer NBA totals when EV beats the moneyline tip."""

        from quantbot.analysis.value import expected_value as ev_fn
        from quantbot.markets.totals import TotalsMarketEngine
        from quantbot.schemas import TotalsSide, ValueMetrics
        from quantbot.schemas.enums import DEFAULT_NBA_TOTALS_LINE

        totals_entry = self.provider.get_latest_totals_odds(
            match.match_id, as_of, line=DEFAULT_NBA_TOTALS_LINE
        )
        if totals_entry is None:
            return signal_ml
        p_over, p_under = model.totals_probabilities(match, line=DEFAULT_NBA_TOTALS_LINE)
        totals_engine = TotalsMarketEngine(method=self._totals_margin_method)
        totals_market = totals_engine.to_market_data(totals_entry)
        fair = totals_market.fair_probabilities()
        metrics = (
            ValueMetrics(
                outcome=TotalsSide.OVER,
                model_prob=p_over,
                fair_market_prob=fair[TotalsSide.OVER],
                decimal_odds=totals_entry.over,
                edge=p_over - fair[TotalsSide.OVER],
                expected_value=ev_fn(p_over, totals_entry.over),
            ),
            ValueMetrics(
                outcome=TotalsSide.UNDER,
                model_prob=p_under,
                fair_market_prob=fair[TotalsSide.UNDER],
                decimal_odds=totals_entry.under,
                edge=p_under - fair[TotalsSide.UNDER],
                expected_value=ev_fn(p_under, totals_entry.under),
            ),
        )
        metrics = self.analysis_engine.shrink_totals_metrics(metrics, quality)
        totals_signal = self.decision_engine.decide_totals(
            match_id=match.match_id,
            market=totals_market,
            metrics=metrics,
            data_quality=data_quality,
            model_confidence=model_confidence,
        )
        if not totals_signal.is_bet:
            return signal_ml
        if not signal_ml.is_bet:
            return totals_signal
        if (totals_signal.expected_value or 0.0) > (signal_ml.expected_value or 0.0):
            return totals_signal
        return signal_ml

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
