"""No-bet rules (Layer 4).

Each candidate bet must clear every filter. ``evaluate`` collects all failing
reasons (it does not short-circuit) so the decision output can report every
reason a bet was rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quantbot.schemas import ValueMetrics


@dataclass(frozen=True)
class RuleResult:
    """Outcome of evaluating the no-bet rules for one candidate."""

    passed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NoBetRules:
    """Configurable value/quality filters.

    Args:
        min_ev: Minimum expected value per unit stake.
        min_edge: Minimum raw edge (model prob minus fair market prob).
        max_overround: Reject markets whose bookmaker margin exceeds this.
        min_data_quality: Minimum 0-100 data-quality score.
        min_model_confidence: Minimum 0-100 model-confidence score.
        min_odds / max_odds: Extreme-odds filter (illiquid or unstable prices).
    """

    min_ev: float = 0.0
    min_edge: float = 0.03
    max_overround: float = 0.12
    min_data_quality: float = 60.0
    min_model_confidence: float = 55.0
    min_odds: float = 1.2
    max_odds: float = 15.0

    def evaluate(
        self,
        metric: ValueMetrics,
        overround: float,
        data_quality: float,
        model_confidence: float,
    ) -> RuleResult:
        reasons: list[str] = []

        if metric.expected_value < self.min_ev:
            reasons.append(
                f"ev {metric.expected_value:.4f} below minimum {self.min_ev:.4f}"
            )
        if metric.edge < self.min_edge:
            reasons.append(f"edge {metric.edge:.4f} below minimum {self.min_edge:.4f}")
        if overround > self.max_overround:
            reasons.append(
                f"overround {overround:.4f} above maximum {self.max_overround:.4f}"
            )
        if data_quality < self.min_data_quality:
            reasons.append(
                f"data quality {data_quality:.1f} below minimum {self.min_data_quality:.1f}"
            )
        if model_confidence < self.min_model_confidence:
            reasons.append(
                f"model confidence {model_confidence:.1f} below minimum "
                f"{self.min_model_confidence:.1f}"
            )
        if metric.decimal_odds < self.min_odds:
            reasons.append(
                f"odds {metric.decimal_odds:.2f} below minimum {self.min_odds:.2f}"
            )
        if metric.decimal_odds > self.max_odds:
            reasons.append(
                f"odds {metric.decimal_odds:.2f} above maximum {self.max_odds:.2f}"
            )

        return RuleResult(passed=not reasons, reasons=tuple(reasons))
