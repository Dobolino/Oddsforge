# Glossar: Was bedeuten die Begriffe?

QuantBot zeigt Kennzahlen, die aus dem Sportwetten- und Finanzumfeld stammen. Hier die wichtigsten in einfacher Sprache. QuantBot wettet nicht selbst, es bewertet nur.

## Signale

- VALUE_HOME, VALUE_DRAW, VALUE_AWAY: Das Modell sieht einen Value auf Heimsieg, Unentschieden oder Auswärtssieg. Value heisst, die Quote ist im Verhältnis zur geschätzten Wahrscheinlichkeit zu hoch.
- NO_BET / Kein Value: Kein ausreichend belastbarer Value. Die Rejection Reasons sagen dir, warum (zum Beispiel zu wenig Edge, zu geringe Datenqualität).

## Wahrscheinlichkeit und Quoten

- Wahrscheinlichkeit P(Home/Draw/Away): Schätzung des Modells, wie oft ein Ergebnis eintritt. Die drei Werte ergeben zusammen 100 Prozent.
- Dezimalquote (Odds): Auszahlung pro Einheit Einsatz. Quote 2.0 heisst, 1 Einsatz wird zu 2 (also 1 Gewinn plus Einsatz zurück).
- Faire Wahrscheinlichkeit: Marktwahrscheinlichkeit, nachdem die Buchmacher-Marge herausgerechnet wurde.
- Overround (Marge): Der Aufschlag des Buchmachers. Die Summe der impliziten Wahrscheinlichkeiten liegt über 100 Prozent. Der Überschuss ist die Marge.

## Value und Einsatz

- Edge: Modellwahrscheinlichkeit minus faire Marktwahrscheinlichkeit. Positiver Edge heisst, das Modell hält das Ergebnis für wahrscheinlicher als der Markt.
- EV (Expected Value, Erwartungswert): Erwarteter Gewinn pro Einheit Einsatz. EV von 0.10 heisst im Schnitt 10 Prozent Gewinn pro Einsatz, wenn das Modell recht hat.
- Kelly Stake: Vorgeschlagener Einsatz als Anteil der Bankroll, basierend auf Edge und Quote. QuantBot nutzt Fractional Kelly, also einen Bruchteil, um das Risiko zu senken. Rein theoretisch.
- Prognosequalität (früher oft „Confidence“): Messbare Zuverlässigkeit von 0 bis 100 aus Ensemble-Einigkeit und Datenqualität — keine Gewinnchance und keine Siegprognose.
- Data Quality: Wie gut die Datenlage ist, von 0 bis 100 (Anzahl Spiele, Buchmacher, Verletzungsinfos).

## Backtest-Kennzahlen

- Bankroll: Dein simuliertes Kapital.
- ROI (Yield): Gewinn geteilt durch gesamten Einsatz, in Prozent.
- Total Return: Gesamtveränderung der Bankroll, in Prozent.
- Win Rate: Anteil gewonnener Wetten.
- Profit Factor: Bruttogewinne geteilt durch Bruttoverluste. Über 1 ist profitabel.
- Sharpe Ratio: Rendite im Verhältnis zur Schwankung. Höher ist besser.
- Sortino Ratio: Wie Sharpe, bestraft aber nur Abwärtsschwankungen. Höher ist besser.
- Max Drawdown: Grösster Rückgang vom Höchststand zum Tief, in Prozent. Kleiner ist besser.
- Risk of Ruin: Wahrscheinlichkeit, dass die Bankroll unter eine kritische Grenze fällt (Monte-Carlo-Simulation).

## Modelle

- Elo: Bewertet Teamstärke dynamisch, ähnlich wie im Schach.
- Dixon-Coles: Poisson-Modell für Tore, mit Korrektur für niedrige Ergebnisse. Liefert eine Ergebnis-Matrix.
- Logistic Regression, Gradient Boosting: klassische ML-Modelle.
- Ensemble: Kombination mehrerer Modelle.
- Kalibrierung: Nachträgliche Korrektur, damit die Wahrscheinlichkeiten realistisch sind.

## Markt und CLV

- CLV (Closing Line Value): Vergleich deiner Einstiegsquote mit der Schlussquote. Positiver CLV heisst, du hattest eine bessere Quote als der Markt am Ende. Gilt als bester Frühindikator für langfristigen Erfolg.
- Beat-CLV-Rate: Anteil der Wetten, bei denen du die Schlussquote geschlagen hast.
- Arbitrage (Surebet): Wenn die besten Quoten über verschiedene Buchmacher zusammen unter 100 Prozent liegen, ist ein risikoloser Gewinn möglich.
- Line Shopping: Für jedes Ergebnis die beste verfügbare Quote über alle Buchmacher suchen.

## Wichtiger Hinweis

Kein Modell garantiert Gewinne. Alle Werte sind Schätzungen mit Unsicherheit. QuantBot ist ein Analysewerkzeug, keine Wettmaschine.
