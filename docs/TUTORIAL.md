# QuantBot Tutorial

Diese Anleitung zeigt dir, wie du QuantBot installierst, über die CLI benutzt und über die Python-API in eigenen Skripten einsetzt. QuantBot ist ein Analyse- und Entscheidungsunterstützungssystem. Es platziert keine Wetten. Alle Stakes sind theoretische Vorschläge.

## 1. Installation

Voraussetzung: Python 3.11 oder neuer.

Mit uv (empfohlen):

```bash
uv venv
uv pip install -e ".[dev]"
```

Oder mit pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Test, ob alles läuft:

```bash
pytest
```

## 2. Schnellstart über die CLI

Ohne API-Key kannst du sofort mit dem eingebauten `DummyDataProvider` starten. Er erzeugt eine reproduzierbare Saison für Premier League und Bundesliga.

System- und Modellinfo anzeigen:

```bash
quantbot info
```

Wettsignale für kommende Spiele berechnen:

```bash
quantbot predict --league premier_league --season 2024-2025
```

Walk-Forward-Backtest mit Metriken:

```bash
quantbot backtest --league bundesliga --bankroll 1000
```

Dashboard im Browser starten:

```bash
quantbot dashboard --port 8501
```

Die drei Dashboard-Seiten sind Upcoming Value Signals, Model Insights and Scorelines und Backtest Performance.

## 3. Grundkonzept: die 4 Layer

QuantBot trennt die Verarbeitung strikt:

- Layer 1 Prediction. Modelle liefern nur Wahrscheinlichkeiten P(Home), P(Draw), P(Away).
- Layer 2 Market. Rechnet die Buchmacher-Marge heraus und liefert faire Wahrscheinlichkeiten.
- Layer 3 Value und Calibration. Berechnet Edge, Expected Value, Kalibrierung und Confidence.
- Layer 4 Decision. Wendet No-Bet-Regeln an und erzeugt das finale Signal plus theoretischen Stake.

Der Orchestrator verbindet diese Layer für dich.

## 4. Python-API: Vorhersagen

```python
from quantbot.orchestrator import QuantBotOrchestrator
from quantbot.schemas import League

orch = QuantBotOrchestrator()
reports = orch.predict(League.PREMIER_LEAGUE, "2024-2025")

for r in reports:
    s = r.signal
    print(r.match.home_team.name, "vs", r.match.away_team.name)
    print("  Signal:", s.signal.value, "Stake %:", round(s.stake_fraction * 100, 2))
    print("  Grund:", s.rationale)
```

Jeder `SignalReport` enthält das Spiel, das `ValueSignal` (Signaltyp, Edge, EV, Stake, Rejection Reasons) und das `AnalysisResult` (Metriken je Outcome, Data Quality, Confidence).

## 5. Python-API: Backtest

Mit den Standardregeln ist QuantBot streng und lehnt bei dünner Datenlage viele Wetten ab. Für einen aussagekräftigen Beispiel-Backtest kannst du die Regeln lockern:

```python
from quantbot.orchestrator import QuantBotOrchestrator
from quantbot.decision import DecisionEngine, NoBetRules, KellySizer
from quantbot.models import EloModel
from quantbot.schemas import League

engine = DecisionEngine(
    rules=NoBetRules(
        min_ev=0.02,
        min_edge=0.0,
        max_overround=1.0,
        min_data_quality=0.0,
        min_model_confidence=0.0,
        min_odds=1.01,
        max_odds=100.0,
    ),
    sizer=KellySizer(kelly_fraction=0.25, max_fraction=0.05),
)

orch = QuantBotOrchestrator(model=EloModel(), decision_engine=engine)
result = orch.run_backtest(League.PREMIER_LEAGUE, "2024-2025")

m = result.metrics
print("Bets:", result.n_bets)
print("Endkapital:", round(result.final_bankroll, 2))
print("ROI:", round(m.roi * 100, 2), "%")
print("Sharpe:", round(m.sharpe, 3), "Sortino:", round(m.sortino, 3))
print("Max Drawdown:", round(m.max_drawdown * 100, 2), "%")
print("Beat-CLV-Rate:", m.beat_clv_rate)
```

Wichtig: Der Backtester ist streng chronologisch und leckfrei. Jedes Modell wird nur auf Spielen vor dem `prediction_timestamp` neu gefittet, und die Closing Line dient ausschliesslich dem CLV nach der Abrechnung.

## 6. Modelle wählen und kombinieren

Verfügbare Modelle:

- `EloModel`: dynamisches Elo mit Home Advantage und Margin of Victory.
- `DixonColesModel`: Poisson-Modell mit Score-Matrix, Time-Decay und optionalem xG.
- `LogisticRegressionModel`, `GradientBoostingModel`: ML-Baselines.
- `EnsembleModel`: gewichtete Kombination, optional per Brier-Score optimiert.
- `CalibratedModel`: Wrapper, der kalibrierte Wahrscheinlichkeiten liefert.

Ensemble mit Gewichtsoptimierung und Kalibrierung:

```python
from quantbot.orchestrator import QuantBotOrchestrator
from quantbot.models import EnsembleModel, EloModel, LogisticRegressionModel
from quantbot.analysis import IsotonicCalibrator
from quantbot.schemas import League

ensemble = EnsembleModel(
    [EloModel(), LogisticRegressionModel()],
    optimize_weights=True,
)
orch = QuantBotOrchestrator(model=ensemble, calibrator=IsotonicCalibrator())
reports = orch.predict(League.PREMIER_LEAGUE, "2024-2025")
```

## 7. Time-Decay und xG bei Dixon-Coles

Neuere Spiele stärker gewichten (xi ist die tägliche Zerfallsrate):

