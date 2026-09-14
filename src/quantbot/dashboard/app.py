"""QuantBot Streamlit dashboard.

Run with ``quantbot dashboard`` (or ``streamlit run <this file>``). The UI is
executed only when the module runs as the Streamlit entry script, so importing
it for tests stays side-effect free. German/English switchable in the sidebar.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import streamlit as st

from quantbot import __version__
from quantbot.dashboard.components import (
    beginner_tip_cards,
    clv_distribution_figure,
    equity_curve_figure,
    metrics_dataframe,
    model_comparison_figure,
    render_signals_table,
    scoreline_heatmap_figure,
    signals_dataframe,
)
from quantbot.dashboard.leagues import (
    ALL_LEAGUES,
    format_league_choice,
    league_choices,
    league_title,
    resolve_leagues,
)
from quantbot.dashboard.slip import (
    build_boosted_slip,
    build_safe_slip,
    default_leg_count,
    format_ticket,
    slip_with_legs,
    ticket_html,
)
from quantbot.dashboard.ux import UXMode, pages_for
from quantbot.i18n import DEFAULT_LANGUAGE, GLOSSARY, LANGUAGES, t


def _current_season() -> str:
    """Season label for today, e.g. '2026-2027' from August 2026 on."""

    now = datetime.now(timezone.utc)
    start = now.year if now.month >= 7 else now.year - 1
    return f"{start}-{start + 1}"


def _resolve_season(provider, preferred: str, *, live: bool) -> tuple[str, str | None]:
    """Pick a season that actually has fixtures when live data is empty.

    Returns ``(season, note_key)`` where ``note_key`` is an i18n key for an
    optional caption, or ``None`` when ``preferred`` already works.
    """

    if not live or provider is None:
        return preferred, None
    available = getattr(provider, "available_seasons", lambda: [])()
    if not available:
        return preferred, "no_matches_live_empty"
    if preferred in available:
        return preferred, None
    return available[0], "no_matches_season_fallback"


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
        from quantbot.models import DixonColesModel
        # Align with dashboard predict default (Claude: show calibration of the live model).
        return calibration_report(_matches, DixonColesModel(min_matches=5))

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
    st.sidebar.caption(f"Stand: v{__version__} · Spieltag-Fenster · Tippschein-Hero")

    default_lang = get_settings().language if get_settings().language in LANGUAGES else DEFAULT_LANGUAGE
    lang = st.sidebar.radio(
        "Sprache / Language",
        list(LANGUAGES),
        index=list(LANGUAGES).index(default_lang),
        format_func=lambda c: "Deutsch" if c == "de" else "English",
        horizontal=True,
    )
    st.sidebar.caption(t("tagline", lang))

    ux_labels = {
        UXMode.BEGINNER: t("ux.beginner", lang),
        UXMode.ADVANCED: t("ux.advanced", lang),
        UXMode.EXPERT: t("ux.expert", lang),
    }
    # Selectbox is easier for beginners (and more reliable) than stacked radios.
    ux_mode = st.sidebar.selectbox(
        t("ux.title", lang),
        list(UXMode),
        index=0,
        format_func=lambda m: ux_labels[m],
        key="ux_mode",
        help=t(f"ux.{list(UXMode)[0].value}_hint", lang),
    )
    st.sidebar.caption(t(f"ux.{ux_mode.value}_hint", lang))

    all_pages = {
        "signals": t("page.signals", lang),
        "slip": t("page.slip", lang),
        "card": t("page.card", lang),
        "tracker": t("page.tracker", lang),
        "insights": t("page.insights", lang),
        "calibration": t("page.calibration", lang),
        "models": t("page.models", lang),
        "diagnostics": t("page.diagnostics", lang),
        "backtest": t("page.backtest", lang),
        "glossary": t("page.glossary", lang),
    }
    visible = pages_for(ux_mode)
    pages = {k: all_pages[k] for k in visible}
    # Apply deferred navigation BEFORE the radio widget is created — Streamlit
    # forbids mutating a widget's session_state key after it is instantiated.
    pending = st.session_state.pop("pending_nav_page", None)
    if pending in pages:
        st.session_state["nav_page"] = pending
    if "nav_page" not in st.session_state or st.session_state["nav_page"] not in pages:
        st.session_state["nav_page"] = next(iter(pages))
    page = st.sidebar.radio(
        t("nav.pages", lang),
        list(pages),
        format_func=lambda k: pages[k],
        key="nav_page",
    )
    league_choice = st.sidebar.selectbox(
        t("ctrl.league", lang),
        league_choices(),
        index=0,
        format_func=lambda c: format_league_choice(c, lang),
        help=t("ctrl.league_all_hint", lang),
    )
    selected_leagues = resolve_leagues(league_choice)
    multi_league = league_choice == ALL_LEAGUES

    # API keys: load from local file when present; never show plaintext.
    from quantbot.local_credentials import clear_api_keys, load_api_keys, save_api_keys

    stored = load_api_keys()
    if "keys_edit_mode" not in st.session_state:
        st.session_state["keys_edit_mode"] = stored is None

    fd_key = ""
    odds_key = ""
    with st.sidebar.expander(t("keys.title", lang), expanded=False):
        if stored is not None and not st.session_state["keys_edit_mode"]:
            st.success(t("keys.loaded", lang))
            c1, c2 = st.columns(2)
            if c1.button(t("keys.change", lang), key="keys_change_btn"):
                st.session_state["keys_edit_mode"] = True
                st.rerun()
            if c2.button(t("keys.clear", lang), key="keys_clear_btn"):
                clear_api_keys()
                st.session_state["keys_edit_mode"] = True
                st.rerun()
            fd_key, odds_key = stored
        else:
            fd_key = st.text_input(t("keys.football", lang), type="password", key="fd_key_input")
            odds_key = st.text_input(t("keys.odds", lang), type="password", key="odds_key_input")
            st.caption(t("keys.hint", lang))
            if fd_key and odds_key:
                save_api_keys(fd_key, odds_key)
                st.caption(t("keys.saved", lang))
                st.session_state["keys_edit_mode"] = False
            elif stored is not None and st.button(t("keys.use_saved", lang), key="keys_use_saved"):
                st.session_state["keys_edit_mode"] = False
                st.rerun()

    provider = None
    live = False
    if fd_key and odds_key:
        try:
            from quantbot.data.providers import build_live_provider

            provider = build_live_provider(
                fd_key,
                odds_key,
                selected_leagues,
                cache_dir=Path.home() / ".quantbot" / "cache",
            )
            live = True
            st.sidebar.success(t("mode.live", lang))
            last = getattr(provider, "finished_last_updated", None)
            if last is not None:
                when = last.astimezone().strftime("%Y-%m-%d %H:%M")
                st.sidebar.caption(t("mode.finished_cache", lang).format(when=when))
            else:
                st.sidebar.caption(t("mode.finished_cache_never", lang))
        except Exception:  # noqa: BLE001
            st.sidebar.warning(t("mode.live_failed", lang))
            provider = None
    else:
        st.sidebar.info(t("mode.demo", lang))

    # Beginners also need season when live data is empty for the default year.
    default_season = _current_season() if live else "2024-2025"
    preferred_season = st.sidebar.text_input(t("ctrl.season", lang), default_season)
    season, season_note = _resolve_season(provider, preferred_season, live=live)
    if season_note == "no_matches_season_fallback":
        st.sidebar.info(
            t("no_matches_season_fallback", lang).format(
                preferred=preferred_season, season=season
            )
        )

    orchestrator = QuantBotOrchestrator(
        provider=provider,
        model=DixonColesModel(min_matches=5),
    )
    mode = "live" if live else "demo"
    C = _install_cache()

    # Thin safety line once onboarding is done; full banner only on first visit.
    if st.session_state.get("welcome_dismissed"):
        st.caption(t("safety.short", lang))
        if not live:
            st.caption(t("safety.demo", lang))
    else:
        st.info(t("safety.banner", lang))
        if not live:
            st.caption(t("safety.demo", lang))
        st.caption(t("safety.account_limits", lang))

    _welcome_card(lang, ux_mode)
    if live and provider is not None:
        _name_match_warnings(lang, provider, selected_leagues)

    if page == "glossary":
        _glossary_page(lang)
        return

    # Always show the matchday / date-range control on Tips and Tip slip —
    # including when no fixtures loaded yet. After the math-review merge the
    # picker was hidden behind the empty-season early return, so users lost
    # date + range selection whenever Football-Data returned no games.
    shared_window = None
    if page in ("signals", "slip"):
        shared_window = _pick_window(
            lang,
            orchestrator,
            selected_leagues,
            season,
            live,
            where="sidebar",
        )

    # Keep only leagues that actually have fixtures (demo: PL + Bundesliga).
    active_leagues = [
        lg
        for lg in selected_leagues
        if C["universe"](orchestrator, mode, lg.value, season)
    ]
    if not active_leagues:
        st.header(pages[page])
        label = t("ctrl.league_all", lang) if multi_league else selected_leagues[0].value
        st.warning(t("no_matches", lang).format(league=label, season=season))
        if not live:
            st.info(t("no_matches_demo", lang))
        elif season_note == "no_matches_live_empty":
            st.info(t("no_matches_live_empty", lang))
        else:
            st.info(t("no_matches_live_hint", lang).format(season=season))
        st.caption(t("ctrl.date_range_empty_hint", lang))
        return

    if multi_league and page not in ("signals", "slip", "tracker"):
        st.header(pages[page])
        st.info(t("ctrl.league_all_pick_one", lang))
        return

    league = active_leagues[0]

    if page == "tracker":
        _tracker_page(lang, C, orchestrator.provider, mode, active_leagues, season)
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

    universe = C["universe"](orchestrator, mode, league.value, season)

    if page == "signals":
        _signals_page(
            lang, ux_mode, C, orchestrator, mode, active_leagues, season, live,
            window=shared_window,
        )

    elif page == "slip":
        _slip_page(
            lang, ux_mode, C, orchestrator, mode, active_leagues, season, live,
            window=shared_window,
        )

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
                    st.plotly_chart(scoreline_heatmap_figure(dcp.score_matrix.matrix), width="stretch")
            except (ValueError, RuntimeError):
                st.info("Insufficient history." if lang == "en" else "Zu wenig Historie.")
        with col2:
            st.subheader(t("ins.compare", lang))
            st.caption(t("ins.compare_hint", lang))
            if model_probs:
                labels = (t("ins.home", lang), t("ins.draw", lang), t("ins.away", lang))
                st.plotly_chart(model_comparison_figure(model_probs, labels), width="stretch")

    else:  # backtest
        st.header(t("page.backtest", lang))
        st.caption(t("bt.intro", lang))
        result = C["backtest"](orchestrator, mode, league.value, season)
        m = result.metrics
        if ux_mode is UXMode.ADVANCED:
            c1, c2, c3 = st.columns(3)
            c1.metric(t("bt.roi", lang), f"{m.roi * 100:.2f}%")
            c2.metric(t("bt.max_dd", lang), f"{m.max_drawdown * 100:.2f}%")
            c3.metric(t("bt.win_rate", lang), f"{m.win_rate * 100:.1f}%")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(t("bt.roi", lang), f"{m.roi * 100:.2f}%")
            c2.metric("Sharpe / Sortino", f"{m.sharpe:.2f} / {m.sortino:.2f}")
            c3.metric(t("bt.max_dd", lang), f"{m.max_drawdown * 100:.2f}%")
            c4.metric(t("bt.beat_clv", lang), "-" if m.beat_clv_rate is None else f"{m.beat_clv_rate * 100:.1f}%")
        st.caption(t("bt.roi_caveat", lang))
        st.caption(t("safety.account_limits", lang))
        st.plotly_chart(equity_curve_figure(result.bankroll_curve, result.initial_bankroll), width="stretch")
        if ux_mode in (UXMode.ADVANCED, UXMode.EXPERT) and result.settled_bets:
            from quantbot.backtest.montecarlo import bet_specs_from_result, monte_carlo_bankroll
            specs = bet_specs_from_result(result)
            if specs:
                st.subheader(t("bt.monte_carlo", lang))
                st.caption(t("bt.monte_carlo_hint", lang))
                mc = monte_carlo_bankroll(
                    specs,
                    initial_bankroll=result.initial_bankroll,
                    n_sims=2000 if ux_mode is UXMode.ADVANCED else 5000,
                    seed=7,
                )
                m1, m2, m3 = st.columns(3)
                m1.metric(t("bt.risk_of_ruin", lang), f"{mc.risk_of_ruin * 100:.1f}%")
                m2.metric(t("bt.dd_p95", lang), f"{mc.drawdown_p95 * 100:.1f}%")
                m3.metric(t("bt.final_p5", lang), f"{mc.final_p5:.0f}")
        if ux_mode is UXMode.EXPERT:
            clvs = [b.clv for b in result.settled_bets if b.clv is not None]
            if clvs:
                st.plotly_chart(clv_distribution_figure(clvs), width="stretch")
        st.subheader(t("bt.metrics", lang))
        st.table(metrics_dataframe(m, mode=ux_mode))

        if ux_mode is UXMode.EXPERT:
            import pandas as pd

            from quantbot.backtest import by_edge, by_league, by_month, by_odds

            st.subheader(t("bt.breakdowns", lang))
            bets = result.settled_bets
            tabs = st.tabs([t("bt.by_odds", lang), t("bt.by_edge", lang), t("bt.by_league", lang), t("bt.by_month", lang)])
            for tab, rows in zip(tabs, (by_odds(bets), by_edge(bets), by_league(bets), by_month(bets))):
                with tab:
                    if rows:
                        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                    else:
                        st.caption("-")


def _welcome_card(lang: str, ux_mode: UXMode) -> None:  # pragma: no cover - requires Streamlit runtime
    """First-run onboarding: demo mode, age/risk gate, stay on Simple view."""

    from quantbot.preferences import is_welcome_dismissed, set_welcome_dismissed

    if st.session_state.get("welcome_dismissed") or is_welcome_dismissed():
        st.session_state["welcome_dismissed"] = True
        return
    with st.container(border=True):
        st.subheader(t("welcome.title", lang))
        st.write(t("welcome.body", lang))
        st.markdown(t("welcome.steps", lang))
        st.info(t("welcome.responsible", lang))
        age_ok = st.checkbox(t("welcome.age_confirm", lang), key="welcome_age_confirm")
        if not age_ok:
            st.caption(t("welcome.age_required", lang))
            return
        if ux_mode is UXMode.BEGINNER:
            c1, c2 = st.columns(2)
            if c1.button(t("welcome.go_tips", lang), type="primary", key="welcome_go_tips"):
                set_welcome_dismissed()
                st.session_state["welcome_dismissed"] = True
                st.session_state["pending_nav_page"] = "signals"
                st.rerun()
            if c2.button(t("welcome.later", lang), key="welcome_later"):
                set_welcome_dismissed()
                st.session_state["welcome_dismissed"] = True
                st.rerun()
        else:
            c1, c2, c3 = st.columns(3)
            if c1.button(t("welcome.go_tips", lang), type="primary", key="welcome_go_tips"):
                set_welcome_dismissed()
                st.session_state["welcome_dismissed"] = True
                st.session_state["pending_nav_page"] = "signals"
                st.rerun()
            if c2.button(t("welcome.go_slip", lang), key="welcome_go_slip"):
                set_welcome_dismissed()
                st.session_state["welcome_dismissed"] = True
                st.session_state["pending_nav_page"] = "glossary"
                st.session_state["pending_nav_after_glossary"] = "slip"
                st.rerun()
            if c3.button(t("welcome.later", lang), key="welcome_later"):
                set_welcome_dismissed()
                st.session_state["welcome_dismissed"] = True
                st.rerun()


def _name_match_warnings(lang, provider, leagues) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    """Warn when live odds were matched fuzzily or not at all (any league)."""

    fuzzy = unmatched = 0
    issues: list = []
    for league in leagues:
        report = getattr(provider, "name_match_report", lambda *_a, **_k: None)(league)
        if report is None or not report.has_warnings:
            continue
        fuzzy += report.matched_fuzzy
        unmatched += report.unmatched_odds
        issues.extend(report.issues)
    if fuzzy == 0 and unmatched == 0:
        return
    st.warning(
        t("matchwarn.title", lang)
        + " — "
        + t("matchwarn.body", lang).format(fuzzy=fuzzy, unmatched=unmatched)
    )
    with st.expander(t("matchwarn.title", lang), expanded=False):
        for issue in issues[:12]:
            odds = f"{issue.odds_home} vs {issue.odds_away}"
            if issue.kind == "fuzzy" and issue.fixture_home and issue.fixture_away:
                fixture = f"{issue.fixture_home} vs {issue.fixture_away}"
                st.caption(
                    t("matchwarn.fuzzy_row", lang).format(
                        odds=odds,
                        fixture=fixture,
                        score=issue.score or 0.0,
                    )
                )
            else:
                st.caption(t("matchwarn.unmatched_row", lang).format(odds=odds))


def _window_key(leagues, season: str, live: bool) -> str:  # type: ignore[no-untyped-def]
    return f"window::{','.join(lg.value for lg in leagues)}::{season}::{'live' if live else 'demo'}"


def _default_window_bounds(orchestrator, leagues, season: str, live: bool):  # type: ignore[no-untyped-def]
    if live:
        start_default = datetime.now(timezone.utc).date()
    else:
        start_default = None
        for league in leagues:
            try:
                start_default = orchestrator.default_as_of(league, season).date()
                break
            except ValueError:
                continue
        if start_default is None:
            start_default = datetime.now(timezone.utc).date()
    # Demo fixtures are weekly — default to two weeks so several matchdays fit.
    end_default = start_default + timedelta(days=2 if live else 13)
    return start_default, end_default


def _pick_window(
    lang,
    orchestrator,
    leagues,
    season,
    live: bool,
    *,
    where: str = "main",
):  # type: ignore[no-untyped-def]  # pragma: no cover
    """Kickoff date range for tips/slip; model stand = range start.

    ``where`` is ``"main"`` (page body) or ``"sidebar"`` (shared for Einfach).
    """

    start_default, end_default = _default_window_bounds(orchestrator, leagues, season, live)
    key = _window_key(leagues, season, live)
    if key not in st.session_state:
        st.session_state[key] = (start_default, end_default)

    ui = st.sidebar if where == "sidebar" else st
    if where == "sidebar":
        ui.markdown(f"**{t('ctrl.window_sidebar', lang)}**")

    presets = ui.columns(3)
    if presets[0].button(t("ctrl.range_today", lang), width="stretch", key=f"{key}::today"):
        st.session_state[key] = (start_default, start_default)
        st.rerun()
    if presets[1].button(t("ctrl.range_3d", lang), width="stretch", key=f"{key}::3d"):
        st.session_state[key] = (start_default, start_default + timedelta(days=2))
        st.rerun()
    if presets[2].button(t("ctrl.range_7d", lang), width="stretch", key=f"{key}::7d"):
        st.session_state[key] = (start_default, start_default + timedelta(days=6))
        st.rerun()

    raw = ui.date_input(t("ctrl.date_range", lang), key=key)
    if isinstance(raw, (tuple, list)) and len(raw) == 2:
        start_d, end_d = raw[0], raw[1]
    else:
        start_d = end_d = raw if isinstance(raw, date) else start_default
    if end_d < start_d:
        start_d, end_d = end_d, start_d
    ui.caption(t("ctrl.date_range_hint", lang))
    as_of = datetime(start_d.year, start_d.month, start_d.day, tzinfo=timezone.utc)
    return as_of, start_d, end_d


def _predict_leagues(C, orchestrator, mode, leagues, season, as_of_iso: str):  # type: ignore[no-untyped-def]
    """Run predictions for every selected league and concatenate reports."""

    reports = []
    for league in leagues:
        reports.extend(C["predict"](orchestrator, mode, league.value, season, as_of_iso))
    return reports


def _filter_by_kickoff(reports, start_d: date, end_d: date):  # type: ignore[no-untyped-def]
    """Keep tips whose kickoff day lies inside the chosen window."""

    return [
        r
        for r in reports
        if start_d <= r.match.kickoff.date() <= end_d
    ]


def _signals_page(
    lang, ux_mode, C, orchestrator, mode, leagues, season, live, window=None
) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    """Tips page: beginner cards / tables, grouped by league, filtered by date range."""

    st.header(t("page.signals", lang))
    if len(leagues) > 1:
        st.caption(t("sig.all_leagues_intro", lang))
    if window is None:
        as_of, start_d, end_d = _pick_window(lang, orchestrator, leagues, season, live)
    else:
        as_of, start_d, end_d = window
    if ux_mode is UXMode.BEGINNER:
        st.caption(t("sig.beginner_intro", lang))
    else:
        st.caption(t("sig.intro", lang))
        if ux_mode is UXMode.ADVANCED:
            st.caption(f"{t('term.edge', lang)} · {t('term.ev', lang)} · {t('term.stake', lang)}")

    reports = _filter_by_kickoff(
        _predict_leagues(C, orchestrator, mode, leagues, season, as_of.isoformat()),
        start_d,
        end_d,
    )
    n_bets = sum(1 for r in reports if r.signal.is_bet)
    st.caption(
        t("sig.range_summary", lang).format(
            start=start_d.isoformat(), end=end_d.isoformat(), n=len(reports), k=n_bets
        )
    )
    if ux_mode is UXMode.BEGINNER:
        try:
            from quantbot.tracking import TipHistoryStore, tracker_path
            store = TipHistoryStore(tracker_path(mode))
            rate = store.hit_rate()
            if rate is None:
                st.caption(t("sig.hit_rate_none", lang))
            else:
                st.caption(t("sig.hit_rate_caption", lang).format(rate=f"{rate:.0f}%"))
        except Exception:  # noqa: BLE001 — history is optional for the tips view
            st.caption(t("sig.hit_rate_none", lang))
    else:
        st.caption(t("sig.edge_band_hint", lang))

    if ux_mode is UXMode.BEGINNER:
        for league in leagues:
            lg_reports = [r for r in reports if r.match.league is league]
            if not lg_reports:
                continue
            st.subheader(league_title(league))
            cards = beginner_tip_cards(lg_reports, lang=lang, limit=5)
            bets = [c for c in cards if c["is_bet"] == "1"]
            if not bets:
                st.success(t("sig.no_clear_tip", lang))
            else:
                top = bets[0]
                st.markdown(f"### {top['match']}")
                st.html(top["tip_html"])
                st.caption(
                    t("sig.beginner_metrics", lang).format(
                        model=top["model_p"],
                        edge=top["edge_pp"],
                        quality=top["quality"],
                    )
                )
                st.caption(t("sig.model_estimate_caption", lang))
                st.write(top["why"])
                if len(bets) > 1:
                    st.caption(t("sig.other_matches", lang))
                    for extra in bets[1:]:
                        st.html(
                            f'<div style="margin:0.35rem 0;">'
                            f'<b>{extra["match"]}</b> — {extra["tip_html_small"]}'
                            f'<div style="opacity:0.85;margin-top:0.15rem;">{extra["why"]}</div>'
                            f"</div>"
                        )
                st.caption(t("sig.tip_legend", lang))
            with st.expander(t("sig.all_matches", lang), expanded=False):
                render_signals_table(signals_dataframe(lg_reports, mode=UXMode.BEGINNER, lang=lang))
        # Accumulators stay out of Simple mode (Gemini/Claude review).
        return

    c1, c2 = st.columns(2)
    c1.metric(t("sig.matches", lang), len(reports))
    c2.metric(t("sig.values", lang), n_bets)
    if len(leagues) == 1:
        render_signals_table(signals_dataframe(reports, mode=ux_mode, lang=lang))
    else:
        for league in leagues:
            lg_reports = [r for r in reports if r.match.league is league]
            if not lg_reports:
                continue
            st.subheader(league_title(league))
            render_signals_table(signals_dataframe(lg_reports, mode=ux_mode, lang=lang))


def _slip_page(
    lang, ux_mode, C, orchestrator, mode, leagues, season, live, window=None
) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    """Theoretical tip slip across leagues and a kickoff date range."""

    st.header(t("page.slip", lang))
    from quantbot.preferences import is_glossary_seen, set_glossary_seen
    if not (st.session_state.get("glossary_seen") or is_glossary_seen()):
        st.warning(t("slip.glossary_gate", lang))
        if st.button(t("slip.glossary_cta", lang), key="slip_goto_glossary"):
            st.session_state["pending_nav_page"] = "glossary"
            st.session_state["pending_nav_after_glossary"] = "slip"
            st.rerun()
        return
    beginner = ux_mode is UXMode.BEGINNER
    from_tips = bool(st.session_state.pop("slip_from_tips", False))
    if from_tips:
        st.info(t("slip.from_tips", lang))
    elif not beginner:
        st.caption(t("slip.intro", lang))
    if len(leagues) > 1:
        st.caption(t("slip.all_leagues", lang))

    if window is None:
        as_of, start_d, end_d = _pick_window(lang, orchestrator, leagues, season, live)
    else:
        as_of, start_d, end_d = window

    reports = _filter_by_kickoff(
        _predict_leagues(C, orchestrator, mode, leagues, season, as_of.isoformat()),
        start_d,
        end_d,
    )
    available = sum(1 for r in reports if r.signal.is_bet)
    span_days = (end_d - start_d).days + 1
    default_legs = default_leg_count(
        beginner=beginner, span_days=span_days, available=max(available, 1)
    )

    style_labels = {
        "safe": t("slip.style_safe", lang),
        "boosted": t("slip.style_boosted", lang),
    }
    pref = st.session_state.pop("slip_pref_style", None)
    # Beginner: selection only — no “booster” / high-odds accumulator style.
    style_options = ["safe"] if beginner else list(style_labels)
    if pref not in style_options:
        pref = "safe"
    style_index = style_options.index(pref)

    def _controls() -> tuple[str, float, object]:
        style_local = st.radio(
            t("slip.style", lang),
            style_options,
            index=style_index,
            format_func=lambda k: style_labels[k],
            horizontal=True,
            help=t("slip.style_safe_hint", lang),
            key="slip_style_radio",
        )
        st.caption(t(f"slip.style_{style_local}_hint", lang))
        stake_local = st.number_input(
            t("slip.stake", lang),
            min_value=1.0,
            max_value=1000.0 if beginner else 10000.0,
            value=10.0,
            step=1.0,
            key="slip_stake_input",
        )
        max_available = max(1, min(8, available or 1))
        max_legs_local = st.slider(
            t("slip.max_legs", lang),
            min_value=1,
            max_value=max_available,
            value=min(default_legs, max_available),
            help=t("slip.legs_risk", lang),
            key="slip_max_legs",
        )
        st.caption(t("slip.legs_risk", lang))

        if style_local == "safe":
            slip_local = build_safe_slip(reports, lang=lang, max_legs=max_legs_local)
        else:
            core_legs = max(1, (max_legs_local + 1) // 2) if beginner else max(1, min(2, max_legs_local))
            boost_legs = max(0, max_legs_local - core_legs)
            if not beginner:
                c1, c2 = st.columns(2)
                core_legs = c1.slider(t("slip.core_legs", lang), min_value=1, max_value=5, value=core_legs)
                boost_legs = c2.slider(t("slip.boost_legs", lang), min_value=0, max_value=4, value=boost_legs)
            slip_local = build_boosted_slip(
                reports, lang=lang, core_legs=core_legs, boost_legs=boost_legs
            )
        return style_local, float(stake_local), slip_local

    if beginner:
        # Ticket first; knobs live in an expander so the slip stays the hero.
        with st.expander(t("slip.adjust", lang), expanded=False):
            _style, stake, slip = _controls()
            if slip is not None and slip.legs:
                st.caption(t("slip.edit_legs", lang))
                selected_ids = []
                for leg in slip.legs:
                    tip_short = leg.tip.replace("Tipp: ", "").replace("Tip: ", "")
                    label = f"{leg.match} — {tip_short} ({leg.odds:.2f})"
                    if st.checkbox(label, value=True, key=f"slip_leg::{leg.match_id}"):
                        selected_ids.append(leg.match_id)
                slip = slip_with_legs(slip, selected_ids)
    else:
        _style, stake, slip = _controls()
        if slip is not None and slip.legs:
            st.subheader(t("slip.edit_legs", lang))
            selected_ids = []
            for leg in slip.legs:
                tip_short = leg.tip.replace("Tipp: ", "").replace("Tip: ", "")
                label = f"{leg.match} — {tip_short} ({leg.odds:.2f})"
                if st.checkbox(label, value=True, key=f"slip_leg::{leg.match_id}"):
                    selected_ids.append(leg.match_id)
            slip = slip_with_legs(slip, selected_ids)

    if slip is None or not slip.legs:
        st.info(t("slip.empty", lang))
        return

    st.subheader(t("slip.ticket_title", lang))
    st.caption(t("slip.range_note", lang).format(start=start_d.isoformat(), end=end_d.isoformat()))
    st.html(ticket_html(slip, lang=lang, stake=stake))
    with st.expander(t("slip.copy_title", lang), expanded=beginner):
        st.code(format_ticket(slip, lang=lang, stake=stake), language=None)

    if not beginner:
        m1, m2, m3 = st.columns(3)
        m1.metric(t("slip.combined_odds", lang), f"{slip.combined_odds:.2f}")
        m2.metric(t("slip.combined_prob", lang), f"{slip.combined_prob * 100:.1f}%")
        m3.metric(t("slip.combined_ev", lang), f"{slip.expected_value * 100:.1f}%")
        if len(slip.legs) > 1:
            st.warning(t("slip.disclaimer", lang))
        else:
            st.caption(t("slip.disclaimer", lang))
    else:
        st.caption(t("slip.disclaimer", lang))


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
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.subheader(t("diag.importance", lang))
    st.caption(t("diag.importance_hint", lang))
    imp = C["importance"](universe, mode, league.value, season)
    if imp:
        st.dataframe(
            pd.DataFrame([{t("col.feature", lang): r["feature"], t("col.importance", lang): r["importance"]} for r in imp]),
            width="stretch", hide_index=True,
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
        width="stretch", hide_index=True,
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
        st.plotly_chart(reliability_diagram_figure(report["curve"]), width="stretch")
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
        st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)


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
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
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
            t("card.divergence", lang): (
                f"{c.divergence[o]['edge_pp']:+.1f} pp "
                f"[{c.divergence[o].get('edge_low_pp', c.divergence[o]['edge_pp']):.1f}"
                f"–{c.divergence[o].get('edge_high_pp', c.divergence[o]['edge_pp']):.1f}] "
                f"({t('div.' + c.divergence[o]['tier'], lang)})"
            ),
        } for o in outcomes]
        st.dataframe(pd.DataFrame(frows), width="stretch", hide_index=True)
        st.markdown(f"**{t('card.decision', lang)}**: {c.signal}  ·  {t('card.stake', lang)}: {c.stake_fraction:.2f}%")

    st.markdown(f"**{t('card.why', lang)}**")
    for r in c.reasons:
        st.markdown(f"- {r[lang]}")
    st.caption(t("card.disclaimer", lang))


def _tracker_page(lang, C, provider, mode, leagues, season) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    from html import escape

    from quantbot.dashboard.ux import tip_badge_html, tip_kind_from_label
    from quantbot.tracking import TipHistoryStore, sync_tip_history, tracker_path

    st.header(t("page.tracker", lang))
    st.caption(t("track.intro", lang))
    if not isinstance(leagues, list):
        leagues = [leagues]

    store = TipHistoryStore(tracker_path(mode))
    try:
        view = sync_tip_history(store, provider, leagues, season, mode=mode)
    except ValueError as exc:
        st.warning(str(exc))
        return

    if view.total_bets > 0 and view.hit_rate is not None:
        st.success(
            t("track.week_summary", lang).format(
                correct=view.total_correct,
                bets=view.total_bets,
                rate=f"{view.hit_rate:.0f}%",
            )
        )
        misses = view.total_bets - view.total_correct
        if misses > 0:
            st.caption(t("track.learn_miss", lang))
    else:
        st.info(t("track.week_summary_none", lang))

    with st.expander(t("track.path_expander", lang), expanded=False):
        st.caption(t("track.persisted", lang).format(path=str(store.path), n=len(store.all_tips())))

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
        with st.expander(label, expanded=r["upcoming"] and len(leagues) == 1):
            if not r["entries"]:
                st.caption("-")
                continue
            for e in r["entries"]:
                tip_text = str(e["tip"])
                tip_html = tip_badge_html(
                    tip_kind_from_label(tip_text),
                    lang,
                    text=tip_text.replace("Tipp: ", "").replace("Tip: ", ""),
                )
                if e["settled"]:
                    if e["correct"]:
                        outcome_html = (
                            '<span style="color:#1b7f4a;font-weight:700;">'
                            f'{escape(t("track.hit", lang))}</span>'
                        )
                    else:
                        outcome_html = (
                            '<span style="color:#b91c1c;font-weight:700;">'
                            f'{escape(t("track.miss", lang))}</span>'
                        )
                    result = escape(str(e["actual"] or "-"))
                else:
                    outcome_html = (
                        f'<span style="opacity:0.7;">{escape(t("track.pending", lang))}</span>'
                    )
                    result = "-"
                odds = e["odds"]
                odds_s = f"{odds:.2f}" if isinstance(odds, (int, float)) else escape(str(odds or "—"))
                st.html(
                    '<div style="padding:0.55rem 0;border-bottom:1px solid #e5e7eb;">'
                    f'<div style="font-weight:700;">{escape(str(e["match"]))}</div>'
                    f'<div style="margin-top:0.25rem;">→ {tip_html}'
                    f' <span style="margin-left:0.5rem;opacity:0.75;">{odds_s}</span></div>'
                    f'<div style="margin-top:0.2rem;font-size:0.9rem;">{outcome_html}'
                    f' · {escape(t("track.result", lang))}: {result}</div>'
                    "</div>"
                )


def _glossary_page(lang: str) -> None:  # pragma: no cover - requires Streamlit runtime
    from quantbot.preferences import set_glossary_seen
    set_glossary_seen()
    st.session_state["glossary_seen"] = True
    st.header(t("page.glossary", lang))
    st.caption(t("glossary.intro", lang))
    nxt = st.session_state.pop("pending_nav_after_glossary", None)
    if nxt == "slip":
        if st.button(t("page.slip", lang), type="primary", key="glossary_continue_slip"):
            st.session_state["pending_nav_page"] = "slip"
            st.rerun()
    de = lang == "de"
    for section in GLOSSARY:
        st.subheader(section["title"]["de"] if de else section["title"]["en"])
        for term, de_def, en_def in section["items"]:
            st.markdown(f"**{term}** — {de_def if de else en_def}")


if __name__ == "__main__":
    _render()
