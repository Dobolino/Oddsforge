"""Lightweight internationalization for the CLI and dashboard.

German ("de") and English ("en"). ``t(key, lang)`` looks up a UI string and
falls back to German, then to the key itself. ``GLOSSARY`` holds the glossary
content in both languages.
"""

from __future__ import annotations

LANGUAGES: tuple[str, ...] = ("de", "en")
DEFAULT_LANGUAGE = "de"

_STRINGS: dict[str, dict[str, str]] = {
    # Shared / branding
    "tagline": {"de": "Nur Entscheidungshilfe. Keine automatischen Wetten.",
                "en": "Decision support only. No automated betting."},
    "guardrail.stakes": {"de": "Nur theoretische Einsätze", "en": "Theoretical stakes only"},
    "guardrail.prob": {"de": "Wahrscheinlichkeiten, keine Prognosen", "en": "Probabilities, not predictions"},
    "guardrail.sim": {"de": "Simuliert auf Demodaten", "en": "Simulated on dummy data"},
    "guardrails.body": {
        "de": "Leitplanken: kein Data Leakage, keine automatischen Wetten, Wahrscheinlichkeit vor Prognose, strikte Schichtentrennung.",
        "en": "Guardrails: zero data leakage, no automated betting, probability over prediction, strict layer separation.",
    },
    # UX depth modes
    "ux.title": {"de": "Ansicht", "en": "View"},
    "ux.beginner": {"de": "Einfach", "en": "Simple"},
    "ux.advanced": {"de": "Mehr Details", "en": "More detail"},
    "ux.expert": {"de": "Pro", "en": "Pro"},
    "ux.beginner_hint": {
        "de": "Nur das Nötigste: ein Tipp, eine Begründung.",
        "en": "Only the essentials: one tip, one reason.",
    },
    "ux.advanced_hint": {
        "de": "Tipp plus Wahrscheinlichkeiten, Vorsprung und Einsatz.",
        "en": "Tip plus probabilities, edge and stake.",
    },
    "ux.expert_hint": {
        "de": "Alle Kennzahlen, Modelle, Backtest und Diagnose.",
        "en": "All metrics, models, backtest and diagnostics.",
    },
    "welcome.title": {"de": "Willkommen bei QuantBot", "en": "Welcome to QuantBot"},
    "welcome.body": {
        "de": "Du bist im Demomodus. Die Zahlen sind erfunden und nur zum Ausprobieren. "
              "QuantBot wettet nichts selbst — du entscheidest.",
        "en": "You are in demo mode. The numbers are made up and only for trying the app. "
              "QuantBot never places bets — you decide.",
    },
    "welcome.steps": {
        "de": "1. Links Liga „Alle“ oder eine Liga wählen.\n"
              "2. Datumsbereich setzen (Heute / 3 Tage / 7 Tage).\n"
              "3. Unter Tipps lesen, dann Tippschein öffnen.",
        "en": "1. Choose „All“ or one league on the left.\n"
              "2. Set a date range (Today / 3 days / 7 days).\n"
              "3. Read Tips, then open the tip slip.",
    },
    "welcome.dismiss": {"de": "Verstanden — starten", "en": "Got it — start"},
    "welcome.go_tips": {"de": "Zu den Tipps", "en": "Go to tips"},
    "welcome.go_slip": {"de": "Tippschein öffnen", "en": "Open tip slip"},
    "welcome.later": {"de": "Später", "en": "Later"},
    "matchwarn.title": {
        "de": "Achtung: Teamnamen-Zuordnung unsicher",
        "en": "Warning: uncertain team-name matching",
    },
    "matchwarn.body": {
        "de": "Bei {fuzzy} Spielen wurden Vereinsnamen nur ungefähr zugeordnet "
              "({unmatched} Quoten-Events ohne Treffer). Prüfe diese Paare, bevor du "
              "echte Entscheidungen triffst.",
        "en": "{fuzzy} matches used approximate club-name mapping "
              "({unmatched} odds events unmatched). Check these pairs before making "
              "real decisions.",
    },
    "matchwarn.fuzzy_row": {
        "de": "Ungefähr: {odds} ↔ {fixture} (Ähnlichkeit {score:.0%})",
        "en": "Approximate: {odds} ↔ {fixture} (similarity {score:.0%})",
    },
    "matchwarn.unmatched_row": {
        "de": "Ohne Treffer: {odds}",
        "en": "No match: {odds}",
    },
    "safety.banner": {
        "de": "QuantBot platziert keine Wetten und garantiert keinen Gewinn. "
              "Fussball ist nicht sicher vorhersagbar. Entscheide selbst und "
              "setze nie mehr, als du verlieren kannst.",
        "en": "QuantBot does not place bets and guarantees no profit. "
              "Football is not reliably predictable. Decide yourself and "
              "never stake more than you can afford to lose.",
    },
    "safety.short": {
        "de": "Nur Entscheidungshilfe — QuantBot wettet nicht.",
        "en": "Decision support only — QuantBot does not bet.",
    },
    "safety.demo": {
        "de": "Du siehst Demodaten mit erfundenen Zahlen. Gut zum Ausprobieren, "
              "nicht zum Wetten.",
        "en": "You are seeing demo data with made-up numbers. Fine for trying "
              "the app, not for real betting.",
    },
    "ctrl.window_sidebar": {"de": "Spieltag-Fenster", "en": "Matchday window"},
    "slip.from_tips": {
        "de": "Aus Tipps übernommen: Beste Chancen — kurze Kombi mit den Tipps höchster Modellwahrscheinlichkeit.",
        "en": "Taken from Tips: Best win chance — short slip with the highest-probability tips.",
    },
    "slip.adjust": {"de": "Schein anpassen", "en": "Adjust slip"},
    "track.learn_miss": {
        "de": "Tipp daneben? Oft war „Kein Tipp“ die bessere Entscheidung — unsichere Spiele werden bewusst ausgelassen.",
        "en": "Missed a tip? Often „No tip“ was the better call — uncertain matches are skipped on purpose.",
    },
    "sig.beginner_intro": {
        "de": "Hier siehst du den klarsten Tipp für die kommenden Spiele. "
              "Ein Vorschlag, eine kurze Begründung. Mehr nicht.",
        "en": "Here is the clearest tip for the upcoming matches. "
              "One suggestion, one short reason. Nothing more.",
    },
    "sig.no_clear_tip": {
        "de": "Heute kein klarer Tipp. Oft ist „kein Tipp“ die beste Entscheidung.",
        "en": "No clear tip today. Often „no tip“ is the best decision.",
    },
    "sig.all_matches": {"de": "Alle Spiele im Überblick", "en": "All matches at a glance"},
    "sig.other_matches": {"de": "Weitere Tipps", "en": "More tips"},
    "sig.tip_of_day": {"de": "Klarer Vorschlag", "en": "Clear suggestion"},
    "term.edge": {
        "de": "Edge = geschätzter Vorteil gegenüber dem Markt (Modell minus faire Marktquote).",
        "en": "Edge = estimated advantage versus the market (model minus fair market).",
    },
    "term.ev": {
        "de": "EV = erwarteter Gewinn pro Einsatz, wenn die Schätzung stimmt.",
        "en": "EV = expected profit per stake if the estimate is right.",
    },
    "term.stake": {
        "de": "Einsatz % = theoretischer Vorschlag nach Kelly. Kein Aufruf, echt zu setzen.",
        "en": "Stake % = theoretical Kelly suggestion. Not a call to stake real money.",
    },
    # Nav / pages
    "nav.pages": {"de": "Seiten", "en": "Pages"},
    "page.signals": {"de": "Tipps", "en": "Tips"},
    "page.slip": {"de": "Tippschein", "en": "Tip slip"},
    "slip.range_note": {"de": "Spieltage {start} bis {end}.", "en": "Match days {start} to {end}."},
    "slip.copy_title": {"de": "Als Text zum Kopieren", "en": "As text to copy"},
    "slip.ticket_title": {"de": "Dein Tippschein", "en": "Your tip slip"},
    "slip.stake": {"de": "Denkbarer Einsatz (€)", "en": "Notional stake"},
    "slip.all_leagues": {"de": "Der Schein holt Value-Tipps aus allen gewählten Ligen im Datumsbereich.", "en": "The slip pulls value tips from all selected leagues in the date window."},
    "sig.open_slip_hint": {"de": "Willst du daraus einen Tippschein? Button darunter oder links unter Seiten „Tippschein“.", "en": "Want a tip slip from this? Use the button below or Tip slip under Pages."},
    "sig.open_slip": {"de": "Tippschein anzeigen", "en": "Show tip slip"},
    "sig.tip_legend": {
        "de": "Farben: 🟢 Heimsieg · 🟡 Unentschieden · 🔵 Auswärtssieg",
        "en": "Colors: 🟢 home win · 🟡 draw · 🔵 away win",
    },
    "sig.range_summary": {"de": "Zeitraum {start}–{end}: {n} Spiele, {k} klare Tipps.", "en": "Window {start}–{end}: {n} matches, {k} clear tips."},
    "sig.all_leagues_intro": {"de": "Tipps nach Liga unterteilt. Der Tippschein kann alle Ligen im Zeitraum mischen.", "en": "Tips grouped by league. The tip slip can mix all leagues in the date window."},
    "page.insights": {"de": "Modell-Einblicke", "en": "Model insights"},
    "page.backtest": {"de": "Backtest", "en": "Backtest"},
    "page.glossary": {"de": "Glossar", "en": "Glossary"},
    "page.tracker": {"de": "Verlauf", "en": "History"},
    "page.card": {"de": "Spielkarte", "en": "Match card"},
    "page.calibration": {"de": "Kalibrierung", "en": "Calibration"},
    "page.models": {"de": "Modellvergleich", "en": "Model comparison"},
    "page.diagnostics": {"de": "Diagnose", "en": "Diagnostics"},
    # Diagnostics page
    "diag.intro": {
        "de": "Welche Features bringen wirklich etwas, und welche Modellversion war besser? Bitte vorsichtig lesen.",
        "en": "Which features actually help, and which model version was better? Read with care.",
    },
    "diag.ablation": {"de": "Ablation: Feature weglassen", "en": "Ablation: leave a feature out"},
    "diag.ablation_hint": {
        "de": "Höherer Brier nach dem Weglassen (positives Delta) heisst, das Feature war nützlich.",
        "en": "A higher Brier after removal (positive delta) means the feature was useful.",
    },
    "diag.importance": {"de": "Feature Importance", "en": "Feature importance"},
    "diag.importance_hint": {
        "de": "Anteil am Einfluss laut Permutationstest. Nur ein Hinweis, kein Beweis.",
        "en": "Share of influence from a permutation test. A hint, not proof.",
    },
    "diag.experiments": {"de": "Experimente und Versionen", "en": "Experiments and versions"},
    "diag.experiments_hint": {
        "de": "Jede Modellversion mit Out-of-Sample-Kennzahlen. So sieht man, ob eine Version besser wurde.",
        "en": "Each model version with out-of-sample metrics, so you can see if a version improved.",
    },
    "col.group": {"de": "Feature-Gruppe", "en": "Feature group"},
    "col.delta": {"de": "Delta Brier", "en": "Brier delta"},
    "col.feature": {"de": "Feature", "en": "Feature"},
    "col.importance": {"de": "Einfluss %", "en": "Importance %"},
    "col.version": {"de": "Version", "en": "Version"},
    "col.dataset": {"de": "Datensatz", "en": "Dataset"},
    # Calibration page
    "cal.intro": {
        "de": "Sind die Wahrscheinlichkeiten realistisch? Vorhergesagte Konfidenz gegen tatsächliche Trefferquote, aus dem Walk-Forward.",
        "en": "Are the probabilities realistic? Predicted confidence versus actual accuracy, from the walk-forward.",
    },
    "cal.confidence": {"de": "Vorhergesagte Konfidenz", "en": "Predicted confidence"},
    "cal.accuracy": {"de": "Tatsächliche Trefferquote", "en": "Actual accuracy"},
    "cal.note": {
        "de": "Punkte über der Diagonale bedeuten zu vorsichtig, darunter zu selbstsicher.",
        "en": "Points above the diagonal mean underconfident, below means overconfident.",
    },
    # Model comparison
    "models.intro": {
        "de": "Jedes Modell durch den Walk-Forward. Niedriger ist besser bei Brier und Log Loss.",
        "en": "Each model through the walk-forward. Lower is better for Brier and log loss.",
    },
    "col.brier": {"de": "Brier", "en": "Brier"},
    "col.logloss": {"de": "Log Loss", "en": "Log loss"},
    "col.ece": {"de": "Kalibrierungsfehler", "en": "Calibration error"},
    "col.samples": {"de": "Spiele", "en": "Samples"},
    # Backtest breakdowns
    "bt.breakdowns": {"de": "Aufschlüsselung", "en": "Breakdowns"},
    "bt.by_odds": {"de": "Nach Quotenbereich", "en": "By odds range"},
    "bt.by_edge": {"de": "Nach Edge-Stufe", "en": "By edge bucket"},
    "bt.by_league": {"de": "Nach Liga", "en": "By league"},
    "bt.by_month": {"de": "Nach Monat", "en": "By month"},
    "col.range": {"de": "Bereich", "en": "Range"},
    "col.n": {"de": "Anzahl", "en": "Count"},
    # Match card
    "card.intro": {
        "de": "Volle Analyse pro Spiel: Modelle, Konsens, Unsicherheit, faire Quoten, Divergenz, Datenqualität und das Warum.",
        "en": "Full per-match analysis: models, consensus, uncertainty, fair odds, divergence, data quality and the why.",
    },
    "card.probs": {"de": "Wahrscheinlichkeit (mit Bandbreite)", "en": "Probability (with range)"},
    "card.consensus": {"de": "Modell-Konsens", "en": "Model consensus"},
    "card.agreement": {"de": "Einigkeit", "en": "Agreement"},
    "card.fair_vs_market": {"de": "Faire vs Marktquote", "en": "Fair vs market odds"},
    "card.fair": {"de": "Fair", "en": "Fair"},
    "card.market": {"de": "Markt", "en": "Market"},
    "card.divergence": {"de": "Abweichung Modell zu Markt", "en": "Model vs market divergence"},
    "card.reliability": {"de": "Verlässlichkeit (nicht Gewinnchance)", "en": "Reliability (not win chance)"},
    "card.data_quality": {"de": "Datenqualität", "en": "Data quality"},
    "card.why": {"de": "Warum dieses Signal", "en": "Why this signal"},
    "card.decision": {"de": "Entscheidung", "en": "Decision"},
    "card.stake": {"de": "Kelly-Einsatz", "en": "Kelly stake"},
    "col.model": {"de": "Modell", "en": "Model"},
    # Divergence tiers
    "div.none": {"de": "kein Unterschied", "en": "no difference"},
    "div.slight": {"de": "leicht", "en": "slight"},
    "div.interesting": {"de": "interessant", "en": "interesting"},
    "div.strong": {"de": "stark", "en": "strong"},
    "div.extreme": {"de": "extrem", "en": "extreme"},
    # Data-quality component labels
    "dq.history": {"de": "Historische Spiele", "en": "Match history"},
    "dq.market": {"de": "Mehrere Buchmacher", "en": "Multiple bookmakers"},
    "dq.injuries": {"de": "Verletzungsdaten", "en": "Injury data"},
    "dq.liquidity": {"de": "Liquidität", "en": "Liquidity"},
    "card.disclaimer": {
        "de": "Keine Gewinngarantie. Modellwahrscheinlichkeit ist nicht das tatsächliche Ergebnis.",
        "en": "No guarantee of profit. Model probability is not the actual outcome.",
    },
    # Tracker page
    "track.intro": {
        "de": "Was der Bot vorgeschlagen hat und wie es ausging, Woche für Woche. Tipps werden dauerhaft gespeichert und nach dem Spiel abgerechnet.",
        "en": "What the bot suggested and how it turned out, week by week. Tips are stored persistently and settled after the match.",
    },
    "track.persisted": {
        "de": "Gespeicherter Verlauf ({n} Tipps): {path}",
        "en": "Saved history ({n} tips): {path}",
    },
    "track.hit_rate": {"de": "Trefferquote gesamt", "en": "Overall hit rate"},
    "track.settled_bets": {"de": "Abgerechnete Tipps", "en": "Settled tips"},
    "track.correct": {"de": "Richtig", "en": "Correct"},
    "track.upcoming_label": {"de": "kommende Woche", "en": "upcoming"},
    "track.tip": {"de": "Tipp", "en": "Tip"},
    "track.result": {"de": "Ergebnis", "en": "Result"},
    "track.hit": {"de": "Treffer", "en": "Hit"},
    "track.miss": {"de": "Daneben", "en": "Miss"},
    "track.pending": {"de": "offen", "en": "pending"},
    # API keys
    "keys.title": {"de": "API-Schlüssel (für echte Daten)", "en": "API keys (for real data)"},
    "keys.football": {"de": "Football-Data.org Schlüssel", "en": "Football-Data.org key"},
    "keys.odds": {"de": "The Odds API Schlüssel", "en": "The Odds API key"},
    "keys.hint": {
        "de": "Leer lassen für Demodaten. Mit beiden Schlüsseln laufen echte Spiele. Schlüssel werden nur lokal auf diesem PC gespeichert.",
        "en": "Leave empty for demo data. With both keys real matches are used. Keys are stored only on this PC.",
    },
    "keys.loaded": {
        "de": "Gespeicherte Schlüssel geladen (nicht im Klartext angezeigt).",
        "en": "Saved keys loaded (not shown in plain text).",
    },
    "keys.saved": {
        "de": "Schlüssel lokal gespeichert. Beim nächsten Start automatisch geladen.",
        "en": "Keys saved locally. They will load automatically next time.",
    },
    "keys.clear": {"de": "Gespeicherte Schlüssel löschen", "en": "Delete saved keys"},
    "keys.change": {"de": "Schlüssel neu eingeben", "en": "Enter keys again"},
    "keys.use_saved": {"de": "Gespeicherte Schlüssel verwenden", "en": "Use saved keys"},
    "mode.demo": {"de": "Modus: Demodaten", "en": "Mode: demo data"},
    "mode.live": {"de": "Modus: echte Daten", "en": "Mode: real data"},
    "mode.live_failed": {"de": "Echte Daten nicht erreichbar, nutze Demodaten.", "en": "Real data unavailable, using demo data."},
    "mode.finished_cache": {
        "de": "Ergebnisse lokal gespeichert (zuletzt {when}). Abgeschlossene Spiele werden nicht erneut geladen.",
        "en": "Results stored locally (last {when}). Finished matches are not re-fetched.",
    },
    "mode.finished_cache_never": {
        "de": "Noch keine abgeschlossenen Spiele lokal gespeichert.",
        "en": "No finished matches stored locally yet.",
    },
    "no_matches": {
        "de": "Keine Spiele für {league} {season} gefunden.",
        "en": "No matches found for {league} {season}.",
    },
    "no_matches_demo": {
        "de": "Die Demodaten decken nur die Saison 2024-2025 ab. Für andere Ligen und Saisons oben die API-Schlüssel eintragen.",
        "en": "The demo data only covers the 2024-2025 season. For other leagues and seasons enter the API keys above.",
    },
    "no_matches_live_empty": {
        "de": "Football-Data lieferte keine Spiele. Prüfe den Football-Data-API-Schlüssel, "
              "dein Kontingent und die Internetverbindung. Danach Dashboard neu starten "
              "(oder Update QuantBot + Start).",
        "en": "Football-Data returned no fixtures. Check the Football-Data API key, "
              "quota and network, then restart the dashboard (or Update QuantBot + Start).",
    },
    "no_matches_live_hint": {
        "de": "Live-Modus aktiv, aber keine Spiele für {season}. "
              "Unter Fortgeschritten eine andere Saison eintragen (z. B. 2025-2026) "
              "oder den Football-Data-Schlüssel prüfen.",
        "en": "Live mode is on, but there are no fixtures for {season}. "
              "In Advanced mode try another season (e.g. 2025-2026) "
              "or check the Football-Data API key.",
    },
    "no_matches_season_fallback": {
        "de": "Für {preferred} keine Spiele — zeige verfügbare Saison {season}.",
        "en": "No fixtures for {preferred} — showing available season {season}.",
    },
    # Controls
    "ctrl.language": {"de": "Sprache", "en": "Language"},
    "ctrl.league": {"de": "Liga", "en": "League"},
    "ctrl.league_all": {"de": "Alle Ligen", "en": "All leagues"},
    "ctrl.league_all_hint": {
        "de": "„Alle Ligen“ zeigt Tipps und Tippschein über mehrere Wettbewerbe.",
        "en": "„All leagues“ shows tips and the tip slip across competitions.",
    },
    "ctrl.league_all_pick_one": {
        "de": "Für diese Seite bitte eine einzelne Liga wählen. „Alle“ gilt für Tipps, Tippschein und Verlauf.",
        "en": "Pick a single league for this page. „All“ applies to Tips, Tip slip and Tracker.",
    },
    "ctrl.date_range": {"de": "Spieltage (von–bis)", "en": "Match days (from–to)"},
    "ctrl.date_range_hint": {
        "de": "Nur Spiele in diesem Zeitraum kommen auf Tipps und Tippschein.",
        "en": "Only matches in this window appear on Tips and the tip slip.",
    },
    "ctrl.range_today": {"de": "Heute", "en": "Today"},
    "ctrl.range_3d": {"de": "3 Tage", "en": "3 days"},
    "ctrl.range_7d": {"de": "7 Tage", "en": "7 days"},
    "ctrl.season": {"de": "Saison", "en": "Season"},
    "ctrl.as_of": {"de": "Prognosedatum (Stand)", "en": "Prediction date (as of)"},
    "ctrl.as_of_today": {"de": "Auf heute setzen", "en": "Jump to today"},
    "ctrl.as_of_hint_live": {
        "de": "Standard ist heute. Ändere das Datum, wenn du einen anderen Spieltag anschauen willst.",
        "en": "Default is today. Change the date to look at another matchday.",
    },
    "ctrl.as_of_hint_demo": {
        "de": "In der Demo liegt der Standard in der Mitte der Demaison, damit Spiele sichtbar sind.",
        "en": "In demo mode the default is mid-season so fixtures are visible.",
    },
    "slip.intro": {
        "de": "Hier entsteht ein Tippschein wie beim Buchmacher: Spiel, Tipp, Quote, "
              "über Liga und Datumsbereich. QuantBot setzt nichts — nur zum Abschreiben.",
        "en": "Builds a tip slip like at a bookmaker: match, tip, odds, across league "
              "and date range. QuantBot places nothing — copy only.",
    },
    "slip.style": {"de": "Schein-Art", "en": "Slip style"},
    "slip.style_safe": {"de": "Beste Chancen", "en": "Best win chance"},
    "slip.style_boosted": {
        "de": "Beste Chancen + Quoten-Booster",
        "en": "Best chance + odds boosters",
    },
    "slip.style_safe_hint": {
        "de": "Nimmt die Tipps mit der höchsten Modell-Wahrscheinlichkeit.",
        "en": "Takes the tips with the highest model probability.",
    },
    "slip.style_boosted_hint": {
        "de": "Sichere Kern-Tipps plus zusätzliche Tipps mit höherer Quote, um die Kombi-Quote zu heben.",
        "en": "Safer core tips plus extra higher-odds tips to lift the combined price.",
    },
    "slip.max_legs": {"de": "Anzahl Tipps im Schein", "en": "Number of tips on the slip"},
    "slip.core_legs": {"de": "Kern-Tipps", "en": "Core tips"},
    "slip.boost_legs": {"de": "Booster-Tipps", "en": "Booster tips"},
    "slip.edit_legs": {
        "de": "Tipps auswählen (Haken weg = raus aus dem Schein)",
        "en": "Select tips (uncheck = remove from the slip)",
    },
    "slip.legs_risk": {
        "de": "Mehr Tipps = höhere Quote, aber kleinere Chance, dass alles trifft.",
        "en": "More tips = higher odds, but a lower chance that all hit.",
    },
    "slip.empty": {
        "de": "Keine Value-Tipps für einen Schein. Oft ist kein Schein die beste Entscheidung.",
        "en": "No value tips for a slip. Often no slip is the best decision.",
    },
    "slip.combined_odds": {"de": "Kombi-Quote", "en": "Combined odds"},
    "slip.combined_prob": {"de": "Geschätzte Trefferchance", "en": "Estimated hit chance"},
    "slip.combined_ev": {"de": "Erwartungswert (Kombi)", "en": "Expected value (slip)"},
    "slip.legs": {"de": "Tipps im Schein", "en": "Legs on the slip"},
    "slip.role": {"de": "Rolle", "en": "Role"},
    "slip.role_core": {"de": "Kern", "en": "Core"},
    "slip.role_boost": {"de": "Booster", "en": "Booster"},
    "slip.disclaimer": {
        "de": "Unabhängigkeitsannahme: Die Trefferchance ist das Produkt der Einzelwahrscheinlichkeiten. "
              "In der Praxis hängen Spiele zusammen. Kein Aufruf zum Wetten.",
        "en": "Independence assumption: hit chance is the product of single probabilities. "
              "In practice matches are correlated. Not a call to bet.",
    },
    "slip.col_prob": {"de": "Chance", "en": "Chance"},
    "track.week_summary": {
        "de": "Zuletzt abgerechnet: {correct} von {bets} Tipps richtig ({rate}).",
        "en": "Latest settled: {correct} of {bets} tips correct ({rate}).",
    },
    "track.week_summary_none": {
        "de": "Noch keine abgerechneten Tipps in der Historie.",
        "en": "No settled tips in the history yet.",
    },
    "track.path_expander": {
        "de": "Technische Speicherung",
        "en": "Technical storage",
    },
    # Signals page
    "sig.intro": {
        "de": "Signale vergleichen Modellwahrscheinlichkeiten mit margenfreien Marktpreisen. Edge, Erwartungswert und ein Fractional-Kelly-Einsatz je Spiel.",
        "en": "Signals compare model probabilities against margin-free market prices. Edge, expected value and a fractional-Kelly stake per fixture.",
    },
    "sig.matches": {"de": "Ausgewertete Spiele", "en": "Matches evaluated"},
    "sig.values": {"de": "Value-Signale", "en": "Value signals"},
    "sig.avg_edge": {"de": "Ø Edge", "en": "Avg edge"},
    "sig.avg_stake": {"de": "Ø Kelly-Einsatz", "en": "Avg Kelly stake"},
    "sig.table": {"de": "Signale", "en": "Signals"},
    # Columns
    "col.match": {"de": "Spiel", "en": "Match"},
    "col.signal": {"de": "Signal", "en": "Signal"},
    "col.odds": {"de": "Quote", "en": "Odds"},
    "col.edge": {"de": "Edge", "en": "Edge"},
    "col.ev": {"de": "EV", "en": "EV"},
    "col.stake": {"de": "Einsatz %", "en": "Stake %"},
    "col.conf": {"de": "Konfidenz", "en": "Confidence"},
    "col.reason": {"de": "Begründung", "en": "Rationale"},
    "col.metric": {"de": "Kennzahl", "en": "Metric"},
    "col.value": {"de": "Wert", "en": "Value"},
    "col.data_quality": {"de": "Datenqualität", "en": "Data quality"},
    # Insights page
    "ins.intro": {
        "de": "Die Dixon-Coles Ergebnis-Matrix und wie jedes Modell die 1X2-Wahrscheinlichkeit aufteilt.",
        "en": "The Dixon-Coles scoreline matrix and how each model splits the 1X2 probability.",
    },
    "ins.heat": {"de": "Dixon-Coles Ergebniswahrscheinlichkeiten", "en": "Dixon-Coles scoreline probabilities"},
    "ins.heat_hint": {"de": "Zeilen = Heimtore, Spalten = Auswärtstore. Farbe skaliert mit Wahrscheinlichkeit.",
                      "en": "Rows = home goals, columns = away goals. Cell shade scales with probability."},
    "ins.compare": {"de": "Modellvergleich", "en": "Model comparison"},
    "ins.compare_hint": {"de": "P(Heim / Unentschieden / Auswärts) je Modell.", "en": "P(Home / Draw / Away) per model."},
    "ins.home": {"de": "Heim", "en": "Home"},
    "ins.draw": {"de": "Remis", "en": "Draw"},
    "ins.away": {"de": "Auswärts", "en": "Away"},
    "ins.home_goals": {"de": "Heimtore", "en": "Home goals"},
    "ins.away_goals": {"de": "Auswärtstore", "en": "Away goals"},
    # Backtest page
    "bt.intro": {
        "de": "Streng chronologisch. Die Schlussquote fliesst nur in den CLV, nie in die Entscheidung.",
        "en": "Strictly chronological. The closing line feeds only Closing Line Value, never the decision.",
    },
    "bt.roi": {"de": "ROI (Yield)", "en": "ROI (yield)"},
    "bt.final": {"de": "Endkapital", "en": "Final bankroll"},
    "bt.max_dd": {"de": "Max Drawdown", "en": "Max drawdown"},
    "bt.beat_clv": {"de": "Beat-CLV-Rate", "en": "Beat-CLV rate"},
    "bt.equity": {"de": "Bankroll-Verlauf", "en": "Bankroll equity curve"},
    "bt.equity_hint": {"de": "Bankroll nach jeder abgerechneten Wette.", "en": "Bankroll after each settled bet."},
    "bt.clv": {"de": "CLV je Wette", "en": "Closing Line Value per bet"},
    "bt.clv_hint": {"de": "Positiv heisst, die Einstiegsquote war besser als die Schlussquote.",
                    "en": "Positive means the entry price beat the close."},
    "bt.metrics": {"de": "Alle Kennzahlen", "en": "Full metric set"},
    "bt.from": {"de": "von", "en": "from"},
    "bt.beat_close": {"de": "Schluss geschlagen", "en": "Beat close"},
    "bt.worse_close": {"de": "Schlechter als Schluss", "en": "Worse than close"},
    # Glossary page
    "glossary.intro": {
        "de": "Was die Begriffe bedeuten, in einfacher Sprache. QuantBot wettet nicht selbst, es bewertet nur.",
        "en": "What the terms mean, in plain language. QuantBot does not bet; it only evaluates.",
    },
    # CLI-only strings
    "info.model": {"de": "Modell", "en": "Model"},
    "info.provider": {"de": "Datenquelle", "en": "Data provider"},
    "info.margin": {"de": "Margen-Methode", "en": "Margin method"},
    "info.bankroll": {"de": "Startkapital", "en": "Initial bankroll"},
    "info.autobet": {"de": "Automatische Wetten", "en": "Automated betting"},
    "info.autobet_value": {"de": "deaktiviert (nur Entscheidungshilfe)", "en": "disabled (decision support only)"},
    "guardrails.title": {"de": "Leitplanken", "en": "Guardrails"},
    "sig.footer": {"de": "{n} Spiele ausgewertet, {k} Value-Signale.", "en": "{n} matches evaluated, {k} value signals."},
    "sig.title": {"de": "Signale: {league} {season}", "en": "Signals: {league} {season}"},
    "bt.title": {"de": "Backtest: {league} {season}", "en": "Backtest: {league} {season}"},
    "bt.matches_eval": {"de": "Ausgewertete Spiele", "en": "Matches evaluated"},
    "bt.bets": {"de": "Platzierte Wetten", "en": "Bets placed"},
    "bt.no_bets": {"de": "Keine-Wette-Entscheidungen", "en": "No-bet decisions"},
    "bt.initial": {"de": "Startkapital", "en": "Initial bankroll"},
    "bt.total_return": {"de": "Gesamtrendite", "en": "Total return"},
    "bt.win_rate": {"de": "Trefferquote", "en": "Win rate"},
    "bt.profit_factor": {"de": "Profit Factor", "en": "Profit factor"},
    "bt.sharpe": {"de": "Sharpe", "en": "Sharpe"},
    "bt.sortino": {"de": "Sortino", "en": "Sortino"},
    "bt.avg_clv": {"de": "Ø CLV", "en": "Avg CLV"},
    "no_demo": {
        "de": "Die Demodaten decken premier_league und bundesliga ab. Für andere Ligen --live mit API-Keys nutzen.",
        "en": "The demo data covers premier_league and bundesliga. For other leagues use --live with API keys.",
    },
    "live_keys_missing": {
        "de": "Der Live-Modus braucht QUANTBOT_FOOTBALL_DATA_API_KEY und QUANTBOT_THE_ODDS_API_KEY in der Umgebung oder .env.",
        "en": "Live mode needs QUANTBOT_FOOTBALL_DATA_API_KEY and QUANTBOT_THE_ODDS_API_KEY in your environment or .env file.",
    },
}


