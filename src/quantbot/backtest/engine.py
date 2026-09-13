"""Walk-forward backtester (Layer 5).

Strictly chronological. For each target match the model is re-fit on matches
finished before that match's ``prediction_timestamp`` (leak-free), the entry
market is built only from odds recorded on or before that instant, and the
closing line is used exclusively for CLV after settlement. There is no random
train/test split.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quantbot.analysis.confidence import DataQualitySignals
from quantbot.analysis.engine import AnalysisEngine
from quantbot.backtest.execution import ExecutionSimulator, SettledBet
from quantbot.backtest.metrics import BacktestMetrics, compute_metrics
from quantbot.data.base import BaseDataProvider
from quantbot.decision.engine import DecisionEngine
from quantbot.markets.odds import MarketEngine
from quantbot.models.base import BaseModel, NotFittedError
from quantbot.schemas import InjuryStatus, Match, MatchStatus, ValueSignal


@dataclass(frozen=True)
class BacktestResult:
    """Outcome of a walk-forward run."""

    initial_bankroll: float
    final_bankroll: float
    bankroll_curve: tuple[float, ...]
    settled_bets: tuple[SettledBet, ...]
    signals: tuple[ValueSignal, ...]
    n_evaluated: int
    n_bets: int
    n_no_bet: int
    metrics: BacktestMetrics


class WalkForwardBacktester:
    """Runs a leak-free walk-forward simulation over a match universe.

    Args:
        model: A model refit at every step via ``fit_until``.
        market_engine / analysis_engine / decision_engine: Pipeline stages.
        initial_bankroll: Starting bankroll for the paper simulation.
    """

    def __init__(
        self,
        model: BaseModel,
        market_engine: MarketEngine | None = None,
        analysis_engine: AnalysisEngine | None = None,
        decision_engine: DecisionEngine | None = None,
        initial_bankroll: float = 1000.0,
    ) -> None:
        if initial_bankroll <= 0.0:
            raise ValueError("initial_bankroll must be positive")
        self.model = model
        self.market_engine = market_engine or MarketEngine()
        self.analysis_engine = analysis_engine or AnalysisEngine()
        self.decision_engine = decision_engine or DecisionEngine()
        self.executor = ExecutionSimulator()
        self.initial_bankroll = initial_bankroll

    def run(self, matches: Sequence[Match], provider: BaseDataProvider) -> BacktestResult:
        universe = sorted(
            (m for m in matches if m.is_finished and m.result is not None),
            key=lambda m: m.kickoff,
        )

        bankroll = self.initial_bankroll
        curve: list[float] = [bankroll]
        settled: list[SettledBet] = []
        signals: list[ValueSignal] = []
        team_counts: dict[str, int] = {}
        n_evaluated = 0
        n_bets = 0

        for match in universe:
            as_of = match.prediction_timestamp

            # Leak-free training slice and entry market.
            try:
                self.model.fit_until(universe, as_of)
                masked = self._mask(match)
                prediction = self.model.predict(masked)
            except (ValueError, NotFittedError):
                self._bump_counts(team_counts, match)
                continue

            entry = provider.get_latest_odds(match.match_id, as_of)
            if entry is None:
                self._bump_counts(team_counts, match)
                continue

            n_evaluated += 1
            market = self.market_engine.to_market_data(entry)
            decimal_odds = entry.decimal_odds()
            signals_snapshot = provider.get_odds(match.match_id, as_of)
            n_books = len({o.bookmaker for o in signals_snapshot})

            quality = DataQualitySignals(
                home_matches=team_counts.get(match.home_team.team_id, 0),
                away_matches=team_counts.get(match.away_team.team_id, 0),
                n_bookmakers=n_books,
                injuries_known=(
                    match.home_injury_status is not InjuryStatus.UNKNOWN
                    and match.away_injury_status is not InjuryStatus.UNKNOWN
                ),
                liquidity=None,
            )
            analysis = self.analysis_engine.analyze(prediction, market, decimal_odds, quality)
            signal = self.decision_engine.decide(analysis, market)
            signals.append(signal)

            if signal.is_bet and signal.chosen_outcome is not None:
                stake = signal.stake_fraction * bankroll
                closing = provider.get_closing_odds(match.match_id)
                closing_odds = (
                    closing.decimal_odds()[signal.chosen_outcome] if closing is not None else None
                )
                assert match.result is not None
                bet = self.executor.settle(
                    match_id=match.match_id,
                    outcome=signal.chosen_outcome,
                    stake=stake,
                    entry_odds=decimal_odds[signal.chosen_outcome],
                    actual_outcome=match.result.outcome,
                    model_prob=prediction.probability_of(signal.chosen_outcome),
                    closing_odds=closing_odds,
                )
                bankroll += bet.pnl
                settled.append(bet)
                curve.append(bankroll)
                n_bets += 1

            self._bump_counts(team_counts, match)

        metrics = compute_metrics(settled, curve, self.initial_bankroll)
        return BacktestResult(
            initial_bankroll=self.initial_bankroll,
            final_bankroll=bankroll,
            bankroll_curve=tuple(curve),
            settled_bets=tuple(settled),
            signals=tuple(signals),
            n_evaluated=n_evaluated,
            n_bets=n_bets,
            n_no_bet=len(signals) - n_bets,
            metrics=metrics,
        )

    @staticmethod
    def _mask(match: Match) -> Match:
        """Strip the result before prediction, so no model can peek at it."""

        return match.model_copy(update={"status": MatchStatus.SCHEDULED, "result": None})

    @staticmethod
    def _bump_counts(counts: dict[str, int], match: Match) -> None:
        counts[match.home_team.team_id] = counts.get(match.home_team.team_id, 0) + 1
        counts[match.away_team.team_id] = counts.get(match.away_team.team_id, 0) + 1
