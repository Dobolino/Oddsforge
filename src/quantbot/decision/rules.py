"""No-bet rules (Layer 4).

Each candidate bet must clear every filter. ``evaluate`` collects all failing
reasons (it does not short-circuit) so the decision output can report every
reason a bet was rejected. Reasons are bilingual (de/en) plus a technical
English string for logs and expert mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Reason:
    """One rejection or acceptance reason in plain language + technical form."""

    code: str
    de: str
    en: str
    technical: str

    def text(self, lang: str = "en") -> str:
        return self.de if lang.startswith("de") else self.en


@dataclass(frozen=True)
class RuleResult:
    """Outcome of evaluating the no-bet rules for one candidate."""

    passed: bool
    reasons: tuple[Reason, ...] = field(default_factory=tuple)

    def join(self, lang: str = "en", *, technical: bool = False) -> str:
        if technical:
            return "; ".join(r.technical for r in self.reasons)
        return "; ".join(r.text(lang) for r in self.reasons)


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
        metric,  # ValueMetrics — kept untyped here to avoid circular imports in hints
        overround: float,
        data_quality: float,
        model_confidence: float,
    ) -> RuleResult:
        from quantbot.schemas import ValueMetrics

        if not isinstance(metric, ValueMetrics):
            raise TypeError("metric must be a ValueMetrics instance")

        reasons: list[Reason] = []

        if metric.expected_value < self.min_ev:
            reasons.append(
                Reason(
                    code="low_ev",
                    de="Der erwartete Gewinn ist zu gering.",
                    en="The expected value is too low.",
                    technical=(
                        f"ev {metric.expected_value:.4f} below minimum {self.min_ev:.4f}"
                    ),
                )
            )
        if metric.edge < self.min_edge:
            reasons.append(
                Reason(
                    code="low_edge",
                    de="Der Vorteil gegenüber dem Markt ist zu gering.",
                    en="The edge versus the market is too small.",
                    technical=(
                        f"edge {metric.edge:.4f} below minimum {self.min_edge:.4f}"
                    ),
                )
            )
        if overround > self.max_overround:
            reasons.append(
                Reason(
                    code="high_overround",
                    de="Die Buchmacher-Marge ist zu hoch.",
                    en="The bookmaker margin is too high.",
                    technical=(
                        f"overround {overround:.4f} above maximum {self.max_overround:.4f}"
                    ),
                )
            )
        if data_quality < self.min_data_quality:
            reasons.append(
                Reason(
                    code="low_data_quality",
                    de="Zu wenig verlässliche Daten für dieses Spiel.",
                    en="Not enough reliable data for this match.",
                    technical=(
                        f"data quality {data_quality:.1f} below minimum "
                        f"{self.min_data_quality:.1f}"
                    ),
                )
            )
        if model_confidence < self.min_model_confidence:
            reasons.append(
                Reason(
                    code="low_model_confidence",
                    de="Das Modell ist sich hier zu unsicher.",
                    en="The model is too uncertain here.",
                    technical=(
                        f"model confidence {model_confidence:.1f} below minimum "
                        f"{self.min_model_confidence:.1f}"
                    ),
                )
            )
        if metric.decimal_odds < self.min_odds:
            reasons.append(
                Reason(
                    code="odds_too_low",
                    de="Die Quote ist ungewöhnlich niedrig.",
                    en="The odds are unusually low.",
                    technical=(
                        f"odds {metric.decimal_odds:.2f} below minimum {self.min_odds:.2f}"
                    ),
                )
            )
        if metric.decimal_odds > self.max_odds:
            reasons.append(
                Reason(
                    code="odds_too_high",
                    de="Die Quote ist ungewöhnlich hoch oder unsicher.",
                    en="The odds are unusually high or unstable.",
                    technical=(
                        f"odds {metric.decimal_odds:.2f} above maximum {self.max_odds:.2f}"
                    ),
                )
            )

        return RuleResult(passed=not reasons, reasons=tuple(reasons))


KELLY_ZERO = Reason(
    code="kelly_zero",
    de="Der sinnvolle Einsatz wäre praktisch null.",
    en="A sensible stake would be practically zero.",
    technical="kelly stake rounds to zero",
)


def value_reason(outcome: str, edge: float, ev: float, stake: float) -> Reason:
    """Acceptance reason when a value tip is issued."""

    return Reason(
        code="value",
        de="Das Modell sieht hier einen Vorteil gegenüber dem Markt.",
        en="The model sees an advantage versus the market here.",
        technical=(
            f"value on {outcome}: edge {edge:.4f}, ev {ev:.4f}, "
            f"stake {stake:.4f} of bankroll"
        ),
    )
