# Schnellstart für Mac (für Einsteiger)

Der einfachste Weg braucht kaum Terminal-Kenntnisse. Du klickst zwei Dateien doppelt an. QuantBot wettet nichts selbst, es rechnet und zeigt Hinweise.

## Der einfache Weg (empfohlen)

### 1. Python installieren (nur beim ersten Mal)

**Variante A — python.org (einfach):**
1. Gehe auf https://www.python.org/downloads/macos/
2. Lade Python 3.11 oder neuer und starte das Installationsprogramm.
3. Danach einmal das Terminal öffnen und prüfen:

```bash
python3 --version
```

**Variante B — Homebrew:**

```bash
brew install python@3.12
```

Falls Python fehlt, öffnet die Startdatei die Download-Seite automatisch.

### 2. QuantBot herunterladen

1. Öffne https://github.com/Dobolino/Oddsforge
2. Grüner Knopf **Code**, dann **Download ZIP**.
3. Entpacke die ZIP, zum Beispiel nach `~/Downloads/Oddsforge` oder `~/Oddsforge`.

### 3. Starten

Im Finder den Projektordner öffnen und doppelklicken auf:

```
Start QuantBot.command
```

Beim ersten Mal richtet sie alles automatisch ein (dauert ein paar Minuten). Danach öffnet sich das Dashboard von selbst im Browser. Ab dem zweiten Mal startet es sofort.

Zum Beenden das Terminal-Fenster schliessen.

#### macOS meldet „nicht öffnen“ / Gatekeeper?

Beim ersten Doppelklick kann macOS warnen, weil die Datei aus dem Internet kommt:

1. **Rechtsklick** (oder Control-Klick) auf `Start QuantBot.command`
2. **Öffnen** wählen
3. Nochmal **Öffnen** bestätigen

Alternativ einmal im Terminal:

```bash
cd ~/Oddsforge   # dein Entpack-Ordner
chmod +x "Start QuantBot.command" "Update QuantBot.command"
```

Danach funktioniert Doppelklick.

### 4. Aktualisieren

Doppelklick auf:

```
Update QuantBot.command
```

Das holt **immer den Branch `main`** von GitHub (per Git oder per ZIP), räumt Python-Caches und installiert neu. Am Ende siehst du Version und Git-Stand.

Danach QuantBot **komplett beenden** (Terminal-Fenster schliessen) und erneut mit `Start QuantBot.command` starten.

## Was du im Dashboard machst

1. Beim ersten Start die Willkommenskarte lesen und Alter/Risiko bestätigen.
2. Links die Sprache auf Deutsch stellen.
3. Die Ansicht auf **Einfach / Anfänger** lassen.
4. Eine Liga wählen.
5. Zwischen den Seiten wechseln: Tipps, Tracker, Glossar (Tippschein erst ab Fortgeschritten).

Oben steht immer ein Warnhinweis: QuantBot wettet nicht selbst und garantiert keinen Gewinn.

## Der Terminal-Weg (nur für Fortgeschrittene)

```bash
cd ~/Oddsforge
bash install.sh
source .venv/bin/activate
quantbot dashboard
```

Oder ohne Browser: `quantbot predict` und `quantbot backtest`.

## Echte Spiele der laufenden Saison

Dafür brauchst du zwei kostenlose Schlüssel (Football-Data.org und The Odds API). Am einfachsten trägst du sie im Dashboard unter API-Schlüssel ein — sie bleiben nur auf deinem Mac.

Alternativ `.env.example` nach `.env` kopieren und die Keys eintragen (siehe README).

## Wenn etwas klemmt

- **„python3: command not found“**: Python von python.org oder per Homebrew installieren, Terminal neu öffnen.
- **Startdatei lässt sich nicht öffnen**: Rechtsklick → Öffnen; oder `chmod +x` wie oben.
- **„quantbot wird nicht erkannt“**: Umgebung aktivieren mit `source .venv/bin/activate`.
- **Live-Modus meckert über fehlende Schlüssel**: Keys im Dashboard oder in `.env` prüfen.

## Zur Sicherheit

QuantBot garantiert keinen Gewinn und platziert keine Wetten. Du entscheidest immer selbst. Wette nie mehr, als du verlieren kannst. Hilfe bei Glücksspielproblemen: BZgA-Hotline 0800 1 37 27 00 · check-dein-spiel.de · OASIS-Selbstsperre.