```python
from quantbot.models import DixonColesModel

model = DixonColesModel(time_decay_xi=0.005)   # Halbwertszeit rund 139 Tage
```

Lambdas auf xG statt Tore fitten (fällt auf Tore zurück, falls xG fehlt):

```python
model = DixonColesModel(use_xg=True)
```

Optimales xi per Kreuzvalidierung bestimmen:

```python
from quantbot.models.tuning import tune_time_decay
from quantbot.models import DixonColesModel
from quantbot.schemas import League
from quantbot.orchestrator import QuantBotOrchestrator

orch = QuantBotOrchestrator()
matches = orch.universe(League.PREMIER_LEAGUE, "2024-2025")

result = tune_time_decay(
    matches,
    xi_grid=[0.0, 0.005, 0.05],
    build_model=lambda xi: DixonColesModel(min_matches=5, time_decay_xi=xi),
    n_splits=3,
)
print("Bestes xi:", result.best_xi, "Score:", round(result.best_score, 4))
```

## 8. Monte-Carlo-Simulation der Bankroll

Aus einem Backtest die Risk-of-Ruin und die Drawdown-Verteilung schätzen:

```python
from quantbot.backtest import bet_specs_from_result, monte_carlo_bankroll

specs = bet_specs_from_result(result)   # result aus Abschnitt 5
mc = monte_carlo_bankroll(specs, initial_bankroll=1000.0, n_sims=10000, ruin_fraction=0.5)

print("Risk of Ruin:", mc.risk_of_ruin)
print("Endkapital Median:", round(mc.final_median, 2))
print("Endkapital P5 bis P95:", round(mc.final_p5, 2), "bis", round(mc.final_p95, 2))
print("Max Drawdown Median:", round(mc.drawdown_median * 100, 2), "%")
```

## 9. Line Shopping und Arbitrage

Beste Quoten über mehrere Buchmacher finden und Surebets erkennen:

```python
from datetime import datetime, timezone
from quantbot.markets import ArbitrageEngine
from quantbot.schemas import Odds

ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
books = [
    Odds(match_id="m1", bookmaker="BookA", timestamp=ts, home=2.1, draw=3.5, away=4.0),
    Odds(match_id="m1", bookmaker="BookB", timestamp=ts, home=2.3, draw=4.1, away=4.6),
]

engine = ArbitrageEngine()
opp = engine.find_arbitrage(books, total_stake=100.0)

print("Arbitrage:", opp.is_arbitrage)
print("Marge:", round(opp.profit_margin * 100, 2), "%")
print("Garantierter Profit:", round(opp.guaranteed_profit, 2))
for outcome, stake in opp.stakes.items():
    odds, bookmaker = opp.best_odds[outcome]
    print(f"  {outcome.value}: {round(stake, 2)} bei {bookmaker} @ {odds}")
```

Ist `booksum` kleiner als 1.0, ist es eine echte Arbitrage. Die Stakes sind so verteilt, dass jede Auszahlung gleich hoch ist.

## 10. Echte Daten anbinden

Ohne Keys nutzt du den `DummyDataProvider`. Für Realdaten brauchst du API-Keys.

The Odds API (Quoten):

```python
from pathlib import Path
from quantbot.data.providers import TheOddsAPIProvider

provider = TheOddsAPIProvider(
    api_key="DEIN_KEY",
    cache_dir=Path(".cache/odds"),
    ttl_seconds=3600,      # Cache eine Stunde gültig
    min_interval=1.0,      # mindestens 1 Sekunde zwischen API-Calls
)
odds_by_match = provider.fetch_odds("soccer_epl")     # dict match_id -> Liste Odds
markets = provider.fetch_market_data("soccer_epl")    # Consensus MarketData je Spiel
```

Football-Data.org (Ergebnisse, Spielpläne, Tabellen):

```python
from pathlib import Path
from quantbot.data.providers import FootballDataProvider

fd = FootballDataProvider(api_key="DEIN_KEY", cache_dir=Path(".cache/fd"))
matches = fd.fetch_matches("PL")        # Match-DTOs, Ergebnis bei FINISHED
table = fd.fetch_standings("PL")        # Tabellenzeilen
```

Beide Provider nutzen einen lokalen Datei-Cache mit TTL und einen Rate-Limiter zum Schutz deines API-Kontingents. Unterstützte Football-Data-Codes: PL, BL1, CL.

Die Keys legst du am besten in `.env` ab (siehe `.env.example`, Präfix `QUANTBOT_`).

## 11. Konfiguration

Zentrale Schwellen und Einstellungen kommen aus `quantbot.config.Settings` und lassen sich per Umgebungsvariable setzen:

```bash
QUANTBOT_MIN_EDGE=0.03
QUANTBOT_KELLY_FRACTION=0.25
QUANTBOT_MARGIN_METHOD=shin
QUANTBOT_LOG_LEVEL=INFO
```

Der Guardrail `allow_automated_betting` steht fest auf `False` und lässt sich nicht per Umgebungsvariable aktivieren.

## 12. Typischer Workflow

1. Modell wählen und optional kalibrieren.
2. xi per `tune_time_decay` bestimmen.
3. Backtest laufen lassen und ROI, Sharpe, Sortino, Max Drawdown, CLV prüfen.
4. Monte Carlo für Risk of Ruin rechnen.
5. Erst wenn Kalibrierung und CLV stimmen, `predict` für kommende Spiele nutzen.
6. Signale beobachten und per Paper Trading verfolgen. QuantBot wettet nicht selbst.

## 13. Weiterführend

- Architektur und Guardrails: `README.md`
- Leakage-Absicherung: `tests/test_data_leakage.py`
- Metriken und Backtester: `src/quantbot/backtest/`
- Roadmap 2.0 und offene Features: frag im Projekt nach den Blöcken A bis C und den geplanten Erweiterungen.
