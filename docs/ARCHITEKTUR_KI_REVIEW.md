# QuantBot (Oddsforge) — vollständige Architektur & Technikbeschreibung

**Zweck:** Dieses Dokument ist zum Weitergeben an Gemini, ChatGPT oder andere Reviewer gedacht.  
Bitte kritisch prüfen: Architektur, Formeln, Schwellenwerte, UX, fehlende Features, Risiken, Vereinfachungen.

**Stand:** Repo Oddsforge · Paket `quantbot` · Version laut Code `0.2.9` (`__init__.py`; `pyproject.toml` noch `0.2.6`)  
**Sprache der Produkt-UI:** Deutsch / Englisch · **Zielgruppe:** Laie bis Experte

---

## Auftrag an den Reviewer

1. Ergibt der Gesamtaufbau Sinn? Wo ist er unnötig kompliziert?
2. Sind die Formeln und Schwellenwerte vernünftig für Freizeit-/Sharp-Märkte?
3. Welche Guardrails fehlen oder sind zu streng / zu lasch?
4. UX: Was verwirrt Laien? Was sollte weg, umbenannt oder besser erklärt werden?
5. Was fehlt als nächstes (Features), was sollte man bewusst **nicht** bauen?
6. Ethische / regulatorische Hinweise (Glücksspielhilfe, Limits bei Buchmachern)?

---

## 1. Was QuantBot ist — und was nicht

### Ist
- Probabilistische **Entscheidungshilfe** für Sportmärkte (primär Fußball, NBA nur Demo).
- Vergleicht **Modell-Wahrscheinlichkeiten** mit **fairen** Buchmacher-Wahrscheinlichkeiten (Marge entfernt).
- Erzeugt Signale: `VALUE_HOME` / `VALUE_DRAW` / `VALUE_AWAY` / Totals-Varianten **oder** `NO_BET`.
- Zeigt theoretische Einsätze (Fractional Kelly), Tippschein-Simulationen, Backtest, Verlauf.
- Läuft lokal: Streamlit-Dashboard (Doppelklick-Start) + optional CLI (`quantbot`).

### Ist nicht
- Kein Auto-Betting, kein Broker, kein Konto, keine Order-API.
- Keine Gewinngarantie, keine „sicheren Tipps“.
- Kein Live-/In-Play-Trading.
- Keine Vermischung von Demo- und Live-Tipp-Historie.
- Ollama (optional) erklärt nur Text — wählt **keine** Tipps.

**Leitsatz im UI:** „Nur Simulation. QuantBot wettet nicht.“

---

## 2. Harte Leitplanken (nicht verhandelbar)

| # | Regel | Umsetzung |
|---|--------|-----------|
| 1 | **Zero temporal leakage** | Features/Modelle/Quoten nur mit Infos **vor** `as_of` / `prediction_timestamp`. Ergebnisse erst ab `result_available_at`, nicht ab Anpfiff. |
| 2 | **Keine automatischen Wetten** | `Settings.allow_automated_betting` ist frozen `False`; Validator wirft, wenn man es auf `True` setzt (`config.py`). |
| 3 | **Probability over Prediction** | Ausgabe sind Wahrscheinlichkeiten + Value — keine Sieger-Garantien. |
| 4 | **Modellvertrauen ≠ Siegchance** | Confidence/Reliability sind Qualitäts-Scores, keine Win-%. |
| 5 | **Secrets lokal** | Keys in `~/.quantbot/credentials.env` oder `.env`, nie im Repo. |

---

## 3. Gesamtarchitektur (Datenfluss)

```
┌─────────────────────────────────────────────────────────────────┐
│  Daten-Provider                                                 │
│  Demo: DummyDataProvider (+ NBA BasketballDataProvider)         │
│  Live: Football-Data.org + The Odds API (+ optional API-Football│
│        für Asian Handicap / Extra-Totals)                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ as_of-Maskierung (BaseDataProvider)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Features (FeatureExtractor)                                    │
│  Elo-Diff, Form (Fenster 5), Tore/xG-MA, Ruhetage, Spiele-n     │
│  Nur Results mit result_available_at < as_of                    │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1 — Prediction                                           │
│  Elo (Default) · Dixon-Coles · ML · Ensemble · Basketball-Gauss │
│  → P(H/D/A) bzw. Moneyline · optional ScoreMatrix               │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2 — Market                                               │
│  Shin (1X2) · Power (2-Wege Totals/ML) · Overround              │
│  → faire Markt-Wahrscheinlichkeiten                             │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3 — Value & Confidence                                   │
│  Edge, EV, Datenqualität, Modellvertrauen                       │
│  optional Market-Shrinkage (wenig Spiele → näher am Markt)      │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4 — Decision                                             │
│  NoBetRules (alle Gründe sammeln) → KellySizer → VALUE_*|NO_BET │
└──────────────────────────────┬──────────────────────────────────┘
                               ▼
        ┌──────────────┬───────────────┬─────────────┬────────────┐
        │ Dashboard    │ Tippschein    │ Backtest    │ Tracking   │
        │ Signale/Card │ (Kombi-Sim.)  │ + MonteCarlo│ Verlauf    │
        └──────────────┴───────────────┴─────────────┴────────────┘
```

