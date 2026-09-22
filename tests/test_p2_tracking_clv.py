"""P2: Run-Manifest, CLV comparability, AH settlement, validation runner."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantbot.analysis.validation import ValidationCriteria, ValidationStatus
from quantbot.analysis.validation_run import (
    chronological_split,
    run_chronological_validation,
)
from quantbot.backtest.execution import ExecutionSimulator
from quantbot.data.dummy import DummyDataProvider
from quantbot.markets.clv import (
    ClvStatus,
    ClosingQuoteRef,
    EntryQuoteRef,
    closing_reference_ev,
    evaluate_clv,
)
from quantbot.markets.settlement import LineMarketKind, settle_line_market
from quantbot.models.elo import EloModel
from quantbot.orchestrator import QuantBotOrchestrator
from quantbot.runs import (
    attach_settlement_event,
    build_run_manifest,
    load_manifest,
    save_manifest,
)
from quantbot.schemas import League, Market, MarketKind, MarketOutcome, SettlementStatus
from quantbot.schemas.lines import require_quarter_tick
from quantbot.tracking import TipHistoryStore, TipRecord

UTC = timezone.utc


def test_run_manifest_immutable_across_settlement(tmp_path: Path) -> None:
    as_of = datetime(2025, 1, 15, tzinfo=UTC)
    manifest = build_run_manifest(
        as_of=as_of,
        data_mode="demo",
        model_name="Elo",
        policy_version="1.0.0",
        policy_hash="abc",
        pipeline_hash="def",
        config_hash="ghi",
        snapshot_ids=("snap-1",),
        validation_artifact_id="art-1",
        validation_status="unvalidated",
    )
    path = save_manifest(manifest, directory=tmp_path)
    before = path.read_text(encoding="utf-8")
    attach_settlement_event(
        run_id=manifest.run_id,
        tip_id="tip-1",
        event={"kind": "settle", "won": False},
        directory=tmp_path,
    )
    after = path.read_text(encoding="utf-8")
    assert before == after
    loaded = load_manifest(path)
    assert loaded.run_id == manifest.run_id
    assert loaded.snapshot_ids == ("snap-1",)
    assert loaded.as_of == as_of


def test_orchestrator_predict_writes_run_manifest(tmp_path: Path, monkeypatch) -> None:
    from quantbot import runs as runs_mod

    monkeypatch.setattr(runs_mod, "manifests_dir", lambda base=None: tmp_path)
    orch = QuantBotOrchestrator(provider=DummyDataProvider(), live=False)
    reports = orch.predict(League.PREMIER_LEAGUE, "2024-2025")
    assert orch.last_run_manifest is not None
    assert orch.last_run_manifest.data_mode == "demo"
    assert (tmp_path / f"{orch.last_run_manifest.run_id}.json").exists()
    assert isinstance(reports, list)


def test_clv_line_mismatch_and_post_kickoff_are_na() -> None:
    kick = datetime(2025, 2, 1, 15, 0, tzinfo=UTC)
    entry = EntryQuoteRef(
        decimal_odds=2.10,
        market_kind="1x2",
        line=None,
        period="FT",
        rules="90min",
        kickoff=kick,
    )
    bad_line = ClosingQuoteRef(
        decimal_odds=2.00,
        fair_probability=0.48,
        market_kind="1x2",
        line=2.5,
        period="FT",
        rules="90min",
        timestamp=kick - timedelta(minutes=5),
    )
    assert evaluate_clv(entry, bad_line).status is ClvStatus.NA_LINE_MISMATCH

    post = ClosingQuoteRef(
        decimal_odds=2.00,
        fair_probability=0.48,
        market_kind="1x2",
        timestamp=kick + timedelta(minutes=1),
        period="FT",
        rules="90min",
    )
    assert evaluate_clv(entry, post).status is ClvStatus.NA_POST_KICKOFF

    ok = ClosingQuoteRef(
        decimal_odds=1.95,
        fair_probability=0.50,
        market_kind="1x2",
        timestamp=kick - timedelta(minutes=10),
        period="FT",
        rules="90min",
    )
    result = evaluate_clv(entry, ok)
    assert result.status is ClvStatus.OK
    assert result.odds_ratio_clv == pytest.approx(2.10 / 1.95 - 1.0)
    assert result.closing_reference_ev == pytest.approx(closing_reference_ev(2.10, 0.50))
    assert evaluate_clv(entry, None).status is ClvStatus.NA_MISSING_CLOSE


def test_execution_simulator_exposes_closing_reference_ev() -> None:
    assert ExecutionSimulator.closing_reference_ev(2.0, 0.55) == pytest.approx(0.10)


def test_ah_quarter_settlement_prompt_examples() -> None:
    # AH -0.25 at draw → HALF_LOSS; AH +0.25 at draw → HALF_WIN
    home_fav = settle_line_market(
        kind=LineMarketKind.SPREAD,
        selection="home",
        line=-0.25,
        home_score=1,
        away_score=1,
        decimal_odds=1.90,
    )
    assert home_fav.status is SettlementStatus.HALF_LOSS
    assert home_fav.payoff_factor == pytest.approx(0.5)

    home_dog = settle_line_market(
        kind=LineMarketKind.SPREAD,
        selection="home",
        line=0.25,
        home_score=1,
        away_score=1,
        decimal_odds=1.90,
    )
    assert home_dog.status is SettlementStatus.HALF_WIN
    assert home_dog.payoff_factor == pytest.approx((1.90 + 1.0) / 2.0)

    # Over 2.25 with 2 goals → HALF_LOSS; Under 2.25 with 2 goals → HALF_WIN
    over = settle_line_market(
        kind=LineMarketKind.TOTALS,
        selection="over",
        line=2.25,
        home_score=1,
        away_score=1,
        decimal_odds=1.95,
    )
    assert over.status is SettlementStatus.HALF_LOSS
    under = settle_line_market(
        kind=LineMarketKind.TOTALS,
        selection="under",
        line=2.25,
        home_score=1,
        away_score=1,
        decimal_odds=1.95,
    )
    assert under.status is SettlementStatus.HALF_WIN


def test_market_settle_uses_push_for_whole_line() -> None:
    ts = datetime(2025, 1, 1, tzinfo=UTC)
    totals = Market(
        match_id="m",
        bookmaker="b",
        timestamp=ts,
        kind=MarketKind.TOTALS,
        outcomes=(
            MarketOutcome(name="over", line=2.0, price=1.9),
            MarketOutcome(name="under", line=2.0, price=1.9),
        ),
    )
    assert totals.settle("over", 1, 1) is SettlementStatus.VOID
    assert totals.payoff("over", 1, 1) == pytest.approx(1.0)


def test_quarter_tick_rejects_non_lattice() -> None:
    with pytest.raises(ValueError):
        require_quarter_tick(1.1)


def test_chronological_validation_demo_stays_unvalidated_without_criteria() -> None:
    provider = DummyDataProvider()
    matches = provider.get_matches(League.PREMIER_LEAGUE, "2024-2025", datetime(2100, 1, 1, tzinfo=UTC))
    split = chronological_split(matches, train_frac=0.5, calib_frac=0.2)
    assert split.train[-1].kickoff < split.test[0].kickoff
    artifact = run_chronological_validation(
        matches,
        EloModel(),
        scope="demo_pl",
        profile="demo",
        criteria=None,
        notes="synthetic — must not unlock live",
    )
    assert artifact.status is ValidationStatus.UNVALIDATED
    assert artifact.profile == "demo"
    assert artifact.n_test >= 0


def test_chronological_validation_demo_never_unlocks_live(tmp_path: Path) -> None:
    """Even a green demo artifact must not unlock live Kelly sizing."""

    from quantbot.analysis.validation import policy_from_artifact
    from quantbot.decision.policy import ValidationStatus as VS
    from quantbot.decision.policy import live_policy

    provider = DummyDataProvider()
    matches = provider.get_matches(
        League.PREMIER_LEAGUE, "2024-2025", datetime(2100, 1, 1, tzinfo=UTC)
    )
    artifact = run_chronological_validation(
        matches,
        EloModel(),
        scope="demo_pl",
        profile="demo",
        criteria=ValidationCriteria(min_n=1, max_brier=1.0),
        save=True,
        directory=tmp_path,
    )
    assert artifact.profile == "demo"
    unlocked = policy_from_artifact(artifact, base=live_policy())
    assert unlocked.validation_status is VS.UNVALIDATED


def test_tip_history_legacy_flag_and_clv_attach(tmp_path: Path) -> None:
    path = tmp_path / "tips.json"
    store = TipHistoryStore(path)
    tip = TipRecord(
        tip_id="t1",
        match_id="m1",
        kickoff="2025-01-01T00:00:00+00:00",
        league="premier_league",
        home="A",
        away="B",
        tip="home",
        odds=2.0,
        model_prob=0.5,
        as_of="2025-01-01T00:00:00+00:00",
        mode="demo",
        run_id="run-xyz",
    )
    store.append_new([tip])
    assert store.attach_clv(
        "t1",
        closing_odds=1.9,
        clv_odds_ratio=0.05,
        closing_reference_ev=0.01,
        clv_status=ClvStatus.OK.value,
    )
    loaded = TipHistoryStore(path).all_tips()[0]
    assert loaded.clv_status == ClvStatus.OK.value
    assert loaded.closing_odds == pytest.approx(1.9)

    # Legacy JSON without run_id
    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        '{"tips":[{"tip_id":"old","match_id":"m","kickoff":"2025-01-01T00:00:00+00:00",'
        '"league":"premier_league","home":"A","away":"B","tip":"home","odds":2.0,'
        '"model_prob":0.5,"as_of":"2025-01-01T00:00:00+00:00","mode":"demo",'
        '"settled":false,"actual":null,"correct":null}]}',
        encoding="utf-8",
    )
    old = TipHistoryStore(legacy).all_tips()[0]
    assert old.legacy_missing_provenance is True
