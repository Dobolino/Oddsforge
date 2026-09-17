"""Settings connection checks classify provider responses without exposing keys."""

from __future__ import annotations

import httpx
import pytest

from quantbot.dashboard.connection import test_connection as check_connection
from quantbot.data.providers.base_http import get_with_rate_limit_retry


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(200, "active"), (401, "invalid"), (403, "invalid"),
     (429, "rate_limited"), (503, "unavailable")],
)
def test_connection_status(status_code: int, expected: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Auth-Token"] == "secret"
        return httpx.Response(status_code)

    transport = httpx.MockTransport(handler)
    assert check_connection("football_data", "secret", transport=transport) == expected


def test_missing_key_does_not_call_provider() -> None:
    transport = httpx.MockTransport(lambda _request: pytest.fail("unexpected request"))
    assert check_connection("the_odds_api", "", transport=transport) == "missing"


def test_rate_limit_retry_respects_retry_after() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0.5"})
        return httpx.Response(200)

    with httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler)) as client:
        response = get_with_rate_limit_retry(client, "/", params={}, sleep_fn=delays.append)
    assert response.status_code == 200
    assert attempts == 2
    assert delays == [0.5]