**Zentrale Orchestrierung:** `src/quantbot/orchestrator.py`  
Dashboard setzt u. a. `min_team_matches=3` und `market_shrinkage=True`.  
Wenn Totals-EV höher als 1X2/Moneyline-EV ist, bevorzugt der Orchestrator Totals.

---

## 4. Projektstruktur (wichtigste Pfade)

```
Oddsforge/
├── pyproject.toml, README.md, .env.example
├── Start QuantBot.{bat,command} / Update QuantBot.{bat,command}
├── docs/                          # Anleitungen, Glossar, dieses Review-Doc
├── src/quantbot/
│   ├── config.py                  # Settings, Guardrails
│   ├── orchestrator.py            # End-to-End Pipeline
│   ├── cli.py                     # Typer CLI
│   ├── i18n.py                    # DE/EN Strings
│   ├── preferences.py             # Welcome, Glossar-Gatter, Ollama-Prefs
│   ├── local_credentials.py       # ~/.quantbot/credentials.env
│   ├── ollama_explain.py          # optionale Text-Erklärung Tippschein
│   ├── tracking.py                # Tip-Historie (Verlauf)
│   ├── schemas/                   # Match, Odds, Market, Prediction, Signal
│   ├── data/                      # Provider, Demo, Live, Cache
│   ├── features/                  # leckfreie Features
│   ├── models/                    # Elo, Dixon-Coles, ML, Ensemble, NBA
│   ├── markets/                   # Margin, Odds, Totals, Arbitrage
│   ├── analysis/                  # Value, Confidence, Calibration, Card
│   ├── decision/                  # Rules, Kelly, DecisionEngine
│   ├── backtest/                  # Walk-Forward, Metrics, Monte Carlo
│   └── dashboard/                 # Streamlit UI, slip.py, ux.py
└── tests/                         # Leakage, Slip, Decision, Markets, …
```

User-Daten:
- `~/.quantbot/` — Credentials, Welcome dismissed, Glossary seen, `ollama.json`
- `data/tracker/demo.json` vs `data/tracker/live.json` — **getrennte** Tip-Historien

---

## 5. Kernformeln

### 5.1 Edge & Expected Value
\[
\text{Edge} = p_{\text{Modell}} - p_{\text{Markt, fair}}
\]
\[
\text{EV} = p_{\text{Modell}} \cdot o - 1
\]
\[
\text{relativer Edge} = (p_m - p_f) / p_f
\]
Unsicherheitsband der Edge-Anzeige: Halbweite etwa **0,5–5,0 Prozentpunkte** (aus Confidence/Agreement).

### 5.2 Kelly (theoretischer Einsatzanteil)
Voll-Kelly:
\[
f^* = \frac{p\cdot o - 1}{o - 1} = \frac{\text{EV}}{o-1}
\]
Fractional + Caps:
\[
f = \min\bigl(\max(f^*\cdot f_{\text{frac}},\,0),\, 0{,}05\bigr)
\]
- Default `kelly_fraction` im Code: **0,10** (`config.py`)
- Hard Cap: **5 %** Bankroll (`HARD_STAKE_CAP = 0.05`)
- Schema: `stake_fraction ≤ 0.05`

> Hinweis Doc/Code-Drift: `.env.example` / ältere Docs erwähnen noch 0,25 — Code-Default ist 0,10.

### 5.3 Marge entfernen
- **1X2:** Shin (Default)
- **2-Wege** (Moneyline, Totals): Power
- Overround = Buchsumme − 1; zu hohe Marge → No-Bet

### 5.4 Market Shrinkage (Dashboard)
Bei wenig Historie wird Modell-P Richtung Markt gezogen:
\[
p' = w\cdot p_{\text{Modell}} + (1-w)\cdot p_{\text{fair}},\quad
w = \min\bigl(\min(n_{\text{home}}, n_{\text{away}}) / 10,\, 1\bigr)
\]
Ziel: frühe Saison / dünne Daten → weniger übertriebene Edges.

