"""Experiment tracking and model versioning.

Records each evaluated model configuration as a run: a version number, the
dataset, features and parameters, and out-of-sample metrics. Runs persist to a
JSON file so results are reproducible and comparable over time ("v1.4 beat
v1.3, and here is why").
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from quantbot.analysis.evaluation import walk_forward_probabilities
from quantbot.analysis.calibration import (
    brier_score,
    expected_calibration_error,
    log_loss,
)
from quantbot.logging import get_logger
from quantbot.models.base import BaseModel
from quantbot.schemas import Match

logger = get_logger(__name__)


@dataclass
class ExperimentRun:
    """One evaluated model configuration."""

    run_id: str
    created: str
    model: str
    version: str
    dataset: str
    n_samples: int
    metrics: dict[str, float | None]
    params: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_run(
    matches: Sequence[Match],
    model: BaseModel,
    *,
    dataset: str,
    version: str,
    params: dict[str, object] | None = None,
) -> ExperimentRun:
    """Compute out-of-sample metrics for a model and wrap them as a run."""

    probs, labels = walk_forward_probabilities(matches, model)
    if probs.size == 0:
        metrics: dict[str, float | None] = {"brier": None, "log_loss": None, "ece": None}
        n = 0
    else:
        metrics = {
            "brier": round(brier_score(probs, labels), 4),
            "log_loss": round(log_loss(probs, labels), 4),
            "ece": round(expected_calibration_error(probs, labels), 4),
        }
        n = int(len(labels))

    now = datetime.now(timezone.utc)
    return ExperimentRun(
        run_id=now.strftime("%Y%m%d%H%M%S") + f"-{model.name}",
        created=now.isoformat(),
        model=model.name,
        version=version,
        dataset=dataset,
        n_samples=n,
        metrics=metrics,
        params=params or {},
    )


class ExperimentStore:
    """Append-only JSON store of experiment runs."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> list[ExperimentRun]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [ExperimentRun(**r) for r in data]

    def log(self, run: ExperimentRun) -> None:
        runs = self.load()
        runs.append(run)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([r.to_dict() for r in runs], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Logged experiment %s (%s %s)", run.run_id, run.model, run.version)

    def next_version(self, model_name: str) -> str:
        """Auto-increment a simple v1, v2, ... version for a model."""

        existing = [r for r in self.load() if r.model == model_name]
        return f"v{len(existing) + 1}"

    def best(self, metric: str = "brier") -> ExperimentRun | None:
        runs = [r for r in self.load() if r.metrics.get(metric) is not None]
        if not runs:
            return None
        return min(runs, key=lambda r: r.metrics[metric])  # type: ignore[return-value,arg-type]
