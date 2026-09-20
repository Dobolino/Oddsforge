# Fortschritt: CURSOR_PROMPT_QUANTBOT (P0 → P1 → P2 → P3)

Stand: P0–P2 + **P3** auf Branch `cursor/p3-ah-clv-kelly-9483`
(basiert auf `cursor/p2-clv-manifest-valid-9483`).

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
| AH Settlement (typed, experimental flag) | DONE |
| Generalisiertes Kelly (Push/Viertel) | DONE |
| AH Value-Signale (exploratory, sizing gated) | DONE |
| Closing last-prematch Proxy | DONE |
| CLV im Verlauf-UI | DONE |
| Empirische Live-VALID-Daten | **BLOCKER** |

## P3 geliefert

1. **Generalisiertes Kelly** (`KellySizer.generalized_*`, `binary_win_lose_outcomes`, `push_market_outcomes`) — AH-Pfad nutzt generalized Kelly auf Binär-Payoffs; Push-Märkte vorbereitet
2. **AH DecisionEngine** (`decide_ah`, `VALUE_AH_*`, Orchestrator `_maybe_prefer_ah` hinter `enable_ah_experimental`) — exploratory Signale; `ah_sizing_released=False` bis AH-VALID
3. **Closing** (`markets/closing.py`) — tagged `is_closing`, sonst last prematch vor Kickoff (dokumentiert); nie post-kickoff
4. **CLV Verlauf** — TipHistory `attach_clv` + Tracker-Metrik/Zeilen; AH/Totals ehrlich `na_market_mismatch`
5. **AH Settlement im Tracker** — `ah_*` Tips via `settle_line_market`; Push aus Hit-Rate ausgeschlossen

## Blocker (ehrlich)

Ohne echte chronologische Live-Daten und **vorab** festgelegte Criteria gibt es kein Live-`VALID`-Artefakt → Live-Sizing und AH-Sizing bleiben gesperrt. Synthetische/Demo-Läufe dürfen das nicht freischalten.

## Bewusst zurückgestellt / gated

- AH-Sizing Release (braucht dediziertes AH ValidationArtifact)
- Live exchange closes als Pflicht (Proxy last-prematch ist dokumentiert, nicht gleichwertig)
- CLV für Totals/AH mit matching close lines
