# QuantBot: Konzept und Features (zum Weitergeben)

Diese Beschreibung erklärt die Idee und die Funktionen von QuantBot, ohne Code. Sie ist so geschrieben, dass sie für sich allein verständlich ist und man sie einem anderen Assistenten zur Prüfung oder für Ideen geben kann.

## Was ist QuantBot

QuantBot ist ein Analyse- und Entscheidungswerkzeug für Fussballwetten und Prediction Markets. Es schätzt für jedes Spiel die Wahrscheinlichkeit für Heimsieg, Unentschieden und Auswärtssieg, vergleicht diese mit den Quoten der Buchmacher und zeigt, wo rechnerisch ein Vorteil liegen könnte. Es platziert keine Wetten und verwaltet kein Konto. Der Mensch entscheidet.

## Grundhaltung und Leitplanken

1. Kein Data Leakage. Für jedes Spiel werden nur Daten benutzt, die vor dem Anpfiff bekannt waren. Nichts aus der Zukunft fliesst in eine Schätzung ein.
2. Keine automatischen Wetten. Version 1 ist reine Entscheidungshilfe. Es gibt keine Order, kein Konto, keine Umgehung von AGB.
3. Wahrscheinlichkeit statt Sieger raten. Das System sagt nicht einfach wer gewinnt, sondern kalibrierte Wahrscheinlichkeiten. Die Güte wird mit anerkannten Kennzahlen gemessen.
4. Strikte Trennung. Das Vorhersagemodell liefert nur Wahrscheinlichkeiten. Eine separate Logik entscheidet über Value und Risiko.
5. Keine Gewinngarantie. Alles wird als Schätzung mit Unsicherheit dargestellt.

## Die vier Ebenen (einfach erklärt)

1. Vorhersage. Modelle schätzen die Wahrscheinlichkeiten und eine Ergebnis-Matrix (wie oft welches Resultat).
2. Markt. Aus den Buchmacherquoten wird die Marge herausgerechnet, um faire Marktwahrscheinlichkeiten zu bekommen.
3. Value und Kalibrierung. Modell gegen Markt: wie gross ist der Vorteil (Edge), wie hoch der Erwartungswert, wie gut kalibriert.
4. Entscheidung. Regeln prüfen, ob sich ein Tipp lohnt, und schlagen einen theoretischen Einsatz vor. Ergebnis ist ein Signal wie VALUE_HOME oder NO_BET.

## Die Modelle

- Elo: bewertet Teamstärke dynamisch, mit Heimvorteil und Berücksichtigung der Tordifferenz.
- Dixon-Coles: Poisson-Modell für Tore mit Korrektur für niedrige Ergebnisse. Liefert eine Ergebnis-Matrix. Unterstützt Zeitgewichtung (neuere Spiele zählen mehr) und optional xG statt Tore.
- Logistische Regression und Gradient Boosting: klassische Machine-Learning-Modelle auf selbst gebauten Features.
- Ensemble: kombiniert mehrere Modelle, optional mit optimierten Gewichten.
- Kalibrierung: korrigiert die Wahrscheinlichkeiten nachträglich, damit sie realistisch sind.

## Die Features im Überblick

- Feature-Bausteine je Team: Elo-Differenz, Form der letzten Spiele, Tore und xG als gleitende Durchschnitte, Ruhetage. Alles leckfrei berechnet.
- Marktmodul: Margenentfernung nach Shin, Power und einfacher Methode. Faire Quoten.
- Value-Modul: Edge, Erwartungswert, Datenqualität und Modellkonfidenz je Spiel.
- Entscheidungsmodul: konfigurierbare Regeln (Mindest-Edge, Mindest-EV, maximale Marge, Mindestdatenqualität, extreme Quoten filtern) plus Einsatzberechnung nach Fractional Kelly.
- Backtest: streng chronologisch, testet an vergangenen Spielen. Kennzahlen: Rendite, ROI, Trefferquote, Profit Factor, Sharpe, Sortino, maximaler Drawdown.
- Closing Line Value: vergleicht die Einstiegsquote mit der Schlussquote. Gilt als guter Frühindikator.
- Monte-Carlo-Simulation: schätzt Risk of Ruin und die Bandbreite möglicher Kapitalverläufe.
- Arbitrage und Line Shopping: beste Quote je Ergebnis über mehrere Buchmacher, Erkennung von risikolosen Surebets mit passender Einsatzverteilung.

## Bedienung

- Textbefehle: predict für kommende Tipps, backtest für die Auswertung, info für den Status.
- Dashboard im Browser mit fünf Seiten: Signale, Verlauf, Modell-Einblicke, Backtest, Glossar.
- Verlauf-Seite: zeigt Woche für Woche, was getippt wurde, das Ergebnis, Treffer oder Daneben, die Trefferquote über die Zeit und die Tipps der kommenden Woche.
- Sprache umschaltbar Deutsch und Englisch.
- API-Schlüssel direkt im Dashboard eingebbar, ohne Dateien zu bearbeiten.

## Daten

- Ohne Schlüssel: eingebaute Demodaten, reproduzierbar, zum Ausprobieren. Die Zahlen sind erfunden.
- Mit Schlüssel: echte Spiele und Quoten der laufenden Saison. Ergebnisse und Spielpläne von Football-Data.org, Quoten von The Odds API.
- Unterstützte Ligen: Premier League, Bundesliga, La Liga, Serie A, Ligue 1, Champions League.

## Aktueller Stand

- Läuft lokal auf einem PC. Eine Version für Handy oder Web bräuchte einen Server, ist noch nicht gebaut.
- Die Verlauf-Seite und alle Kennzahlen funktionieren. In der Demo mit erfundenen Ergebnissen, mit Schlüsseln mit echten.
- Die Zuordnung der Teamnamen zwischen den zwei Datenquellen kann bei einzelnen Vereinen noch haken und braucht Feinschliff an echten Daten.
- Umfangreiche automatische Tests sind vorhanden, inklusive einer eigenen Suite gegen Data Leakage.

## Bewusst noch nicht enthalten

- Automatisches Wetten und Kontoverwaltung. Ist gewollt ausgeschlossen.
- Bayesianische hierarchische Modelle für bessere Unsicherheit bei wenig Daten.
- Stacking-Ensemble mit einem Meta-Modell.
- Verletzungs- und News-Analyse per Sprachmodell als zusätzliche Features.
- Weitere Sportarten wie Basketball oder Tennis.
- Schweizer Super League, sobald eine verlässliche Ergebnisquelle da ist.

## Fragen, die ein Reviewer prüfen könnte

1. Sind die Leitplanken sinnvoll und vollständig, vor allem die Absicherung gegen Data Leakage.
2. Welche Features fehlen, die den grössten Mehrwert brächten, und in welcher Reihenfolge.
3. Ist die Trennung von Vorhersage und Entscheidung sauber und praxistauglich.
4. Welche Kennzahlen sind für die Bewertung am aussagekräftigsten, und fehlt etwas.
5. Wo liegen die grössten Risiken für Selbsttäuschung, etwa Overfitting oder zu optimistische Backtests.
6. Ist der Plan für echte Daten und die Namenszuordnung robust genug.

## Wichtiger Hinweis

QuantBot garantiert keinen Gewinn. Fussball ist nicht sicher vorhersagbar. Das System ist ein Werkzeug zur Analyse und Entscheidungsunterstützung. Wette nie mehr, als du verlieren kannst.
