"""Run manifests: immutable provenance for one prediction batch (P2)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from quantbot.config import DATA_DIR

MANIFEST_SCHEMA_VERSION = 1


def manifests_dir(*, base: Path | None = None) -> Path:
    root = Path(base) if base is not None else DATA_DIR / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


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


def config_content_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RunManifest:
    """Frozen record of inputs for one prediction run.

    Settlement and later corrections must not mutate this object; they attach
    as separate events that only *reference* ``run_id``.
    """

    run_id: str
    as_of: datetime
    data_mode: str  # "demo" | "live" | "live_replay" | ...
    model_name: str
    model_version: str
    policy_version: str
    policy_hash: str
    pipeline_hash: str
    config_hash: str
    snapshot_ids: tuple[str, ...] = ()
    validation_artifact_id: str | None = None
    validation_status: str | None = None
    calibrator_name: str | None = None
    calibrator_fitted_at: datetime | None = None
    calib_start: datetime | None = None
    calib_end: datetime | None = None
    league: str | None = None
    season: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    notes: str = ""
    schema_version: int = MANIFEST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "as_of": _dt_iso(self.as_of),
            "data_mode": self.data_mode,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "policy_version": self.policy_version,
            "policy_hash": self.policy_hash,
            "pipeline_hash": self.pipeline_hash,
            "config_hash": self.config_hash,
            "snapshot_ids": list(self.snapshot_ids),
            "validation_artifact_id": self.validation_artifact_id,
            "validation_status": self.validation_status,
            "calibrator_name": self.calibrator_name,
            "calibrator_fitted_at": _dt_iso(self.calibrator_fitted_at),
            "calib_start": _dt_iso(self.calib_start),
            "calib_end": _dt_iso(self.calib_end),
            "league": self.league,
            "season": self.season,
            "created_at": _dt_iso(self.created_at),
            "notes": self.notes,
            "schema_version": self.schema_version,
        }


def build_run_manifest(
    *,
    as_of: datetime,
    data_mode: str,
    model_name: str,
    model_version: str = "",
    policy_version: str,
    policy_hash: str,
    pipeline_hash: str,
    config_hash: str,
    snapshot_ids: tuple[str, ...] | list[str] = (),
    validation_artifact_id: str | None = None,
    validation_status: str | None = None,
    calibrator_name: str | None = None,
    calibrator_fitted_at: datetime | None = None,
    calib_start: datetime | None = None,
    calib_end: datetime | None = None,
    league: str | None = None,
    season: str | None = None,
    notes: str = "",
    run_id: str | None = None,
    created_at: datetime | None = None,
) -> RunManifest:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    return RunManifest(
        run_id=run_id or str(uuid4()),
        as_of=as_of.astimezone(timezone.utc),
        data_mode=data_mode,
        model_name=model_name,
        model_version=model_version,
        policy_version=policy_version,
        policy_hash=policy_hash,
        pipeline_hash=pipeline_hash,
        config_hash=config_hash,
        snapshot_ids=tuple(snapshot_ids),
        validation_artifact_id=validation_artifact_id,
        validation_status=validation_status,
        calibrator_name=calibrator_name,
        calibrator_fitted_at=calibrator_fitted_at,
        calib_start=calib_start,
        calib_end=calib_end,
        league=league,
        season=season,
        created_at=created_at or _utc_now(),
        notes=notes,
    )


def save_manifest(manifest: RunManifest, *, directory: Path | None = None) -> Path:
    root = manifests_dir(base=directory)
    path = root / f"{manifest.run_id}.json"
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_manifest(path: Path) -> RunManifest:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return manifest_from_dict(data)


def manifest_from_dict(data: dict[str, Any]) -> RunManifest:
    return RunManifest(
        run_id=str(data["run_id"]),
        as_of=_parse_dt(data["as_of"]),  # type: ignore[arg-type]
        data_mode=str(data["data_mode"]),
        model_name=str(data["model_name"]),
        model_version=str(data.get("model_version") or ""),
        policy_version=str(data["policy_version"]),
        policy_hash=str(data["policy_hash"]),
        pipeline_hash=str(data["pipeline_hash"]),
        config_hash=str(data["config_hash"]),
        snapshot_ids=tuple(str(x) for x in data.get("snapshot_ids") or ()),
        validation_artifact_id=data.get("validation_artifact_id"),
        validation_status=data.get("validation_status"),
        calibrator_name=data.get("calibrator_name"),
        calibrator_fitted_at=_parse_dt(data.get("calibrator_fitted_at")),
        calib_start=_parse_dt(data.get("calib_start")),
        calib_end=_parse_dt(data.get("calib_end")),
        league=data.get("league"),
        season=data.get("season"),
        created_at=_parse_dt(data.get("created_at")) or _utc_now(),
        notes=str(data.get("notes") or ""),
        schema_version=int(data.get("schema_version", MANIFEST_SCHEMA_VERSION)),
    )


def attach_settlement_event(
    *,
    run_id: str,
    tip_id: str,
    event: dict[str, Any],
    directory: Path | None = None,
) -> Path:
    """Append a settlement follow-up without mutating the run manifest."""

    root = manifests_dir(base=directory) / "events"
    root.mkdir(parents=True, exist_ok=True)
    safe_tip = "".join(c if c.isalnum() or c in "-_" else "_" for c in tip_id)[:80]
    path = root / f"{run_id}__{safe_tip}.jsonl"
    payload = {
        "run_id": run_id,
        "tip_id": tip_id,
        "recorded_at": _dt_iso(_utc_now()),
        **event,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path
