# QuantBot auf Windows installieren

Diese Anleitung ist für Windows und bewusst einfach gehalten. QuantBot ist ein Python-Programm. Du startest es über die Eingabeaufforderung oder das Dashboard im Browser.

## Schritt 1: Python installieren

1. Öffne https://www.python.org/downloads/windows/
2. Lade Python 3.11 oder neuer herunter.
3. Starte das Installationsprogramm. Setze unten das Häkchen bei "Add python.exe to PATH". Das ist wichtig.
4. Klicke auf "Install Now".

Test: Öffne die Eingabeaufforderung (Windows-Taste, dann "cmd" tippen, Enter) und gib ein:

```
python --version
```

Es sollte eine Version wie "Python 3.11.x" erscheinen.

## Schritt 2: QuantBot herunterladen

Variante A, mit Git (empfohlen):

```
git clone https://github.com/Dobolino/Oddsforge.git
cd Oddsforge
```

Variante B, ohne Git:

1. Öffne die Projektseite auf GitHub im Browser.
2. Klicke auf "Code", dann "Download ZIP".
3. Entpacke die ZIP-Datei, zum Beispiel nach `C:\Oddsforge`.
4. Öffne die Eingabeaufforderung und wechsle in den Ordner, zum Beispiel:

```
cd C:\Oddsforge
```

## Schritt 3: Automatisch installieren

Im Projektordner liegt ein Skript. Führe es in PowerShell aus:

```
powershell -ExecutionPolicy Bypass -File install.ps1
```

Das Skript legt eine virtuelle Umgebung an, installiert alle Pakete und prüft die Installation. Beim ersten Mal dauert das ein paar Minuten.

## Schritt 4: QuantBot starten

Jedes Mal, wenn du QuantBot benutzt, aktivierst du zuerst die Umgebung:

```
.venv\Scripts\activate
```

Danach kannst du die Befehle nutzen:

```
quantbot info
quantbot predict --league premier_league
quantbot backtest --league bundesliga
quantbot dashboard
```

Der letzte Befehl öffnet das Dashboard im Browser unter http://localhost:8501

## Schritt 5: Echte Daten (optional)

Ohne API-Keys nutzt QuantBot Demodaten. Für echte Spiele der laufenden Saison brauchst du zwei kostenlose Keys:

1. Football-Data.org: Konto anlegen unter https://www.football-data.org/client/register und den Token kopieren.
2. The Odds API: Konto anlegen unter https://the-odds-api.com/ und den Key kopieren.

Lege im Projektordner eine Datei namens `.env` an (Vorlage ist `.env.example`) und trage ein:

```
QUANTBOT_FOOTBALL_DATA_API_KEY=dein_football_data_token
QUANTBOT_THE_ODDS_API_KEY=dein_odds_api_key
```

Dann Live-Modus starten:

```
quantbot predict --league premier_league --live
```

Unterstützte Ligen: premier_league, bundesliga, la_liga, serie_a, ligue_1, champions_league.

## Häufige Probleme

- "python wird nicht erkannt": Python neu installieren und das Häkchen bei "Add to PATH" setzen. Danach die Eingabeaufforderung neu öffnen.
- "quantbot wird nicht erkannt": Du hast die Umgebung nicht aktiviert. Führe zuerst `.venv\Scripts\activate` aus.
- Firewall-Frage beim Dashboard: erlauben, damit der lokale Server im Browser erreichbar ist.

## Wichtig

QuantBot platziert keine Wetten. Es ist ein Analyse- und Entscheidungswerkzeug. Alle Einsätze sind theoretische Vorschläge.
