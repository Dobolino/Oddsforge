"""Read-only credential checks for the Settings page."""

from __future__ import annotations

from typing import Literal

import httpx

ConnectionStatus = Literal["active", "missing", "invalid", "rate_limited", "unavailable"]


def test_connection(
    provider: Literal["football_data", "the_odds_api"],
    key: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ConnectionStatus:
    """Check a harmless provider endpoint without returning secrets or URLs."""

    if not key.strip():
        return "missing"
    if provider == "football_data":
        url = "https://api.football-data.org/v4/competitions/PL"
        params: dict[str, str] = {}
        headers = {"X-Auth-Token": key}
    elif provider == "the_odds_api":
        url = "https://api.the-odds-api.com/v4/sports"
        params = {"apiKey": key}
        headers = {}
    else:
        raise ValueError(f"unsupported provider: {provider}")

    try:
        with httpx.Client(timeout=8.0, transport=transport) as client:
            response = client.get(url, params=params, headers=headers)
    except httpx.RequestError:
        return "unavailable"
    if response.status_code in (401, 403):
        return "invalid"
    if response.status_code == 429:
        return "rate_limited"
    return "active" if response.is_success else "unavailable"
