# Fortschritt: CURSOR_PROMPT_QUANTBOT (P0 → P1 → P2)

Stand: P0 + P1 + **P2 Kern** auf Branch `cursor/p2-clv-manifest-valid-9483`
(basiert auf `cursor/p0-decision-policy-9483`).

## Bestandsaufnahme (Kurz)

| Bereich | Status |
|---------|--------|
| DecisionPolicy zentral | DONE |
| Snapshots / Quoten-Integrität | DONE |
| ValidationArtifact Schema + Gate | DONE |
| Shrinkage EFF_SAMPLE | DONE |
| Dixon-Coles Restmasse | DONE |
| PaperLedger Caps | DONE |
| P1 UX | DONE |
| Run-Manifest | DONE |
| CLV Comparability + closing_reference_ev | DONE |
| Chronologischer VALID-Runner + CLI | DONE |
| AH Settlement (typed, experimental flag) | DONE (Math); Signale noch nicht verdrahtet |
| Empirische Live-VALID-Daten | **BLOCKER** |

## P2 geliefert

1. **Run-Manifest** (`quantbot.runs`) — Run-ID, as_of, Snapshot-IDs, Pipeline-/Policy-/Config-Hash, Validation-Ref; Settlement nur als Folgeereignis (Manifest unverändert)
2. **CLV** (`quantbot.markets.clv`) — N/A bei Line/Markt/Period/Post-Kickoff; Odds-Ratio und `closing_reference_ev` getrennt; TipHistory `attach_clv`
3. **VALID-Runner** (`quantbot.analysis.validation_run` + `quantbot validate`) — chronologisches Train/Calib/Test; ohne vorab gesetzte Criteria → UNVALIDATED; Demo validiert nie Live
4. **AH Settlement** — PUSH/HALF_WIN/HALF_LOSS + Viertellinien; `enable_ah_experimental=False`; kein AH-Kelly ohne generalized Kelly + AH-VALID

## Blocker (ehrlich)

Ohne echte chronologische Live-Daten und **vorab** festgelegte Criteria gibt es kein Live-`VALID`-Artefakt → Live-Sizing bleibt gesperrt. Synthetische/Demo-Läufe dürfen das nicht freischalten.

## Bewusst zurückgestellt

- AH Value-Signale in DecisionEngine (Flag existiert; Sizing absichtlich aus)
- Live Closing-Quotes (`is_closing`) aus Provider-Historie
- Dashboard-Spalten für CLV im Verlauf (Datenpfad bereit)
- Generalisiertes Kelly für Push-/Viertellinien
