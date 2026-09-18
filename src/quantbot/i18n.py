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
        "de": "Nur das Nötigste: ein Modell-Signal und eine Begründung.",
        "en": "Only the essentials: one tip, one reason.",
    },
    "ux.advanced_hint": {
        "de": "Modell-Signal, Modell-P, statistische Abweichung und erwartete Rendite.",
        "en": "Tip plus model P, edge in percentage points and expected return.",
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
              "3. Unter Modell-Signale lesen — ohne Kombi-Analyse im Einfach-Modus.",
        "en": "1. Choose „All“ or one league on the left.\n"
              "2. Set a date range (Today / 3 days / 7 days).\n"
              "3. Read Model signals — no accumulator analysis in Simple mode.",
    },
    "welcome.dismiss": {"de": "Verstanden — starten", "en": "Got it — start"},
    "welcome.go_tips": {"de": "Zu den Modell-Signalen", "en": "Go to model signals"},
    "welcome.go_slip": {"de": "Kombi-Analyse öffnen", "en": "Open accumulator analysis"},
    "welcome.later": {"de": "Später", "en": "Later"},
    "welcome.responsible": {
        "de": "Nur für Erwachsene (18+). Glücksspiel kann süchtig machen. "
              "Hilfe: BZgA-Hotline 0800 1 37 27 00 · check-dein-spiel.de · "
              "Selbstsperre über OASIS (gluecksspiel-behoerde.de). "
              "QuantBot ist eine statistische Entscheidungshilfe — keine Gewinnzusage.",
        "en": "Adults only (18+). Gambling can be addictive. "
              "Help: BZgA hotline 0800 1 37 27 00 · check-dein-spiel.de · "
              "Self-exclusion via OASIS (gluecksspiel-behoerde.de). "
              "QuantBot is statistical decision support — not a promise of profit.",
    },
    "welcome.age_confirm": {
        "de": "Ich bin mindestens 18 Jahre alt und verstehe die Risiken von Glücksspiel.",
        "en": "I am at least 18 years old and understand the risks of gambling.",
    },
    "welcome.age_required": {
        "de": "Bitte bestätige zuerst das Alter (18+), bevor du startest.",
        "en": "Please confirm you are 18+ before starting.",
    },
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
              "setze nie mehr, als du verlieren kannst. Hilfe bei Glücksspielproblemen: "
              "Check dein Spiel (check-dein-spiel.de) · BZgA-Hotline 0800 1 37 27 00 · "
              "Selbstsperre OASIS (gluecksspiel-behoerde.de). "
              "Erfolgreiches Spielen kann bei Buchmachern zu Limits/Kontosperren führen.",
        "en": "QuantBot does not place bets and guarantees no profit. "
              "Football is not reliably predictable. Decide yourself and "
              "never stake more than you can afford to lose. Help with gambling problems: "
              "Check dein Spiel (check-dein-spiel.de) · BZgA hotline 0800 1 37 27 00 · "
              "Self-exclusion OASIS (gluecksspiel-behoerde.de). "
              "Successful play can lead to bookmaker limits or account restrictions.",
    },
    "safety.short": {
        "de": "Nur Entscheidungshilfe — QuantBot wettet nicht. Hilfe: check-dein-spiel.de · 0800 1 37 27 00.",
        "en": "Decision support only — QuantBot does not bet. Help: check-dein-spiel.de · 0800 1 37 27 00.",
    },
    "safety.demo": {
        "de": "Demodaten — nur zum Ausprobieren, keine reale Erwartung.",
        "en": "Demo data — for trying the app, not a real return expectation.",
    },
    "safety.account_limits": {
        "de": "Hinweis: Gute Tipps können bei Buchmachern zu Limits führen.",
        "en": "Note: Strong tips can lead to bookmaker stake limits.",
    },
    "ctrl.window_sidebar": {"de": "Spieltag-Fenster", "en": "Matchday window"},
    "ctrl.agenda": {"de": "Agenda", "en": "Agenda"},
    "ctrl.agenda_hint": {
        "de": "Tag tippen → Entwurf. Danach „Übernehmen“.",
        "en": "Tap a day → draft. Then press Apply.",
    },
    "ctrl.agenda_empty": {
        "de": "Keine Spiele in diesem Entwurf.",
        "en": "No fixtures in this draft range.",
    },
    "ctrl.window_apply": {"de": "Zeitraum übernehmen", "en": "Apply date range"},
    "ctrl.window_pending": {
        "de": "Entwurf noch nicht übernommen.",
        "en": "Draft not applied yet.",
    },
    "ctrl.window_active": {
        "de": "Aktiv: {start} – {end}",
        "en": "Active: {start} – {end}",
    },
    "ctrl.date_range": {"de": "Spieltage (von–bis)", "en": "Matchdays (from–to)"},
    "ctrl.date_range_hint": {
        "de": "Nur Spiele in diesem Zeitraum.",
        "en": "Only fixtures in this window.",
    },
    "slip.from_tips": {
        "de": "Aus Modell-Signalen: kurze Kombi mit hoher Modell-P.",
        "en": "From model signals: short high model-P slip.",
    },
    "slip.adjust": {"de": "Analyse anpassen", "en": "Adjust analysis"},
    "slip.hero_kicker": {"de": "Simulation", "en": "Simulation"},
    "slip.hero_sub": {
        "de": "Signale + Quoten im Zeitraum — QuantBot wettet nicht.",
        "en": "Signals + odds in the window — QuantBot does not bet.",
    },
    "slip.options": {"de": "Optionen", "en": "Options"},
    "track.learn_miss": {
        "de": "Signal daneben? Oft war „Kein Signal“ die bessere Entscheidung — unsichere Spiele werden bewusst ausgelassen.",
        "en": "Missed a signal? Often „No signal“ was the better call — uncertain matches are skipped on purpose.",
    },
    "sig.beginner_intro": {
        "de": "Hier siehst du den klarsten Value für die kommenden Spiele. "
              "Ein Modell-Signal, eine kurze Begründung. Mehr nicht.",
        "en": "Here is the clearest value for the upcoming matches. "
              "One model signal, one short reason. Nothing more.",
    },
    "sig.hit_rate_caption": {
        "de": "Bisherige Trefferquote (abgerechnet): {rate} — keine Garantie für künftige Signale.",
        "en": "Settled hit rate so far: {rate} — no guarantee for future signals.",
    },
    "sig.hit_rate_none": {
        "de": "Noch keine abgerechneten Signale — Trefferquote erscheint nach ersten Ergebnissen.",
        "en": "No settled signals yet — hit rate appears after the first results.",
    },
    "sig.edge_band_hint": {
        "de": "Edge wird mit Unsicherheitsband gezeigt (kein formales Konfidenzintervall).",
        "en": "Edge is shown with an uncertainty band (not a formal confidence interval).",
    },
    "sig.no_clear_tip": {
        "de": "Warum kein Signal? Kein ausreichend belastbarer Value — das ist ein normales Ergebnis, kein Fehler.",
        "en": "Why no signal? No sufficiently robust value — that is a normal outcome, not a failure.",
    },
    "sig.exploratory": {
        "de": "Explorativ — Modell nicht empirisch freigegeben; kein Simulations-Einsatz.",
        "en": "Exploratory — model not empirically released; no simulated stake.",
    },
    "sig.validation": {
        "de": "Validierung: {status}",
        "en": "Validation: {status}",
    },
    "sig.model_estimate_caption": {
        "de": "Modellschätzung, keine Gewinnzusage. Unsicherheit nicht belastbar quantifiziert, sofern nicht ausgewiesen.",
        "en": "Model estimate, not a promise of winning. Uncertainty not reliably quantified unless shown.",
    },
    "sig.beginner_metrics": {
        "de": "Modell {model} · Abweichung {edge} · Datenabdeckung/Qualität {quality}",
        "en": "Model {model} · Deviation {edge} · Data coverage/quality {quality}",
    },
    "sig.all_matches": {"de": "Alle Spiele im Überblick", "en": "All matches at a glance"},
    "sig.other_matches": {"de": "Weitere Modell-Signale", "en": "More model signals"},
    "sig.tip_of_day": {"de": "Modell-Signal", "en": "Model signal"},
    "term.edge": {
        "de": "Edge = Modell-P minus Marktschätzung ohne Marge, in Prozentpunkten. Nicht dasselbe wie relative %.",
        "en": "Edge = model P minus margin-free market estimate, in percentage points. Not the same as relative %.",
    },
    "term.ev": {
        "de": "EV = geschätzter langfristiger Nettoertrag pro Einsatz unter Modellannahmen (p × Quote − 1). Kein garantierter Return.",
        "en": "EV = estimated long-term net return per unit stake under model assumptions (p × odds − 1). Not a guaranteed return.",
    },
    "term.stake": {
        "de": "Einsatz % = theoretischer Fractional-Kelly-Vorschlag nur bei freigegebenem Validierungsstatus. Kein Echtgeld.",
        "en": "Stake % = theoretical fractional-Kelly suggestion only when validation releases sizing. Not real money.",
    },
    "term.forecast_quality": {
        "de": "Modellübereinstimmung, Datenabdeckung und Validierungsstatus sind getrennt — keine kombinierte „Sicherheitszahl“.",
        "en": "Model agreement, data coverage and validation status are separate — not one combined “safety score”.",
    },
    # Nav / pages
    "nav.pages": {"de": "Seiten", "en": "Pages"},
    "page.signals": {"de": "Modell-Signale", "en": "Model signals"},
    "page.slip": {"de": "Kombi-Analyse", "en": "Accumulator analysis"},
    "slip.range_note": {"de": "Spieltage {start} bis {end}.", "en": "Match days {start} to {end}."},
    "slip.copy_title": {"de": "Als Text zum Kopieren", "en": "As text to copy"},
    "slip.ticket_title": {"de": "Kombi-Simulation", "en": "Accumulator scenario"},
    "slip.stake": {
        "de": "Simulierte Einheiten",
        "en": "Simulated units",
    },
    "slip.all_leagues": {
        "de": "Alle gewählten Ligen im Zeitraum.",
        "en": "All selected leagues in the window.",
    },
    "sig.open_slip_hint": {
        "de": "Kombi-Analyse? Button darunter oder links unter Seiten „Kombi-Analyse“.",
        "en": "Accumulator analysis? Use the button below or Accumulator analysis under Pages.",
    },
    "sig.open_slip": {"de": "Kombi-Analyse anzeigen", "en": "Show accumulator analysis"},
    "sig.tip_legend": {
        "de": "Farben: 🟢 Heimsieg · 🟡 Unentschieden · 🔵 Auswärtssieg",
        "en": "Colors: 🟢 home win · 🟡 draw · 🔵 away win",
    },
    "sig.range_summary": {
        "de": "Zeitraum {start}–{end}: {n} Spiele, {k} Modell-Signale.",
        "en": "Window {start}–{end}: {n} matches, {k} model signals.",
    },
    "sig.value_rate": {
        "de": "Value-Anteil: {k} von {n} Spielen ({pct}%). Bei sehr hohem Anteil oft zu wenig Daten — vorsichtig bleiben.",
        "en": "Value share: {k} of {n} matches ({pct}%). A very high share often means thin data — stay cautious.",
    },
    "sig.value_share": {"de": "Value-Anteil", "en": "Value share"},
    "sig.top_n_note": {
        "de": "Hauptliste: Top {n} nach Edge (von {total} Value-Tipps). Rest unter „Alle Spiele“.",
        "en": "Main list: top {n} by edge (of {total} value tips). Rest under “All matches”.",
    },
    "sig.all_leagues_intro": {"de": "Tipps nach Liga unterteilt. Der Tippschein kann alle Ligen im Zeitraum mischen.", "en": "Tips grouped by league. The tip slip can mix all leagues in the date window."},
    "page.insights": {"de": "Modell-Einblicke", "en": "Model insights"},
    "page.backtest": {"de": "Backtest", "en": "Backtest"},
    "page.glossary": {"de": "Glossar", "en": "Glossary"},
    "page.tracker": {"de": "Verlauf", "en": "History"},
    "page.paper": {"de": "Papiersimulation", "en": "Paper simulation"},
    "paper.hero_kicker": {"de": "Einheiten", "en": "Units"},
    "paper.hero_sub": {
        "de": "Papierkonto mit Caps — kein Echtgeld, kein Auto-Betting.",
        "en": "Paper account with caps — no real money, no auto-betting.",
    },
    "paper.intro": {
        "de": "Basis 1000 Einheiten · max. 5 % pro Spiel · max. 10 % offen.",
        "en": "Base 1000 units · max 5% per match · max 10% open.",
    },
    "paper.available": {"de": "Verfügbar", "en": "Available"},
    "paper.open": {"de": "Offen", "en": "Open"},
    "paper.realized": {"de": "Realisiert", "en": "Realized"},
    "paper.capital": {"de": "Kapitalbasis", "en": "Capital base"},
    "paper.caps": {
        "de": "Cap Spiel {match:.0f} · Cap offen {open:.0f}",
        "en": "Match cap {match:.0f} · Open cap {open:.0f}",
    },
    "paper.open_list": {"de": "Offene Reservierungen", "en": "Open reservations"},
    "paper.empty": {
        "de": "Keine offenen Buchungen. Reserviere über die Kombi-Analyse.",
        "en": "No open bookings. Reserve from Accumulator analysis.",
    },
    "paper.booking_meta": {
        "de": "{stake:.1f} Einheiten · Quote {odds:.2f} · ID {id}",
        "en": "{stake:.1f} units · odds {odds:.2f} · ID {id}",
    },
    "paper.leg_line": {
        "de": "{n}. {match} · {sel} @ {odds:.2f}",
        "en": "{n}. {match} · {sel} @ {odds:.2f}",
    },
    "paper.settle_win": {"de": "Gewinn", "en": "Win"},
    "paper.settle_loss": {"de": "Verlust", "en": "Loss"},
    "paper.settle_void": {"de": "Void", "en": "Void"},
    "paper.cancel": {"de": "Lösen", "en": "Release"},
    "paper.commit": {
        "de": "In Papiersimulation reservieren",
        "en": "Reserve in paper simulation",
    },
    "paper.commit_ok": {
        "de": "Reserviert ({id}).",
        "en": "Reserved ({id}).",
    },
    "paper.commit_blocked": {
        "de": "Blockiert: {reasons}",
        "en": "Blocked: {reasons}",
    },
    "paper.preview": {
        "de": "Danach offen {open:.1f} · verfügbar {avail:.1f}",
        "en": "Then open {open:.1f} · available {avail:.1f}",
    },
    "paper.mode_note": {
        "de": "Modus „{mode}“ — Demo- und Live-Ledger getrennt.",
        "en": "Mode “{mode}” — demo and live ledgers stay separate.",
    },
    "paper.open_page": {
        "de": "Zur Papiersimulation",
        "en": "Open paper simulation",
    },
    "help.footer": {
        "de": "Hilfe & Glossar jederzeit über Seiten → Glossar · check-dein-spiel.de · 0800 1 37 27 00",
        "en": "Help & glossary always via Pages → Glossary · check-dein-spiel.de · 0800 1 37 27 00",
    },
    "help.open_glossary": {"de": "Glossar", "en": "Glossary"},
    "safety.demo_badge": {"de": "DEMO", "en": "DEMO"},
    "page.card": {"de": "Spielkarte", "en": "Match card"},
    "page.calibration": {"de": "Kalibrierung", "en": "Calibration"},
    "page.models": {"de": "Modellvergleich", "en": "Model comparison"},
    "page.diagnostics": {"de": "Diagnose", "en": "Diagnostics"},
    # Diagnostics page
    "diag.intro": {
        "de": "Welche Features bringen wirklich etwas, und welche Modellversion war besser? Bitte vorsichtig lesen.",
        "en": "Which features actually help, and which model version was better? Read with care.",
    },
    "sig.no_odds_matched": {
        "de": "{n} kommende Spiele im Fenster, aber keine passenden Quoten "
              "(Namens-Mismatch oder Odds-API). Sidebar-Warnungen und API-Key prüfen; "
              "Cache leeren und neu laden.",
        "en": "{n} upcoming matches in the window, but no matching odds "
              "(name mismatch or Odds API). Check sidebar warnings and API key; "
              "clear cache and reload.",
    },
    "sig.no_fixtures_in_window": {
        "de": "Keine kommenden Spiele in diesem Zeitraum für die gewählte Liga/Saison.",
        "en": "No upcoming matches in this window for the selected league/season.",
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
        "de": "Kalibrierung des Live-Defaults Dixon-Coles (Walk-Forward): "
              "vorhergesagte Wahrscheinlichkeit gegen tatsächliche Trefferquote. "
              "Brier Score und ECE zeigen, wie gut p_Modell dem echten Outcome entspricht.",
        "en": "Calibration of the live default Dixon–Coles (walk-forward): "
              "predicted probability versus actual hit rate. "
              "Brier score and ECE show how well p_model matches real outcomes.",
    },
    "cal.confidence": {"de": "Vorhergesagte Konfidenz", "en": "Predicted confidence"},
    "cal.accuracy": {"de": "Tatsächliche Trefferquote", "en": "Actual accuracy"},
    "cal.note": {
        "de": "Punkte über der Diagonale bedeuten zu vorsichtig, darunter zu selbstsicher. "
              "Ohne gute Kalibrierung ist Edge nur Rauschen — prüfe Brier/ECE vor Live-Nutzung.",
        "en": "Points above the diagonal mean underconfident, below means overconfident. "
              "Without good calibration, edge is noise — check Brier/ECE before live use.",
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
    "card.no_matches_in_window": {
        "de": "Keine kommenden Spiele im gewählten Zeitraum ({start} – {end}). Zeitraum in der Sidebar anpassen.",
        "en": "No upcoming matches in the selected window ({start} – {end}). Adjust the range in the sidebar.",
    },
    "card.probs": {"de": "Wahrscheinlichkeit (mit Bandbreite)", "en": "Probability (with range)"},
    "card.consensus": {"de": "Modell-Konsens", "en": "Model consensus"},
    "card.agreement": {"de": "Einigkeit", "en": "Agreement"},
    "card.fair_vs_market": {
        "de": "Marktschätzung ohne Marge vs. Angebot",
        "en": "Margin-free market estimate vs offered",
    },
    "card.fair": {"de": "Ohne Marge", "en": "Margin-free"},
    "card.market": {"de": "Angebot", "en": "Offered"},
    "card.reliability": {
        "de": "Modellübereinstimmung (nicht Gewinnchance)",
        "en": "Model agreement (not win chance)",
    },
    "card.divergence": {"de": "Abweichung Modell zu Markt", "en": "Model vs market divergence"},
    "card.data_quality": {"de": "Datenabdeckung", "en": "Data coverage"},
    "card.why": {"de": "Warum dieses Signal", "en": "Why this signal"},
    "card.decision": {"de": "Entscheidung", "en": "Decision"},
    "card.stake": {"de": "Papier-Kelly (nur freigegeben)", "en": "Paper Kelly (released only)"},
    "card.validation": {"de": "Validierungsstatus", "en": "Validation status"},
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
        "de": "Keine Gewinn- oder Renditegarantie. Modellwahrscheinlichkeit ist eine Schätzung, "
              "keine Gewinnzusage. Vergangene Modellleistung ist keine Garantie zukünftiger Ergebnisse.",
        "en": "No win or return guarantee. Model probability is an estimate, not a promise of winning. "
              "Past model performance does not guarantee future results.",
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
    "track.tip": {"de": "Modell-Signal", "en": "Model signal"},
    "track.result": {"de": "Ergebnis", "en": "Result"},
    "track.hit": {"de": "Treffer", "en": "Hit"},
    "track.miss": {"de": "Daneben", "en": "Miss"},
    "track.pending": {"de": "offen", "en": "pending"},
    "track.clv": {"de": "CLV", "en": "CLV"},
    "track.clv_na": {"de": "CLV n/a", "en": "CLV n/a"},
    "track.clv_ref_ev": {"de": "Close-Ref-EV", "en": "Close-ref EV"},
    "track.avg_clv": {"de": "Ø CLV (Odds)", "en": "Avg CLV (odds)"},
    # API keys
    "keys.save": {"de": "Schlüssel speichern", "en": "Save keys"},
    "keys.cancel": {"de": "Änderungen verwerfen", "en": "Discard changes"},
    "keys.invalid": {"de": "Bitte beide Schlüssel ohne Leerzeichen oder Zeilenumbrüche eingeben.", "en": "Enter both keys without whitespace or line breaks."},
    "keys.write_failed": {"de": "Die lokale Schlüsseldatei konnte nicht geändert werden. Bitte Dateirechte prüfen.", "en": "Could not update the local credentials file. Check file permissions."},
    "keys.external": {"de": "Schlüssel aus der Umgebung oder .env haben Vorrang. Lokales Speichern oder Löschen ändert diese Vorgaben nicht.", "en": "Keys from the environment or .env take priority. Saving or deleting local keys does not change these overrides."},
    "keys.title": {"de": "API-Schlüssel (für echte Daten)", "en": "API keys (for real data)"},
    "keys.football": {"de": "Football-Data.org Schlüssel", "en": "Football-Data.org key"},
    "keys.odds": {"de": "The Odds API Schlüssel", "en": "The Odds API key"},
    "ctrl.sport": {"de": "Sport", "en": "Sport"},
    "ctrl.sport_all": {"de": "Alle Sportarten", "en": "All sports"},
    "ctrl.sport_football": {"de": "Fußball", "en": "Football"},
    "ctrl.sport_basketball": {"de": "Basketball / NBA", "en": "Basketball / NBA"},
    "ctrl.sport_hint": {
        "de": "Filtert die Liga-Liste. Tippschein kann Quersport-Kombi erlauben.",
        "en": "Filters the league list. Tip slips can mix sports.",
    },
    "page.settings": {"de": "Einstellungen", "en": "Settings"},
    "settings.intro": {"de": "API-Schlüssel für externe Datenanbieter. Die Anzeige bestätigt keine erfolgreiche Verbindung.", "en": "API keys for external data providers. Presence does not confirm a successful connection."},
    "settings.validate": {"de": "Hinterlegte Schlüssel", "en": "Configured keys"},
    "settings.test_connection": {"de": "Verbindung testen", "en": "Test connection"},
    "settings.connection_active": {"de": "Verbindung erfolgreich geprüft.", "en": "Connection verified."},
    "settings.connection_missing": {"de": "Kein Schlüssel hinterlegt.", "en": "No key configured."},
    "settings.connection_invalid": {"de": "Schlüssel ungültig oder Zugriff verweigert.", "en": "Invalid key or access denied."},
    "settings.connection_rate_limited": {"de": "Anbieter-Limit erreicht. Später erneut prüfen.", "en": "Provider rate limit reached. Try again later."},
    "settings.connection_unavailable": {"de": "Anbieter derzeit nicht erreichbar.", "en": "Provider currently unavailable."},
    "settings.keys_sidebar_hint": {
        "de": "Schlüssel kannst du in der Seitenleiste unter API-Schlüssel speichern oder ändern.",
        "en": "Save or change keys in the sidebar under API keys.",
    },
    "settings.ollama": {"de": "Ollama (lokal, optional)", "en": "Ollama (local, optional)"},
    "settings.ollama_intro": {
        "de": "Lokale KI nur zur Erklärung des Tippscheins — sie ändert keine Tipps. "
              "Voraussetzung: Ollama installiert und ein Modell geladen (z. B. ollama pull llama3.2).",
        "en": "Local AI only explains the tip slip — it does not change tips. "
              "Requires Ollama installed and a model pulled (e.g. ollama pull llama3.2).",
    },
    "settings.ollama_enabled": {"de": "Ollama-Erklärung aktivieren", "en": "Enable Ollama explanation"},
    "settings.ollama_url": {"de": "Ollama-URL", "en": "Ollama URL"},
    "settings.ollama_model": {"de": "Modell", "en": "Model"},
    "settings.ollama_save": {"de": "Ollama-Einstellungen speichern", "en": "Save Ollama settings"},
    "settings.ollama_test": {"de": "Verbindung testen", "en": "Test connection"},
    "settings.ollama_ok": {"de": "Ollama erreichbar. Modelle: {models}", "en": "Ollama reachable. Models: {models}"},
    "settings.ollama_fail": {"de": "Ollama nicht erreichbar: {error}", "en": "Ollama unreachable: {error}"},
    "settings.ollama_saved": {"de": "Ollama-Einstellungen gespeichert.", "en": "Ollama settings saved."},
    "slip.ollama_explain": {"de": "Erklärung mit Ollama", "en": "Explain with Ollama"},
    "slip.ollama_hint": {
        "de": "Optionale lokale KI-Zusammenfassung. Tipps bleiben unverändert.",
        "en": "Optional local AI summary. Tips stay unchanged.",
    },
    "slip.ollama_disabled": {
        "de": "Ollama ist aus. Unter Einstellungen aktivieren und Verbindung testen.",
        "en": "Ollama is off. Enable it under Settings and test the connection.",
    },
    "slip.ollama_title": {"de": "KI-Erklärung (Ollama)", "en": "AI explanation (Ollama)"},
    "keys.basketball": {"de": "BallDontLie / NBA Schlüssel (optional)", "en": "BallDontLie / NBA key (optional)"},
    "keys.basketball_missing": {"de": "BallDontLie / NBA: nicht hinterlegt (Demo-NBA aktiv)", "en": "BallDontLie / NBA: not set (demo NBA active)"},
    "keys.basketball_optional": {"de": "NBA: Demodaten (kein Schlüssel nötig).", "en": "NBA: demo data (no key needed)."},
    "keys.apifootball": {"de": "API-Football Schlüssel (optional, für Handicap-Quoten)", "en": "API-Football key (optional, for handicap odds)"},
    "keys.apifootball_optional": {"de": "API-Football optional (AH/Tore, Free: 100/Tag).", "en": "API-Football optional (AH/totals, free: 100/day)."},
    "keys.test": {"de": "API-Football testen", "en": "Test API-Football"},
    "keys.test_missing": {"de": "Zuerst den API-Football Schlüssel eintragen und speichern.", "en": "Save the API-Football key first."},
    "keys.test_ok": {"de": "Verbindung steht. Konto {account}, Tarif {plan}. Heute {used} von {limit} Abrufen genutzt, {left} übrig.", "en": "Connected. Account {account}, plan {plan}. {used} of {limit} requests used today, {left} left."},
    "keys.test_failed": {"de": "Test fehlgeschlagen: {error}", "en": "Test failed: {error}"},
    "status.active": {"de": "HINTERLEGT · UNGEPRÜFT", "en": "CONFIGURED · UNVERIFIED"},
    "status.missing": {"de": "FEHLT", "en": "MISSING"},
    "slip.smart_cross_sport": {"de": "⚡ Smart Cross-Sport Selection", "en": "⚡ Smart Cross-Sport Selection"},
    "slip.cross_sport_note": {
        "de": "Cross-Sport kann Liga-Abhängigkeit senken — Parlay-Drag bleibt.",
        "en": "Cross-sport can reduce league dependency — parlay drag remains.",
    },
    "slip.smart_empty": {
        "de": "Keine Legs erfüllen die Smart-Kriterien (Edge > 2 %, Datenqualität > 70 %).",
        "en": "No legs meet the smart criteria (edge > 2%, data quality > 70%).",
    },
    "slip.smart_done": {
        "de": "Smart Selection: {n} Legs übernommen.",
        "en": "Smart selection applied: {n} legs.",
    },

    "keys.hint": {"de": "Beide Schlüssel eintragen und speichern. Speicherung unverschlüsselt auf diesem Rechner; Übertragung per HTTPS an die Datenanbieter.", "en": "Enter both keys and save. Stored unencrypted on this machine; sent via HTTPS to the data providers."},
    "keys.loaded": {
        "de": "Gespeicherte Schlüssel geladen (nicht im Klartext angezeigt).",
        "en": "Saved keys loaded (not shown in plain text).",
    },
    "keys.active": {"de": "Schlüssel hinterlegt. Ihre Gültigkeit wird erst bei einem API-Abruf geprüft.", "en": "Keys configured. Their validity is checked only when an API request is made."},
    "keys.autoload": {
        "de": "Werden bei jedem Start automatisch geladen. Nur die letzten vier Zeichen sind sichtbar.",
        "en": "Loaded automatically on every start. Only the last four characters are shown.",
    },
    "keys.saved": {
        "de": "Schlüssel lokal gespeichert. Beim nächsten Start automatisch geladen.",
        "en": "Keys saved locally. They will load automatically next time.",
    },
    "cache.title": {"de": "Zwischenspeicher / Wartung", "en": "Cache / maintenance"},
    "cache.hint": {
        "de": "Leert die lokal gespeicherten Spiele und Quoten. Beim nächsten Laden holt die App alles frisch von den APIs. Deine Schlüssel bleiben erhalten.",
        "en": "Clears locally stored matches and odds. The next load fetches everything fresh from the APIs. Your keys stay saved.",
    },
    "cache.clear": {"de": "Zwischenspeicher leeren", "en": "Clear cache"},
    "cache.cleared": {
        "de": "Zwischenspeicher geleert. Wähle eine Liga und lade neu.",
        "en": "Cache cleared. Pick a league and reload.",
    },
    "keys.clear": {"de": "Gespeicherte Schlüssel löschen", "en": "Delete saved keys"},
    "keys.change": {"de": "Schlüssel neu eingeben", "en": "Enter keys again"},
    "keys.use_saved": {"de": "Gespeicherte Schlüssel verwenden", "en": "Use saved keys"},
    "mode.demo": {"de": "Modus: Demodaten", "en": "Mode: demo data"},
    "mode.live": {"de": "Modus: echte Daten", "en": "Mode: real data"},
    "mode.live_toggle": {"de": "Live-Daten aktivieren", "en": "Enable live data"},
    "mode.live_toggle_help": {
        "de": "Aus = Demodaten (kein API-Verbrauch). An = echte Fixtures/Quoten; "
              "braucht Football-Data + The Odds API und verbraucht Abrufe.",
        "en": "Off = demo data (no API usage). On = real fixtures/odds; "
              "needs Football-Data + The Odds API and uses request quota.",
    },
    "mode.live_needs_keys": {
        "de": "Live braucht beide Schlüssel (Football-Data + The Odds API) unter API-Schlüssel.",
        "en": "Live needs both keys (Football-Data + The Odds API) under API keys.",
    },
    "mode.live_failed": {"de": "Echte Daten nicht erreichbar, nutze Demodaten.", "en": "Real data unavailable, using demo data."},
    "mode.load_errors": {
        "de": "{n} Liga(en) konnten nicht vollständig geladen werden (siehe Details).",
        "en": "{n} league(s) could not be fully loaded (see details).",
    },
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
    "ctrl.date_range_empty_hint": {
        "de": "Spieltag-Fenster und Saison stehen links in der Sidebar.",
        "en": "Matchday window and season are in the left sidebar.",
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
        "de": "Kombi aus Signalen im Zeitraum. Mehr Tipps = mehr Risiko.",
        "en": "Combo from signals in the window. More legs = more risk.",
    },
    "slip.style": {"de": "Schein-Art", "en": "Slip style"},
    "slip.orient": {"de": "Ausrichtung", "en": "Orientation"},
    "slip.orient_safe": {"de": "Sicher", "en": "Safe"},
    "slip.orient_balanced": {"de": "Ausgewogen", "en": "Balanced"},
    "slip.orient_contra": {
        "de": "Gegen den Markt",
        "en": "Against the market",
    },
    "slip.orient_hint": {
        "de": "Sicher = kurze Quoten. Gegen den Markt = bewusst riskanter.",
        "en": "Safe = short odds. Against the market = deliberately riskier.",
    },
    "slip.orient_safe_default": {
        "de": "Standard: Sicher. Gegen den Markt erst bewusst wählen.",
        "en": "Default: Safe. Choose against the market deliberately.",
    },
    "slip.active_orient": {
        "de": "Ausrichtung: {orient}",
        "en": "Orientation: {orient}",
    },
    "slip.high_risk": {
        "de": "Höheres Risiko (mehr Tipps)",
        "en": "Higher risk (more tips)",
    },
    "slip.high_risk_help": {
        "de": "Hebt Sicherheitsgrenzen an — Kombi kann unglaubwürdig wirken.",
        "en": "Lifts safety caps — combo may look unrealistic.",
    },
    "slip.high_risk_warn": {
        "de": "⚠ HÖHERES RISIKO — längere Kombi, oft unrealistische Chancen. Nur Simulation.",
        "en": "⚠ HIGHER RISK — longer combo, often unrealistic chances. Simulation only.",
    },
    "slip.high_risk_count": {
        "de": "Tipps: {have} (gewünscht {want})",
        "en": "Tips: {have} (wanted {want})",
    },
    "slip.limits_caption": {
        "de": "{n} Tipps (max. {cap}). Ohne Höheres Risiko wird gekürzt.",
        "en": "{n} tips (max {cap}). Without higher risk the slip is trimmed.",
    },
    "slip.combo_chance_na": {
        "de": "nicht belastbar",
        "en": "not reliable",
    },
    "slip.style_safe": {"de": "Hohe Modell-P", "en": "High model-P"},
    "slip.style_boosted": {
        "de": "Auswahl + höhere Quoten",
        "en": "Selection + higher odds",
    },
    "slip.style_safe_hint": {
        "de": "Höchste Modell-Wahrscheinlichkeiten.",
        "en": "Highest model probabilities.",
    },
    "slip.style_boosted_hint": {
        "de": "Kern + Zusatz mit höheren Quoten.",
        "en": "Core + extras with higher odds.",
    },
    "slip.max_legs": {"de": "Anzahl Tipps", "en": "Number of tips"},
    "slip.core_legs": {"de": "Kern-Tipps", "en": "Core tips"},
    "slip.boost_legs": {"de": "Zusatz-Tipps", "en": "Extra tips"},
    "slip.edit_legs": {
        "de": "Tipps auswählen (Haken weg = raus aus dem Schein)",
        "en": "Select tips (uncheck = remove from the slip)",
    },
    "slip.legs_risk": {
        "de": "Mehr Tipps = höhere Quote, kleinere Trefferchance.",
        "en": "More tips = higher odds, lower hit chance.",
    },
    "slip.empty": {
        "de": "Keine Value-Tipps für einen Schein.",
        "en": "No value tips for a slip.",
    },
    "slip.combined_odds": {"de": "Kombi-Quote", "en": "Combined odds"},
    "slip.combined_prob": {"de": "Kombi-P", "en": "Combo P"},
    "slip.combined_ev": {"de": "Erwartete Rendite", "en": "Expected return"},
    "slip.implausible": {
        "de": "Modellwerte zu hoch / zu wenig Daten — nicht verlässlich.",
        "en": "Model values too high / too little data — not reliable.",
    },
    "slip.trimmed_note": {
        "de": "Schein gekürzt (Glaubwürdigkeit).",
        "en": "Slip shortened (credibility).",
    },
    "slip.legs": {"de": "Tipps im Schein", "en": "Legs on the slip"},
    "slip.role": {"de": "Rolle", "en": "Role"},
    "slip.role_core": {"de": "Kern", "en": "Core"},
    "slip.role_boost": {"de": "Zusatz", "en": "Extra"},
    "slip.disclaimer": {
        "de": "Kombi-P ist eine Näherung (Spiele korrelieren). Keine Wett-Aufforderung.",
        "en": "Combo P is an approximation (matches correlate). Not a call to bet.",
    },
    "slip.glossary_gate": {
        "de": "Bitte einmal das Glossar lesen, bevor der Tippschein freigeschaltet wird.",
        "en": "Please open the glossary once before the tip slip unlocks.",
    },
    "slip.glossary_cta": {"de": "Zum Glossar", "en": "Open glossary"},
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
        "de": "Signale vergleichen Modellwahrscheinlichkeiten mit margenfreien Marktpreisen. "
              "Edge in Prozentpunkten, erwartete Rendite und theoretischer Fractional-Kelly-Einsatz.",
        "en": "Signals compare model probabilities against margin-free market prices. "
              "Edge in percentage points, expected return and a theoretical fractional-Kelly stake.",
    },
    "sig.matches": {"de": "Ausgewertete Spiele", "en": "Matches evaluated"},
    "sig.values": {"de": "Value-Signale", "en": "Value signals"},
    "sig.avg_edge": {"de": "Ø Edge (pp)", "en": "Avg edge (pp)"},
    "sig.avg_stake": {"de": "Ø Kelly-Einsatz", "en": "Avg Kelly stake"},
    "sig.table": {"de": "Signale", "en": "Signals"},
    # Columns
    "col.match": {"de": "Spiel", "en": "Match"},
    "col.signal": {"de": "Signal", "en": "Signal"},
    "col.odds": {"de": "Quote", "en": "Odds"},
    "col.edge": {"de": "Edge (pp)", "en": "Edge (pp)"},
    "col.ev": {"de": "Erw. Rendite", "en": "Exp. return"},
    "col.stake": {"de": "Einsatz %", "en": "Stake %"},
    "col.conf": {"de": "Prognosequalität", "en": "Forecast quality"},
    "col.reason": {"de": "Begründung", "en": "Rationale"},
    "col.metric": {"de": "Kennzahl", "en": "Metric"},
    "col.value": {"de": "Wert", "en": "Value"},
    "col.data_quality": {"de": "Datenqualität", "en": "Data quality"},
    "col.model_p": {"de": "Modell-P", "en": "Model P"},
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
    "bt.roi_caveat": {
        "de": "ROI ohne Standardabweichung und Max-Drawdown ist irreführend. "
              "Vergangene Backtest-Ergebnisse sind keine Garantie für die Zukunft. "
              "Demo-Daten verzerren die reale Erwartung. "
              "Overround-Filter sind Liquiditäts-Proxys, kein Qualitätsmaß für das Modell.",
        "en": "ROI without standard deviation and max drawdown is misleading. "
              "Past backtest results are not a guarantee of the future. "
              "Demo data distorts real expectations. "
              "Overround filters are liquidity proxies, not a model-quality measure.",
    },
    "bt.monte_carlo": {"de": "Bankroll-Simulation (theoretisch)", "en": "Bankroll simulation (theoretical)"},
    "bt.monte_carlo_hint": {
        "de": "Monte-Carlo unter Modellwahrscheinlichkeiten — zeigt Drawdown-Risiko, keine Prognose.",
        "en": "Monte Carlo under model probabilities — shows drawdown risk, not a forecast.",
    },
    "bt.risk_of_ruin": {"de": "Ruin-Risiko (50%-Schwelle)", "en": "Risk of ruin (50% threshold)"},
    "bt.dd_p95": {"de": "Max-Drawdown p95", "en": "Max drawdown p95"},
    "bt.final_p5": {"de": "End-Bankroll p5", "en": "Final bankroll p5"},
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
    "live_keys_missing": {"de": "API-Schlüssel fehlen. Im Dashboard speichern oder QUANTBOT_FOOTBALL_DATA_API_KEY und QUANTBOT_THE_ODDS_API_KEY in .env setzen.", "en": "API keys missing. Save them in the dashboard or set QUANTBOT_FOOTBALL_DATA_API_KEY and QUANTBOT_THE_ODDS_API_KEY in .env."},
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
             "Warum kein Signal? Korrektes Ergebnis, wenn kein ausreichend belastbarer Value vorliegt. "
             "Reason-Codes erklären warum (z. B. NO_BET_LOW_EDGE).",
             "Why no signal? The correct outcome when there is no sufficiently robust value. "
             "Reason codes explain why (e.g. NO_BET_LOW_EDGE)."),
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
            ("Marktschätzung ohne Marge / Margin-free market estimate",
             "Marktwahrscheinlichkeit nach Herausrechnen der Buchmacher-Marge (Methode im Detailbereich).",
             "Market probability after removing the bookmaker margin (method in the detail view)."),
            ("Overround / Marge",
             "Aufschlag des Buchmachers. Die impliziten Wahrscheinlichkeiten summieren über 100 Prozent.",
             "The bookmaker's margin. Implied probabilities sum to more than 100 percent."),
        ],
    },
    {
        "title": {"de": "Value & Einsatz", "en": "Value & Staking"},
        "items": [
            ("Edge (absolut, pp)",
             "Modellwahrscheinlichkeit minus Marktschätzung ohne Marge, in Prozentpunkten. "
             "Beispiel: 56,3 % − 50,0 % = +6,3 Prozentpunkte. Nicht dasselbe wie relative %.",
             "Model probability minus margin-free market estimate, in percentage points. "
             "Example: 56.3% − 50.0% = +6.3 percentage points. Not the same as relative %."),
            ("Edge (relativ)",
             "(Modell − Markt) / Markt. Beispiel: (0,563 − 0,50) / 0,50 = 12,6 % relativ.",
             "(Model − market) / market. Example: (0.563 − 0.50) / 0.50 = 12.6% relative."),
            ("Erwartete Rendite / EV",
             "Geschätzter langfristiger Nettoertrag pro Einsatz unter Modellannahmen: EV = p × Quote − 1. "
             "Kein garantierter Return einer einzelnen Wette.",
             "Estimated long-term net return per unit stake under model assumptions: EV = p × odds − 1. "
             "Not a guaranteed return on a single bet."),
            ("Kelly-Einsatz / Kelly stake",
             "Theoretischer Einsatzanteil der Papierbankroll nur bei freigegebenem Validierungsstatus. "
             "Fractional Kelly senkt das Risiko. Nie automatisch ausgeführt.",
             "Theoretical paper-bankroll fraction only when validation releases sizing. "
             "Fractional Kelly lowers risk. Never auto-executed."),
            ("Prognosequalität / Forecast quality",
             "Modellübereinstimmung, Datenabdeckung und Validierungsstatus getrennt führen — "
             "keine kombinierte Sicherheitszahl und keine Gewinnwahrscheinlichkeit.",
             "Keep model agreement, data coverage and validation status separate — "
             "not one combined safety score and not a win probability."),
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
