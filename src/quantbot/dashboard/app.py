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
    best_tips_dataframe,
    clv_distribution_figure,
    equity_curve_figure,
    metrics_dataframe,
    model_comparison_figure,
    render_colored_signals_table,
    render_signals_table,
    scoreline_heatmap_figure,
    signals_dataframe,
)
from quantbot.dashboard.leagues import (
    ALL_LEAGUES,
    ALL_SPORTS,
    format_league_choice,
    format_sport_choice,
    league_choices,
    league_title,
    resolve_leagues,
    resolve_sport,
    sport_choices,
)
from quantbot.dashboard.paper import (
    commit_slip,
    open_bookings,
    paper_ledger_for_mode,
    preview_slip,
)
from quantbot.dashboard.slip import (
    build_boosted_slip,
    build_safe_slip,
    build_smart_cross_sport_slip,
    default_leg_count,
    format_ticket,
    slip_with_legs,
    ticket_html,
)
from quantbot.dashboard.ux import UXMode, pages_for
from quantbot.i18n import DEFAULT_LANGUAGE, GLOSSARY, LANGUAGES, t
from quantbot.ledger import CapViolationError


def _current_season() -> str:
    """Season label for today, e.g. '2026-2027' from August 2026 on."""

    now = datetime.now(timezone.utc)
    start = now.year if now.month >= 7 else now.year - 1
    return f"{start}-{start + 1}"


def _resolve_season(
    provider, preferred: str, *, live: bool, leagues=None
) -> tuple[str, str | None]:
    """Pick a season that actually has fixtures when live data is empty.

    Returns ``(season, note_key)`` where ``note_key`` is an i18n key for an
    optional caption, or ``None`` when ``preferred`` already works.
    When ``leagues`` is a single league, only that league's seasons count —
    so Alle-mode PL seasons cannot mask an empty Bundesliga season.
    """

    if not live or provider is None:
        return preferred, None
    available_fn = getattr(provider, "available_seasons", lambda *a, **k: [])
    league = leagues[0] if leagues is not None and len(leagues) == 1 else None
    try:
        available = available_fn(league) if league is not None else available_fn()
    except TypeError:
        available = available_fn()
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
    def cards(_orch, mode, league_value, season, as_of_iso):
        from quantbot.schemas import League
        a = datetime.fromisoformat(as_of_iso) if as_of_iso else None
        return _orch.build_match_cards(League(league_value), season, a)

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


def _mask_key(key: str) -> str:
    """Show only the last four characters of a key; hide the rest."""

    key = (key or "").strip()
    if len(key) <= 4:
        return "••••"
    return "••••" + key[-4:]


def _clear_local_cache() -> list[str]:
    """Delete local API caches and the finished-match archive.

    Next load fetches fresh from the APIs (uses some free quota). Stored API
    keys are NOT touched — only cached data.
    """

    import shutil
    from pathlib import Path

    from quantbot.config import DATA_DIR

    removed: list[str] = []
    targets = [Path.home() / ".quantbot" / "cache", DATA_DIR / "finished"]
    for target in targets:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            removed.append(str(target))
    return removed



def _api_status_badges(
    lang: str,
    *,
    fd_key: str,
    odds_key: str,
    bball_key: str,
    apif_key: str = "",
    live: bool,
) -> None:
    """Compact header badges with masked key tails and active/missing dots."""

    def _badge(label: str, key: str, active: bool) -> str:
        dot = "•"
        status = t("status.active", lang) if active else t("status.missing", lang)
        tail = _mask_key(key) if key else "••••"
        return f"{dot} {label}: {tail} [{status}]"

    bits = [
        _badge("Football-Data", fd_key, bool(fd_key)),
        _badge("The Odds API", odds_key, bool(odds_key)),
        _badge("API-Football", apif_key, bool(apif_key))
        if apif_key
        else t("keys.apifootball_optional", lang),
        t("keys.basketball_optional", lang),
    ]
    mode = t("mode.live", lang) if live else t("mode.demo", lang)
    st.caption(" · ".join(bits) + f"  |  {mode}")


