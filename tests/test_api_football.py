"""API-Football provider: status probe, market summary, odds parsing.

All offline via ``httpx.MockTransport``. The sample payload mirrors the v3
``/odds`` envelope (``response[].bookmakers[].bets[].values[]``) so the parser
is exercised against the real shape without a live key.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from quantbot.data.providers.api_football import (
    AccountStatus,
    ApiFootballError,
    ApiFootballProvider,
)

UTC = timezone.utc

STATUS_PAYLOAD = {
    "get": "status",
    "errors": [],
    "response": {
        "account": {"firstname": "Alex", "lastname": "D", "email": "a@example.com"},
        "subscription": {"plan": "Free", "active": True},
        "requests": {"current": 12, "limit_day": 100},
    },
}

ODDS_PAYLOAD = {
    "get": "odds",
    "errors": [],
    "response": [
        {
            "fixture": {"id": 867946},
            "update": "2026-09-18T09:00:00+00:00",
            "bookmakers": [
                {
                    "id": 8,
                    "name": "Bet365",
                    "bets": [
                        {
                            "id": 1,
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": "2.10"},
                                {"value": "Draw", "odd": "3.40"},
                                {"value": "Away", "odd": "3.60"},
                            ],
                        },
                        {
                            "id": 4,
                            "name": "Asian Handicap",
                            # Real API-Football format: both sides carry the same
                            # signed line from the home team's perspective.
                            "values": [
                                {"value": "Home -0.5", "odd": "1.78"},
                                {"value": "Away -0.5", "odd": "2.02"},
                                {"value": "Home -1.5", "odd": "3.10"},
                                {"value": "Away -1.5", "odd": "1.36"},
                                # Quarter line: must be ignored (can push).
                                {"value": "Home -0.75", "odd": "2.00"},
                                {"value": "Away -0.75", "odd": "1.80"},
                                # Whole line: must be ignored (can push).
                                {"value": "Home -1", "odd": "2.35"},
                                {"value": "Away -1", "odd": "1.58"},
                            ],
                        },
                        {
                            "id": 5,
                            "name": "Goals Over/Under",
                            "values": [
                                {"value": "Over 2.5", "odd": "1.85"},
                                {"value": "Under 2.5", "odd": "1.95"},
                                {"value": "Over 3.5", "odd": "2.90"},
                                {"value": "Under 3.5", "odd": "1.40"},
                            ],
                        },
                    ],
                }
            ],
        }
    ],
}


def _client(payload: dict, counter: list[int] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if counter is not None:
            counter[0] += 1
        assert request.headers.get("x-apisports-key") == "secret-key"
        if request.url.path == "/status":
            return httpx.Response(200, json=STATUS_PAYLOAD)
        return httpx.Response(200, json=payload)

    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://v3.football.api-sports.io",
    )


def _provider(payload: dict, tmp_path, counter: list[int] | None = None) -> ApiFootballProvider:
    return ApiFootballProvider(
        "secret-key", cache_dir=tmp_path, client=_client(payload, counter)
    )


def test_status_reports_account_and_quota(tmp_path) -> None:
    status = _provider(ODDS_PAYLOAD, tmp_path).fetch_status()
    assert isinstance(status, AccountStatus)
    assert status.account == "Alex D"
    assert status.plan == "Free"
    assert status.requests_used == 12
    assert status.requests_limit == 100
    assert status.requests_left == 88


def test_key_travels_in_header_not_url(tmp_path) -> None:
    # The handler asserts the header; a missing header would raise inside it.
    _provider(ODDS_PAYLOAD, tmp_path).fetch_status()


def test_api_errors_raise(tmp_path) -> None:
    bad = {"errors": {"token": "invalid API key"}, "response": []}
    provider = ApiFootballProvider(
        "secret-key",
        cache_dir=tmp_path,
        client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=bad)),
            base_url="https://v3.football.api-sports.io",
        ),
    )
    with pytest.raises(ApiFootballError, match="invalid API key"):
        provider.fetch_odds(fixture=1)


def test_summarize_markets_lists_raw_labels(tmp_path) -> None:
    payload = _provider(ODDS_PAYLOAD, tmp_path).fetch_odds(fixture=867946)
    summaries = _provider(ODDS_PAYLOAD, tmp_path).summarize_markets(payload)
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.fixture_id == 867946
    assert summary.has_market("Asian Handicap")
    assert summary.has_market("Goals Over/Under")
    bet365 = summary.bookmakers["Bet365"]
    ah = next(b for b in bet365 if b.bet_name == "Asian Handicap")
    assert "Home -0.5 @ 1.78" in ah.sample_values


def test_parse_asian_handicap_pairs_half_lines(tmp_path) -> None:
    payload = _provider(ODDS_PAYLOAD, tmp_path).fetch_odds(fixture=867946)
    spreads = _provider(ODDS_PAYLOAD, tmp_path).parse_asian_handicap(payload, "m1")
    lines = sorted(s.line for s in spreads)
    # -1.5 and -0.5 survive; -0.75 (quarter) and -1.0 (whole) are dropped.
    assert lines == [-1.5, -0.5]
    half = next(s for s in spreads if s.line == -0.5)
    assert half.match_id == "m1"
    assert half.bookmaker == "Bet365"
    assert half.home == pytest.approx(1.78)
    assert half.away == pytest.approx(2.02)
    assert half.timestamp == datetime(2026, 9, 18, 9, 0, tzinfo=UTC)


def test_parse_totals_selects_line(tmp_path) -> None:
    payload = _provider(ODDS_PAYLOAD, tmp_path).fetch_odds(fixture=867946)
    totals = _provider(ODDS_PAYLOAD, tmp_path).parse_totals(payload, "m1", line=2.5)
    assert len(totals) == 1
    quote = totals[0]
    assert quote.line == 2.5
    assert quote.over == pytest.approx(1.85)
    assert quote.under == pytest.approx(1.95)


def test_parse_totals_other_line(tmp_path) -> None:
    payload = _provider(ODDS_PAYLOAD, tmp_path).fetch_odds(fixture=867946)
    totals = _provider(ODDS_PAYLOAD, tmp_path).parse_totals(payload, "m1", line=3.5)
    assert len(totals) == 1
    assert totals[0].over == pytest.approx(2.90)


def test_fetch_odds_requires_a_selector(tmp_path) -> None:
    with pytest.raises(ValueError, match="fixture/league/date"):
        _provider(ODDS_PAYLOAD, tmp_path).fetch_odds()
