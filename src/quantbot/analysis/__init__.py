"""Value, calibration, and confidence analysis (Layer 3)."""

from __future__ import annotations

from quantbot.analysis.calibration import (
    BaseCalibrator,
    IsotonicCalibrator,
    PlattScaler,
    brier_score,
    expected_calibration_error,
    log_loss,
)
from quantbot.analysis.confidence import (
    ConfidenceEvaluator,
    ConfidenceLevel,
    DataQualitySignals,
    ensemble_agreement,
)
from quantbot.analysis.engine import AnalysisEngine, AnalysisResult
from quantbot.analysis.evaluation import (
    calibration_report,
    model_comparison,
    reliability_curve,
    walk_forward_probabilities,
)
from quantbot.analysis.matchcard import MatchCard, build_match_card, divergence_tier
from quantbot.analysis.value import (
    ValueCalculator,
    edge,
    expected_value,
    odds_to_dict,
)

__all__ = [
    "AnalysisEngine",
    "AnalysisResult",
    "MatchCard",
    "build_match_card",
    "divergence_tier",
    "calibration_report",
    "model_comparison",
    "reliability_curve",
    "walk_forward_probabilities",
    "ValueCalculator",
    "edge",
    "expected_value",
    "odds_to_dict",
    "ConfidenceEvaluator",
    "ConfidenceLevel",
    "DataQualitySignals",
    "ensemble_agreement",
    "BaseCalibrator",
    "IsotonicCalibrator",
    "PlattScaler",
    "brier_score",
    "expected_calibration_error",
    "log_loss",
]
