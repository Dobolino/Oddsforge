"""QuantBot Streamlit dashboard.

Run with ``quantbot dashboard`` (or ``streamlit run <this file>``). The UI is
executed only when the module runs as the Streamlit entry script, so importing
it for tests stays side-effect free. German/English switchable in the sidebar.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from quantbot import __version__
from quantbot.dashboard.components import (
    clv_distribution_figure,
    equity_curve_figure,
    metrics_dataframe,
    model_comparison_figure,
    scoreline_heatmap_figure,
    signals_dataframe,
)
from quantbot.i18n import DEFAULT_LANGUAGE, GLOSSARY, LANGUAGES, t


def _current_season() -> str:
    """Season label for today, e.g. '2026-2027' from August 2026 on."""

    now = datetime.now(timezone.utc)
    start = now.year if now.month >= 7 else now.year - 1
    return f"{start}-{start + 1}"


# --- Cached heavy computations ---
# Streamlit does not hash arguments whose names start with "_", so the live
# provider / orchestrator can be passed without being hashed; ``mode`` (demo or
# live), league and season form the cache key. This stops every page from
# recomputing models on each click.

def _finished(_provider, mode, league_value, season):  # type: ignore[no-untyped-def]  # pragma: no cover
    from quantbot.schemas import League

    far = datetime(2100, 1, 1, tzinfo=timezone.utc)
    return [m for m in _provider.get_matches(League(league_value), season, far) if m.is_finished]


def _install_cache():  # pragma: no cover - requires Streamlit runtime
    """Wrap the expensive calls in st.cache_data (30 min TTL)."""

    cache = st.cache_data(ttl=1800, show_spinner="Berechne …")

    @cache
    def universe(_orch, mode, league_value, season):
        from quantbot.schemas import League
        return _orch.universe(League(league_value), season)

    @cache
    def predict(_orch, mode, league_value, season, as_of_iso):
        from quantbot.schemas import League
        a = datetime.fromisoformat(as_of_iso) if as_of_iso else None
        return _orch.predict(League(league_value), season, a)

    @cache
    def cards(_orch, mode, league_value, season):
        from quantbot.schemas import League
        return _orch.build_match_cards(League(league_value), season)

    @cache
    def backtest(_orch, mode, league_value, season):
        from quantbot.schemas import League
        return _orch.run_backtest(League(league_value), season)

    @cache
    def rounds(_provider, mode, league_value, season):
        from quantbot.schemas import League
        from quantbot.tracking import build_rounds
        return build_rounds(_provider, League(league_value), season, hold_out_last=1)

    @cache
    def calibration(_matches, mode, league_value, season):
        from quantbot.analysis.evaluation import calibration_report
        from quantbot.models import EloModel
        return calibration_report(_matches, EloModel())

    @cache
    def models(_matches, mode, league_value, season):
        from quantbot.analysis.evaluation import model_comparison
        from quantbot.models import DixonColesModel, EloModel, LogisticRegressionModel
        return model_comparison(
            {"Elo": EloModel(), "Dixon-Coles": DixonColesModel(min_matches=5),
             "Logistic": LogisticRegressionModel()},
            _matches,
        )

    @cache
    def ablation(_matches, mode, league_value, season):
        from quantbot.analysis.diagnostics import ablation_report
        return ablation_report(_matches)

    @cache
    def importance(_matches, mode, league_value, season):
        from quantbot.analysis.diagnostics import feature_importance
        return feature_importance(_matches)

    return {
        "universe": universe, "predict": predict, "cards": cards, "backtest": backtest,
        "rounds": rounds, "calibration": calibration, "models": models,
        "ablation": ablation, "importance": importance,
        "finished": st.cache_data(ttl=1800, show_spinner="Berechne …")(_finished),
    }


def _render() -> None:  # pragma: no cover - requires Streamlit runtime
    from pathlib import Path

    from quantbot.config import get_settings
    from quantbot.models import DixonColesModel, EloModel, LogisticRegressionModel
    from quantbot.orchestrator import QuantBotOrchestrator
    from quantbot.schemas import League

    st.set_page_config(page_title="QuantBot", page_icon="⚽", layout="wide")
    st.sidebar.title(f"QuantBot v{__version__}")

    default_lang = get_settings().language if get_settings().language in LANGUAGES else DEFAULT_LANGUAGE
    lang = st.sidebar.radio(
        "Sprache / Language",
        list(LANGUAGES),
        index=list(LANGUAGES).index(default_lang),
        format_func=lambda c: "Deutsch" if c == "de" else "English",
        horizontal=True,
    )
    st.sidebar.caption(t("tagline", lang))

    pages = {
        "signals": t("page.signals", lang),
        "card": t("page.card", lang),
        "tracker": t("page.tracker", lang),
        "insights": t("page.insights", lang),
        "calibration": t("page.calibration", lang),
        "models": t("page.models", lang),
        "diagnostics": t("page.diagnostics", lang),
        "backtest": t("page.backtest", lang),
        "glossary": t("page.glossary", lang),
    }
    page = st.sidebar.radio(t("nav.pages", lang), list(pages), format_func=lambda k: pages[k])
    league = st.sidebar.selectbox(t("ctrl.league", lang), list(League), format_func=lambda lg: lg.value)

    # API keys: paste here instead of editing files. Both filled -> real data.
    with st.sidebar.expander(t("keys.title", lang)):
        fd_key = st.text_input(t("keys.football", lang), type="password")
        odds_key = st.text_input(t("keys.odds", lang), type="password")
        st.caption(t("keys.hint", lang))

    provider = None
    live = False
    if fd_key and odds_key:
        try:
            from quantbot.data.providers import build_live_provider

            provider = build_live_provider(fd_key, odds_key, [league], cache_dir=Path.home() / ".quantbot" / "cache")
            live = True
            st.sidebar.success(t("mode.live", lang))
        except Exception:  # noqa: BLE001
            st.sidebar.warning(t("mode.live_failed", lang))
            provider = None
    else:
        st.sidebar.info(t("mode.demo", lang))

    # Demo data only exists for 2024-2025; live data uses the current season.
    default_season = _current_season() if live else "2024-2025"
    season = st.sidebar.text_input(t("ctrl.season", lang), default_season)

    orchestrator = QuantBotOrchestrator(provider=provider)
    mode = "live" if live else "demo"
    C = _install_cache()

    if page == "glossary":
        _glossary_page(lang)
        return

    # Every other page needs matches. Fail softly instead of crashing.
    uni_all = C["universe"](orchestrator, mode, league.value, season)
    if not uni_all:
        st.header(pages[page])
        st.warning(t("no_matches", lang).format(league=league.value, season=season))
        if not live:
            st.info(t("no_matches_demo", lang))
        return

    if page == "tracker":
        _tracker_page(lang, C, orchestrator.provider, mode, league, season)
        return

    if page == "card":
        _card_page(lang, C, orchestrator, mode, league, season)
        return

    if page in ("calibration", "models"):
        _evaluation_page(page, lang, C, orchestrator.provider, mode, league, season)
        return

    if page == "diagnostics":
        _diagnostics_page(lang, C, orchestrator.provider, mode, league, season)
        return

    universe = uni_all

    if page == "signals":
        st.header(t("page.signals", lang))
        default_as_of = orchestrator.default_as_of(league, season).date()
        as_of_date = st.date_input(t("ctrl.as_of", lang), default_as_of)
        as_of = datetime(as_of_date.year, as_of_date.month, as_of_date.day, tzinfo=timezone.utc)
        reports = C["predict"](orchestrator, mode, league.value, season, as_of.isoformat())
        n_bets = sum(1 for r in reports if r.signal.is_bet)
        st.caption(t("sig.intro", lang))
        c1, c2 = st.columns(2)
        c1.metric(t("sig.matches", lang), len(reports))
        c2.metric(t("sig.values", lang), n_bets)
        st.dataframe(signals_dataframe(reports), use_container_width=True)

    elif page == "insights":
        st.header(t("page.insights", lang))
        st.caption(t("ins.intro", lang))
        as_of = orchestrator.default_as_of(league, season)
        upcoming = [m for m in universe if m.kickoff > as_of]
        if not upcoming:
            st.warning("No upcoming matches." if lang == "en" else "Keine kommenden Spiele.")
            return
        match = st.selectbox(
            t("col.match", lang),
            upcoming,
            format_func=lambda m: f"{m.home_team.name} vs {m.away_team.name}",
        )
        model_probs: dict[str, list[float]] = {}
        for name, model in (("Elo", EloModel()), ("Logistic", LogisticRegressionModel()),
                            ("Dixon-Coles", DixonColesModel(min_matches=10))):
            try:
                model.fit_until(universe, as_of)
                p = model.predict(match)
                model_probs[name] = [p.prob_home, p.prob_draw, p.prob_away]
            except (ValueError, RuntimeError):
                pass
        col1, col2 = st.columns([1.6, 1])
        with col1:
            st.subheader(t("ins.heat", lang))
            st.caption(t("ins.heat_hint", lang))
            try:
                dc = DixonColesModel(min_matches=10)
                dc.fit_until(universe, as_of)
                dcp = dc.predict(match)
                if dcp.score_matrix is not None:
                    st.plotly_chart(scoreline_heatmap_figure(dcp.score_matrix.matrix), use_container_width=True)
            except (ValueError, RuntimeError):
                st.info("Insufficient history." if lang == "en" else "Zu wenig Historie.")
        with col2:
            st.subheader(t("ins.compare", lang))
            st.caption(t("ins.compare_hint", lang))
            if model_probs:
                labels = (t("ins.home", lang), t("ins.draw", lang), t("ins.away", lang))
                st.plotly_chart(model_comparison_figure(model_probs, labels), use_container_width=True)

    else:  # backtest
        st.header(t("page.backtest", lang))
        st.caption(t("bt.intro", lang))
        result = C["backtest"](orchestrator, mode, league.value, season)
        m = result.metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(t("bt.roi", lang), f"{m.roi * 100:.2f}%")
        c2.metric("Sharpe / Sortino", f"{m.sharpe:.2f} / {m.sortino:.2f}")
        c3.metric(t("bt.max_dd", lang), f"{m.max_drawdown * 100:.2f}%")
        c4.metric(t("bt.beat_clv", lang), "-" if m.beat_clv_rate is None else f"{m.beat_clv_rate * 100:.1f}%")
        st.plotly_chart(equity_curve_figure(result.bankroll_curve, result.initial_bankroll), use_container_width=True)
        clvs = [b.clv for b in result.settled_bets if b.clv is not None]
        if clvs:
            st.plotly_chart(clv_distribution_figure(clvs), use_container_width=True)
        st.subheader(t("bt.metrics", lang))
        st.table(metrics_dataframe(m))

        # Breakdowns: where the edge comes from.
        import pandas as pd

        from quantbot.backtest import by_edge, by_league, by_month, by_odds

        st.subheader(t("bt.breakdowns", lang))
        bets = result.settled_bets
        tabs = st.tabs([t("bt.by_odds", lang), t("bt.by_edge", lang), t("bt.by_league", lang), t("bt.by_month", lang)])
        for tab, rows in zip(tabs, (by_odds(bets), by_edge(bets), by_league(bets), by_month(bets))):
            with tab:
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                else:
                    st.caption("-")


def _diagnostics_page(lang, C, provider, mode, league, season) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    from pathlib import Path

    import pandas as pd

    from quantbot.experiments import ExperimentStore, evaluate_run
    from quantbot.models import DixonColesModel, EloModel, LogisticRegressionModel

    universe = C["finished"](provider, mode, league.value, season)

    st.header(t("page.diagnostics", lang))
    st.caption(t("diag.intro", lang))

    st.subheader(t("diag.ablation", lang))
    st.caption(t("diag.ablation_hint", lang))
    rep = C["ablation"](universe, mode, league.value, season)
    if rep["rows"]:
        rows = [{
            t("col.group", lang): r["group"],
            t("col.brier", lang): r["brier"],
            t("col.delta", lang): r["delta"],
        } for r in rep["rows"]]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.subheader(t("diag.importance", lang))
    st.caption(t("diag.importance_hint", lang))
    imp = C["importance"](universe, mode, league.value, season)
    if imp:
        st.dataframe(
            pd.DataFrame([{t("col.feature", lang): r["feature"], t("col.importance", lang): r["importance"]} for r in imp]),
            use_container_width=True, hide_index=True,
        )

    st.subheader(t("diag.experiments", lang))
    st.caption(t("diag.experiments_hint", lang))
    store = ExperimentStore(Path.home() / ".quantbot" / "experiments.json")
    runs = store.load()
    if not runs:
        for name, model in (("Elo", EloModel()), ("Dixon-Coles", DixonColesModel(min_matches=5)), ("Logistic", LogisticRegressionModel())):
            store.log(evaluate_run(universe, model, dataset=f"{league.value} {season}", version=store.next_version(model.name)))
        runs = store.load()
    st.dataframe(
        pd.DataFrame([{
            t("col.model", lang): r.model,
            t("col.version", lang): r.version,
            t("col.dataset", lang): r.dataset,
            t("col.brier", lang): r.metrics.get("brier"),
            t("col.logloss", lang): r.metrics.get("log_loss"),
            t("col.samples", lang): r.n_samples,
        } for r in runs]),
        use_container_width=True, hide_index=True,
    )


def _evaluation_page(page, lang, C, provider, mode, league, season) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    import pandas as pd

    from quantbot.dashboard.components import reliability_diagram_figure

    universe = C["finished"](provider, mode, league.value, season)

    if page == "calibration":
        st.header(t("page.calibration", lang))
        st.caption(t("cal.intro", lang))
        report = C["calibration"](universe, mode, league.value, season)
        if not report["curve"]:
            st.info("Zu wenig Daten." if lang == "de" else "Not enough data.")
            return
        c1, c2, c3 = st.columns(3)
        c1.metric(t("col.brier", lang), report["brier"])
        c2.metric(t("col.logloss", lang), report["log_loss"])
        c3.metric(t("col.ece", lang), report["ece"])
        st.plotly_chart(reliability_diagram_figure(report["curve"]), use_container_width=True)
        st.caption(t("cal.note", lang))
    else:  # models
        st.header(t("page.models", lang))
        st.caption(t("models.intro", lang))
        rows = C["models"](universe, mode, league.value, season)
        table = [{
            t("col.model", lang): r["model"],
            t("col.brier", lang): r["brier"],
            t("col.logloss", lang): r["log_loss"],
            t("col.ece", lang): r["ece"],
            t("col.samples", lang): r["n"],
        } for r in rows]
        st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)


def _card_page(lang, C, orchestrator, mode, league, season) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    import pandas as pd

    st.header(t("page.card", lang))
    st.caption(t("card.intro", lang))
    try:
        cards = C["cards"](orchestrator, mode, league.value, season)
    except ValueError as exc:
        st.warning(str(exc))
        return
    if not cards:
        st.info("Keine kommenden Spiele." if lang == "de" else "No upcoming matches.")
        return

    idx = st.selectbox(
        t("col.match", lang),
        range(len(cards)),
        format_func=lambda i: f"{cards[i].home} vs {cards[i].away}",
    )
    c = cards[idx]
    outcomes = ("home", "draw", "away")
    out_lbl = {"home": t("ins.home", lang), "draw": t("ins.draw", lang), "away": t("ins.away", lang)}

    st.subheader(f"{c.home} vs {c.away}")
    cols = st.columns(3)
    for col, o in zip(cols, outcomes):
        u = c.uncertainty[o]
        col.metric(out_lbl[o], f"{c.probs[o] * 100:.0f}%", f"± {(u['high'] - u['low']) / 2 * 100:.0f}%")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**{t('card.consensus', lang)}** · {t('card.agreement', lang)}: {c.agreement:.0f}/100")
        rows = [{t("col.model", lang): m["name"], **{out_lbl[o]: f"{m[o] * 100:.0f}%" for o in outcomes}} for m in c.models]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.markdown(f"**{t('card.reliability', lang)}**: {c.reliability:.0f}/100 ({c.reliability_level})")
        st.markdown(f"**{t('card.data_quality', lang)}**: {c.data_quality:.0f}/100")
        for comp in c.data_quality_components:
            mark = "✓" if comp["ok"] else "✕"
            st.caption(f"{mark} {t('dq.' + comp['key'], lang)}")
    with col2:
        st.markdown(f"**{t('card.fair_vs_market', lang)}**")
        frows = [{
            "": out_lbl[o],
            t("card.fair", lang): c.fair_odds[o],
            t("card.market", lang): c.market_odds[o],
            t("card.divergence", lang): f"{c.divergence[o]['edge'] * 100:+.1f}% ({t('div.' + c.divergence[o]['tier'], lang)})",
        } for o in outcomes]
        st.dataframe(pd.DataFrame(frows), use_container_width=True, hide_index=True)
        st.markdown(f"**{t('card.decision', lang)}**: {c.signal}  ·  {t('card.stake', lang)}: {c.stake_fraction:.2f}%")

    st.markdown(f"**{t('card.why', lang)}**")
    for r in c.reasons:
        st.markdown(f"- {r[lang]}")
    st.caption(t("card.disclaimer", lang))


def _tracker_page(lang, C, provider, mode, league, season) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    import pandas as pd

    st.header(t("page.tracker", lang))
    st.caption(t("track.intro", lang))
    try:
        view = C["rounds"](provider, mode, league.value, season)
    except ValueError as exc:
        st.warning(str(exc))
        return

    c1, c2, c3 = st.columns(3)
    c1.metric(t("track.hit_rate", lang), "-" if view.hit_rate is None else f"{view.hit_rate:.1f}%")
    c2.metric(t("track.settled_bets", lang), view.total_bets)
    c3.metric(t("track.correct", lang), view.total_correct)

    for r in reversed(view.rounds):
        label = r["label"]
        if r["upcoming"]:
            label += f" ({t('track.upcoming_label', lang)})"
        elif r["hit_rate"] is not None:
            label += f" · {r['correct']}/{r['bets']} · {r['hit_rate']:.0f}%"
        with st.expander(label, expanded=r["upcoming"]):
            if not r["entries"]:
                st.caption("-")
                continue
            rows = []
            for e in r["entries"]:
                if e["settled"]:
                    outcome = t("track.hit", lang) if e["correct"] else t("track.miss", lang)
                    result = e["actual"]
                else:
                    outcome = t("track.pending", lang)
                    result = "-"
                rows.append({
                    t("col.match", lang): e["match"],
                    t("track.tip", lang): e["tip"],
                    t("col.odds", lang): e["odds"],
                    t("track.result", lang): result,
                    "": outcome,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _glossary_page(lang: str) -> None:  # pragma: no cover - requires Streamlit runtime
    st.header(t("page.glossary", lang))
    st.caption(t("glossary.intro", lang))
    de = lang == "de"
    for section in GLOSSARY:
        st.subheader(section["title"]["de"] if de else section["title"]["en"])
        for term, de_def, en_def in section["items"]:
            st.markdown(f"**{term}** — {de_def if de else en_def}")


if __name__ == "__main__":
    _render()
