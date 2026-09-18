"""Value and decision schemas (Layer 3 and Layer 4).

``ValueMetrics`` holds the raw comparison between model and market. The
:class:`ValueSignal` is the Decision Engine's final, auditable output: what to
do, why, and a theoretical (never executed) stake.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from quantbot.schemas.base import QuantBotModel
from quantbot.schemas.enums import MatchOutcome, SignalType, TotalsSide

Selection = MatchOutcome | TotalsSide


class ValueMetrics(QuantBotModel):
    """Per-outcome value comparison of model vs. fair market probability.

    Attributes:
        model_prob: Model probability for the outcome.
        fair_market_prob: Margin-free market probability for the outcome.
        decimal_odds: Best available decimal odds for the outcome.
        edge: model_prob - fair_market_prob.
        expected_value: (model_prob * decimal_odds) - 1.
    """

    outcome: Selection
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

    @property
    def edge_pp(self) -> float:
        """Absolute edge in percentage points (e.g. 6.3 for +6.3 pp)."""

        return self.edge * 100.0

    @property
    def relative_edge(self) -> float:
        """Relative edge ``(model - market) / market`` (not percentage points)."""

        return (self.model_prob - self.fair_market_prob) / self.fair_market_prob

    @property
    def expected_return_pct(self) -> float:
        """Expected return as percent (EV * 100), e.g. 21.0 for +21%."""

        return self.expected_value * 100.0


class ValueSignal(QuantBotModel):
    """Final decision-engine output for one match.

    Guardrail: ``stake_fraction`` is a theoretical fractional-Kelly suggestion.
    QuantBot v1 never executes it. A ``NO_BET`` signal always has zero stake
    and no chosen outcome.

    Attributes:
        data_quality: 0-100 completeness/reliability score of the inputs.
        model_confidence: 0-100 forecast-quality score (not a win probability).
        stake_fraction: Fraction of bankroll (theoretical), 0.0 for NO_BET.
        totals_line: Set when the tip is an Over/Under selection.
        reason_codes: Stable audit codes (e.g. NO_BET_LOW_EDGE, VALUE).
    """

    match_id: str = Field(min_length=1)
    timestamp: datetime
    signal: SignalType
    chosen_outcome: Selection | None = None
    edge: float | None = None
    expected_value: float | None = None
    decimal_odds: float | None = Field(default=None, gt=1.0)
    model_confidence: float = Field(ge=0.0, le=100.0)
    data_quality: float = Field(ge=0.0, le=100.0)
    stake_fraction: float = Field(default=0.0, ge=0.0, le=0.05)
    rationale: str = Field(
        default="",
        description="Technical English decision reason (logs / expert mode).",
    )
    rationale_de: str = Field(default="", description="Plain-language German reason.")
    rationale_en: str = Field(default="", description="Plain-language English reason.")
    reason_codes: tuple[str, ...] = Field(default_factory=tuple)
    metrics: tuple[ValueMetrics, ...] = Field(default_factory=tuple)
    totals_line: float | None = Field(default=None, gt=0.0)
    # Central DecisionPolicy audit fields (defaults keep legacy constructors valid).
    policy_version: str = Field(default="")
    policy_profile: str = Field(default="")
    validation_status: str = Field(default="unvalidated")
    decision_status: str = Field(default="")
    sizing_allowed: bool = False
    p_final: float | None = Field(default=None, ge=0.0, le=1.0)

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
            expected = _SIGNAL_TO_SELECTION[self.signal]
            if self.chosen_outcome is not expected:
                raise ValueError(
                    f"{self.signal.value} must choose {expected.value}, "
                    f"got {self.chosen_outcome.value}"
                )
            if self.signal in (SignalType.VALUE_OVER, SignalType.VALUE_UNDER):
                if self.totals_line is None:
                    raise ValueError("totals tips require totals_line")
            elif self.totals_line is not None:
                raise ValueError("1X2 tips must not set totals_line")
        return self

    @property
    def is_bet(self) -> bool:
        return self.signal is not SignalType.NO_BET

    @property
    def tip_label(self) -> str | None:
        """Stable tip id string for history (e.g. home, over_2.5)."""

        if self.chosen_outcome is None:
            return None
        if isinstance(self.chosen_outcome, TotalsSide) and self.totals_line is not None:
            line = self.totals_line
            line_s = str(int(line)) if float(line).is_integer() else str(line)
            return f"{self.chosen_outcome.value}_{line_s}"
        return self.chosen_outcome.value

    def plain_rationale(self, lang: str = "de") -> str:
        """Prefer bilingual plain text; fall back to the technical rationale."""

        if lang.startswith("de") and self.rationale_de:
            return self.rationale_de
        if self.rationale_en:
            return self.rationale_en
        return self.rationale


_SIGNAL_TO_SELECTION: dict[SignalType, Selection] = {
    SignalType.VALUE_HOME: MatchOutcome.HOME,
    SignalType.VALUE_DRAW: MatchOutcome.DRAW,
    SignalType.VALUE_AWAY: MatchOutcome.AWAY,
    SignalType.VALUE_OVER: TotalsSide.OVER,
    SignalType.VALUE_UNDER: TotalsSide.UNDER,
}