### 5.5 Tippschein (Kombi)
Unabhängigkeit angenommen (bewusst vereinfacht):
\[
O_{\text{Kombi}} = \prod o_i,\qquad
P_{\text{Kombi}} = \prod p_i,\qquad
\text{EV}_{\text{Kombi}} = P\cdot O - 1
\]
Wenn Plausibilität fehlschlägt → Anzeige Chance = **„unrealistisch“** (keine rosige %-Zahl).

### 5.6 Dixon-Coles (Tore)
Bivariate Poisson mit Korrektur τ(ρ) für 0-0, 1-0, 0-1, 1-1; Zeitgewichtung \(e^{-\xi\cdot\text{Alter}}\); λ geclampt; optional xG. Liefert Score-Matrix → Totals / Handicap-Wahrscheinlichkeiten.

### 5.7 Elo
Dynamische Teamstärke, Heimvorteil, Margin-of-Victory-Skalierung; Draw-Anteil aus Differenz.

### 5.8 Totals aus Score-Matrix
Nur **Halblinien** für Auto-Signale (kein Push):
- Over: \(P(i+j > L)\), Under: \(P(i+j < L)\)
- Default-Linien: Fußball **2.5**, NBA **225.5**

### 5.9 Asian Handicap
Mathematik + API-Football-Ingest vorhanden; **noch nicht** in der DecisionEngine als Auto-Tipp verdrahtet. Ganzzahlige Linien können bei Settlement **VOID** (Einsatz zurück) ergeben.

### 5.10 Settlement / Payoff (Papier)
- Win → Quote; Loss → 0; VOID → **1.0** (voller Einsatz zurück)

---

## 6. Decision Engine — No-Bet-Filter

Datei: `src/quantbot/decision/rules.py`  
Alle Gründe werden **gesammelt** (kein Early-Exit), Codes `NO_BET_*`.

| Filter | Default | Bedeutung |
|--------|---------|-----------|
| Unrealistic EV | EV > **0,50** | Modell behauptet >50 % EV → unglaubwürdig |
| Min EV | **0,0** | negativer EV raus |
| Min Edge | **0,03** (3 pp) | `QUANTBOT_MIN_EDGE` |
| Max Overround | **0,12** | zu fette Buchmacher-Marge |
| Min Datenqualität | **60**/100 | |
| Min Modellvertrauen | **55**/100 | |
| Odds-Band | **1,2 … 15,0** | extreme Quoten raus |
| Kelly = 0 | Stake ≤ 0 | `NO_BET_KELLY_ZERO` |

**Zusätzlich Dashboard/Orchestrator:**
- `min_team_matches = 3` — sonst kein Tipp
- Market Shrinkage an

**Demo-Tracker** nutzt bewusst **laschere** Regeln, damit Demo überhaupt Tipps zeigt (nur für Verlaufs-Demo, nicht für Live-Logik).

---

## 7. Tippschein / Kombi-Analyse (`dashboard/slip.py`)

### Zweck
Theoretischer Akkumulator („KOMBI-SIMULATION“). **Platziert nichts.**

### Builder
| Funktion | Verhalten |
|----------|-----------|
| `build_safe_slip` | Sortiert nach Ausrichtung (Sicher / Ausgewogen / Gegen Markt), greedy Auswahl unter Caps |
| `build_boosted_slip` | Kern-Beine + Boosters (`min_boost_odds` default 2.2) |
| `build_smart_cross_sport_slip` | Cross-Sport, `min_edge≥0.02`, `data_quality≥70`, lieber gemischt |
| `slip_with_legs` | Manuelle Auswahl; ohne High-Risk wird ggf. re-getrimmt |
| `make_plausible_slip` | Wirft überhebliche Beine raus |

### Ausrichtung (Bias)
- **Sicher:** bevorzugt Mit-Markt, Quote ≤ **2,60**, kein O/U, nie Gegen-Markt; Kombi-Quote ≤ **8**, max **4** Tipps
- **Ausgewogen:** Blend aus Prob + Edge
- **Gegen Markt:** größter Edge zuerst (konträr)

### Plausibilitäts-Caps (ohne High-Risk)
| Konstante | Wert | Wirkung |
|-----------|------|---------|
| `_MAX_PLAUSIBLE_COMBINED_RETURN_FACTOR` | **2,5** | \(P\cdot O \le 2{,}5\) |
| `_MAX_PLAUSIBLE_LEG_EDGE` | **0,25** | einzelnes Bein max. 25 pp über Marktpreis |
| `_MAX_PLAUSIBLE_LEG_ODDS` | **8,0** | große Underdogs raus |
| `_MIN_GAMES_FOR_TOTALS_SLIP` | **6** | O/U erst mit genug Team-Historie |
| `_MAX_SAFE_LEG_ODDS` | **2,60** | Sicher-Modus |
| `_MAX_SAFE_COMBINED_ODDS` | **8,0** | Sicher-Kombi |
| `_MAX_SAFE_LEGS` | **4** | Sicher-Länge |

