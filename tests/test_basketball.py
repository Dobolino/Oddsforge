"""Basketball model, provider, and leakage-safe odds."""

from __future__ import annotations

from datetime import datetime, timezone

from quantbot.data.basketball import BasketballDataProvider
from quantbot.data.basketball_demo import build_nba_matches, build_nba_odds, build_nba_totals
from quantbot.models.basketball import BasketballModel
from quantbot.orchestrator import QuantBotOrchestrator
from quantbot.schemas import League
from quantbot.schemas.enums import DEFAULT_NBA_TOTALS_LINE, Sport


def test_nba_demo_has_finished_and_upcoming() -> None:
    matches = build_nba_matches()
    assert len(matches) >= 15
    assert all(m.sport is Sport.BASKETBALL for m in matches)
    assert sum(1 for m in matches if m.is_finished) >= 5
    assert sum(1 for m in matches if not m.is_finished) >= 3


def test_nba_odds_snapshots_available_before_tipoff() -> None:
    matches = build_nba_matches()
    upcoming = [m for m in matches if not m.is_finished][0]
    odds = build_nba_odds([upcoming])[upcoming.match_id]
    assert len(odds) >= 4
    leads = sorted((upcoming.kickoff - o.timestamp).total_seconds() for o in odds)
    assert leads[-1] > 0
    assert max(leads) >= 24 * 3600


def test_basketball_provider_masks_future_odds() -> None:
    provider = BasketballDataProvider()
    as_of = datetime(2024, 12, 1, tzinfo=timezone.utc)
    upcoming = provider.get_upcoming_matches(League.NBA, "2024-2025", as_of)
    assert upcoming
    # Opening line (72h) may exist for near games; far games must stay empty.
    far = [m for m in upcoming if (m.kickoff - as_of).days >= 5]
    if far:
        assert provider.get_latest_odds(far[0].match_id, as_of) is None


def test_basketball_model_probabilities_sum_and_totals() -> None:
    provider = BasketballDataProvider()
    orch = QuantBotOrchestrator(provider=provider)
    as_of = orch.default_as_of(League.NBA, "2024-2025")
    universe = orch.universe(League.NBA, "2024-2025")
    model = BasketballModel()
    model.fit_until(universe, as_of)
    match = next(m for m in provider.get_upcoming_matches(League.NBA, "2024-2025", as_of))
    pred = model.predict(match)
    total = pred.prob_home + pred.prob_draw + pred.prob_away
    assert abs(total - 1.0) < 1e-9
    assert pred.prob_draw < 1e-3
    p_over, p_under = model.totals_probabilities(match, line=DEFAULT_NBA_TOTALS_LINE)
    assert abs(p_over + p_under - 1.0) < 1e-9
    p_hc, p_ac = model.spread_probabilities(match, line=-3.5)
    assert abs(p_hc + p_ac - 1.0) < 1e-9


def test_orchestrator_predicts_nba_value_signals() -> None:
    orch = QuantBotOrchestrator(provider=BasketballDataProvider())
    reports = orch.predict(League.NBA, "2024-2025")
    assert reports
    assert all(r.match.league is League.NBA for r in reports)
    assert any(r.signal.is_bet for r in reports)


def test_nba_totals_line_in_demo() -> None:
    matches = build_nba_matches()
    totals = build_nba_totals(matches[:1])
    snap = next(iter(totals.values()))[0]
    assert snap.line == DEFAULT_NBA_TOTALS_LINE
