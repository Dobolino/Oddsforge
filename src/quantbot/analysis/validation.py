"""Empirical validation artifacts and release gating (P0).

A :class:`ValidationArtifact` records a chronological train → calib → test
evaluation of the *final* pipeline. Status becomes ``VALID`` only when
explicit criteria were fixed *before* looking at test metrics and those
metrics pass. Without criteria the status stays ``UNVALIDATED`` — no invented
universal ECE/Brier thresholds.

Only ``VALID`` releases Kelly sizing via :class:`DecisionPolicy`. ``DEGRADED``
and ``EXPIRED`` never unlock sizing by raising ``min_edge``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from quantbot.config import MODEL_DIR
from quantbot.decision.policy import (
    DecisionPolicy,
    PolicyProfile,
    ValidationStatus,
    demo_policy,
    live_policy,
)

ARTIFACT_SCHEMA_VERSION = 1


def validation_dir(*, base: Path | None = None) -> Path:
    root = Path(base) if base is not None else MODEL_DIR / "validation"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _dt_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class ValidationCriteria:
    """Release thresholds fixed *before* inspecting outer-test metrics.

    Any field left ``None`` is not checked. An empty criteria object (all
    ``None``) cannot produce ``VALID`` — that requires at least one bound.
    """

    min_n: int | None = None
    max_brier: float | None = None
    max_log_loss: float | None = None
    max_ece: float | None = None
    min_coverage: float | None = None

    def has_bounds(self) -> bool:
        return any(
            v is not None
            for v in (
                self.min_n,
                self.max_brier,
                self.max_log_loss,
                self.max_ece,
                self.min_coverage,
            )
        )


@dataclass(frozen=True)
class ValidationMetrics:
    """Observed outer-test metrics (never used to invent criteria)."""

    n: int
    brier: float | None = None
    log_loss: float | None = None
    ece: float | None = None
    coverage: float | None = None


@dataclass(frozen=True)
class ValidationArtifact:
    """Frozen empirical release record for one scope and pipeline hash."""

    artifact_id: str
    scope: str
    status: ValidationStatus
    profile: str  # "live" | "demo" — demo artifacts never validate live
    train_end: datetime
    test_start: datetime
    test_end: datetime
    pipeline_hash: str
    policy_hash: str
    policy_version: str
    n_train: int
    n_test: int
    criteria: ValidationCriteria | None = None
    metrics: ValidationMetrics | None = None
    calib_start: datetime | None = None
    calib_end: datetime | None = None
    n_calib: int = 0
    created_at: datetime = field(default_factory=_utc_now)
    expires_at: datetime | None = None
    notes: str = ""
    schema_version: int = ARTIFACT_SCHEMA_VERSION

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        clock = now or _utc_now()
        if clock.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        return clock >= self.expires_at.astimezone(timezone.utc)

    def effective_status(self, *, now: datetime | None = None) -> ValidationStatus:
        if self.is_expired(now=now):
            return ValidationStatus.EXPIRED
        return self.status


def compute_content_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def pipeline_hash(
    *,
    model_name: str,
    model_version: str = "",
    shrinkage_mode: str = "off",
    calibrator: str | None = None,
    extras: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model_name": model_name,
        "model_version": model_version,
        "shrinkage_mode": shrinkage_mode,
        "calibrator": calibrator,
    }
    if extras:
        payload["extras"] = extras
    return compute_content_hash(payload)


def policy_content_hash(policy: DecisionPolicy) -> str:
    payload = {
        "version": policy.version,
        "profile": policy.profile.value,
        "min_ev": policy.min_ev,
        "min_edge": policy.min_edge,
        "max_overround": policy.max_overround,
        "min_data_quality": policy.min_data_quality,
        "min_model_confidence": policy.min_model_confidence,
        "min_odds": policy.min_odds,
        "max_odds": policy.max_odds,
        "max_plausible_ev": policy.max_plausible_ev,
        "min_team_matches": policy.min_team_matches,
        "kelly_fraction": policy.kelly_fraction,
        "max_stake_fraction": policy.max_stake_fraction,
        "require_validation_for_sizing": policy.require_validation_for_sizing,
        "allow_exploratory_value_signals": policy.allow_exploratory_value_signals,
    }
    return compute_content_hash(payload)


def evaluate_artifact(
    *,
    criteria: ValidationCriteria | None,
    metrics: ValidationMetrics | None,
    expires_at: datetime | None = None,
    now: datetime | None = None,
) -> ValidationStatus:
    """Derive status from pre-declared criteria and observed metrics.

    Rules:
    - Past ``expires_at`` → ``EXPIRED``
    - Missing criteria / no bounds / missing metrics → ``UNVALIDATED``
    - All declared bounds pass → ``VALID``
    - Any bound fails → ``UNVALIDATED`` (not silently ``DEGRADED``)
    """

    clock = now or _utc_now()
    if expires_at is not None:
        if expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        if clock >= expires_at.astimezone(timezone.utc):
            return ValidationStatus.EXPIRED

    if criteria is None or not criteria.has_bounds() or metrics is None:
        return ValidationStatus.UNVALIDATED

    if criteria.min_n is not None and metrics.n < criteria.min_n:
        return ValidationStatus.UNVALIDATED
    if criteria.max_brier is not None:
        if metrics.brier is None or metrics.brier > criteria.max_brier:
            return ValidationStatus.UNVALIDATED
    if criteria.max_log_loss is not None:
        if metrics.log_loss is None or metrics.log_loss > criteria.max_log_loss:
            return ValidationStatus.UNVALIDATED
    if criteria.max_ece is not None:
        if metrics.ece is None or metrics.ece > criteria.max_ece:
            return ValidationStatus.UNVALIDATED
    if criteria.min_coverage is not None:
        if metrics.coverage is None or metrics.coverage < criteria.min_coverage:
            return ValidationStatus.UNVALIDATED
    return ValidationStatus.VALID


def build_artifact(
    *,
    scope: str,
    profile: str,
    train_end: datetime,
    test_start: datetime,
    test_end: datetime,
    pipeline_hash: str,
    policy_hash: str,
    policy_version: str,
    n_train: int,
    n_test: int,
    criteria: ValidationCriteria | None = None,
    metrics: ValidationMetrics | None = None,
    calib_start: datetime | None = None,
    calib_end: datetime | None = None,
    n_calib: int = 0,
    expires_at: datetime | None = None,
    notes: str = "",
    artifact_id: str | None = None,
    created_at: datetime | None = None,
    evaluate: bool = True,
    status: ValidationStatus | None = None,
) -> ValidationArtifact:
    """Construct an artifact; optionally evaluate status from criteria/metrics."""

    if profile not in ("live", "demo"):
        raise ValueError("profile must be 'live' or 'demo'")
    if evaluate:
        derived = evaluate_artifact(
            criteria=criteria, metrics=metrics, expires_at=expires_at
        )
    else:
        if status is None:
            raise ValueError("status required when evaluate=False")
        derived = status

    return ValidationArtifact(
        artifact_id=artifact_id or str(uuid4()),
        scope=scope.strip(),
        status=derived,
        profile=profile,
        train_end=train_end,
        test_start=test_start,
        test_end=test_end,
        pipeline_hash=pipeline_hash,
        policy_hash=policy_hash,
        policy_version=policy_version,
        n_train=n_train,
        n_test=n_test,
        criteria=criteria,
        metrics=metrics,
        calib_start=calib_start,
        calib_end=calib_end,
        n_calib=n_calib,
        created_at=created_at or _utc_now(),
        expires_at=expires_at,
        notes=notes,
    )


def artifact_to_dict(artifact: ValidationArtifact) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "scope": artifact.scope,
        "status": artifact.status.value,
        "profile": artifact.profile,
        "train_end": _dt_iso(artifact.train_end),
        "test_start": _dt_iso(artifact.test_start),
        "test_end": _dt_iso(artifact.test_end),
        "pipeline_hash": artifact.pipeline_hash,
        "policy_hash": artifact.policy_hash,
        "policy_version": artifact.policy_version,
        "n_train": artifact.n_train,
        "n_test": artifact.n_test,
        "n_calib": artifact.n_calib,
        "criteria": asdict(artifact.criteria) if artifact.criteria else None,
        "metrics": asdict(artifact.metrics) if artifact.metrics else None,
        "calib_start": _dt_iso(artifact.calib_start),
        "calib_end": _dt_iso(artifact.calib_end),
        "created_at": _dt_iso(artifact.created_at),
        "expires_at": _dt_iso(artifact.expires_at),
        "notes": artifact.notes,
        "schema_version": artifact.schema_version,
    }


def artifact_from_dict(data: dict[str, Any]) -> ValidationArtifact:
    criteria_raw = data.get("criteria")
    metrics_raw = data.get("metrics")
    criteria = (
        ValidationCriteria(**criteria_raw) if isinstance(criteria_raw, dict) else None
    )
    metrics = ValidationMetrics(**metrics_raw) if isinstance(metrics_raw, dict) else None
    train_end = _parse_dt(data["train_end"])
    test_start = _parse_dt(data["test_start"])
    test_end = _parse_dt(data["test_end"])
    created_at = _parse_dt(data.get("created_at")) or _utc_now()
    if train_end is None or test_start is None or test_end is None:
        raise ValueError("train_end/test_start/test_end are required")
    return ValidationArtifact(
        artifact_id=str(data["artifact_id"]),
        scope=str(data["scope"]),
        status=ValidationStatus(str(data["status"])),
        profile=str(data["profile"]),
        train_end=train_end,
        test_start=test_start,
        test_end=test_end,
        pipeline_hash=str(data["pipeline_hash"]),
        policy_hash=str(data["policy_hash"]),
        policy_version=str(data["policy_version"]),
        n_train=int(data["n_train"]),
        n_test=int(data["n_test"]),
        criteria=criteria,
        metrics=metrics,
        calib_start=_parse_dt(data.get("calib_start")),
        calib_end=_parse_dt(data.get("calib_end")),
        n_calib=int(data.get("n_calib") or 0),
        created_at=created_at,
        expires_at=_parse_dt(data.get("expires_at")),
        notes=str(data.get("notes") or ""),
        schema_version=int(data.get("schema_version") or ARTIFACT_SCHEMA_VERSION),
    )


def save_artifact(
    artifact: ValidationArtifact, *, directory: Path | None = None
) -> Path:
    root = validation_dir(base=directory)
    path = root / f"{artifact.artifact_id}.json"
    path.write_text(
        json.dumps(artifact_to_dict(artifact), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_artifact(path: Path) -> ValidationArtifact:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("validation artifact must be a JSON object")
    return artifact_from_dict(data)


def list_artifacts(*, directory: Path | None = None) -> list[ValidationArtifact]:
    root = Path(directory) if directory is not None else MODEL_DIR / "validation"
    if not root.exists():
        return []
    out: list[ValidationArtifact] = []
    for path in sorted(root.glob("*.json")):
        try:
            out.append(load_artifact(path))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    return out


def load_latest_artifact(
    *,
    scope: str | None = None,
    profile: str | None = None,
    pipeline_hash: str | None = None,
    directory: Path | None = None,
    now: datetime | None = None,
) -> ValidationArtifact | None:
    """Return the newest matching artifact (by ``created_at``), if any."""

    candidates = list_artifacts(directory=directory)
    if scope is not None:
        candidates = [a for a in candidates if a.scope == scope]
    if profile is not None:
        candidates = [a for a in candidates if a.profile == profile]
    if pipeline_hash is not None:
        candidates = [a for a in candidates if a.pipeline_hash == pipeline_hash]
    if not candidates:
        return None
    candidates.sort(key=lambda a: a.created_at, reverse=True)
    latest = candidates[0]
    # Surface expiry without mutating the stored file.
    eff = latest.effective_status(now=now)
    if eff is not latest.status:
        return replace(latest, status=eff)
    return latest


def policy_from_artifact(
    artifact: ValidationArtifact,
    *,
    base: DecisionPolicy | None = None,
    now: datetime | None = None,
    expected_scope: str | None = None,
    expected_pipeline_hash: str | None = None,
) -> DecisionPolicy:
    """Map an artifact onto a DecisionPolicy validation gate.

    Demo artifacts never release live sizing. Scope / pipeline mismatches stay
    ``UNVALIDATED``. ``DEGRADED`` and ``EXPIRED`` do not set ``VALID``.
    """

    if base is None:
        base = live_policy() if artifact.profile == "live" else demo_policy()

    status = artifact.effective_status(now=now)

    if base.profile is PolicyProfile.LIVE and artifact.profile != "live":
        return base.with_validation(ValidationStatus.UNVALIDATED)
    if expected_scope is not None and artifact.scope != expected_scope:
        return base.with_validation(ValidationStatus.UNVALIDATED)
    if (
        expected_pipeline_hash is not None
        and artifact.pipeline_hash != expected_pipeline_hash
    ):
        return base.with_validation(ValidationStatus.UNVALIDATED)

    return base.with_validation(status)