def _render() -> None:  # pragma: no cover - requires Streamlit runtime
    from pathlib import Path

    from quantbot.config import get_settings
    from quantbot.models import DixonColesModel, EloModel, LogisticRegressionModel
    from quantbot.orchestrator import QuantBotOrchestrator
    from quantbot.schemas import League

    st.set_page_config(page_title="QuantBot", page_icon="⚽", layout="wide")
    # Let sidebar dropdowns wrap long labels instead of clipping them to "…".
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] div[data-baseweb="select"] div {
            white-space: normal !important;
        }
        ul[data-baseweb="menu"] li {
            white-space: normal !important;
            height: auto !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
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
        "paper": t("page.paper", lang),
        "card": t("page.card", lang),
        "tracker": t("page.tracker", lang),
        "insights": t("page.insights", lang),
        "calibration": t("page.calibration", lang),
        "models": t("page.models", lang),
        "diagnostics": t("page.diagnostics", lang),
        "backtest": t("page.backtest", lang),
        "settings": t("page.settings", lang),
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
    sport_choice = st.sidebar.selectbox(
        t("ctrl.sport", lang),
        sport_choices(),
        index=0,
        format_func=lambda c: format_sport_choice(c, lang),
        help=t("ctrl.sport_hint", lang),
        key="sport_filter",
    )
    selected_sport = resolve_sport(sport_choice)

    league_choice = st.sidebar.selectbox(
        t("ctrl.league", lang),
        league_choices(selected_sport),
        index=0,
        format_func=lambda c: format_league_choice(c, lang),
        help=t("ctrl.league_all_hint", lang),
    )
    selected_leagues = resolve_leagues(league_choice, selected_sport)
    multi_league = league_choice == ALL_LEAGUES

    from quantbot.dashboard.credentials import credential_controls

    # StoredApiKeys is a 4-field named tuple (football, odds, basketball, apifootball).
    # Unpack by attribute so a new optional key cannot crash startup again.
    keys = credential_controls(lang)
    fd_key, odds_key, bball_key, apif_key = (
        keys.football,
        keys.odds,
        keys.basketball,
        keys.apifootball,
    )

    with st.sidebar.expander(t("cache.title", lang), expanded=False):
        if st.session_state.pop("cache_cleared", False):
            st.success(t("cache.cleared", lang))
        st.caption(t("cache.hint", lang))
        if st.button(t("cache.clear", lang), key="cache_clear_btn"):
            _clear_local_cache()
            try:
                st.cache_data.clear()
            except Exception:  # noqa: BLE001
                pass
            st.session_state["cache_cleared"] = True
            st.rerun()

    from quantbot.preferences import (
        load_live_enabled,
        resolve_live_activation,
        save_live_enabled,
    )

    has_live_keys = bool(fd_key and odds_key)
    if "live_mode_toggle" not in st.session_state:
        st.session_state["live_mode_toggle"] = bool(load_live_enabled() and has_live_keys)
    if not has_live_keys:
        st.session_state["live_mode_toggle"] = False
    want_live = st.sidebar.toggle(
        t("mode.live_toggle", lang),
        key="live_mode_toggle",
        disabled=not has_live_keys,
        help=t("mode.live_toggle_help", lang),
    )
    if has_live_keys:
        save_live_enabled(bool(want_live))
    else:
        st.sidebar.caption(t("mode.live_needs_keys", lang))

    live_ok, live_warn = resolve_live_activation(want_live=bool(want_live), has_keys=has_live_keys)
    if live_warn:
        st.sidebar.warning(t(live_warn, lang))

    provider = None
    live = False
    if live_ok:
        try:
            from quantbot.data.providers import build_live_provider

            from quantbot.data.basketball import BasketballDataProvider
            from quantbot.data.composite import CompositeDataProvider
            from quantbot.schemas.enums import Sport, sport_for_league

            football_leagues = [lg for lg in selected_leagues if sport_for_league(lg) is Sport.FOOTBALL]
            basketball_leagues = [lg for lg in selected_leagues if sport_for_league(lg) is Sport.BASKETBALL]
            live_provider = None
            if football_leagues:
                live_provider = build_live_provider(
                    fd_key,
                    odds_key,
                    football_leagues,
                    cache_dir=Path.home() / ".quantbot" / "cache",
                    # Load last season too, so early-season fits have a backbone.
                    history_seasons=1,
                )
            basketball_provider = BasketballDataProvider()
            if live_provider is not None and basketball_leagues:
                provider = CompositeDataProvider(live_provider, basketball_provider)
            elif live_provider is not None:
                provider = live_provider
            else:
                provider = basketball_provider
            live = live_provider is not None
            if live:
                st.sidebar.info(t("mode.live", lang))
            else:
                st.sidebar.markdown(f"**[{t('safety.demo_badge', lang)}]**")
                st.sidebar.info(t("mode.demo", lang))
            last = getattr(provider, "finished_last_updated", None)
            if last is not None:
                when = last.astimezone().strftime("%Y-%m-%d %H:%M")
                st.sidebar.caption(t("mode.finished_cache", lang).format(when=when))
            else:
                st.sidebar.caption(t("mode.finished_cache_never", lang))
            if live:
                try:
                    from quantbot.data.snapshot_repo import DataMode, SnapshotRepository

                    n_snap = SnapshotRepository().count(data_mode=DataMode.LIVE_REPLAY)
                    if n_snap:
                        st.sidebar.caption(t("mode.odds_archive", lang).format(n=n_snap))
                    else:
                        st.sidebar.caption(t("mode.odds_archive_empty", lang))
                except Exception:  # noqa: BLE001
                    pass
            errs = getattr(provider, "load_errors", None) or []
            if errs:
                st.sidebar.warning(t("mode.load_errors", lang).format(n=len(errs)))
                for err in errs[:6]:
                    st.sidebar.caption(err)
        except Exception:  # noqa: BLE001
            st.sidebar.warning(t("mode.live_failed", lang))
            provider = None
            live = False
    else:
        st.sidebar.markdown(f"**[{t('safety.demo_badge', lang)}]**")
        st.sidebar.info(t("mode.demo", lang))

    # Beginners also need season when live data is empty for the default year.
    default_season = _current_season() if live else "2024-2025"
    preferred_season = st.sidebar.text_input(t("ctrl.season", lang), default_season)
    season, season_note = _resolve_season(provider, preferred_season, live=live, leagues=selected_leagues)
    if season_note == "no_matches_season_fallback":
        st.sidebar.info(
            t("no_matches_season_fallback", lang).format(
                preferred=preferred_season, season=season
            )
        )

    high_risk = st.sidebar.toggle(
        t("ctrl.high_risk", lang),
        value=bool(st.session_state.get("global_high_risk", False)),
        key="global_high_risk",
        help=t("ctrl.high_risk_help", lang),
    )
    if high_risk:
        st.sidebar.warning(t("ctrl.high_risk_warn", lang))
    # Keep tip-slip builders aligned with the sidebar risk profile.
    st.session_state["slip_high_risk"] = bool(high_risk)

    from quantbot.analysis.calibration import PlattScaler
    from quantbot.analysis.engine import AnalysisEngine
    from quantbot.decision import high_risk_policy, policy_for_mode

    decision_policy = high_risk_policy() if high_risk else policy_for_mode(live=live)
    # Nations League / early cups often have 0–few finished rows in the local
    # archive (Odds API scores only cover ~3 days). High-Risk uses a tiny fit
    # floor and falls back to market tips when even that fails.
    dc_min_matches = 1 if high_risk else 5
    team_min = 0 if high_risk else 3

    orchestrator = QuantBotOrchestrator(
        provider=provider,
        # Time-decay weighting (xi ~= 198-day half-life) lets last season act as
        # a backbone that fades as the new season's games accumulate.
        model=DixonColesModel(min_matches=dc_min_matches, time_decay_xi=0.0035),
        # Calibrate 1X2 probabilities against out-of-sample history (disables
        # itself gracefully when there is too little data); Platt is robust for
        # small samples.
        calibrator=PlattScaler(),
        # Pull model probabilities toward the fair market when data is thin, so
        # sparse-fit overconfidence does not turn into false value.
        analysis_engine=AnalysisEngine(market_shrinkage=True),
        min_team_matches=team_min,
        # Fit on the current season plus last season (live mode loads both).
        fit_prior_seasons=1,
        live=live,
        decision_policy=decision_policy,
    )
    mode = "live" if live else "demo"
    # Cache key must distinguish High-Risk predict runs without polluting
    # tip-history path names (tracker_path uses ``mode``).
    cache_mode = f"{mode}|high_risk" if high_risk else mode
    C = _install_cache()
    # Bind cache_mode into helpers that call C["predict"].
    st.session_state["_predict_cache_mode"] = cache_mode

    with st.expander(t("page.settings", lang) + " · API", expanded=False):
        _api_status_badges(
            lang,
            fd_key=fd_key,
            odds_key=odds_key,
            bball_key=bball_key,
            apif_key=apif_key,
            live=live,
        )

    # Thin safety line once onboarding is done; full banner only on first visit.
    if st.session_state.get("welcome_dismissed"):
        st.caption(t("safety.short", lang))
        if not live:
            st.caption(f"**[{t('safety.demo_badge', lang)}]** {t('safety.demo', lang)}")
    else:
        st.info(t("safety.banner", lang))
        if not live:
            st.caption(f"**[{t('safety.demo_badge', lang)}]** {t('safety.demo', lang)}")
        st.caption(t("safety.account_limits", lang))
        help_cols = st.columns([4, 1])
        help_cols[0].caption(t("help.footer", lang))
        if help_cols[1].button(t("help.open_glossary", lang), key="help_open_glossary"):
            st.session_state["pending_nav_page"] = "glossary"
            st.rerun()

    _welcome_card(lang, ux_mode)
    # Odds name-matching reports are filled during predict/odds fetch — warn
    # after those pages load data (see _signals_page / _slip_page), not here.

    if page == "glossary":
        _glossary_page(lang)
        return

    if page == "settings":
        _settings_page(
            lang,
            fd_key=fd_key,
            odds_key=odds_key,
            bball_key=bball_key,
            apif_key=apif_key,
            live=live,
        )
        return

    # Paper ledger is mode-scoped and does not need fixtures/leagues.
    if page == "paper":
        _paper_page(lang, mode)
        return

    # Matchday / date-range on Tips, Tip slip, and Match card (incl. empty season).
    shared_window = None
    if page in ("signals", "slip", "card"):
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
        _card_page(
            lang, C, orchestrator, mode, league, season, live,
            window=shared_window,
        )
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
    # Expand details when events failed to match — those matches never become tips.
    with st.expander(t("matchwarn.title", lang), expanded=unmatched > 0):
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
    # Sort so league multi-select order never forks a second empty 3-day window.
    ids = ",".join(sorted(lg.value for lg in leagues))
    return f"window::{ids}::{season}::{'live' if live else 'demo'}"


def _window_draft_key(leagues, season: str, live: bool) -> str:  # type: ignore[no-untyped-def]
    ids = ",".join(sorted(lg.value for lg in leagues))
    return f"window_draft::{ids}::{season}::{'live' if live else 'demo'}"


def _fixture_days(orchestrator, leagues, season: str, start_d: date, end_d: date) -> list[tuple[date, list[str]]]:
    """Group upcoming fixtures in ``[start_d, end_d]`` by kickoff day for the agenda."""

    by_day: dict[date, list[str]] = {}
    for league in leagues:
        try:
            matches = orchestrator.universe(league, season)
        except Exception:  # noqa: BLE001
            continue
        for match in matches:
            day = match.kickoff.date()
            if day < start_d or day > end_d:
                continue
            label = f"{match.home_team.name} – {match.away_team.name}"
            by_day.setdefault(day, []).append(label)
    return sorted(by_day.items(), key=lambda item: item[0])


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
    # Live: one week ahead so midweek internationals are not missed by the
    # old 3-day default. Demo fixtures are weekly — keep two weeks.
    end_default = start_default + timedelta(days=6 if live else 13)
    return start_default, end_default


def _live_committed_window_is_stale(
    committed_end: date,
    today: date,
    *,
    max_past_days: int = 14,
) -> bool:
    """True when the whole committed window already ended too far in the past.

    Future windows (e.g. international matchdays ~3 weeks out) must stay.
    """

    return (today - committed_end).days > max_past_days


def _as_of_for_window(start_d: date, end_d: date, *, live: bool) -> datetime:
    """Model stand for a kickoff window.

    Live windows that include today use ``now`` (rounded to the minute) so
    bookmaker ``last_update`` timestamps from later today remain visible and
    Streamlit ``cache_data`` keys stay stable across widget reruns.
    Historical / demo windows use midnight UTC of the start day.
    """

    today = datetime.now(timezone.utc).date()
    if live and start_d <= today <= end_d:
        now = datetime.now(timezone.utc)
        # Drop seconds/µs — otherwise every Streamlit rerun busts the predict cache.
        return now.replace(second=0, microsecond=0)
    return datetime(start_d.year, start_d.month, start_d.day, tzinfo=timezone.utc)


def _as_of_cache_key(as_of: datetime) -> str:
    """Stable ISO key for cached predict/card calls (minute precision)."""

    return as_of.replace(second=0, microsecond=0).isoformat()


def _apply_window_input_sync(session_state, input_key: str, sync_key: str, draft) -> None:  # type: ignore[no-untyped-def]
    """Seed ``date_input`` from draft before the widget mounts.

    Call only *before* instantiating the widget with ``key=input_key``.
    Preset/agenda clicks set ``sync_key`` and rerun; blindly writing the
    widget key after mount raises StreamlitWidgetAlreadyInstantiatedError.
    """

    if session_state.pop(sync_key, False) or input_key not in session_state:
        session_state[input_key] = draft


def _pick_window(
    lang,
    orchestrator,
    leagues,
    season,
    live: bool,
    *,
    where: str = "main",
):  # type: ignore[no-untyped-def]  # pragma: no cover
    """Kickoff date range with draft → confirm; agenda days set the draft.

    ``where`` is ``"main"`` (page body) or ``"sidebar"`` (shared for Einfach).
    Predictions always use the *committed* window until the user confirms.
    """

    start_default, end_default = _default_window_bounds(orchestrator, leagues, season, live)
    store = _window_key(leagues, season, live)
    draft_store = _window_draft_key(leagues, season, live)
    if store not in st.session_state:
        st.session_state[store] = (start_default, end_default)
    elif live:
        # Only wipe stuck *past* windows (e.g. demo 2024 left in session).
        # Do NOT reset future windows — Nations League / CL / Quali often sit
        # >14 days ahead; abs()-reset made "Zeitraum übernehmen" look broken.
        today = datetime.now(timezone.utc).date()
        committed_end = st.session_state[store][1]
        if _live_committed_window_is_stale(committed_end, today):
            st.session_state[store] = (start_default, end_default)
            st.session_state[draft_store] = (start_default, end_default)
    if draft_store not in st.session_state:
        st.session_state[draft_store] = st.session_state[store]

    ui = st.sidebar if where == "sidebar" else st
    if where == "sidebar":
        ui.markdown(f"**{t('ctrl.window_sidebar', lang)}**")

    committed = st.session_state[store]
    draft = st.session_state[draft_store]
    input_key = f"{draft_store}::input"
    sync_key = f"{draft_store}::sync_input"

    def _set_draft(start: date, end: date, *, apply: bool = False) -> None:
        # Never write ``input_key`` after date_input has mounted (agenda path).
        # Flag sync so the next run seeds date_input before it mounts.
        st.session_state[draft_store] = (start, end)
        st.session_state[sync_key] = True
        if apply:
            # Presets / agenda mean "show these games now" — commit immediately.
            st.session_state[store] = (start, end)

    presets = ui.columns(3)
    if presets[0].button(t("ctrl.range_today", lang), width="stretch", key=f"{draft_store}::today"):
        _set_draft(start_default, start_default, apply=True)
        st.rerun()
    if presets[1].button(t("ctrl.range_3d", lang), width="stretch", key=f"{draft_store}::3d"):
        _set_draft(start_default, start_default + timedelta(days=2), apply=True)
        st.rerun()
    if presets[2].button(t("ctrl.range_7d", lang), width="stretch", key=f"{draft_store}::7d"):
        _set_draft(start_default, start_default + timedelta(days=6), apply=True)
        st.rerun()

    _apply_window_input_sync(st.session_state, input_key, sync_key, st.session_state[draft_store])

    raw = ui.date_input(
        t("ctrl.date_range", lang),
        key=input_key,
    )
    if isinstance(raw, (tuple, list)) and len(raw) == 2:
        draft_start, draft_end = raw[0], raw[1]
    else:
        draft_start = draft_end = raw if isinstance(raw, date) else start_default
    if draft_end < draft_start:
        draft_start, draft_end = draft_end, draft_start
    st.session_state[draft_store] = (draft_start, draft_end)

    # Agenda look-ahead: show days with fixtures around the draft / defaults.
    agenda_from = min(draft_start, start_default)
    agenda_to = max(draft_end, start_default + timedelta(days=13 if not live else 6))
    days = _fixture_days(orchestrator, leagues, season, agenda_from, agenda_to)
    with ui.expander(t("ctrl.agenda", lang), expanded=False):
        ui.caption(t("ctrl.agenda_hint", lang))
        if not days:
            ui.caption(t("ctrl.agenda_empty", lang))
        else:
            for day, labels in days[:12]:
                cols = ui.columns([1, 3])
                if cols[0].button(day.isoformat(), key=f"{draft_store}::day::{day.isoformat()}"):
                    _set_draft(day, day, apply=True)
                    st.rerun()
                preview = ", ".join(labels[:2])
                if len(labels) > 2:
                    preview += f" (+{len(labels) - 2})"
                cols[1].caption(preview)

    pending = st.session_state[draft_store] != st.session_state[store]
    if pending:
        ui.warning(t("ctrl.window_pending", lang))
    else:
        committed = st.session_state[store]
        ui.caption(
            t("ctrl.window_active", lang).format(
                start=committed[0].isoformat(),
                end=committed[1].isoformat(),
            )
        )
    if ui.button(
        t("ctrl.window_apply", lang),
        type="primary" if pending else "secondary",
        width="stretch",
        key=f"{draft_store}::apply",
        disabled=not pending,
    ):
        st.session_state[store] = st.session_state[draft_store]
        st.rerun()

    ui.caption(t("ctrl.date_range_hint", lang))
    start_d, end_d = st.session_state[store]
    as_of = _as_of_for_window(start_d, end_d, live=live)
    return as_of, start_d, end_d


def _predict_leagues(C, orchestrator, mode, leagues, season, as_of_iso: str):  # type: ignore[no-untyped-def]
    """Run predictions for every selected league and concatenate reports."""

    cache_mode = st.session_state.get("_predict_cache_mode", mode)
    reports = []
    for league in leagues:
        reports.extend(C["predict"](orchestrator, cache_mode, league.value, season, as_of_iso))
    return reports


def _filter_by_kickoff(reports, start_d: date, end_d: date):  # type: ignore[no-untyped-def]
    """Keep tips whose kickoff day lies inside the chosen window."""

    return [
        r
        for r in reports
        if start_d <= r.match.kickoff.date() <= end_d
    ]


def _rank_value_reports(reports):  # type: ignore[no-untyped-def]
    """Value tips by composite score first, then remaining matches.

    The score blends likelihood, value and data reliability (see
    ``ux.tip_score``); edge and kickoff break ties for a stable order.
    """

    from quantbot.dashboard.ux import tip_score

    bets = sorted(
        (r for r in reports if r.signal.is_bet),
        key=lambda r: (-tip_score(r.signal), -float(r.signal.edge or 0.0), r.match.kickoff),
    )
    others = [r for r in reports if not r.signal.is_bet]
    return bets + others


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
            st.caption(f"{t('term.edge', lang)} · {t('term.ev', lang)} · {t('term.forecast_quality', lang)}")
            st.caption(t("term.stake", lang))

    reports = _filter_by_kickoff(
        _predict_leagues(C, orchestrator, mode, leagues, season, _as_of_cache_key(as_of)),
        start_d,
        end_d,
    )
    if live and orchestrator.provider is not None:
        _name_match_warnings(lang, orchestrator.provider, leagues)
    n_bets = sum(1 for r in reports if r.signal.is_bet)
    value_pct = (100.0 * n_bets / len(reports)) if reports else 0.0
    st.caption(
        t("sig.range_summary", lang).format(
            start=start_d.isoformat(), end=end_d.isoformat(), n=len(reports), k=n_bets
        )
    )
    st.caption(
        t("sig.value_rate", lang).format(k=n_bets, n=len(reports), pct=f"{value_pct:.0f}")
    )
    if (
        reports
        and n_bets == 0
        and not st.session_state.get("global_high_risk", False)
        and any(
            "INVALID_DATA_MODEL_NOT_FIT" in (r.signal.reason_codes or ())
            for r in reports
        )
    ):
        st.info(t("sig.thin_history_high_risk_hint", lang))
    if live and not reports:
        upcoming_n = 0
        for league in leagues:
            try:
                for match in orchestrator.provider.get_upcoming_matches(league, season, as_of):
                    day = match.kickoff.date()
                    if start_d <= day <= end_d:
                        upcoming_n += 1
            except Exception:  # noqa: BLE001
                continue
        if upcoming_n:
            st.warning(t("sig.no_odds_matched", lang).format(n=upcoming_n))
        else:
            draft_store = _window_draft_key(leagues, season, live)
            draft = st.session_state.get(draft_store)
            if (
                draft is not None
                and isinstance(draft, tuple)
                and len(draft) == 2
                and draft != (start_d, end_d)
            ):
                st.warning(
                    t("sig.no_fixtures_pending_draft", lang).format(
                        active=f"{start_d.isoformat()}–{end_d.isoformat()}",
                        draft=f"{draft[0].isoformat()}–{draft[1].isoformat()}",
                    )
                )
            else:
                st.info(t("sig.no_fixtures_in_window", lang))
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
            with st.expander(t("sig.all_matches", lang), expanded=not bets):
                render_signals_table(signals_dataframe(lg_reports, mode=UXMode.BEGINNER, lang=lang))
        # Accumulators stay out of Simple mode (Gemini/Claude review).
        return

    c1, c2, c3 = st.columns(3)
    c1.metric(t("sig.matches", lang), len(reports))
    c2.metric(t("sig.values", lang), n_bets)
    c3.metric(t("sig.value_share", lang), f"{value_pct:.0f}%")

    # Cross-league ranking of the strongest tips (likelihood + value + data).
    if n_bets:
        st.subheader(t("sig.best_tips_title", lang))
        st.caption(t("sig.best_tips_hint", lang))
        render_signals_table(best_tips_dataframe(reports, lang=lang, limit=10))

    # Cap the main table when almost every match is "value" (early-season noise).
    top_n = 12 if ux_mode is UXMode.ADVANCED else 20
    ranked = _rank_value_reports(reports)
    show_top = ranked[:top_n] if n_bets > top_n else ranked
    if n_bets > top_n:
        st.caption(t("sig.top_n_note", lang).format(n=top_n, total=n_bets))
    if len(leagues) == 1:
        render_colored_signals_table(show_top, mode=ux_mode, lang=lang)
        if n_bets > top_n:
            with st.expander(t("sig.all_matches", lang), expanded=False):
                render_colored_signals_table(reports, mode=ux_mode, lang=lang)
    else:
        for league in leagues:
            lg_reports = [r for r in reports if r.match.league is league]
            if not lg_reports:
                continue
            st.subheader(league_title(league))
            lg_ranked = _rank_value_reports(lg_reports)
            lg_bets = sum(1 for r in lg_ranked if r.signal.is_bet)
            lg_show = lg_ranked[:top_n] if lg_bets > top_n else lg_ranked
            if lg_bets > top_n:
                st.caption(t("sig.top_n_note", lang).format(n=top_n, total=lg_bets))
            render_colored_signals_table(lg_show, mode=ux_mode, lang=lang)



def _settings_page(
    lang, *, fd_key: str, odds_key: str, bball_key: str, apif_key: str = "", live: bool
) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    """Dedicated API settings / connection status page."""

    st.header(t("page.settings", lang))
    st.caption(t("settings.intro", lang))
    _api_status_badges(
        lang,
        fd_key=fd_key,
        odds_key=odds_key,
        bball_key=bball_key,
        apif_key=apif_key,
        live=live,
    )

    st.subheader(t("settings.validate", lang))
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"**Football-Data.org**")
        st.write(_mask_key(fd_key) if fd_key else t("status.missing", lang))
        st.info(t("status.active", lang)) if fd_key else st.error(t("status.missing", lang))
        if st.button(t("settings.test_connection", lang), key="test_fd", disabled=not fd_key):
            from quantbot.dashboard.connection import test_connection
            status = test_connection("football_data", fd_key)
            (st.success if status == "active" else st.warning)(t(f"settings.connection_{status}", lang))
    with c2:
        st.markdown(f"**The Odds API**")
        st.write(_mask_key(odds_key) if odds_key else t("status.missing", lang))
        st.info(t("status.active", lang)) if odds_key else st.error(t("status.missing", lang))
        if st.button(t("settings.test_connection", lang), key="test_odds", disabled=not odds_key):
            from quantbot.dashboard.connection import test_connection
            status = test_connection("the_odds_api", odds_key)
            (st.success if status == "active" else st.warning)(t(f"settings.connection_{status}", lang))
    with c3:
        st.markdown(f"**API-Football**")
        st.write(_mask_key(apif_key) if apif_key else t("status.missing", lang))
        st.info(t("keys.apifootball_optional", lang))
    with c4:
        st.markdown(f"**BallDontLie / NBA**")
        st.write(_mask_key(bball_key) if bball_key else t("status.missing", lang))
        st.info(t("keys.basketball_optional", lang))

    st.info(t("settings.keys_sidebar_hint", lang))

    from quantbot.ollama_explain import OllamaSettings, ping_ollama
    from quantbot.preferences import load_ollama_settings, save_ollama_settings

    st.subheader(t("settings.ollama", lang))
    st.caption(t("settings.ollama_intro", lang))
    current = load_ollama_settings()
    enabled = st.checkbox(
        t("settings.ollama_enabled", lang),
        value=current.enabled,
        key="ollama_enabled_cb",
    )
    url = st.text_input(
        t("settings.ollama_url", lang),
        value=current.base_url,
        key="ollama_url_input",
    )
    model = st.text_input(
        t("settings.ollama_model", lang),
        value=current.model,
        key="ollama_model_input",
    )
    draft = OllamaSettings(
        enabled=enabled,
        base_url=url.strip() or current.base_url,
        model=model.strip() or current.model,
        timeout_s=current.timeout_s,
    )
    b1, b2 = st.columns(2)
    if b1.button(t("settings.ollama_save", lang), key="ollama_save_btn"):
        save_ollama_settings(draft)
        st.success(t("settings.ollama_saved", lang))
    if b2.button(t("settings.ollama_test", lang), key="ollama_test_btn"):
        result = ping_ollama(draft)
        if result.ok:
            st.success(t("settings.ollama_ok", lang).format(models=result.text))
        else:
            st.error(t("settings.ollama_fail", lang).format(error=result.error))


