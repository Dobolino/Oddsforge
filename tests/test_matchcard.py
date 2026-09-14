"""Tests for the Match Card (Batch 1: consensus, uncertainty, divergence,
fair odds, data-quality breakdown, reliability, explanation)."""

from __future__ import annotations

from quantbot.analysis import build_match_card, divergence_tier
from quantbot.analysis.confidence import ConfidenceEvaluator, DataQualitySignals
from quantbot.orchestrator import QuantBotOrchestrator
from quantbot.schemas import League

SEASON = "2024-2025"


def test_divergence_tiers() -> None:
    assert divergence_tier(0.0) == "none"
    assert divergence_tier(0.03) == "slight"
    assert divergence_tier(0.06) == "interesting"
    assert divergence_tier(0.10) == "strong"
    assert divergence_tier(0.20) == "extreme"


def test_reliability_separate_from_probability() -> None:
    ev = ConfidenceEvaluator()
    strong = DataQualitySignals(home_matches=12, away_matches=12, n_bookmakers=5, injuries_known=True)
    weak = DataQualitySignals(home_matches=1, away_matches=1, n_bookmakers=1, injuries_known=False)
    hi, _ = ev.reliability_score(0.95, ev.data_quality(strong), 12)
    lo, _ = ev.reliability_score(0.30, ev.data_quality(weak), 1)
    assert 0.0 <= lo < hi <= 100.0


def test_data_quality_components() -> None:
    ev = ConfidenceEvaluator()
    comps = ev.data_quality_components(
        DataQualitySignals(home_matches=12, away_matches=12, n_bookmakers=3, injuries_known=True)
    )
    keys = {c["key"] for c in comps}
    assert keys == {"history", "market", "injuries", "liquidity"}
    history = next(c for c in comps if c["key"] == "history")
    assert history["ok"] is True


def test_orchestrator_builds_match_cards() -> None:
    cards = QuantBotOrchestrator().build_match_cards(League.PREMIER_LEAGUE, SEASON)
    assert cards
    card = cards[0]
    # Probabilities sum to ~1 and every block is populated.
    assert abs(sum(card.probs.values()) - 1.0) < 1e-6
    assert set(card.probs) == {"home", "draw", "away"}
    assert card.models  # per-model consensus rows
    assert 0.0 <= card.agreement <= 100.0
    assert 0.0 <= card.reliability <= 100.0
    assert set(card.fair_odds) == {"home", "draw", "away"}
    assert all("tier" in d for d in card.divergence.values())
    assert card.data_quality_components
    assert card.reasons  # at least the market-vs-model reason
    # Fair odds are the inverse of fair probabilities (sanity).
    assert card.fair_odds["home"] > 1.0


def test_match_card_to_dict_serializable() -> None:
    import json

    cards = QuantBotOrchestrator().build_match_cards(League.PREMIER_LEAGUE, SEASON)
    payload = cards[0].to_dict()
    # Round-trips through JSON (used by the dashboard and preview).
    assert json.loads(json.dumps(payload))["match_id"]


def test_match_card_reasons_bilingual() -> None:
    cards = QuantBotOrchestrator().build_match_cards(League.PREMIER_LEAGUE, SEASON)
    for reason in cards[0].reasons:
        assert reason["de"] and reason["en"]
