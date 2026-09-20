"""Local SQLite repository for immutable market / decision snapshots.

Point-in-time semantics (documented, not inferred from filenames):

- ``source_timestamp``: when the quote/version was valid at the provider.
- ``available_at``: when that version was known to be published (may equal
  source_timestamp when the provider gives no separate publication time).
- ``fetched_at``: when this process locally persisted the row (UTC).

``fetched_at`` today does **not** make a historical payload automatically
usable for live-replay. Rows tagged ``historical_import`` are a separate
backtest mode and must not silently substitute current quotes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from quantbot.schemas import Odds, TotalsOdds

SCHEMA_VERSION = 1


class DataMode(str, Enum):
    DEMO = "demo"
    LIVE_REPLAY = "live_replay"
    HISTORICAL_IMPORT = "historical_import"


def snapshot_db_path(*, base: Path | None = None) -> Path:
    """Default under ``~/.quantbot/snapshots`` so archives survive app updates."""

    root = Path(base) if base is not None else Path.home() / ".quantbot" / "snapshots"
    return root / "snapshots.sqlite3"


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _redact_endpoint(endpoint: str) -> str:
    """Strip query strings that might contain API keys."""

    cleaned = endpoint.split("?", 1)[0].strip()
    for token in ("apiKey=", "api_key=", "apikey=", "token=", "key="):
        if token.lower() in endpoint.lower():
            return cleaned + "?[redacted]"
    return cleaned or "unknown"


def _content_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StoredSnapshot:
    snapshot_id: str
    content_hash: str
    provider: str
    endpoint: str
    data_mode: DataMode
    match_id: str
    market_kind: str
    period: str
    line: float | None
    bookmaker: str | None
    selection_payload: dict[str, Any]
    source_timestamp: datetime
    available_at: datetime | None
    fetched_at: datetime
    schema_version: int = SCHEMA_VERSION


class SnapshotRepository:
    """Transactional local snapshot store (no server DB)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else snapshot_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    data_mode TEXT NOT NULL,
                    match_id TEXT NOT NULL,
                    market_kind TEXT NOT NULL,
                    period TEXT NOT NULL DEFAULT 'full_time',
                    line REAL,
                    bookmaker TEXT,
                    selection_payload TEXT NOT NULL,
                    source_timestamp TEXT NOT NULL,
                    available_at TEXT,
                    fetched_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_snap_match_time
                    ON market_snapshots(match_id, source_timestamp);
                CREATE INDEX IF NOT EXISTS idx_snap_mode
                    ON market_snapshots(data_mode, match_id);
                """
            )
            conn.commit()

    def put_odds(
        self,
        odds: Odds,
        *,
        provider: str,
        endpoint: str,
        data_mode: DataMode,
        fetched_at: datetime | None = None,
        available_at: datetime | None = None,
        period: str = "full_time",
    ) -> StoredSnapshot:
        fetched = fetched_at or datetime.now(timezone.utc)
        payload = {
            "home": odds.home,
            "draw": odds.draw,
            "away": odds.away,
            "kind": odds.kind.value,
            "is_closing": odds.is_closing,
        }
        return self._insert(
            provider=provider,
            endpoint=endpoint,
            data_mode=data_mode,
            match_id=odds.match_id,
            market_kind=odds.kind.value,
            period=period,
            line=None,
            bookmaker=odds.bookmaker,
            selection_payload=payload,
            source_timestamp=odds.timestamp,
            available_at=available_at or odds.timestamp,
            fetched_at=fetched,
        )

    def put_totals(
        self,
        odds: TotalsOdds,
        *,
        provider: str,
        endpoint: str,
        data_mode: DataMode,
        fetched_at: datetime | None = None,
        available_at: datetime | None = None,
        period: str = "full_time",
    ) -> StoredSnapshot:
        fetched = fetched_at or datetime.now(timezone.utc)
        payload = {
            "over": odds.over,
            "under": odds.under,
            "line": odds.line,
            "kind": "totals",
        }
        return self._insert(
            provider=provider,
            endpoint=endpoint,
            data_mode=data_mode,
            match_id=odds.match_id,
            market_kind="totals",
            period=period,
            line=float(odds.line),
            bookmaker=odds.bookmaker,
            selection_payload=payload,
            source_timestamp=odds.timestamp,
            available_at=available_at or odds.timestamp,
            fetched_at=fetched,
        )

    def _insert(
        self,
        *,
        provider: str,
        endpoint: str,
        data_mode: DataMode,
        match_id: str,
        market_kind: str,
        period: str,
        line: float | None,
        bookmaker: str | None,
        selection_payload: dict[str, Any],
        source_timestamp: datetime,
        available_at: datetime | None,
        fetched_at: datetime,
    ) -> StoredSnapshot:
        redacted = _redact_endpoint(endpoint)
        digest_body = {
            "provider": provider,
            "endpoint": redacted,
            "data_mode": data_mode.value,
            "match_id": match_id,
            "market_kind": market_kind,
            "period": period,
            "line": line,
            "bookmaker": bookmaker,
            "selection_payload": selection_payload,
            "source_timestamp": _utc_iso(source_timestamp),
            "available_at": None if available_at is None else _utc_iso(available_at),
        }
        digest = _content_hash(digest_body)
        snapshot_id = f"snap_{digest[:24]}_{uuid4().hex[:8]}"
        row = StoredSnapshot(
            snapshot_id=snapshot_id,
            content_hash=digest,
            provider=provider,
            endpoint=redacted,
            data_mode=data_mode,
            match_id=match_id,
            market_kind=market_kind,
            period=period,
            line=line,
            bookmaker=bookmaker,
            selection_payload=selection_payload,
            source_timestamp=source_timestamp.astimezone(timezone.utc),
            available_at=None if available_at is None else available_at.astimezone(timezone.utc),
            fetched_at=fetched_at.astimezone(timezone.utc),
            schema_version=SCHEMA_VERSION,
        )
        with self._connect() as conn:
            # Idempotent on identical content: reuse existing hash for same match/mode.
            existing = conn.execute(
                """
                SELECT snapshot_id FROM market_snapshots
                WHERE content_hash = ? AND match_id = ? AND data_mode = ?
                LIMIT 1
                """,
                (digest, match_id, data_mode.value),
            ).fetchone()
            if existing:
                return self.get(existing["snapshot_id"])  # type: ignore[return-value]
            conn.execute(
                """
                INSERT INTO market_snapshots (
                    snapshot_id, content_hash, provider, endpoint, data_mode,
                    match_id, market_kind, period, line, bookmaker,
                    selection_payload, source_timestamp, available_at, fetched_at,
                    schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.snapshot_id,
                    row.content_hash,
                    row.provider,
                    row.endpoint,
                    row.data_mode.value,
                    row.match_id,
                    row.market_kind,
                    row.period,
                    row.line,
                    row.bookmaker,
                    json.dumps(row.selection_payload, ensure_ascii=False),
                    _utc_iso(row.source_timestamp),
                    None if row.available_at is None else _utc_iso(row.available_at),
                    _utc_iso(row.fetched_at),
                    row.schema_version,
                ),
            )
            conn.commit()
        return row

    def get(self, snapshot_id: str) -> StoredSnapshot | None:
        with self._connect() as conn:
            raw = conn.execute(
                "SELECT * FROM market_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        return None if raw is None else self._row_to_snapshot(raw)

    def count(self, *, data_mode: DataMode | None = None) -> int:
        """Number of stored rows (optional filter by :class:`DataMode`)."""

        with self._connect() as conn:
            if data_mode is None:
                row = conn.execute("SELECT COUNT(*) AS n FROM market_snapshots").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM market_snapshots WHERE data_mode = ?",
                    (data_mode.value,),
                ).fetchone()
        return int(row["n"]) if row is not None else 0

    def list_for_match(
        self,
        match_id: str,
        *,
        as_of: datetime | None = None,
        data_mode: DataMode | None = None,
    ) -> list[StoredSnapshot]:
        """Snapshots for a match, optionally only those available at ``as_of``.

        Availability uses ``available_at`` when set, else ``source_timestamp``.
        Boundary is inclusive (``<= as_of``) — same as Odds provider filtering.
        """

        clauses = ["match_id = ?"]
        params: list[Any] = [match_id]
        if data_mode is not None:
            clauses.append("data_mode = ?")
            params.append(data_mode.value)
        sql = "SELECT * FROM market_snapshots WHERE " + " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        out = [self._row_to_snapshot(r) for r in rows]
        if as_of is not None:
            if as_of.tzinfo is None:
                raise ValueError("as_of must be timezone-aware")
            cutoff = as_of.astimezone(timezone.utc)

            def _available(s: StoredSnapshot) -> datetime:
                return s.available_at or s.source_timestamp

            out = [s for s in out if _available(s) <= cutoff]
        return sorted(out, key=lambda s: s.source_timestamp)

    def latest_for_match(
        self,
        match_id: str,
        *,
        as_of: datetime,
        data_mode: DataMode | None = None,
        market_kind: str = "1x2",
    ) -> StoredSnapshot | None:
        rows = [
            s
            for s in self.list_for_match(match_id, as_of=as_of, data_mode=data_mode)
            if s.market_kind == market_kind
        ]
        return rows[-1] if rows else None

    @staticmethod
    def _row_to_snapshot(raw: sqlite3.Row) -> StoredSnapshot:
        return StoredSnapshot(
            snapshot_id=raw["snapshot_id"],
            content_hash=raw["content_hash"],
            provider=raw["provider"],
            endpoint=raw["endpoint"],
            data_mode=DataMode(raw["data_mode"]),
            match_id=raw["match_id"],
            market_kind=raw["market_kind"],
            period=raw["period"],
            line=raw["line"],
            bookmaker=raw["bookmaker"],
            selection_payload=json.loads(raw["selection_payload"]),
            source_timestamp=datetime.fromisoformat(raw["source_timestamp"]),
            available_at=(
                None
                if raw["available_at"] is None
                else datetime.fromisoformat(raw["available_at"])
            ),
            fetched_at=datetime.fromisoformat(raw["fetched_at"]),
            schema_version=int(raw["schema_version"]),
        )
