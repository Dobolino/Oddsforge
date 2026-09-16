"""Credential controls shared by all dashboard pages."""

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
        for name in ("fd_key_input", "odds_key_input", "bball_key_input"):
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
            st.caption(t("keys.active", lang))
            if st.button(t("keys.change", lang), key="keys_change_btn"):
                st.session_state["keys_edit_mode"] = True
                st.rerun()
        else:
            with st.form("api_credentials", clear_on_submit=False):
                football = st.text_input(t("keys.football", lang), type="password", key="fd_key_input")
                odds = st.text_input(t("keys.odds", lang), type="password", key="odds_key_input")
                st.caption(t("keys.hint", lang))
                submitted = st.form_submit_button(t("keys.save", lang))
            if submitted:
                try:
                    save_api_keys(football, odds, stored.basketball if stored else "")
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
    return keys
