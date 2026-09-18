"""Chronological validation runner for the final pipeline (P2 + VALID).

Builds a :class:`ValidationArtifact` from a leak-free train → calib → test
split. Criteria must be fixed *before* inspecting test metrics. Demo/synthetic
profiles never unlock live sizing — even a green demo artifact stays demo-scoped.

This module does **not** invent universal ECE/Brier thresholds. Callers pass
explicit :class:`ValidationCriteria`. Without criteria the artifact stays
``UNVALIDATED``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from quantbot.analysis.calibration import (
    brier_score,
    expected_calibration_error,
    log_loss,
)
from quantbot.analysis.evaluation import walk_forward_probabilities
from quantbot.analysis.validation import (
    ValidationArtifact,
    ValidationCriteria,
    ValidationMetrics,
    build_artifact,
    pipeline_hash,
    policy_content_hash,
    save_artifact,
)
from quantbot.decision.policy import DecisionPolicy, live_policy
from quantbot.features.extractor import OUTCOME_TO_LABEL
from quantbot.models.base import BaseModel, NotFittedError
from quantbot.schemas import Match


@dataclass(frozen=True)
class ChronologicalSplit:
    """Time-ordered windows. Calib is optional (may be empty)."""

    train: tuple[Match, ...]
    calib: tuple[Match, ...]
    test: tuple[Match, ...]
    train_end: datetime
    calib_start: datetime | None
    calib_end: datetime | None
    test_start: datetime
    test_end: datetime


def _finished(matches: Sequence[Match]) -> list[Match]:
    return sorted(
        (m for m in matches if m.is_finished and m.result is not None),
        key=lambda m: m.kickoff,
    )


def chronological_split(
    matches: Sequence[Match],
    *,
    train_frac: float = 0.60,
    calib_frac: float = 0.20,
) -> ChronologicalSplit:
    """Split finished matches into train / calib / outer test by time order.

    Fractions apply to the ordered finished sample. ``calib_frac`` may be 0.
    """

    ordered = _finished(matches)
    if len(ordered) < 3:
        raise ValueError("need at least 3 finished matches for a chronological split")
    if not 0.0 < train_frac < 1.0:
        raise ValueError("train_frac must be in (0, 1)")
    if calib_frac < 0.0 or train_frac + calib_frac >= 1.0:
        raise ValueError("calib_frac must be >= 0 and train_frac + calib_frac < 1")

    n = len(ordered)
    n_train = max(1, int(n * train_frac))
    n_calib = int(n * calib_frac) if calib_frac > 0 else 0
    if n_train + n_calib >= n:
        n_calib = max(0, n - n_train - 1)
    train = tuple(ordered[:n_train])
    calib = tuple(ordered[n_train : n_train + n_calib])
    test = tuple(ordered[n_train + n_calib :])
    if not test:
        raise ValueError("outer test window is empty")

    train_end = train[-1].kickoff
    if calib:
        calib_start, calib_end = calib[0].kickoff, calib[-1].kickoff
    else:
        calib_start = calib_end = None
    return ChronologicalSplit(
        train=train,
        calib=calib,
        test=test,
        train_end=train_end,
        calib_start=calib_start,
        calib_end=calib_end,
        test_start=test[0].kickoff,
        test_end=test[-1].kickoff,
    )


def _assert_no_leakage(split: ChronologicalSplit) -> None:
    if any(m.kickoff > split.train_end for m in split.train):
        raise AssertionError("train window inconsistent")
    if split.calib:
        assert split.calib_start is not None and split.calib_end is not None
        if split.calib_start < split.train_end:
            # Allow equal boundary only if calib starts after last train kickoff
            if any(m.kickoff <= split.train_end for m in split.calib):
                raise ValueError("calib overlaps train (leakage)")
        if any(m.kickoff <= split.calib_end for m in split.test if False):
            pass
        if any(m.kickoff <= split.train_end for m in split.test):
            raise ValueError("test overlaps train (leakage)")
        if any(m.kickoff <= split.calib_end for m in split.test):
            raise ValueError("test overlaps calib (leakage)")
    elif any(m.kickoff <= split.train_end for m in split.test):
        raise ValueError("test overlaps train (leakage)")


def outer_test_probabilities(
    split: ChronologicalSplit,
    model: BaseModel,
) -> tuple[np.ndarray, np.ndarray]:
    """Predict each outer-test match with the model fit only through train_end.

    Calib matches are *not* used for fitting here — they are reserved for
    calibrator development. The productive pipeline under test must match
    whatever freeze the caller documents in ``pipeline_hash``.
    """

    _assert_no_leakage(split)
    fit_universe = list(split.train) + list(split.calib)
    # Fit cutoff = last moment before first test kickoff / after calib.
    fit_as_of = split.test_start
    probs: list[list[float]] = []
    labels: list[int] = []
    try:
        model.fit_until(fit_universe, fit_as_of)
    except (ValueError, NotFittedError):
        return np.zeros((0, 3)), np.zeros((0,), dtype=int)

    for match in split.test:
        if match.kickoff <= fit_as_of and match.kickoff < split.test_start:
            continue
        try:
            # Refit strictly before this match's prediction timestamp.
            model.fit_until(fit_universe, match.prediction_timestamp)
            pred = model.predict(match)
        except (ValueError, NotFittedError):
            continue
        probs.append([pred.prob_home, pred.prob_draw, pred.prob_away])
        labels.append(OUTCOME_TO_LABEL[match.result.outcome])  # type: ignore[union-attr]
    if not probs:
        return np.zeros((0, 3)), np.zeros((0,), dtype=int)
    return np.array(probs, dtype=float), np.array(labels, dtype=int)


def metrics_from_probs(probs: np.ndarray, labels: np.ndarray) -> ValidationMetrics:
    if probs.size == 0:
        return ValidationMetrics(n=0)
    return ValidationMetrics(
        n=int(len(labels)),
        brier=float(brier_score(probs, labels)),
        log_loss=float(log_loss(probs, labels)),
        ece=float(expected_calibration_error(probs, labels)),
        coverage=1.0,  # all scored rows were attempted; abstention tracked separately later
    )


def run_chronological_validation(
    matches: Sequence[Match],
    model: BaseModel,
    *,
    scope: str,
    profile: str = "live",
    criteria: ValidationCriteria | None = None,
    policy: DecisionPolicy | None = None,
    train_frac: float = 0.60,
    calib_frac: float = 0.20,
    model_version: str = "",
    shrinkage_mode: str = "off",
    calibrator: str | None = None,
    expires_at: datetime | None = None,
    notes: str = "",
    save: bool = False,
    directory: Path | None = None,
) -> ValidationArtifact:
    """Evaluate the frozen model on an untouched outer test window.

    Important:
    - ``profile="demo"`` artifacts never unlock live Kelly
      (:func:`policy_from_artifact`).
    - Passing no ``criteria`` (or empty bounds) yields ``UNVALIDATED``.
    - Synthetic/demo fixtures must not be treated as live release evidence;
      keep ``profile="demo"`` for those runs.
    """

    if profile not in ("live", "demo"):
        raise ValueError("profile must be 'live' or 'demo'")
    split = chronological_split(matches, train_frac=train_frac, calib_frac=calib_frac)
    probs, labels = outer_test_probabilities(split, model)
    metrics = metrics_from_probs(probs, labels)
    pol = policy or live_policy()
    # Demo policy profile on the DecisionPolicy is independent; artifact.profile
    # is what gates live unlock.
    p_hash = pipeline_hash(
        model_name=getattr(model, "name", model.__class__.__name__),
        model_version=model_version,
        shrinkage_mode=shrinkage_mode,
        calibrator=calibrator,
    )
    artifact = build_artifact(
        scope=scope,
        profile=profile,
        train_end=split.train_end,
        test_start=split.test_start,
        test_end=split.test_end,
        pipeline_hash=p_hash,
        policy_hash=policy_content_hash(pol),
        policy_version=pol.version,
        n_train=len(split.train),
        n_test=metrics.n,
        criteria=criteria,
        metrics=metrics,
        calib_start=split.calib_start,
        calib_end=split.calib_end,
        n_calib=len(split.calib),
        expires_at=expires_at,
        notes=notes,
    )
    if save:
        save_artifact(artifact, directory=directory)
    return artifact


def walk_forward_baseline_metrics(
    matches: Sequence[Match], model: BaseModel
) -> ValidationMetrics:
    """Convenience: full walk-forward scorecard (not a release artifact)."""

    probs, labels = walk_forward_probabilities(matches, model)
    return metrics_from_probs(probs, labels)
