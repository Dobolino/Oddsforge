"""Prediction snapshot: auditable freeze of what QuantBot knew at decide-time.

Every tip should be reconstructible later: data cutoff, odds timestamp, model
identity, probabilities, market view, and the decision with reason codes.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from quantbot.schemas.base import QuantBotModel
from quantbot.schemas.enums import SignalType
from quantbot.schemas.signal import Selection


class PredictionSnapshot(QuantBotModel):
    """Immutable audit record for one prediction/decision.

    Guardrail: stores the inputs and outputs of a decide step; it does not
    place bets. All timestamps must be timezone-aware.
    """

    match_id: str = Field(min_length=1)
    prediction_timestamp: datetime
    data_cutoff: datetime
    odds_timestamp: datetime | None = None
    model_name: str = Field(default="unknown", min_length=1)
    feature_version: str = Field(default="v1")
    dataset_version: str = Field(default="unknown")
    model_prob: float | None = Field(default=None, ge=0.0, le=1.0)
    fair_market_prob: float | None = Field(default=None, gt=0.0, lt=1.0)
    decimal_odds: float | None = Field(default=None, gt=1.0)
    edge: float | None = None
    expected_value: float | None = None
    signal: SignalType
    chosen_outcome: Selection | None = None
    reason_codes: tuple[str, ...] = Field(default_factory=tuple)
    model_confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    data_quality: float = Field(default=0.0, ge=0.0, le=100.0)
    stake_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    totals_line: float | None = Field(default=None, gt=0.0)


def snapshot_from_signal(
    signal: "ValueSignal",  # noqa: F821 — quoted to avoid circular import at runtime
    *,
    data_cutoff: datetime,
    model_name: str = "unknown",
    odds_timestamp: datetime | None = None,
    feature_version: str = "v1",
    dataset_version: str = "unknown",
) -> PredictionSnapshot:
    """Build a snapshot from a decided :class:`ValueSignal`."""

    from quantbot.schemas.signal import ValueSignal

    if not isinstance(signal, ValueSignal):
        raise TypeError("signal must be a ValueSignal")

    model_prob = fair = None
    if signal.chosen_outcome is not None:
        for metric in signal.metrics:
            if metric.outcome is signal.chosen_outcome:
                model_prob = float(metric.model_prob)
                fair = float(metric.fair_market_prob)
                break
    elif signal.metrics:
        best = max(signal.metrics, key=lambda m: m.expected_value)
        model_prob = float(best.model_prob)
        fair = float(best.fair_market_prob)

    return PredictionSnapshot(
        match_id=signal.match_id,
        prediction_timestamp=signal.timestamp,
        data_cutoff=data_cutoff,
        odds_timestamp=odds_timestamp or signal.timestamp,
        model_name=model_name,
        feature_version=feature_version,
        dataset_version=dataset_version,
        model_prob=model_prob,
        fair_market_prob=fair,
        decimal_odds=signal.decimal_odds,
        edge=signal.edge,
        expected_value=signal.expected_value,
        signal=signal.signal,
        chosen_outcome=signal.chosen_outcome,
        reason_codes=tuple(signal.reason_codes),
        model_confidence=signal.model_confidence,
        data_quality=signal.data_quality,
        stake_fraction=signal.stake_fraction,
        totals_line=signal.totals_line,
    )