def _render_ollama_explain(lang: str, slip, stake: float) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    """Optional local LLM narration for an already-built tip slip."""

    from quantbot.ollama_explain import explain_slip
    from quantbot.preferences import load_ollama_settings

    settings = load_ollama_settings()
    st.caption(t("slip.ollama_hint", lang))
    if not settings.enabled:
        st.info(t("slip.ollama_disabled", lang))
        return
    if st.button(t("slip.ollama_explain", lang), key="slip_ollama_explain"):
        with st.spinner("Ollama …"):
            result = explain_slip(slip, settings=settings, lang=lang, stake=stake)
        if result.ok:
            st.session_state["slip_ollama_text"] = result.text
            st.session_state.pop("slip_ollama_error", None)
        else:
            st.session_state["slip_ollama_error"] = result.error
            st.session_state.pop("slip_ollama_text", None)
    err = st.session_state.get("slip_ollama_error")
    text = st.session_state.get("slip_ollama_text")
    if err:
        st.warning(err)
    if text:
        st.subheader(t("slip.ollama_title", lang))
        st.write(text)


def _slip_page(
    lang, ux_mode, C, orchestrator, mode, leagues, season, live, window=None
) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    """Theoretical tip slip across leagues and a kickoff date range."""

    from quantbot.preferences import is_glossary_seen

    # Compact hero — brand + one line, no wall of copy.
    st.markdown(
        f"""
        <div style="margin:0 0 1rem 0;padding:1.1rem 1.25rem;border-radius:12px;
        background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 55%,#0f766e 100%);
        color:#f8fafc;">
          <div style="font-size:0.75rem;letter-spacing:0.14em;text-transform:uppercase;
          opacity:0.75;">{t("slip.hero_kicker", lang)}</div>
          <div style="font-size:1.85rem;font-weight:800;line-height:1.15;margin:0.2rem 0;">
            {t("page.slip", lang)}
          </div>
          <div style="font-size:0.95rem;opacity:0.88;">{t("slip.hero_sub", lang)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
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
        st.caption(t("slip.from_tips", lang))
    if len(leagues) > 1:
        st.caption(t("slip.all_leagues", lang))

    if window is None:
        as_of, start_d, end_d = _pick_window(lang, orchestrator, leagues, season, live)
    else:
        as_of, start_d, end_d = window

    reports = _filter_by_kickoff(
        _predict_leagues(C, orchestrator, mode, leagues, season, _as_of_cache_key(as_of)),
        start_d,
        end_d,
    )
    if live and orchestrator.provider is not None:
        _name_match_warnings(lang, orchestrator.provider, leagues)
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
    style_options = ["safe"] if beginner else list(style_labels)
    if pref not in style_options:
        pref = "safe"
    style_index = style_options.index(pref)

    def _controls() -> tuple[str, float, object, str, bool]:
        if not beginner:
            if st.button(t("slip.smart_cross_sport", lang), key="slip_smart_cross"):
                smart = build_smart_cross_sport_slip(
                    reports,
                    lang=lang,
                    max_legs=min(4, max(1, available or 1)),
                    min_edge=0.02,
                    min_data_quality=70.0,
                    prefer_mixed=True,
                )
                if smart is None or not smart.legs:
                    st.warning(t("slip.smart_empty", lang))
                else:
                    st.session_state["slip_pref_style"] = "safe"
                    for leg in smart.legs:
                        st.session_state[f"slip_leg::{leg.match_id}"] = True
                    st.session_state["slip_smart_override"] = [
                        leg.match_id for leg in smart.legs
                    ]
                    st.rerun()
            st.caption(t("slip.cross_sport_note", lang))

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
        orient_labels = {
            "safe": t("slip.orient_safe", lang),
            "balanced": t("slip.orient_balanced", lang),
            "contra": t("slip.orient_contra", lang),
        }
        if st.session_state.get("slip_orient") not in {"safe", "balanced", "contra"}:
            st.session_state["slip_orient"] = "safe"
        orient_local = st.select_slider(
            t("slip.orient", lang),
            options=["safe", "balanced", "contra"],
            format_func=lambda k: orient_labels[k],
            key="slip_orient",
            help=t("slip.orient_safe_default", lang),
        )
        st.caption(t("slip.orient_hint", lang))

        high_risk = bool(st.session_state.get("global_high_risk", False))
        if high_risk:
            st.markdown(
                f'<p style="color:#b91c1c;font-weight:700;">{t("ctrl.high_risk_warn", lang)}</p>',
                unsafe_allow_html=True,
            )
        elif not beginner:
            st.caption(t("slip.high_risk_sidebar_hint", lang))

        stake_local = st.number_input(
            t("slip.stake", lang),
            min_value=0.0,
            max_value=100.0,
            value=1.0,
            step=0.1,
            key="slip_stake_input",
        )
        max_available = max(1, min(8, available or 1))
        if high_risk:
            max_cap = max_available
        else:
            max_cap = min(4, max_available) if orient_local == "safe" else max_available
        if int(st.session_state.get("slip_max_legs", max_cap)) > max_cap:
            st.session_state["slip_max_legs"] = max_cap
        if max_cap <= 1:
            max_legs_local = 1
            st.caption(t("slip.max_legs", lang) + ": 1")
        else:
            max_legs_local = st.slider(
                t("slip.max_legs", lang),
                min_value=1,
                max_value=max_cap,
                value=min(default_legs, max_cap),
                help=t("slip.legs_risk", lang),
                key="slip_max_legs",
            )
        st.caption(t("slip.limits_caption", lang).format(n=max_legs_local, cap=max_cap))

        if style_local == "safe":
            slip_local = build_safe_slip(
                reports,
                lang=lang,
                max_legs=max_legs_local,
                bias=orient_local,
                allow_high_risk=high_risk,
            )
        else:
            core_legs = (
                max(1, (max_legs_local + 1) // 2)
                if beginner
                else max(1, min(2, max_legs_local))
            )
            boost_legs = max(0, max_legs_local - core_legs)
            if not beginner:
                c1, c2 = st.columns(2)
                core_legs = c1.slider(
                    t("slip.core_legs", lang), min_value=1, max_value=5, value=core_legs
                )
                boost_legs = c2.slider(
                    t("slip.boost_legs", lang), min_value=0, max_value=4, value=boost_legs
                )
            slip_local = build_boosted_slip(
                reports,
                lang=lang,
                core_legs=core_legs,
                boost_legs=boost_legs,
                bias=orient_local,
                allow_high_risk=high_risk,
            )
        return style_local, float(stake_local), slip_local, orient_local, high_risk

    smart_ids = st.session_state.pop("slip_smart_override", None)
    orient_used = st.session_state.get("slip_orient", "safe")
    high_risk_used = bool(st.session_state.get("global_high_risk", False))

    with st.expander(t("slip.adjust", lang), expanded=False):
        if smart_ids:
            slip = build_smart_cross_sport_slip(
                reports,
                lang=lang,
                max_legs=len(smart_ids),
                min_edge=0.02,
                min_data_quality=70.0,
            )
            stake = float(st.session_state.get("slip_stake_input", 1.0))
            high_risk_used = False
            if slip is not None:
                slip = slip_with_legs(slip, smart_ids, allow_high_risk=False)
        else:
            _style, stake, slip, orient_used, high_risk_used = _controls()
        if slip is not None and slip.legs:
            st.caption(t("slip.edit_legs", lang))
            selected_ids = []
            for leg in slip.legs:
                tip_short = (
                    leg.tip.replace("Tipp: ", "")
                    .replace("Tip: ", "")
                    .replace("Value erkannt: ", "")
                    .replace("Value spotted: ", "")
                )
                label = f"{leg.match} — {tip_short} ({leg.odds:.2f})"
                if st.checkbox(label, value=True, key=f"slip_leg::{leg.match_id}"):
                    selected_ids.append(leg.match_id)
            slip = slip_with_legs(slip, selected_ids, allow_high_risk=high_risk_used)

    if slip is None or not slip.legs:
        st.info(t("slip.empty", lang))
        return

    stake = max(0.0, float(stake))

    st.subheader(t("slip.ticket_title", lang))
    st.caption(
        f"{t('slip.range_note', lang).format(start=start_d.isoformat(), end=end_d.isoformat())} · "
        + t("slip.active_orient", lang).format(
            orient={
                "safe": t("slip.orient_safe", lang),
                "balanced": t("slip.orient_balanced", lang),
                "contra": t("slip.orient_contra", lang),
            }.get(str(orient_used), str(orient_used))
        )
    )
    if high_risk_used:
        st.markdown(
            f'<p style="color:#b91c1c;font-weight:700;">{t("slip.high_risk_warn", lang)}</p>',
            unsafe_allow_html=True,
        )
        wanted = int(st.session_state.get("slip_max_legs", len(slip.legs)))
        st.caption(
            t("slip.high_risk_count", lang).format(have=len(slip.legs), want=wanted)
        )
    elif not slip.is_plausible:
        st.error(t("slip.implausible", lang))
    elif len(slip.legs) < max(1, int(st.session_state.get("slip_max_legs", len(slip.legs)))):
        st.info(t("slip.trimmed_note", lang))
    st.html(ticket_html(slip, lang=lang, stake=stake))
    _render_ollama_explain(lang, slip, stake)
    with st.expander(t("slip.copy_title", lang), expanded=False):
        st.code(format_ticket(slip, lang=lang, stake=stake), language=None)

    if not beginner:
        m1, m2, m3 = st.columns(3)
        m1.metric(t("slip.combined_odds", lang), f"{slip.combined_odds:.2f}")
        m2.metric(t("slip.combined_prob", lang), t("slip.combo_chance_na", lang))
        ev_display = f"{slip.expected_value * 100:.1f}%" if slip.is_plausible else "—"
        m3.metric(t("slip.combined_ev", lang), ev_display)
        st.caption(t("slip.disclaimer", lang))
        _slip_paper_reserve(lang, mode, slip, stake)
    else:
        st.caption(t("slip.disclaimer", lang))


def _slip_paper_reserve(lang, mode, slip, stake) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    """Reserve simulated units for the current slip in the paper ledger."""

    st.divider()
    st.caption(t("paper.mode_note", lang).format(mode=mode))
    ledger = paper_ledger_for_mode(mode)
    preview = preview_slip(ledger, slip, stake_units=stake, mode=mode)
    if preview.already_committed and preview.existing_booking_id:
        st.info(
            t("paper.commit_ok", lang).format(id=preview.existing_booking_id[:8])
        )
    elif preview.ok:
        st.caption(
            t("paper.preview", lang).format(
                open=preview.total_open_after,
                avail=preview.available_after,
            )
        )
    else:
        st.warning(
            t("paper.commit_blocked", lang).format(
                reasons=", ".join(preview.reasons) or "—"
            )
        )
    c1, c2 = st.columns(2)
    if c1.button(
        t("paper.commit", lang),
        key="slip_paper_commit",
        disabled=not preview.ok and not preview.already_committed,
    ):
        try:
            booking = commit_slip(ledger, slip, stake_units=stake, mode=mode)
            st.success(t("paper.commit_ok", lang).format(id=booking.booking_id[:8]))
        except CapViolationError as exc:
            st.error(
                t("paper.commit_blocked", lang).format(
                    reasons=", ".join(exc.reasons) or "—"
                )
            )
    if c2.button(t("paper.open_page", lang), key="slip_goto_paper"):
        st.session_state["pending_nav_page"] = "paper"
        st.rerun()


def _paper_page(lang, mode) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    """Paper-simulation ledger: units, caps, open reservations, manual settle."""

    st.markdown(
        f"""
        <div style="margin:0 0 1rem 0;padding:1.1rem 1.25rem;border-radius:12px;
        background:linear-gradient(135deg,#111827 0%,#1f2937 50%,#365314 100%);
        color:#f8fafc;">
          <div style="font-size:0.75rem;letter-spacing:0.14em;text-transform:uppercase;
          opacity:0.75;">{t("paper.hero_kicker", lang)}</div>
          <div style="font-size:1.85rem;font-weight:800;line-height:1.15;margin:0.2rem 0;">
            {t("page.paper", lang)}
          </div>
          <div style="font-size:0.95rem;opacity:0.88;">{t("paper.hero_sub", lang)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"{t('paper.intro', lang)} · {t('paper.mode_note', lang).format(mode=mode)}"
    )
    if mode == "demo":
        st.caption(f"**[{t('safety.demo_badge', lang)}]** {t('safety.demo', lang)}")

    ledger = paper_ledger_for_mode(mode)
    snap = ledger.snapshot()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t("paper.available", lang), f"{snap.available:.1f}")
    m2.metric(t("paper.open", lang), f"{snap.open_reserved:.1f}")
    m3.metric(t("paper.realized", lang), f"{snap.realized_pnl:+.1f}")
    m4.metric(t("paper.capital", lang), f"{snap.paper_capital:.0f}")
    st.caption(
        t("paper.caps", lang).format(
            match=snap.max_match_stake,
            open=snap.max_open_stake,
        )
    )

    st.subheader(t("paper.open_list", lang))
    bookings = open_bookings(ledger)
    if not bookings:
        st.info(t("paper.empty", lang))
        return

    from quantbot.dashboard.paper import booking_ticket_html

    for booking in bookings:
        st.html(booking_ticket_html(booking, lang=lang))
        b1, b2, b3, b4 = st.columns(4)
        if b1.button(
            t("paper.settle_win", lang),
            key=f"paper_win::{booking.booking_id}",
        ):
            ledger.settle(booking.booking_id, won=True)
            st.rerun()
        if b2.button(
            t("paper.settle_loss", lang),
            key=f"paper_loss::{booking.booking_id}",
        ):
            ledger.settle(booking.booking_id, won=False)
            st.rerun()
        if b3.button(
            t("paper.settle_void", lang),
            key=f"paper_void::{booking.booking_id}",
        ):
            ledger.settle(booking.booking_id, void=True)
            st.rerun()
        if b4.button(
            t("paper.cancel", lang),
            key=f"paper_cancel::{booking.booking_id}",
        ):
            ledger.cancel(booking.booking_id)
            st.rerun()


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


def _card_page(
    lang, C, orchestrator, mode, league, season, live, window=None
) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    import pandas as pd

    st.header(t("page.card", lang))
    st.caption(t("card.intro", lang))
    if window is None:
        as_of, start_d, end_d = _pick_window(lang, orchestrator, [league], season, live)
    else:
        as_of, start_d, end_d = window
    try:
        cards = C["cards"](orchestrator, mode, league.value, season, _as_of_cache_key(as_of))
    except ValueError as exc:
        st.warning(str(exc))
        return
    cards = [c for c in cards if start_d <= c.kickoff.date() <= end_d]
    if not cards:
        st.info(
            t("card.no_matches_in_window", lang).format(
                start=start_d.isoformat(), end=end_d.isoformat()
            )
        )
        return

    idx = st.selectbox(
        t("col.match", lang),
        range(len(cards)),
        format_func=lambda i: (
            f"{cards[i].kickoff.strftime('%d.%m. %H:%M')} · "
            f"{cards[i].home} vs {cards[i].away}"
        ),
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
        # Prefer decision/validation fields from the live signal when present.
        decision_line = f"**{t('card.decision', lang)}**: {c.signal}"
        stake_txt = f"{c.stake_fraction:.2f}%"
        if getattr(c, "sizing_allowed", True) is False or c.stake_fraction <= 0.0:
            stake_txt = "—" if lang.startswith("de") else "—"
            decision_line += f" · {t('sig.exploratory', lang)}"
        else:
            decision_line += f" · {t('card.stake', lang)}: {stake_txt}"
        st.markdown(decision_line)

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

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("track.hit_rate", lang), "-" if view.hit_rate is None else f"{view.hit_rate:.1f}%")
    c2.metric(t("track.settled_bets", lang), view.total_bets)
    c3.metric(t("track.correct", lang), view.total_correct)
    clv_vals = [
        e.get("clv_odds_ratio")
        for r in view.rounds
        for e in r["entries"]
        if e.get("settled") and isinstance(e.get("clv_odds_ratio"), (int, float))
    ]
    avg_clv = sum(clv_vals) / len(clv_vals) if clv_vals else None
    c4.metric(
        t("track.avg_clv", lang),
        "—" if avg_clv is None else f"{avg_clv * 100:+.1f}%",
    )

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
                clv_ratio = e.get("clv_odds_ratio")
                clv_status = e.get("clv_status")
                if isinstance(clv_ratio, (int, float)):
                    clv_s = f"{t('track.clv', lang)} {clv_ratio * 100:+.1f}%"
                elif clv_status:
                    clv_s = f"{t('track.clv_na', lang)} ({escape(str(clv_status))})"
                else:
                    clv_s = t("track.clv_na", lang)
                ref_ev = e.get("closing_reference_ev")
                if isinstance(ref_ev, (int, float)):
                    clv_s += f" · {t('track.clv_ref_ev', lang)} {ref_ev * 100:+.1f}%"
                st.html(
                    '<div style="padding:0.55rem 0;border-bottom:1px solid #e5e7eb;">'
                    f'<div style="font-weight:700;">{escape(str(e["match"]))}</div>'
                    f'<div style="margin-top:0.25rem;">→ {tip_html}'
                    f' <span style="margin-left:0.5rem;opacity:0.75;">{odds_s}</span></div>'
                    f'<div style="margin-top:0.2rem;font-size:0.9rem;">{outcome_html}'
                    f' · {escape(t("track.result", lang))}: {result}</div>'
                    f'<div style="margin-top:0.15rem;font-size:0.85rem;opacity:0.85;">{clv_s}</div>'
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
