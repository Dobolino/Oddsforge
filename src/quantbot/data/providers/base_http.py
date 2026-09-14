"""Shared HTTP plumbing for API data providers: file cache and rate limiter.

Both are injectable-clock friendly so tests stay deterministic and offline.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quantbot.logging import get_logger

logger = get_logger(__name__)


class RateLimitError(RuntimeError):
    """Raised when a network call is attempted before the minimum interval."""


class FileCache:
    """A tiny JSON file cache with a per-entry TTL.

    Args:
        directory: Where cache files are written.
        ttl_seconds: Entries older than this are treated as missing.
        time_fn: Injectable wall-clock (defaults to ``time.time``).
    """

    def __init__(
        self,
        directory: Path,
        ttl_seconds: float = 3600.0,
        time_fn: Callable[[], float] = time.time,
    ) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self._time_fn = time_fn

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.directory / f"{digest}.json"

    def get(self, key: str) -> Any | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if self._time_fn() - float(payload.get("ts", 0.0)) > self.ttl_seconds:
            logger.debug("Cache expired for %s", key)
            return None
        return payload.get("data")

    def set(self, key: str, data: Any) -> None:
        path = self._path(key)
        path.write_text(
            json.dumps({"ts": self._time_fn(), "data": data}), encoding="utf-8"
        )


class RateLimiter:
    """Enforces a minimum interval between successful network calls.

    Args:
        min_interval: Minimum seconds between calls (0 disables limiting).
        monotonic_fn: Injectable monotonic clock (defaults to ``time.monotonic``).
    """

    def __init__(
        self,
        min_interval: float = 0.0,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = min_interval
        self._monotonic = monotonic_fn
        self._last: float | None = None

    def acquire(self) -> None:
        if self.min_interval <= 0.0:
            return
        now = self._monotonic()
        if self._last is not None and (now - self._last) < self.min_interval:
            raise RateLimitError(
                f"rate limit: {self.min_interval}s between calls not elapsed"
            )
        self._last = now
