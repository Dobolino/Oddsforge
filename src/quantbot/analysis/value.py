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
    """Absolute edge in probability points: ``p_model - p_market``."""

    return model_prob - fair_market_prob


def relative_edge(model_prob: float, fair_market_prob: float) -> float:
    """Relative edge: ``(p_model - p_market) / p_market``.

    Distinct from absolute edge (percentage points). A 3 pp gap is not the
    same as a 3% relative edge.
    """

    if fair_market_prob <= 0.0:
        raise ValueError("fair_market_prob must be positive for relative edge")
    return (model_prob - fair_market_prob) / fair_market_prob


def expected_value(model_prob: float, decimal_odds: float) -> float:
    """EV per unit stake: ``(model_prob * decimal_odds) - 1``."""

    return (model_prob * decimal_odds) - 1.0


def edge_pp(edge_value: float) -> float:
    """Convert absolute edge to percentage points (0.063 → 6.3)."""

    return edge_value * 100.0


def format_edge_pp(edge_value: float | None, *, digits: int = 1) -> str:
    """Human label for absolute edge, e.g. ``+6.3 pp``."""

    if edge_value is None:
        return "—"
    return f"{edge_pp(edge_value):+.{digits}f} pp"


def edge_uncertainty_band_pp(
    edge_value: float,
    *,
    model_confidence: float,
    ensemble_agreement: float | None = None,
) -> tuple[float, float]:
    """Heuristic edge band in percentage points (not a formal CI).

    Half-width shrinks as forecast quality and ensemble agreement rise.
    Floor 0.5 pp, ceiling 5.0 pp — enough to stop a single edge figure
    looking more precise than the underlying estimate (Claude review).
    """

    conf = max(0.0, min(1.0, float(model_confidence) / 100.0))
    agree = conf if ensemble_agreement is None else max(0.0, min(1.0, float(ensemble_agreement)))
    half = max(0.5, min(5.0, (1.0 - 0.5 * (conf + agree)) * 8.0))
    mid = edge_pp(edge_value)
    return mid - half, mid + half


def format_edge_band_pp(
    edge_value: float | None,
    *,
    model_confidence: float = 50.0,
    ensemble_agreement: float | None = None,
    digits: int = 1,
) -> str:
    """Human edge with uncertainty band, e.g. ``+6.3 pp (5.1–7.5)``."""

    if edge_value is None:
        return "—"
    low, high = edge_uncertainty_band_pp(
        edge_value,
        model_confidence=model_confidence,
        ensemble_agreement=ensemble_agreement,
    )
    return (
        f"{edge_pp(edge_value):+.{digits}f} pp "
        f"({low:.{digits}f}–{high:.{digits}f})"
    )


def format_ev_pct(ev: float | None, *, digits: int = 1) -> str:
    """Human label for expected return, e.g. ``+21.0%`` (not raw +0.21)."""

    if ev is None:
        return "—"
    return f"{ev * 100.0:+.{digits}f}%"


def format_model_prob(prob: float | None, *, digits: int = 1) -> str:
    """Model probability as a percent, e.g. ``56.3%``."""

    if prob is None:
        return "—"
    return f"{prob * 100.0:.{digits}f}%"


def assert_metrics_consistent(metrics: ValueMetrics, *, tol: float = 1e-9) -> None:
    """Raise AssertionError if stored edge/EV disagree with the formulas."""

    expected_edge = edge(metrics.model_prob, metrics.fair_market_prob)
    expected_ev = expected_value(metrics.model_prob, metrics.decimal_odds)
    if abs(metrics.edge - expected_edge) > tol:
        raise AssertionError(
            f"edge inconsistent: stored={metrics.edge}, "
            f"expected={expected_edge} from p={metrics.model_prob}, "
            f"market={metrics.fair_market_prob}"
        )
    if abs(metrics.expected_value - expected_ev) > tol:
        raise AssertionError(
            f"EV inconsistent: stored={metrics.expected_value}, "
            f"expected={expected_ev} from p={metrics.model_prob}, "
            f"odds={metrics.decimal_odds}"
        )


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
