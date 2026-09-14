# QuantBot (Oddsforge)

Probabilistisches Framework für die Analyse von Sportereignissen und Prediction Markets.

Pipeline: Probability zu Market Price zu Edge zu Expected Value zu Backtest zu Decision Support.

## Guardrails

1. Zero Data Leakage. Jedes Feature ist temporal isoliert vor dem `prediction_timestamp`.
2. No Automated Betting. Version 1 unterstützt Entscheidungen, platziert aber keine Wetten.
3. Probability over Prediction. Das System kalibriert Wahrscheinlichkeiten statt Sieger zu raten.
4. Separation of Concerns. Das ML-Modell liefert nur `P(Outcome)`, die Decision Engine bewertet Edge und Risk.

## 4-Layer-Architektur

- Layer 1 Prediction Engine. Liefert `P(Home)`, `P(Draw)`, `P(Away)` und Score-Matrix.
- Layer 2 Market Engine. Entfernt die Buchmacher-Marge und liefert faire Wahrscheinlichkeiten.
- Layer 3 Value & Calibration Engine. Berechnet Edge, EV, Brier Score und Kalibrierung.
- Layer 4 Decision Engine. Erzeugt Signal und theoretischen Stake.

## Projektstruktur

```
Oddsforge/
├── pyproject.toml
├── .python-version
├── .env.example
├── README.md
├── src/quantbot/
│   ├── config.py          # pydantic-settings, Guardrails
│   ├── logging.py         # rich / JSON Logging
│   ├── orchestrator.py    # End-to-End Pipeline
│   ├── cli.py             # Typer + Rich CLI
│   ├── schemas/           # Pydantic v2 Domain-Modelle
│   ├── data/              # Provider-Abstraktion, DummyDataProvider
│   ├── features/          # leckfreie Feature-Extraktion
│   ├── models/            # Elo, Dixon-Coles, ML, Ensemble
│   ├── markets/           # Margin-Removal (Shin), Market Engine
│   ├── analysis/          # Value, Calibration, Confidence
│   ├── decision/          # Kelly-Sizing, No-Bet-Rules, Decision Engine
│   └── backtest/          # Walk-Forward, Execution, Metrics, CLV
└── tests/                 # 145 Tests
```

## Setup

```bash
uv venv
uv pip install -e ".[dev]"
```

## Test

```bash
uv run pytest
```

## CLI

```bash
quantbot info                                   # System- und Modellspezifikation
quantbot predict --league premier_league        # Wettsignale, Kelly-Stakes, Rejection Reasons
quantbot backtest --league bundesliga --bankroll 1000   # Walk-Forward Metriken
```

## Schnellster Start (Windows, ohne Terminal)

1. Python einmal installieren (Häkchen "Add python.exe to PATH").
2. Projekt als ZIP herunterladen und entpacken.
3. Doppelklick auf `Start QuantBot.bat` (richtet beim ersten Mal alles ein und öffnet das Dashboard).
4. Im Dashboard die Ansicht **Anfänger** belassen: ein Tipp, eine Begründung, Warnhinweis oben.
5. Für Updates: Doppelklick auf `Update QuantBot.bat`.

Details in `docs/SCHNELLSTART_WINDOWS.md`.

## Bedienmodi

- **Anfänger**: Tipps, Wettschein, Verlauf, Glossar. Klarer Vorschlag ohne Fachjargon. Prognosedatum änderbar.
- **Fortgeschritten**: plus Spielkarte, Edge/EV/Einsatz, Backtest.
- **Experte**: alle Kennzahlen, Modell-Einblicke, Kalibrierung, Diagnose.

Bei echten Daten springt das Prognosedatum standardmässig auf **heute**. Der Wettschein baut theoretische Kombi-Scheine (beste Chancen, optional Quoten-Booster) — ohne Wetten zu platzieren.

## Tutorial und Anleitungen

- `docs/SCHNELLSTART_WINDOWS.md`: Einsteiger-Anleitung, Doppelklick-Weg und Terminal-Weg.
- `docs/INSTALLATION_WINDOWS.md`: einfache Windows-Installation Schritt für Schritt.
- `docs/GLOSSAR_DE.md`: deutsches Glossar aller Begriffe (Edge, EV, Kelly, CLV, ...).
- `docs/TUTORIAL.md`: Schritt-für-Schritt-Anleitung (CLI, Python-API, Backtest, Monte Carlo, Arbitrage, Realdaten).

Realdaten aktivieren: API-Keys in `.env` eintragen (siehe `.env.example`), dann `quantbot predict --league premier_league --live`. Unterstützte Ligen: premier_league, bundesliga, la_liga, serie_a, ligue_1, champions_league.

## Konfiguration

Kopiere `.env.example` nach `.env`. Alle Variablen tragen das Präfix `QUANTBOT_`.
