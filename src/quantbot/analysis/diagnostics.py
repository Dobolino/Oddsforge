"""Model diagnostics: ablation and feature importance (Layer 3).

Ablation removes one feature group at a time and measures how much the
out-of-sample Brier score changes: a large increase means the group carries
real signal. Feature importance uses permutation importance on a held-out
slice. Both are guides, not proof, and must be read with care.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from quantbot.analysis.calibration import brier_score
from quantbot.analysis.evaluation import walk_forward_probabilities
from quantbot.features.extractor import FEATURE_NAMES, FeatureExtractor
from quantbot.logging import get_logger
from quantbot.models.ml import LogisticRegressionModel
from quantbot.schemas import Match

logger = get_logger(__name__)

# Feature groups for ablation.
FEATURE_GROUPS: dict[str, set[str]] = {
    "elo": {"elo_diff"},
    "form": {"home_form_points", "away_form_points"},
    "goals": {
        "home_goals_for_avg", "home_goals_against_avg",
        "away_goals_for_avg", "away_goals_against_avg",
    },
    "xg": {
        "home_xg_for_avg", "home_xg_against_avg",
        "away_xg_for_avg", "away_xg_against_avg",
    },
    "rest_days": {"home_rest_days", "away_rest_days"},
    "experience": {"home_matches_played", "away_matches_played"},
}


def ablation_report(matches: Sequence[Match]) -> dict[str, object]:
    """Brier with all features vs with each group removed (walk-forward).

    ``delta`` is (removed - baseline). Positive means removing the group hurt,
    so the group was useful.
    """

    base_probs, base_labels = walk_forward_probabilities(matches, LogisticRegressionModel())
    if base_probs.size == 0:
        return {"baseline_brier": None, "rows": []}
    baseline = brier_score(base_probs, base_labels)

    rows: list[dict[str, object]] = []
    for name, feats in FEATURE_GROUPS.items():
        probs, labels = walk_forward_probabilities(
            matches, LogisticRegressionModel(exclude_features=feats)
        )
        if probs.size == 0:
            rows.append({"group": name, "brier": None, "delta": None})
            continue
        b = brier_score(probs, labels)
        rows.append({"group": name, "brier": round(b, 4), "delta": round(b - baseline, 4)})

    rows.sort(key=lambda r: (r["delta"] is None, -(r["delta"] or 0.0)))
    logger.info("Ablation baseline Brier %.4f over %d groups", baseline, len(rows))
    return {"baseline_brier": round(baseline, 4), "rows": rows}


def feature_importance(
    matches: Sequence[Match], n_repeats: int = 8, seed: int = 0, val_fraction: float = 0.3
) -> list[dict[str, object]]:
    """Permutation importance of each feature on a chronological hold-out slice."""

    from sklearn.inspection import permutation_importance

    extractor = FeatureExtractor()
    ordered = sorted(
        (m for m in matches if m.is_finished and m.result is not None),
        key=lambda m: m.kickoff,
    )
    feats, labels = extractor.build_training_set(ordered)
    if len(feats) < 20 or len(set(labels)) < 2:
        return []

    x = np.array([[f[n] for n in FEATURE_NAMES] for f in feats], dtype=float)
    y = np.array(labels, dtype=int)
    split = int(len(x) * (1.0 - val_fraction))
    x_tr, x_val, y_tr, y_val = x[:split], x[split:], y[:split], y[split:]
    if len(x_val) < 5 or len(set(y_tr)) < 2:
        return []

    pipeline = LogisticRegressionModel()._build_pipeline()  # noqa: SLF001
    pipeline.fit(x_tr, y_tr)
    result = permutation_importance(pipeline, x_val, y_val, n_repeats=n_repeats, random_state=seed)

    means = np.clip(result.importances_mean, 0.0, None)
    total = means.sum()
    shares = means / total if total > 0 else np.zeros_like(means)
    rows = [
        {"feature": name, "importance": round(float(s * 100), 1)}
        for name, s in zip(FEATURE_NAMES, shares, strict=True)
    ]
    rows.sort(key=lambda r: r["importance"], reverse=True)
    return rows
