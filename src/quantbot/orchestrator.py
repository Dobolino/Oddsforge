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
from quantbot.analysis.validation import ValidationArtifact, policy_from_artifact
from quantbot.backtest.engine import BacktestResult, WalkForwardBacktester
from quantbot.config import get_settings
from quantbot.data.base import BaseDataProvider
from quantbot.data.dummy import DummyDataProvider
from quantbot.data.snapshot_repo import DataMode, SnapshotRepository
from quantbot.decision.engine import DecisionEngine
from quantbot.decision.policy import DecisionPolicy, policy_for_mode
from quantbot.logging import get_logger
from quantbot.markets.odds import MarketEngine
from quantbot.models.base import BaseModel, NotFittedError
from quantbot.models.calibrated import CalibratedModel
from quantbot.models.elo import EloModel
from quantbot.schemas import InjuryStatus, League, Match, ValueSignal

logger = get_logger(__name__)

_FAR_FUTURE = datetime(2100, 1, 1, tzinfo=timezone.utc)


def previous_season(season: str) -> str | None:
    """Return the season label one year earlier, or ``None`` if unparseable.

    Handles the ``"YYYY-YYYY"`` labels the providers emit (e.g. ``"2026-2027"``
    -> ``"2025-2026"``) and a bare ``"YYYY"``.
    """

    text = str(season).strip()
    if "-" in text:
        start, _, end = text.partition("-")
        if start.isdigit() and end.isdigit():
            return f"{int(start) - 1}-{int(end) - 1}"
        return None
    if text.isdigit():
        return str(int(text) - 1)
    return None


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
        decision_policy: Versioned policy (defaults from ``live`` flag).
        live: When no policy/engine is passed, select live vs demo profile.
        validation_artifact: Optional empirical release record; only ``VALID``
            live artifacts unlock Kelly sizing.
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
        min_team_matches: int | None = None,
        fit_prior_seasons: int = 0,
        *,
        decision_policy: DecisionPolicy | None = None,
        live: bool = False,
        snapshot_repo: SnapshotRepository | None = None,
        persist_snapshots: bool | None = None,
        validation_artifact: ValidationArtifact | None = None,
    ) -> None:
        policy = decision_policy or policy_for_mode(live=live)
        if min_team_matches is not None:
            from dataclasses import replace

            policy = replace(policy, min_team_matches=max(0, int(min_team_matches)))
        # Explicit artifact only — never invent VALID from missing evidence.
        # Optional auto-load of a previously saved live artifact (same scope
        # matching is caller's responsibility via load_latest_artifact).
        if validation_artifact is None and live:
            from quantbot.analysis.validation import load_latest_artifact

            try:
                validation_artifact = load_latest_artifact(scope="live_default")
            except Exception:  # noqa: BLE001
                validation_artifact = None
        if validation_artifact is not None:
            policy = policy_from_artifact(validation_artifact, base=policy)
        self.policy = policy
        self.validation_artifact = validation_artifact
        self.min_team_matches = policy.min_team_matches
        # Fit on the current season plus this many prior seasons, so early in a
        # season the model has a backbone instead of learning from a handful of
        # games. Time-decay weighting (on the model) fades the older games.
        self.fit_prior_seasons = max(0, int(fit_prior_seasons))
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
            decision_engine = DecisionEngine.from_policy(policy)
        self.decision_engine = decision_engine
        self.initial_bankroll = initial_bankroll
        self._totals_margin_method = settings.totals_margin_method
        self._live = bool(live)
        self._data_mode = DataMode.LIVE_REPLAY if live else DataMode.DEMO
        self.snapshot_repo = snapshot_repo
        # Live runs archive every pulled quote into SQLite (local "historical
        # odds") so free API credits build a reusable archive over time.
        self.persist_snapshots = bool(live) if persist_snapshots is None else bool(persist_snapshots)
        if self.persist_snapshots and self.snapshot_repo is None:
            self.snapshot_repo = SnapshotRepository()
        self._last_run_manifest = None

    @property
    def last_run_manifest(self):
        return self._last_run_manifest

    def build_run_manifest(
        self,
        *,
        as_of: datetime,
        league: League | None = None,
        season: str | None = None,
        snapshot_ids: tuple[str, ...] = (),
        persist: bool = True,
    ):
        """Freeze provenance for the current prediction batch (P2)."""

        from quantbot.analysis.validation import pipeline_hash, policy_content_hash
        from quantbot.runs import build_run_manifest, config_content_hash, save_manifest

        settings = get_settings()
        model = self.model
        model_name = getattr(model, "name", model.__class__.__name__)
        model_version = str(getattr(model, "version", "") or "")
        calib_name = None
        if hasattr(model, "calibrator") and model.calibrator is not None:
            calib_name = model.calibrator.__class__.__name__
        artifact = self.validation_artifact
        manifest = build_run_manifest(
            as_of=as_of,
            data_mode=self._data_mode.value if hasattr(self._data_mode, "value") else str(self._data_mode),
            model_name=model_name,
            model_version=model_version,
            policy_version=self.policy.version,
            policy_hash=policy_content_hash(self.policy),
            pipeline_hash=pipeline_hash(
                model_name=model_name,
                model_version=model_version,
                shrinkage_mode=self.analysis_engine.shrinkage_mode.value,
                calibrator=calib_name,
            ),
            config_hash=config_content_hash(
                {
                    "kelly_fraction": settings.kelly_fraction,
                    "min_edge": settings.min_edge,
                    "enable_ah_experimental": settings.enable_ah_experimental,
                    "margin_method": settings.margin_method.value,
                }
            ),
            snapshot_ids=snapshot_ids,
            validation_artifact_id=None if artifact is None else artifact.artifact_id,
            validation_status=(
                None
                if artifact is None
                else artifact.effective_status().value
            ),
            calibrator_name=calib_name,
            league=None if league is None else league.value,
            season=season,
        )
        if persist:
            save_manifest(manifest)
        self._last_run_manifest = manifest
        return manifest

    # --- Universe helpers ---

    def universe(self, league: League, season: str) -> list[Match]:
        """All matches (ground truth, results included) for a league/season."""

        return self.provider.get_matches(league, season, _FAR_FUTURE)

    def fit_universe(self, league: League, season: str) -> list[Match]:
        """Fitting data: the season plus ``fit_prior_seasons`` earlier seasons.

        Prior-season matches provide a backbone early in a season. They are all
        in the past, so temporal isolation is unaffected (the model still fits
        only on matches finished before ``as_of``). Missing prior seasons (demo
        data, promoted teams) simply contribute nothing.
        """

        matches = list(self.universe(league, season))
        current = season
        for _ in range(self.fit_prior_seasons):
            current = previous_season(current)
            if current is None:
                break
            matches.extend(self.provider.get_matches(league, current, _FAR_FUTURE))
        return matches

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

        universe = self.fit_universe(league, season)
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
            from datetime import timedelta

            from quantbot.markets.integrity import DEFAULT_MAX_QUOTE_AGE, check_1x2_odds

            integrity = check_1x2_odds(
                entry,
                as_of=as_of,
                kickoff=match.kickoff if self._live else None,
                max_age=DEFAULT_MAX_QUOTE_AGE if self._live else timedelta(days=3650),
            )
            prediction = model.predict(match)
            snapshots = self.provider.get_odds(match.match_id, as_of)
            if self.persist_snapshots and self.snapshot_repo is not None:
                provider_name = getattr(self.provider, "provider_name", "unknown")
                endpoint = f"provider://{provider_name}/odds"
                fetched_at = datetime.now(timezone.utc)
                try:
                    for quote in snapshots or (entry,):
                        self.snapshot_repo.put_odds(
                            quote,
                            provider=provider_name,
                            endpoint=endpoint,
                            data_mode=self._data_mode,
                            fetched_at=fetched_at,
                            available_at=quote.timestamp,
                        )
                    for totals in self.provider.get_totals_odds(match.match_id, as_of):
                        self.snapshot_repo.put_totals(
                            totals,
                            provider=provider_name,
                            endpoint=f"provider://{provider_name}/totals",
                            data_mode=self._data_mode,
                            fetched_at=fetched_at,
                            available_at=totals.timestamp,
                        )
                except Exception:  # noqa: BLE001 — persistence must not break predict
                    logger.warning("Failed to persist odds snapshot for %s", match.match_id)
            quality = DataQualitySignals(
                home_matches=counts.get(match.home_team.team_id, 0),
                away_matches=counts.get(match.away_team.team_id, 0),
                n_bookmakers=len({o.bookmaker for o in snapshots}),
                injuries_known=(
                    match.home_injury_status is not InjuryStatus.UNKNOWN
                    and match.away_injury_status is not InjuryStatus.UNKNOWN
                ),
            )
            if integrity:
                # Do not release EV/Kelly from a tainted book. Keep a minimal
                # analysis shell so callers still receive a SignalReport.
                from math import isfinite

                from quantbot.analysis.confidence import ConfidenceLevel
                from quantbot.analysis.engine import AnalysisResult
                from quantbot.schemas import MatchOutcome, ValueMetrics

                safe_odds = (
                    float(entry.home)
                    if isfinite(entry.home) and entry.home > 1.0
                    else 1.01
                )
                p_home = float(max(0.0, min(1.0, prediction.home)))
                placeholder = ValueMetrics(
                    outcome=MatchOutcome.HOME,
                    model_prob=p_home,
                    fair_market_prob=0.5,
                    decimal_odds=safe_odds,
                    edge=p_home - 0.5,
                    expected_value=p_home * safe_odds - 1.0,
                )
                analysis = AnalysisResult(
                    match_id=match.match_id,
                    metrics=(placeholder,),
                    best_ev=placeholder,
                    data_quality=0.0,
                    model_confidence=0.0,
                    confidence_level=ConfidenceLevel.LOW,
                    ensemble_agreement=0.0,
                    home_matches=quality.home_matches,
                    away_matches=quality.away_matches,
                )
                signal = self.decision_engine.invalid_data_signal(
                    match_id=match.match_id,
                    timestamp=entry.timestamp,
                    reasons=integrity,
                    metrics=(),
                )
                reports.append(SignalReport(match=match, signal=signal, analysis=analysis))
                continue

            market = self.market_engine.to_market_data(entry)
            analysis = self.analysis_engine.analyze(
                prediction, market, entry.decimal_odds(), quality
            )
            signal = self.decision_engine.decide(
                analysis,
                market,
                home_matches=quality.home_matches,
                away_matches=quality.away_matches,
            )
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
                if get_settings().enable_ah_experimental:
                    signal = self._maybe_prefer_ah(
                        match=match,
                        as_of=as_of,
                        prediction=prediction,
                        data_quality=analysis.data_quality,
                        model_confidence=analysis.model_confidence,
                        signal_current=signal,
                        quality=quality,
                    )
            reports.append(SignalReport(match=match, signal=signal, analysis=analysis))

        n_bets = sum(1 for r in reports if r.signal.is_bet)
        self.build_run_manifest(as_of=as_of, league=league, season=season, persist=True)
        logger.info(
            "Predicted %s %s as of %s: %d matches, %d value signals (run %s)",
            league.value,
            season,
            as_of.isoformat(),
            len(reports),
            n_bets,
            None if self._last_run_manifest is None else self._last_run_manifest.run_id[:8],
        )
        return reports

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
            home_matches=None if quality is None else quality.home_matches,
            away_matches=None if quality is None else quality.away_matches,
        )
        if not totals_signal.is_bet:
            return signal_1x2
        if not signal_1x2.is_bet:
            return totals_signal
        if (totals_signal.expected_value or 0.0) > (signal_1x2.expected_value or 0.0):
            return totals_signal
        return signal_1x2

    def _maybe_prefer_ah(
        self,
        *,
        match: Match,
        as_of: datetime,
        prediction,
        data_quality: float,
        model_confidence: float,
        signal_current: ValueSignal,
        quality: DataQualitySignals | None = None,
    ) -> ValueSignal:
        """Experimental AH: prefer when EV beats current tip; sizing stays gated."""

        from quantbot.analysis.value import ah_metrics_from_prediction
        from quantbot.markets.margin import remove_margin
        from quantbot.schemas.enums import DEFAULT_HANDICAP_LINE

        if prediction.score_matrix is None:
            return signal_current
        spread = self.provider.get_latest_spread(
            match.match_id, as_of, line=DEFAULT_HANDICAP_LINE
        )
        if spread is None:
            return signal_current
        try:
            fair = remove_margin([spread.home, spread.away], "power")
        except Exception:  # noqa: BLE001
            return signal_current
        try:
            metrics = ah_metrics_from_prediction(
                prediction,
                spread,
                fair_home=float(fair[0]),
                fair_away=float(fair[1]),
            )
        except ValueError:
            return signal_current
        overround = 1.0 / spread.home + 1.0 / spread.away - 1.0
        ah_signal = self.decision_engine.decide_ah(
            match_id=match.match_id,
            timestamp=spread.timestamp,
            metrics=metrics,
            handicap_line=float(spread.line),
            data_quality=data_quality,
            model_confidence=model_confidence,
            overround=overround,
            home_matches=None if quality is None else quality.home_matches,
            away_matches=None if quality is None else quality.away_matches,
            ah_sizing_released=False,  # requires dedicated AH ValidationArtifact
        )
        if not ah_signal.is_bet:
            return signal_current
        if not signal_current.is_bet:
            return ah_signal
        if (ah_signal.expected_value or 0.0) > (signal_current.expected_value or 0.0):
            return ah_signal
        return signal_current

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
            home_matches=None if quality is None else quality.home_matches,
            away_matches=None if quality is None else quality.away_matches,
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
                    signal, extractor.extract(match, universe, as_of=as_of), quality,
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
            if m.result_known_before(as_of):
                counts[m.home_team.team_id] = counts.get(m.home_team.team_id, 0) + 1
                counts[m.away_team.team_id] = counts.get(m.away_team.team_id, 0) + 1
        return counts
