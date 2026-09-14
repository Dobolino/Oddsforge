"""Batch 3 tests: feature ablation, feature importance, experiment tracking."""

from __future__ import annotations

from datetime import datetime, timezone

from quantbot.analysis.diagnostics import FEATURE_GROUPS, ablation_report, feature_importance
from quantbot.data import DummyDataProvider
from quantbot.experiments import ExperimentStore, evaluate_run
from quantbot.features.extractor import FEATURE_NAMES
from quantbot.models import EloModel, LogisticRegressionModel
from quantbot.schemas import League

FAR = datetime(2026, 1, 1, tzinfo=timezone.utc)
SEASON = "2024-2025"


def _universe() -> list:
    p = DummyDataProvider()
    return p.get_matches(League.PREMIER_LEAGUE, SEASON, FAR) + p.get_matches(League.BUNDESLIGA, SEASON, FAR)


# --- Feature exclusion in the model ---


def test_model_excludes_features() -> None:
    model = LogisticRegressionModel(exclude_features={"elo_diff"})
    assert "elo_diff" not in model._active
    assert len(model._active) == len(FEATURE_NAMES) - 1
    model.fit(_universe())
    pred = model.predict(_universe()[0])
    assert abs(pred.prob_home + pred.prob_draw + pred.prob_away - 1.0) < 1e-6


# --- Ablation ---


def test_ablation_report_structure() -> None:
    report = ablation_report(_universe())
    assert report["baseline_brier"] is not None
    groups = {r["group"] for r in report["rows"]}
    assert groups == set(FEATURE_GROUPS)
    for r in report["rows"]:
        assert "brier" in r and "delta" in r


# --- Feature importance ---


def test_feature_importance_sums_to_hundred() -> None:
    rows = feature_importance(_universe(), n_repeats=4)
    assert rows
    assert {r["feature"] for r in rows} == set(FEATURE_NAMES)
    total = sum(r["importance"] for r in rows)
    assert abs(total - 100.0) < 1.0 or total == 0.0
    # Sorted descending.
    imps = [r["importance"] for r in rows]
    assert imps == sorted(imps, reverse=True)


# --- Experiments ---


def test_evaluate_run_and_store(tmp_path) -> None:  # type: ignore[no-untyped-def]
    matches = _universe()
    store = ExperimentStore(tmp_path / "experiments.json")
    assert store.load() == []
    assert store.next_version("elo") == "v1"

    run = evaluate_run(matches, EloModel(), dataset="PL+BL", version=store.next_version("elo"))
    assert run.metrics["brier"] is not None
    assert run.n_samples > 0
    store.log(run)

    assert len(store.load()) == 1
    assert store.next_version("elo") == "v2"
    best = store.best("brier")
    assert best is not None and best.model == "elo"


def test_experiment_run_serializable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    run = evaluate_run(_universe(), LogisticRegressionModel(), dataset="PL+BL", version="v1")
    assert json.loads(json.dumps(run.to_dict()))["model"] == "logistic_regression"
