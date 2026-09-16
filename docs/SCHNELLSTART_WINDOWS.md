# Schnellstart für Windows (für Einsteiger)

Der einfachste Weg braucht kein Terminal. Du klickst zwei Dateien doppelt an. QuantBot wettet nichts selbst, es rechnet und zeigt Hinweise.

## Der einfache Weg (empfohlen)

### 1. Python installieren (nur beim ersten Mal)
1. Gehe auf https://www.python.org/downloads/windows/
2. Lade Python 3.11 oder neuer und starte die Datei.
3. Setze unten das Häkchen bei "Add python.exe to PATH". Wichtig.
4. Klicke "Install Now".

Falls Python fehlt, öffnet die Startdatei diese Seite automatisch und sagt dir Bescheid.

### 2. QuantBot herunterladen
1. Öffne https://github.com/Dobolino/Oddsforge
2. Grüner Knopf "Code", dann "Download ZIP".
3. Entpacke die ZIP-Datei, zum Beispiel nach `C:\Oddsforge`.

### 3. Starten
Doppelklick auf die Datei

```
Start QuantBot.bat
```

Beim ersten Mal richtet sie alles automatisch ein, das dauert ein paar Minuten. Danach öffnet sich das Dashboard von selbst im Browser. Ab dem zweiten Mal startet es sofort.

Zum Beenden einfach das schwarze Fenster schliessen.

### 4. Aktualisieren
Doppelklick auf

```
Update QuantBot.bat
```

Das holt **immer den Branch `main`** von GitHub (per Git oder per ZIP), räumt Python-Caches und installiert neu. Am Ende siehst du Version und Git-Stand.

Danach QuantBot **komplett beenden** (schwarzes Fenster schliessen) und erneut mit `Start QuantBot.bat` starten. Links im Dashboard muss mindestens **v0.2.0** stehen und die Seite **Wettschein** sichtbar sein.

Falls Windows warnt (blauer Hinweis): "Weitere Informationen" → "Trotzdem ausführen".

Was du im Dashboard machst:
1. Beim ersten Start die Willkommenskarte lesen und auf **Verstanden — starten** klicken.
2. Links oben die Sprache auf Deutsch stellen.
3. Die Ansicht auf **Anfänger** lassen (Voreinstellung). Fortgeschritten und Experte zeigen mehr Zahlen.
4. Eine Liga wählen (in der Demo funktionieren Premier League und Bundesliga).
5. Das **Prognosedatum** prüfen — bei echten Daten ist das Standard **heute**. Mit dem Button **Auf heute setzen** springst du zurück. Das Datum kannst du in jedem Modus ändern, auch als Anfänger.
6. Zwischen den Seiten wechseln: Tipps, Wettschein, Verlauf, Glossar. (Bei Fortgeschritten/Experte kommen weitere Seiten hinzu.)
7. Auf Tipps siehst du einen klaren Vorschlag und eine kurze Begründung. **Wettschein** baut daraus einen theoretischen Kombi-Schein (beste Chancen, optional mit Quoten-Boostern) — ohne selbst zu tippen.
8. Verlauf zeigt Woche für Woche Tipp gegen Ergebnis. Glossar erklärt jeden Begriff.

Oben steht immer ein Warnhinweis: QuantBot wettet nicht selbst und garantiert keinen Gewinn. Bei echten Daten erscheint zusätzlich eine Warnung, wenn Teamnamen zwischen den Datenquellen unsicher zugeordnet wurden. Die Tipps-Tabelle lässt sich seitlich scrollen, damit Quote, Edge und Begründung sichtbar bleiben.

In der Demo sind die Spiele erfunden. Die Zahlen sind nur zum Anschauen.

## Der Terminal-Weg (nur für Fortgeschrittene)

Wer lieber tippt, kann auch so einrichten und starten:

```
cd C:\Oddsforge
powershell -ExecutionPolicy Bypass -File install.ps1
.venv\Scripts\activate
quantbot dashboard
```

Oder ohne Browser: `quantbot predict` und `quantbot backtest`.

## Teil 3: Echte Spiele der laufenden Saison

Dafür brauchst du zwei kostenlose Schlüssel.

### Schritt 1: Schlüssel holen
1. Football-Data.org: Konto anlegen auf https://www.football-data.org/client/register und den Token kopieren.
2. The Odds API: Konto anlegen auf https://the-odds-api.com/ und den Key kopieren.

### Schritt 2: Schlüssel eintragen

Der einfachste Weg ist direkt im Dashboard, ohne Dateien zu bearbeiten:

1. Starte das Dashboard: `quantbot dashboard`
2. Klicke links auf den Bereich "API-Schlüssel (für echte Daten)".
3. Füge deine zwei Schlüssel in die zwei Felder ein.
4. Klicke auf **Schlüssel speichern**. Erst dann werden die Eingaben übernommen. Ohne hinterlegte Schlüssel läuft die Demo. **HINTERLEGT · UNGEPRÜFT** bedeutet, dass ein Schlüssel vorhanden ist, nicht dass der Anbieter ihn bereits akzeptiert hat.

Die Schlüssel werden unverschlüsselt in `~/.quantbot/credentials.env` auf dem Rechner gespeichert, auf dem QuantBot läuft. Bei API-Abrufen werden sie per HTTPS an den jeweiligen Datenanbieter übertragen. Dashboard und CLI nutzen dieselben Schlüssel; Umgebungsvariablen und `.env` haben Vorrang vor der gespeicherten Datei. Basketball verwendet weiterhin Demodaten und benötigt keinen Schlüssel.

Alternativer Weg über eine Datei (falls du lieber die Textbefehle nutzt):

1. Kopiere im Ordner `C:\Oddsforge` die Datei `.env.example` und nenne die Kopie `.env`.
2. Öffne `.env` mit dem Editor und trage ein:

```
QUANTBOT_FOOTBALL_DATA_API_KEY=dein_football_data_token
QUANTBOT_THE_ODDS_API_KEY=dein_odds_api_key
```

3. Speichern und schliessen.

### Schritt 3: Mit echten Daten starten

Im Dashboard passiert das nach dem Speichern der Schlüssel. Für die Textbefehle:

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
