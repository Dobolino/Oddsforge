# Fortschritt: CURSOR_PROMPT_QUANTBOT (P0 → P1 → P2)

Stand: P0 fertig; P1 UX fertig auf Branch `cursor/p0-decision-policy-9483`.

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
| P1 UX | DONE (Begriffe, Validierung, Paper-UI, Demo/Hilfe) |
| P2 CLV / AH / Run-Manifest | MISSING |

## Verbleibende Arbeitspakete (grob)

1. **P2 Tracking / CLV / Run-Manifest**
2. **P2 AH Settlement** (experimental)
3. **Datenblocker** — echte chronologische VALID-Artefakte (nicht synthetisch)

≈ **1 Hauptphase** (P2) plus Datenblocker.

## Paket 1–4 — P0 (DONE)

DecisionPolicy · Snapshots/Integrität · ValidationArtifact/Shrinkage · Dixon-Coles-Gitter · PaperLedger

## Paket 5 — P1 UX (DONE)

1. „Tipp“ → Modellsignal; „Sicher“ entfernt; NO_BET → „Kein Signal“ / „Warum kein Signal?“
2. „Faire Wahrscheinlichkeit“ → Marktschätzung ohne Marge
3. „Gegen Markt“ → größere Abweichung (kein Vorteil)
4. Validierungs-Spalte; Stake nur bei Freigabe / sonst „—“
5. Kombi-Analyse: Einheiten statt €; volle „Keine belastbare Kombi-Wahrscheinlichkeit…“
6. Beginner ohne Kombi-Nav (bereits zuvor)
7. Papiersimulation-Seite (Advanced/Expert): Caps, Reservierung aus Kombi, Settle/Cancel
8. DEMO-Badge + Hilfe-Footer mit Glossar-Sprung

## Bewusst noch offen

- P2 CLV / AH Settlement / Run-Manifest
- Live-Dashboard Snapshots opt-in → default
- Chronologische Walk-Forward-Läufe für echte VALID-Artefakte

## Blocker

Ohne chronologische Validierungsdaten bleibt Live-Sizing gesperrt (`UNVALIDATED`).