### „Höheres Risiko erlauben“
- Checkbox + **fette rote Warnung**
- Hebt Plausibilitäts-/Kombi-Caps und Sicher-Längenlimit an
- Weicht Sicher-Filter auf „balanced“ auf
- **Behält** Filter Quote > 8,0
- Manuelle Edits werden nur ohne High-Risk erneut plausibel getrimmt

### Einsatz-UI
- Feld **„Denkbarer Einsatz (€)“** für Ticket-Anzeige (Simulation)
- (Auf `main` existiert noch **Beispiel-Bankroll** mit 5 %-Cap; Entfernung ist als PR vorgesehen — Reviewer: Feld wirkt für Laien oft verwirrend)

### Ollama (optional)
- Erklärt den fertigen Schein in Prosa
- Darf Tipps **nicht** ändern, keine Gewinnversprechen

### Glossar-Gatter
Tippschein erst nach einmaligem Glossar-Besuch freigeschaltet (`glossary_seen`).

---

## 8. UX-Modi (`dashboard/ux.py`)

| Modus | Seiten |
|-------|--------|
| **Einfach / Beginner** | Modell-Signale, Verlauf, Einstellungen, Glossar (**kein** Tippschein in der Nav — bewusst, Kombis erhöhen Risiko) |
| **Mehr Details / Advanced** | + Kombi-Analyse, Spielkarte, Kalibrierung, Backtest |
| **Pro / Expert** | + Insights, Modelle, Diagnose |

Signal-Spalten skalieren mit: Beginner nur Match/Tipp/Markt/Spiele/Begründung; Advanced + Modell-P/Quote/Edge/EV/Stake%; Expert + Confidence/Datenqualität.

Welcome: Altersbestätigung 18+, Disclaimer mit Glücksspielhilfe (Check dein Spiel, BZgA, OASIS).

---

## 9. Sport, Ligen, Demo vs Live

### Sport
- **Fußball:** voll (Demo + Live mit Keys)
- **NBA:** Modell + Demo-Daten; **noch keine Live-Anbindung**

### Ligen (Live-fähig Fußball)
Premier League, Bundesliga, La Liga, Serie A, Ligue 1, Champions League · NBA (Demo)

### Demo vs Live
| | Demo | Live |
|--|------|------|
| Provider | Dummy (+ NBA demo) | Football-Data + Odds API (+ optional API-Football) |
| Keys | keine | FD + Odds erforderlich |
| Tip-Historie | `demo.json` | `live.json` |
| `as_of` | Fenster / Mid-Season | „heute“ wenn Fenster heute enthält |

---

## 10. Modelle (Kurz)

| Modell | Rolle |
|--------|--------|
| **Elo** | Default-Stärke, schnell, robust |
| **Dixon-Coles** | Tor-Matrix, Totals/AH-fähig |
| **ML** (LogReg / HistGB) | Features → Outcome-Probs |
| **Ensemble** | gewichtete Mischung, optional Brier-Fit |
| **CalibratedModel** | Isotonic/Platt nach chronologischem Split |
| **Basketball Gaussian** | NBA Offence/Defence + Totals-CDF |

Features: Elo-Diff, Form(5), Tore/xG, Ruhetage (Default 7), Spiele gespielt; Zeitdecay optional.

---

## 11. Analysis / Confidence

**Datenqualität (0–100):** grob  
`0.40·Match-Tiefe + 0.30·Markt-Tiefe + 0.15·Injuries + 0.15·Liquidity`  
(Targets u. a. 10 Spiele, 3 Bücher)

**Modellvertrauen:** Mischung aus Ensemble-Agreement + Datenqualität; Stufen Low &lt;45, Med &lt;70, High ≥70.

**Spielkarte (Matchcard):** Divergenz-Stufen bei ca. 2 / 5 / 8 / 12 Prozentpunkten Modell vs Markt.

**Kalibrierung:** Brier, Log-Loss, ECE; Reliability-Kurve im Dashboard.

---

## 12. Backtest & Tracking

