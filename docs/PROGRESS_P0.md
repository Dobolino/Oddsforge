# Fortschritt: CURSOR_PROMPT_QUANTBOT (P0 → P1 → P2)

Stand: erste P0-Lieferung auf Branch `cursor/p0-decision-policy-9483`.

## Bestandsaufnahme (Kurz)

| Bereich | Status vor diesem Paket |
|---------|-------------------------|
| DecisionEngine + NoBetRules | EXISTS — aber mehrere Konstruktoren (Orchestrator/Tracker/Backtest/Slip) |
| Demo vs Live Policy | PARTIAL — Tracker lasch, Hauptpfad gleich |
| High-Risk-Bypass | EXISTS (zu entfernen) |
| Kalibrierungs-Artefakt / Freigabe | MISSING |
| SnapshotRepository | MISSING |
| Same-Match-Sperre | PARTIAL |
| Kombi-P ehrlich | PARTIAL |

Baseline vor Änderung: decision/slip/tracking-Tests grün.

## In diesem Paket umgesetzt

1. **DecisionPolicy** (`decision/policy.py`, Version `1.0.0`)
   - Profile `live` / `demo` (+ explizites `demo_tracker_policy`)
   - Status: `INVALID_DATA`, `NO_BET`, `VALUE_EXPLORATORY`, `VALUE_RELEASED`
   - ValidationStatus: default `UNVALIDATED` → **kein Kelly-Sizing** (explorative VALUE_* möglich, `stake_fraction=0`)
2. **DecisionEngine** nutzt Policy; Orchestrator/Dashboard/`live=` verdrahtet; Tracker nutzt `demo_tracker_policy`
3. **High-Risk-Schalter entfernt** (UI + Builder); alte Session-Keys werden verworfen
4. **Slip:** max. 1 Bein/Match; Kombi-Chance = „nicht belastbar“; Unabhängigkeits-Produkt nur als Diagnostik
5. ValueSignal-Auditfelder: `policy_version`, `policy_profile`, `validation_status`, `decision_status`, `sizing_allowed`, `p_final`

## Bewusst noch offen (nächste Pakete)

- SnapshotRepository / Point-in-Time Persistenz
- Empirisches Validierungsartefakt (VALID/EXPIRED) + Kriterien
- Shrinkage-Alternative `n/(n+k)`, Dixon-Coles Restmasse
- Papier-Ledger / Exposure-Caps
- P1 UX-Umbenennungen (Tipp→Modellsignal, Sicher weg, …)
- P2 CLV / AH Settlement / Run-Manifest

## Blocker

Ohne chronologische Validierungsdaten bleibt Live-Sizing gesperrt (`UNVALIDATED`). Das ist beabsichtigt — keine erfundene Freigabe.
