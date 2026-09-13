# Schnellstart für Windows (für Einsteiger)

Diese Anleitung führt dich in wenigen Schritten von Null bis zum Dashboard. Tippe die Befehle genau so ab. QuantBot wettet nichts selbst, es rechnet und zeigt Hinweise.

## Teil 1: Einmal einrichten

### Schritt 1: Python installieren
1. Gehe auf https://www.python.org/downloads/windows/
2. Lade Python 3.11 oder neuer herunter und starte die Datei.
3. Setze unten das Häkchen bei "Add python.exe to PATH". Wichtig.
4. Klicke "Install Now" und warte, bis fertig.

### Schritt 2: QuantBot herunterladen
1. Öffne die Projektseite auf GitHub.
2. Klicke auf den grünen Knopf "Code", dann "Download ZIP".
3. Entpacke die ZIP-Datei nach `C:\Oddsforge`.

### Schritt 3: Das Terminal öffnen
1. Drücke die Windows-Taste, tippe `powershell`, drücke Enter.
2. Wechsle in den Ordner. Tippe:

```
cd C:\Oddsforge
```

### Schritt 4: Einrichten (dauert ein paar Minuten)

```
powershell -ExecutionPolicy Bypass -File install.ps1
```

Wenn am Ende eine Tabelle mit "QuantBot" erscheint, hat alles geklappt.

## Teil 2: Demo starten (ohne Schlüssel, sofort)

Jedes Mal, wenn du QuantBot benutzt, machst du zuerst das:

```
cd C:\Oddsforge
.venv\Scripts\activate
```

Dann das Dashboard im Browser öffnen:

```
quantbot dashboard
```

Es öffnet sich eine Seite auf deinem Computer. Falls nicht, tippe im Browser: http://localhost:8501

Was du dort machst:
1. Links oben die Sprache auf Deutsch stellen.
2. Eine Liga wählen (Premier League oder Bundesliga funktionieren in der Demo).
3. Zwischen den Seiten wechseln: Signale, Modell-Einblicke, Backtest, Glossar.
4. Die Seite Glossar erklärt dir jeden Begriff.

Zum Beenden: im Terminal die Tasten Strg und C zusammen drücken.

Lieber ohne Browser, nur Text? Dann statt dem Dashboard:

```
quantbot predict
quantbot backtest
```

Wichtig: In der Demo sind die Spiele erfunden. Die Zahlen sind nur zum Anschauen.

## Teil 3: Echte Spiele der laufenden Saison

Dafür brauchst du zwei kostenlose Schlüssel.

### Schritt 1: Schlüssel holen
1. Football-Data.org: Konto anlegen auf https://www.football-data.org/client/register und den Token kopieren.
2. The Odds API: Konto anlegen auf https://the-odds-api.com/ und den Key kopieren.

### Schritt 2: Schlüssel eintragen
1. Kopiere im Ordner `C:\Oddsforge` die Datei `.env.example` und nenne die Kopie `.env`.
2. Öffne `.env` mit dem Editor und trage ein:

```
QUANTBOT_FOOTBALL_DATA_API_KEY=dein_football_data_token
QUANTBOT_THE_ODDS_API_KEY=dein_odds_api_key
```

3. Speichern und schliessen.

### Schritt 3: Mit echten Daten starten

```
cd C:\Oddsforge
.venv\Scripts\activate
quantbot predict --league premier_league --live
```

Andere Ligen gehen genauso, ersetze premier_league durch:
bundesliga, la_liga, serie_a, ligue_1 oder champions_league.

## Was die Hinweise bedeuten

- VALUE_HOME, VALUE_DRAW, VALUE_AWAY: möglicher Vorteil auf Heim, Unentschieden oder Auswärts.
- NO_BET: kein Hinweis, lieber nichts. Der Grund steht daneben.
- Einsatz in Prozent: nur ein rechnerischer Vorschlag, kein Aufruf, echtes Geld zu setzen.

## Wenn etwas klemmt

- "python wird nicht erkannt": Python neu installieren, Häkchen bei "Add to PATH" setzen, Terminal neu öffnen.
- "quantbot wird nicht erkannt": Du hast die Umgebung nicht aktiviert. Zuerst `.venv\Scripts\activate` ausführen.
- Live-Modus meckert über fehlende Schlüssel: prüfe die Datei `.env`.

## Zur Sicherheit

QuantBot garantiert keinen Gewinn und platziert keine Wetten. Du entscheidest immer selbst. Wette nie mehr, als du verlieren kannst.
