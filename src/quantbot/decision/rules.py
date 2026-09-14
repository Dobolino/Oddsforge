"""No-bet rules (Layer 4).

Each candidate bet must clear every filter. ``evaluate`` collects all failing
reasons (it does not short-circuit) so the decision output can report every
reason a bet was rejected. Reasons are bilingual (de/en) plus a technical
English string for logs and expert mode.

Reason codes use a stable ``NO_BET_*`` / ``VALUE`` vocabulary for audit trails.
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
        min_edge: Minimum absolute edge in probability points
            (``p_model - p_market``). Default 0.03 = 3 percentage points.
        max_overround: Reject markets whose bookmaker margin exceeds this.
        min_data_quality: Minimum 0-100 data-quality score.
        min_model_confidence: Minimum 0-100 forecast-quality score.
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
                    code="NO_BET_LOW_EV",
                    de=(
                        "Die erwartete Rendite ist zu gering "
                        f"(EV {metric.expected_value * 100:.1f}%, "
                        f"Minimum {self.min_ev * 100:.1f}%)."
                    ),
                    en=(
                        "Expected return is too low "
                        f"(EV {metric.expected_value * 100:.1f}%, "
                        f"minimum {self.min_ev * 100:.1f}%)."
                    ),
                    technical=(
                        f"ev {metric.expected_value:.4f} below minimum {self.min_ev:.4f}"
                    ),
                )
            )
        if metric.edge < self.min_edge:
            reasons.append(
                Reason(
                    code="NO_BET_LOW_EDGE",
                    de=(
                        "Der Vorteil gegenüber dem Markt ist zu gering "
                        f"({metric.edge_pp:+.1f} pp, Minimum "
                        f"{self.min_edge * 100:.1f} Prozentpunkte)."
                    ),
                    en=(
                        "The edge versus the market is too small "
                        f"({metric.edge_pp:+.1f} pp, minimum "
                        f"{self.min_edge * 100:.1f} percentage points)."
                    ),
                    technical=(
                        f"edge {metric.edge:.4f} below minimum {self.min_edge:.4f} "
                        f"({self.min_edge * 100:.1f} percentage points)"
                    ),
                )
            )
        if overround > self.max_overround:
            reasons.append(
                Reason(
                    code="NO_BET_HIGH_OVERROUND",
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
                    code="NO_BET_LOW_DATA_QUALITY",
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
                    code="NO_BET_LOW_FORECAST_QUALITY",
                    de="Die Prognosequalität ist hier zu niedrig.",
                    en="Forecast quality is too low here.",
                    technical=(
                        f"forecast quality {model_confidence:.1f} below minimum "
                        f"{self.min_model_confidence:.1f}"
                    ),
                )
            )
        if metric.decimal_odds < self.min_odds:
            reasons.append(
                Reason(
                    code="NO_BET_ODDS_TOO_LOW",
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
                    code="NO_BET_ODDS_TOO_HIGH",
                    de="Die Quote ist ungewöhnlich hoch oder unsicher.",
                    en="The odds are unusually high or unstable.",
                    technical=(
                        f"odds {metric.decimal_odds:.2f} above maximum {self.max_odds:.2f}"
                    ),
                )
            )

        return RuleResult(passed=not reasons, reasons=tuple(reasons))


KELLY_ZERO = Reason(
    code="NO_BET_KELLY_ZERO",
    de="Der sinnvolle theoretische Einsatz wäre praktisch null.",
    en="A sensible theoretical stake would be practically zero.",
    technical="kelly stake rounds to zero",
)


def value_reason(outcome: str, edge: float, ev: float, stake: float) -> Reason:
    """Acceptance reason when a value tip is issued."""

    return Reason(
        code="VALUE",
        de=(
            "Das Modell sieht hier einen Vorteil gegenüber dem Markt "
            f"({edge * 100:+.1f} pp, erwartete Rendite {ev * 100:+.1f}%)."
        ),
        en=(
            "The model sees an advantage versus the market here "
            f"({edge * 100:+.1f} pp, expected return {ev * 100:+.1f}%)."
        ),
        technical=(
            f"value on {outcome}: edge {edge:.4f} ({edge * 100:.1f} pp), "
            f"ev {ev:.4f} ({ev * 100:.1f}%), stake {stake:.4f} of bankroll"
        ),
    )
