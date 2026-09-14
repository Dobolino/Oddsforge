"""Value calculation (Layer 3).

Compares model probabilities against fair market probabilities to produce raw
edge and expected value (EV) per outcome. This layer never decides whether to
bet; it only quantifies value. The Decision Engine (Layer 4) applies rules.
"""

from __future__ import annotations

from collections.abc import Sequence

from quantbot.schemas import (
    MarketData,
    MatchOutcome,
    Odds,
    Prediction,
    TotalsMarketData,
    TotalsOdds,
    TotalsSide,
    ValueMetrics,
)

_ORDER: tuple[MatchOutcome, ...] = (MatchOutcome.HOME, MatchOutcome.DRAW, MatchOutcome.AWAY)
_TOTALS: tuple[TotalsSide, ...] = (TotalsSide.OVER, TotalsSide.UNDER)


def edge(model_prob: float, fair_market_prob: float) -> float:
    """Raw edge: model probability minus fair market probability."""

    return model_prob - fair_market_prob


def expected_value(model_prob: float, decimal_odds: float) -> float:
    """EV per unit stake: ``(model_prob * decimal_odds) - 1``."""

    return (model_prob * decimal_odds) - 1.0


def odds_to_dict(odds: Odds) -> dict[MatchOutcome, float]:
    """Decimal odds of an :class:`Odds` snapshot as an outcome map."""

    return odds.decimal_odds()


class ValueCalculator:
    """Builds :class:`ValueMetrics` from a prediction and market."""

    def metrics(
        self,
        prediction: Prediction,
        market: MarketData,
        decimal_odds: dict[MatchOutcome, float],
    ) -> tuple[ValueMetrics, ...]:
        """One :class:`ValueMetrics` per outcome, in HOME/DRAW/AWAY order.

        ``decimal_odds`` are the odds actually available to bet (e.g. best
        odds); the fair probabilities come from ``market`` (margin removed).
        """

        if prediction.match_id != market.match_id:
            raise ValueError(
                f"prediction/market match_id mismatch: "
                f"{prediction.match_id!r} vs {market.match_id!r}"
            )

        model = prediction.probabilities()
        fair = market.fair_probabilities()
        out: list[ValueMetrics] = []
        for outcome in _ORDER:
            mp = model[outcome]
            fp = fair[outcome]
            od = decimal_odds[outcome]
            out.append(
                ValueMetrics(
                    outcome=outcome,
                    model_prob=mp,
                    fair_market_prob=fp,
                    decimal_odds=od,
                    edge=edge(mp, fp),
                    expected_value=expected_value(mp, od),
                )
            )
        return tuple(out)

    def totals_metrics(
        self,
        model_probs: dict[TotalsSide, float],
        market: TotalsMarketData,
        decimal_odds: dict[TotalsSide, float],
    ) -> tuple[ValueMetrics, ...]:
        """Over/Under value metrics for one totals line."""

        fair = market.fair_probabilities()
        out: list[ValueMetrics] = []
        for side in _TOTALS:
            mp = model_probs[side]
            fp = fair[side]
            od = decimal_odds[side]
            out.append(
                ValueMetrics(
                    outcome=side,
                    model_prob=mp,
                    fair_market_prob=fp,
                    decimal_odds=od,
                    edge=edge(mp, fp),
                    expected_value=expected_value(mp, od),
                )
            )
        return tuple(out)

    @staticmethod
    def best_by_ev(metrics: Sequence[ValueMetrics]) -> ValueMetrics:
        return max(metrics, key=lambda m: m.expected_value)

    @staticmethod
    def best_by_edge(metrics: Sequence[ValueMetrics]) -> ValueMetrics:
        return max(metrics, key=lambda m: m.edge)


def totals_metrics_from_prediction(
    prediction: Prediction,
    totals: TotalsOdds,
    market: TotalsMarketData,
) -> tuple[ValueMetrics, ...]:
    """Derive Over/Under metrics from a score matrix and totals quote."""

    if prediction.score_matrix is None:
        raise ValueError("prediction has no score_matrix for totals")
    model_probs = prediction.score_matrix.totals_probabilities(totals.line)
    calc = ValueCalculator()
    return calc.totals_metrics(model_probs, market, totals.decimal_odds())