def t(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    entry = _STRINGS.get(key, {})
    return entry.get(lang) or entry.get(DEFAULT_LANGUAGE) or key


# Glossary: sections of (term, de-definition, en-definition).
GLOSSARY: list[dict[str, object]] = [
    {
        "title": {"de": "Signale", "en": "Signals"},
        "items": [
            ("VALUE_HOME / VALUE_DRAW / VALUE_AWAY",
             "Value auf Heimsieg, Unentschieden oder Auswärtssieg. Die Quote ist im Verhältnis zur geschätzten Wahrscheinlichkeit zu hoch.",
             "Value on a home win, draw or away win. The odds are too high relative to the estimated probability."),
            ("NO_BET",
             "Keine Empfehlung. Die Begründung nennt den Grund, etwa zu wenig Edge oder Datenqualität.",
             "No recommendation. The rationale states why, e.g. too little edge or data quality."),
        ],
    },
    {
        "title": {"de": "Wahrscheinlichkeit & Quoten", "en": "Probability & Odds"},
        "items": [
            ("P(Home/Draw/Away)",
             "Schätzung des Modells, wie oft ein Ergebnis eintritt. Die drei Werte ergeben 100 Prozent.",
             "The model's estimate of how often an outcome occurs. The three add up to 100 percent."),
            ("Quote / Odds",
             "Dezimalquote. Auszahlung pro Einheit Einsatz. 2.0 heisst 1 Einsatz wird zu 2.",
             "Decimal odds. Payout per unit staked. 2.0 means 1 staked returns 2."),
            ("Faire Wahrscheinlichkeit / Fair probability",
             "Marktwahrscheinlichkeit nach Herausrechnen der Buchmacher-Marge.",
             "Market probability after removing the bookmaker margin."),
            ("Overround / Marge",
             "Aufschlag des Buchmachers. Die impliziten Wahrscheinlichkeiten summieren über 100 Prozent.",
             "The bookmaker's margin. Implied probabilities sum to more than 100 percent."),
        ],
    },
    {
        "title": {"de": "Value & Einsatz", "en": "Value & Staking"},
        "items": [
            ("Edge",
             "Modellwahrscheinlichkeit minus faire Marktwahrscheinlichkeit. Positiv heisst, das Modell hält das Ergebnis für wahrscheinlicher als der Markt.",
             "Model probability minus fair market probability. Positive means the model rates the outcome higher than the market."),
            ("EV (Erwartungswert)",
             "Erwarteter Gewinn pro Einheit Einsatz. 0.10 heisst im Schnitt 10 Prozent Gewinn, wenn das Modell recht hat.",
             "Expected value per unit staked. 0.10 means 10 percent average profit if the model is right."),
            ("Kelly-Einsatz / Kelly stake",
             "Vorgeschlagener Einsatz als Anteil der Bankroll. Fractional Kelly senkt das Risiko. Rein theoretisch.",
             "Suggested stake as a fraction of bankroll. Fractional Kelly lowers risk. Purely theoretical."),
            ("Konfidenz / Confidence",
             "Wie sicher das Modell ist (0 bis 100), aus Ensemble-Einigkeit und Datenqualität.",
             "How confident the model is (0 to 100), from ensemble agreement and data quality."),
        ],
    },
    {
        "title": {"de": "Backtest-Kennzahlen", "en": "Backtest metrics"},
        "items": [
            ("ROI / Yield", "Gewinn geteilt durch gesamten Einsatz, in Prozent.",
             "Profit divided by total staked, in percent."),
            ("Profit Factor", "Bruttogewinne geteilt durch Bruttoverluste. Über 1 ist profitabel.",
             "Gross wins divided by gross losses. Above 1 is profitable."),
            ("Sharpe / Sortino", "Rendite im Verhältnis zur Schwankung. Sortino bestraft nur Abwärtsrisiko. Höher ist besser.",
             "Return relative to volatility. Sortino penalizes only downside. Higher is better."),
            ("Max Drawdown", "Grösster Rückgang vom Höchststand zum Tief. Kleiner ist besser.",
             "Largest peak-to-trough decline. Smaller is better."),
            ("Risk of Ruin", "Wahrscheinlichkeit, dass die Bankroll unter eine kritische Grenze fällt (Monte Carlo).",
             "Probability the bankroll falls below a critical threshold (Monte Carlo)."),
        ],
    },
    {
        "title": {"de": "Markt & CLV", "en": "Market & CLV"},
        "items": [
            ("CLV (Closing Line Value)",
             "Vergleich deiner Einstiegsquote mit der Schlussquote. Positiv heisst, du hattest eine bessere Quote als der Markt am Ende.",
             "Your entry price versus the closing price. Positive means you got a better price than the final market."),
            ("Beat-CLV-Rate", "Anteil der Wetten, bei denen du die Schlussquote geschlagen hast.",
             "Share of bets where you beat the closing price."),
            ("Arbitrage / Surebet", "Beste Quoten mehrerer Buchmacher ergeben zusammen unter 100 Prozent, ein risikoloser Gewinn ist möglich.",
             "Best odds across bookmakers sum below 100 percent, allowing a risk-free profit."),
            ("Line Shopping", "Für jedes Ergebnis die beste Quote über alle Buchmacher suchen.",
             "Finding the best odds per outcome across all bookmakers."),
        ],
    },
]
