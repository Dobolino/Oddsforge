"""Value and decision schemas (Layer 3 and Layer 4).

``ValueMetrics`` holds the raw comparison between model and market. The
:class:`ValueSignal` is the Decision Engine's final, auditable output: what to
do, why, and a theoretical (never executed) stake.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from quantbot.schemas.base import QuantBotModel
from quantbot.schemas.enums import MatchOutcome, SignalType


class ValueMetrics(QuantBotModel):
    """Per-outcome value comparison of model vs. fair market probability.

    Attributes:
        model_prob: Model probability for the outcome.
        fair_market_prob: Margin-free market probability for the outcome.
        decimal_odds: Best available decimal odds for the outcome.
        edge: model_prob - fair_market_prob.
        expected_value: (model_prob * decimal_odds) - 1.
    """

    outcome: MatchOutcome
    model_prob: float = Field(ge=0.0, le=1.0)
    fair_market_prob: float = Field(gt=0.0, lt=1.0)
    decimal_odds: float = Field(gt=1.0)
    edge: float
    expected_value: float

    @model_validator(mode="after")
    def _validate_derived(self) -> ValueMetrics:
        expected_edge = self.model_prob - self.fair_market_prob
        if abs(self.edge - expected_edge) > 1e-9:
            raise ValueError(
                f"edge must equal model_prob - fair_market_prob "
                f"({expected_edge}), got {self.edge}"
            )
        expected_ev = (self.model_prob * self.decimal_odds) - 1.0
        if abs(self.expected_value - expected_ev) > 1e-9:
            raise ValueError(
                f"expected_value must equal (model_prob * decimal_odds) - 1 "
                f"({expected_ev}), got {self.expected_value}"
            )
        return self


class ValueSignal(QuantBotModel):
    """Final decision-engine output for one match.

    Guardrail: ``stake_fraction`` is a theoretical fractional-Kelly suggestion.
    QuantBot v1 never executes it. A ``NO_BET`` signal always has zero stake
    and no chosen outcome.

    Attributes:
        data_quality: 0-100 completeness/reliability score of the inputs.
        model_confidence: 0-100 model self-assessed confidence.
        stake_fraction: Fraction of bankroll (theoretical), 0.0 for NO_BET.
    """

    match_id: str = Field(min_length=1)
    timestamp: datetime
    signal: SignalType
    chosen_outcome: MatchOutcome | None = None
    edge: float | None = None
    expected_value: float | None = None
    decimal_odds: float | None = Field(default=None, gt=1.0)
    model_confidence: float = Field(ge=0.0, le=100.0)
    data_quality: float = Field(ge=0.0, le=100.0)
    stake_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = Field(
        default="",
        description="Technical English decision reason (logs / expert mode).",
    )
    rationale_de: str = Field(default="", description="Plain-language German reason.")
    rationale_en: str = Field(default="", description="Plain-language English reason.")
    metrics: tuple[ValueMetrics, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate(self) -> ValueSignal:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

        if self.signal is SignalType.NO_BET:
            if self.chosen_outcome is not None:
                raise ValueError("NO_BET must not set a chosen_outcome")
            if self.stake_fraction != 0.0:
                raise ValueError("NO_BET must have stake_fraction 0.0")
        else:
            if self.chosen_outcome is None:
                raise ValueError(f"{self.signal.value} requires a chosen_outcome")
            expected = _SIGNAL_TO_OUTCOME[self.signal]
            if self.chosen_outcome is not expected:
                raise ValueError(
                    f"{self.signal.value} must choose {expected.value}, "
                    f"got {self.chosen_outcome.value}"
                )
        return self

    @property
    def is_bet(self) -> bool:
        return self.signal is not SignalType.NO_BET

    def plain_rationale(self, lang: str = "de") -> str:
        """Prefer bilingual plain text; fall back to the technical rationale."""

        if lang.startswith("de") and self.rationale_de:
            return self.rationale_de
        if self.rationale_en:
            return self.rationale_en
        return self.rationale


_SIGNAL_TO_OUTCOME: dict[SignalType, MatchOutcome] = {
    SignalType.VALUE_HOME: MatchOutcome.HOME,
    SignalType.VALUE_DRAW: MatchOutcome.DRAW,
    SignalType.VALUE_AWAY: MatchOutcome.AWAY,
}
