# Fortschritt: CURSOR_PROMPT_QUANTBOT (P0 → P1 → P2)

Stand: P0 Paket 1+2 auf Branch `cursor/p0-decision-policy-9483`.

## Bestandsaufnahme (Kurz)

| Bereich | Status |
|---------|--------|
| DecisionPolicy zentral | DONE (v1.0.0) |
| High-Risk-Bypass | REMOVED |
| Slip Same-Match + ehrliche Kombi-P | DONE |
| SnapshotRepository | DONE (SQLite lokal) |
| Quoten-Integrität (stale/NaN/nach Anpfiff) | DONE (Live streng) |
| Kalibrierungs-Artefakt / Freigabe VALID | MISSING |
| Shrinkage n/(n+k), Dixon-Coles Restmasse | MISSING |
| Papier-Ledger / Exposure-Caps | MISSING |
| P1 UX | MISSING |
| P2 CLV / AH / Run-Manifest | MISSING |

## Paket 1 — DecisionPolicy

1. **DecisionPolicy** (`decision/policy.py`, Version `1.0.0`)
2. Status: `INVALID_DATA` · `NO_BET` · `VALUE_EXPLORATORY` · `VALUE_RELEASED`
3. `UNVALIDATED` → kein Kelly-Sizing
4. High-Risk entfernt; Slip: 1 Bein/Match; Kombi-Chance nicht belastbar

## Paket 2 — Snapshots & Integrität

1. **`SnapshotRepository`** (`data/snapshot_repo.py`) — SQLite unter `data/snapshots/`
   - Felder: provider, redacted endpoint, data_mode (`demo` / `live_replay` / `historical_import`),
     match/market/line/bookmaker, payload, `source_timestamp`, `available_at`, `fetched_at`, hash
   - `as_of`-Filter über `available_at` (sonst source); Grenze inklusiv `<=`
   - Secrets in Query-Strings werden nicht persistiert
2. **`markets/integrity.py`** — Prematch-Checks → `INVALID_DATA_*`
   - NaN/Inf, Quote ≤1, Quote nach Anpfiff, Stale (Default 24h, heuristisch)
   - Live: kickoff + age enforced; Demo: age/kickoff gelockert (kein False-Positive auf Mid-Season-as_of)
3. Orchestrator kann optional Snapshots schreiben (`persist_snapshots=True`)

## Bewusst noch offen

- Empirisches Validierungsartefakt (VALID/EXPIRED) + Kriterien
- Shrinkage-Alternative `n/(n+k)`, Dixon-Coles Restmasse
- Papier-Ledger / Exposure-Caps
- P1 UX-Umbenennungen
- P2 CLV / AH Settlement / Run-Manifest
- Live-Dashboard standardmäßig Snapshots persistieren (Flag noch opt-in)

## Blocker

Ohne chronologische Validierungsdaten bleibt Live-Sizing gesperrt (`UNVALIDATED`).  
Historische Provider-Dumps (`historical_import`) sind kein stilles Live-Replay.
