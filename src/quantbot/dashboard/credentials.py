"""Credential controls shared by all dashboard pages."""

from datetime import date
from pathlib import Path

import streamlit as st

from quantbot.config import get_settings
from quantbot.i18n import t
from quantbot.local_credentials import (
    StoredApiKeys,
    clear_api_keys,
    load_api_keys,
    mask_key,
    resolve_api_keys,
    save_api_keys,
)


def credential_controls(lang: str) -> StoredApiKeys:
    """Only save submitted values; unsaved edits never reach API providers."""
    settings = get_settings()
    stored = load_api_keys()
    keys = resolve_api_keys(settings)
    if st.session_state.pop("keys_clear_inputs", False):
        for name in ("fd_key_input", "odds_key_input", "bball_key_input", "apif_key_input"):
            st.session_state.pop(name, None)
    st.session_state.setdefault("keys_edit_mode", not (keys.football and keys.odds))

    with st.sidebar.expander(t("keys.title", lang), expanded=False):
        if st.session_state.pop("keys_saved_notice", False):
            st.success(t("keys.saved", lang))
        external = any(
            value and value.get_secret_value().strip()
            for value in (settings.football_data_api_key, settings.the_odds_api_key)
        )
        if external:
            st.info(t("keys.external", lang))
        if not st.session_state["keys_edit_mode"]:
            st.caption(f"Football-Data: {mask_key(keys.football)}")
            st.caption(f"The Odds API: {mask_key(keys.odds)}")
            if keys.apifootball:
                st.caption(f"API-Football: {mask_key(keys.apifootball)}")
            st.caption(t("keys.active", lang))
            if st.button(t("keys.change", lang), key="keys_change_btn"):
                st.session_state["keys_edit_mode"] = True
                st.rerun()
        else:
            with st.form("api_credentials", clear_on_submit=False):
                football = st.text_input(t("keys.football", lang), type="password", key="fd_key_input")
                odds = st.text_input(t("keys.odds", lang), type="password", key="odds_key_input")
                apifootball = st.text_input(
                    t("keys.apifootball", lang), type="password", key="apif_key_input"
                )
                st.caption(t("keys.hint", lang))
                submitted = st.form_submit_button(t("keys.save", lang))
            if submitted:
                try:
                    save_api_keys(
                        football,
                        odds,
                        stored.basketball if stored else "",
                        apifootball or (stored.apifootball if stored else ""),
                    )
                except ValueError:
                    st.error(t("keys.invalid", lang))
                except OSError:
                    st.error(t("keys.write_failed", lang))
                else:
                    st.cache_data.clear()
                    st.session_state["keys_edit_mode"] = False
                    st.session_state["keys_clear_inputs"] = True
                    st.session_state["keys_saved_notice"] = True
                    st.rerun()
            if (keys.football or keys.odds) and st.button(t("keys.cancel", lang), key="keys_cancel"):
                st.session_state["keys_edit_mode"] = False
                st.session_state["keys_clear_inputs"] = True
                st.rerun()
        if stored and st.button(t("keys.clear", lang), key="keys_clear_btn"):
            try:
                clear_api_keys()
            except OSError:
                st.error(t("keys.write_failed", lang))
            else:
                st.cache_data.clear()
                st.session_state.pop("keys_edit_mode", None)
                st.session_state["keys_clear_inputs"] = True
                st.rerun()
        st.caption(t("keys.basketball_optional", lang))
        st.caption(t("keys.apifootball_optional", lang))
        _api_football_test(keys, lang)
    return keys


def _api_football_test(keys: StoredApiKeys, lang: str) -> None:
    """Validate the API-Football key and show the markets a fixture returns.

    Confirms the key works (via ``/status``) and, when odds exist for today,
    lists the raw bet labels so the Asian-handicap format can be verified
    before the parser is trusted.
    """

    if not st.button(t("keys.test", lang), key="apif_test_btn"):
        return
    if not keys.apifootball:
        st.warning(t("keys.test_missing", lang))
        return

    from quantbot.data.providers import ApiFootballProvider

    provider = ApiFootballProvider(
        keys.apifootball,
        cache_dir=Path.home() / ".quantbot" / "cache" / "api_football",
        min_interval=1.0,
    )
    try:
        status = provider.fetch_status()
    except Exception as exc:  # show any failure to the user
        st.error(t("keys.test_failed", lang).format(error=str(exc)))
        return

    st.success(
        t("keys.test_ok", lang).format(
            account=status.account,
            plan=status.plan,
            used=status.requests_used,
            limit=status.requests_limit,
            left=status.requests_left,
        )
    )

    # Best-effort market preview: today's odds, first fixture only.
    try:
        payload = provider.fetch_odds(date=date.today().isoformat())
        summaries = provider.summarize_markets(payload)
    except Exception:  # a status pass is already the key win
        summaries = []
    if not summaries:
        st.caption(
            "Heute keine Quoten abrufbar. An einem Spieltag zeigt der Test die gefundenen Märkte."
            if lang == "de"
            else "No odds available today. On a match day the test lists the markets found."
        )
        return
    summary = summaries[0]
    st.caption("Gefundene Märkte im ersten Spiel:" if lang == "de" else "Markets in the first fixture:")
    st.write(", ".join(summary.bet_names) or "—")
    for book, bets in summary.bookmakers.items():
        ah = next((b for b in bets if b.bet_name.lower() == "asian handicap"), None)
        if ah and ah.sample_values:
            st.caption(f"{book} · Asian Handicap: {', '.join(ah.sample_values)}")
            break
