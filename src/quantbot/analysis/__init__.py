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
from quantbot.analysis.diagnostics import FEATURE_GROUPS, ablation_report, feature_importance
from quantbot.analysis.matchcard import MatchCard, build_match_card, divergence_tier
from quantbot.analysis.value import (
    ValueCalculator,
    assert_metrics_consistent,
    edge,
    edge_pp,
    edge_uncertainty_band_pp,
    expected_value,
    format_edge_band_pp,
    format_edge_pp,
    format_ev_pct,
    format_model_prob,
    odds_to_dict,
    relative_edge,
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
    "FEATURE_GROUPS",
    "ablation_report",
    "feature_importance",
    "ValueCalculator",
    "assert_metrics_consistent",
    "edge",
    "edge_pp",
    "edge_uncertainty_band_pp",
    "expected_value",
    "format_edge_band_pp",
    "format_edge_pp",
    "format_ev_pct",
    "format_model_prob",
    "odds_to_dict",
    "relative_edge",
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
