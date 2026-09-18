# Fortschritt: CURSOR_PROMPT_QUANTBOT (P0 → P1 → P2)

Stand: P0 Paket 1–3 + Dixon-Coles-Restmasse auf Branch `cursor/p0-decision-policy-9483`.

## Bestandsaufnahme (Kurz)

| Bereich | Status |
|---------|--------|
| DecisionPolicy zentral | DONE (v1.0.0) |
| High-Risk-Bypass | REMOVED |
| Slip Same-Match + ehrliche Kombi-P | DONE |
| SnapshotRepository | DONE (SQLite lokal) |
| Quoten-Integrität (stale/NaN/nach Anpfiff) | DONE (Live streng) |
| Kalibrierungs-Artefakt / Freigabe VALID | DONE (Schema + Gate; empirische Daten fehlen) |
| Shrinkage n_eff/(n_eff+k) | DONE (Option EFF_SAMPLE; Legacy erhalten) |
| Dixon-Coles Restmasse | DONE (adaptives Gitter, Tol 1e-8) |
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

## Paket 3 — Validierungsartefakt & Shrinkage

1. **`ValidationArtifact`** (`analysis/validation.py`)
   - Scope, Trainingsgrenze, Testfenster, Pipeline-/Policy-Hash, Fallzahlen, Kriterien, Metriken
   - Status nur `VALID` wenn Kriterien **vor** Test explizit gesetzt und alle Bounds passen
   - Ohne Kriterien → `UNVALIDATED` (keine erfundenen ECE-/Brier-Defaults)
   - Persistenz: JSON unter `models/validation/`
   - Demo-Artefakt validiert Live **nicht**; Scope-/Pipeline-Mismatch → `UNVALIDATED`
   - `EXPIRED`/`DEGRADED` geben kein Kelly frei
2. **`policy_from_artifact`** + Orchestrator-Parameter `validation_artifact`
3. **`ShrinkageMode`** (`analysis/engine.py`)
   - `OFF` | `LEGACY_DEPTH` (bisheriges `market_shrinkage=True`) | `EFF_SAMPLE`
   - EFF_SAMPLE: `w = n_eff / (n_eff + k)` mit `n_eff = (Σa)²/Σa²` oder konservativ `min(home, away)`
   - `k` nur auf Entwicklungsdaten bestimmen; Default heuristisch, kein Überlegenheitsanspruch
   - Audit: `p_raw_*`, `shrinkage_weight`, `shrinkage_mode` auf `AnalysisResult`

## Paket 3b — Dixon-Coles Restmasse

1. Beschreibung: unabhängige Poisson-Basis + Niedrigscore-Korrektur (`tau`)
2. **`build_score_grid`**: adaptives `max_goals` bis `independent_rest_mass <= 1e-8`
3. Cap `max_goals_cap` (Default 40) → Status `GRID_LIMIT` (optional `raise_on_grid_limit`)
4. Tau-Positivität/Endlichkeit geprüft; sonst Fallback auf unabhängiges Gitter (`TAU_INVALID`)
5. Renormalisierung nur auf behaltenem Support; Restmasse bleibt im Audit-Feld sichtbar

## Bewusst noch offen

- Papier-Ledger / Exposure-Caps
- P1 UX-Umbenennungen
- P2 CLV / AH Settlement / Run-Manifest
- Live-Dashboard standardmäßig Snapshots persistieren (Flag noch opt-in)
- Chronologische Walk-Forward-Läufe, die echte VALID-Artefakte erzeugen (Datenblocker)

## Blocker

Ohne chronologische Validierungsdaten bleibt Live-Sizing gesperrt (`UNVALIDATED`).  
Historische Provider-Dumps (`historical_import`) sind kein stilles Live-Replay.  
Synthetische Fixtures erzeugen **kein** VALID-Artefakt für den Live-Pfad.