### Backtest
- Strikt **walk-forward** (kein Random-Split)
- Refit chronologisch; Papier-Bankroll (Default 1000)
- Metriken: Return, ROI, Winrate, Profit Factor, Sharpe, Sortino, Max Drawdown, CLV
- Monte Carlo im Dashboard: ~2000 (Advanced) / ~5000 (Expert) Pfade → Risk of Ruin / Bandbreite

### Tracking (Verlauf)
- Tipps zum Predictions-Zeitpunkt „eingefroren“
- Abrechnung nach Ergebnis
- Wochen-Runden; Demo ≠ Live Dateien
- Sync oft, wenn Tracker geöffnet wird (nicht still im Hintergrund für alle Views)

---

## 13. Config & Credentials

Präfix: `QUANTBOT_`

Wichtige Defaults (`config.py`):
- `min_edge = 0.03`
- `min_data_quality = 60`
- `min_model_confidence = 55`
- `kelly_fraction = 0.10`
- `margin_method = shin`, `totals_margin_method = power`
- `allow_automated_betting = False` (hard)

Credentials-Reihenfolge: Environment / `.env` überschreibt gespeicherte lokale Keys.  
Gespeichert: Football-Data + The Odds API (pflicht zum Speichern); API-Football / NBA optional.

---

## 14. Wichtige Konstanten (Schnellreferenz)

| Wert | Ort |
|------|-----|
| Kelly frac 0.10, Cap 0.05 | `config.py`, `decision/sizing.py` |
| Max plausible EV 0.50 | `decision/rules.py` |
| NoBet edge/overround/DQ/conf/odds | `decision/rules.py` |
| Slip return≤2.5, edge≤0.25, odds≤8, totals≥6 Spiele, safe 2.60/8/4 | `dashboard/slip.py` |
| min_team_matches=3 | `dashboard/app.py` |
| Elo k=20, HA=65, init=1500 | `models/elo.py` |
| DC λ∈[0.02,12], max_goals=10 | `models/dixon_coles.py` |
| Form window 5, rest 7d | `features/extractor.py` |
| Totals 2.5 / NBA 225.5 | `schemas/enums.py` |
| Fuzzy Team-Match 0.86 | `data/providers/live.py` |

---

## 15. Bekannte Lücken / Doc-Drift (bitte mitbedenken)

1. README sagt Anfänger haben Wettschein — **Code:** Beginner-Nav **ohne** Slip.
2. Kelly 0.10 Code vs 0.25 in manchen Docs/`.env.example`.
3. Version 0.2.9 vs pyproject 0.2.6.
4. Asian Handicap: Daten + Matrix da, **kein** Auto-Signal in DecisionEngine.
5. NBA: nur Demo.
6. Ganzzahlige Totals/AH: Settlement VOID möglich, Auto-EV nur Halblinien.
7. Kombi-P als Produkt ignoriert Korrelation (UI warnt).
8. Frühe Saison: trotz Shrinkage können Edges noch zu optimistisch wirken (siehe Tippschein-Plausibilität).

---

## 16. Was bewusst fehlen soll (Produktrichtung)

- Kein Auto-Bet / kein „Tipp-Abo mit Garantie“
- Kein Vermischen Demo/Live-Statistik
- Keine In-Play-Quoten-Jagd ohne klare Leakage-Story
- Ollama bleibt Erklärer, kein Tip-Generator

---

## 17. Review-Fragen (konkret)

1. Ist **Market Shrinkage** + EV&gt;0.50-Gate + Slip-Return≤2.5 genug gegen Overconfidence?
2. Ist **Sicher**-Slip (Mit-Markt, ≤2.60, max 4, Kombi≤8) zu konservativ / zu lasch?
3. Sollte „Höheres Risiko“ überhaupt existieren, oder eher streng bleiben?
4. Kelly 0.10 + Cap 5 % — passt das zu Freizeitnutzern?
5. Totals erst ab 6 Spielen im Slip — besser 8–10?
6. UX: Welche Felder (Edge, EV, Bankroll, Ausrichtung) verwirren Laien am meisten?
7. Fehlt: Closing-Line-Feedback prominent? Kalibrierung vor Tipps erzwingen?
8. NBA live — lohnt sich der Aufwand vor Fußball-AH-Signalen?

---

## 18. Kurz: Tech-Stack

Python ≥3.11 · Pydantic v2 · Streamlit · Typer · pandas/polars/numpy/scipy · sklearn/xgboost/lightgbm · httpx · pytest

Start: Doppelklick `Start QuantBot` → Browser `localhost:8501` · CLI: `quantbot predict|backtest|info`

---

*Ende der Beschreibung. Bitte mit konkreten Änderungsvorschlägen antworten (Priorität: Sicherheit/Kalibrierung → UX-Klarheit → Features).*
