# Fortschritt: CURSOR_PROMPT_QUANTBOT (P0 → P1 → P2)

Stand: P0 Paket 1–4 (Ledger) auf Branch `cursor/p0-decision-policy-9483`.

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
| Papier-Ledger / Exposure-Caps | DONE (SQLite; Caps heuristisch) |
| P1 UX | MISSING |
| P2 CLV / AH / Run-Manifest | MISSING |

## Paket 1 — DecisionPolicy

1. **DecisionPolicy** (`decision/policy.py`, Version `1.0.0`)
2. Status: `INVALID_DATA` · `NO_BET` · `VALUE_EXPLORATORY` · `VALUE_RELEASED`
3. `UNVALIDATED` → kein Kelly-Sizing
4. High-Risk entfernt; Slip: 1 Bein/Match; Kombi-Chance nicht belastbar

## Paket 2 — Snapshots & Integrität

1. **`SnapshotRepository`** (`data/snapshot_repo.py`) — SQLite unter `data/snapshots/`
2. **`markets/integrity.py`** — Prematch-Checks → `INVALID_DATA_*`
3. Orchestrator optional: `persist_snapshots=True`

## Paket 3 — Validierungsartefakt & Shrinkage

1. **`ValidationArtifact`** (`analysis/validation.py`) — VALID nur mit expliziten Kriterien
2. **`ShrinkageMode`**: `OFF` | `LEGACY_DEPTH` | `EFF_SAMPLE`

## Paket 3b — Dixon-Coles Restmasse

1. Adaptives Gitter bis `independent_rest_mass <= 1e-8`
2. Status `GRID_LIMIT` / `TAU_INVALID`; Restmasse im Audit sichtbar

## Paket 4 — Papier-Ledger & Exposure-Caps

1. **`PaperLedger`** (`ledger/__init__.py`) — SQLite unter `data/ledger/{mode}.sqlite3`
2. Caps vs Papierkapitalbasis (Default 1000): ≤5 % pro Match, ≤10 % offen gesamt
3. Kombi: Einsatz einmal im Open-Total, voll je Match für Event-Cap
4. `preview` schreibt nicht; `commit` idempotent über `client_key` (keine Doppelbuchung bei Reruns)
5. Settlement/Cancel/Void; Turnover getrennt messbar; keine Reinvestition unabgerechneter Gewinne
6. Tip-History bleibt getrennt (Hit-Rate ≠ Geld)

## Bewusst noch offen

- P1 UX-Umbenennungen / Ledger-UI-Verdrahtung
- P2 CLV / AH Settlement / Run-Manifest
- Live-Dashboard standardmäßig Snapshots persistieren (Flag noch opt-in)
- Chronologische Walk-Forward-Läufe für echte VALID-Artefakte (Datenblocker)

## Blocker

Ohne chronologische Validierungsdaten bleibt Live-Sizing gesperrt (`UNVALIDATED`).  
Historische Provider-Dumps (`historical_import`) sind kein stilles Live-Replay.  
Synthetische Fixtures erzeugen **kein** VALID-Artefakt für den Live-Pfad.
