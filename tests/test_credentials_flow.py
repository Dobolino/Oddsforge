"""Credential resolution and form regressions; no real keys or network calls."""

import pytest
from streamlit.testing.v1 import AppTest

from quantbot.config import Settings
from quantbot.local_credentials import load_api_keys, resolve_api_keys, save_api_keys


@pytest.fixture
def isolated_keys(tmp_path, monkeypatch):
    import quantbot.config as config
    import quantbot.local_credentials as credentials

    for name in ("QUANTBOT_FOOTBALL_DATA_API_KEY", "QUANTBOT_THE_ODDS_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "credentials.env"
    monkeypatch.setattr(credentials, "default_credentials_path", lambda: path)
    monkeypatch.setattr(config, "get_settings", lambda: Settings(_env_file=None))
    return path


def test_shared_resolution_precedence_and_reload(isolated_keys):
    path = isolated_keys
    save_api_keys("saved-football", "saved-odds")
    settings = Settings(_env_file=None, football_data_api_key="explicit-football")
    assert resolve_api_keys(settings).football == "explicit-football"
    assert resolve_api_keys(settings).odds == "saved-odds"
    save_api_keys("changed-football", "changed-odds")
    assert resolve_api_keys(settings).odds == "changed-odds"
    path.unlink()
    assert resolve_api_keys(settings).odds == ""


def test_environment_then_dotenv_then_saved(isolated_keys, tmp_path, monkeypatch):
    save_api_keys("saved-football", "saved-odds")
    dotenv = tmp_path / ".env"
    dotenv.write_text("QUANTBOT_FOOTBALL_DATA_API_KEY=dotenv-football\n")
    assert resolve_api_keys(Settings(_env_file=dotenv)).football == "dotenv-football"
    monkeypatch.setenv("QUANTBOT_FOOTBALL_DATA_API_KEY", "environment-football")
    assert resolve_api_keys(Settings(_env_file=dotenv)).football == "environment-football"
    monkeypatch.setenv("QUANTBOT_FOOTBALL_DATA_API_KEY", " ")
    assert resolve_api_keys(Settings(_env_file=dotenv)).football == "saved-football"


@pytest.mark.parametrize("bad", ["", "   ", "one\nOTHER=value", "one two"])
def test_invalid_save_keeps_existing_keys(isolated_keys, bad):
    save_api_keys("original-football", "original-odds")
    before = isolated_keys.read_bytes()
    with pytest.raises(ValueError):
        save_api_keys(bad, "replacement-odds")
    assert isolated_keys.read_bytes() == before


def test_cli_uses_dashboard_credentials(isolated_keys, monkeypatch):
    import quantbot.data.providers as providers
    from quantbot.cli import _build_provider
    from quantbot.schemas import League

    save_api_keys("saved-football", "saved-odds")
    monkeypatch.setattr(providers, "build_live_provider", lambda **kwargs: kwargs)
    result = _build_provider(True, League.PREMIER_LEAGUE)
    assert result["football_api_key"] == "saved-football"
    assert result["the_odds_api_key"] == "saved-odds"


def _form():
    return AppTest.from_string(
        "from quantbot.dashboard.credentials import credential_controls\n"
        "credential_controls('de')\n",
        default_timeout=15,
    ).run()


def _save(at):
    return next(button for button in at.button if button.label == "Schlüssel speichern").click().run()


def test_form_saves_only_on_submit_then_deletes(isolated_keys):
    at = _form()
    assert not at.exception
    at.text_input(key="fd_key_input").set_value("test-football")
    at.text_input(key="odds_key_input").set_value("test-odds").run()
    assert not isolated_keys.exists()
    _save(at)
    assert not at.exception
    assert load_api_keys().football == "test-football"
    assert len(at.text_input) == 0
    at.button(key="keys_clear_btn").click().run()
    assert not at.exception
    assert not isolated_keys.exists()
    assert all(widget.value == "" for widget in at.text_input)


def test_form_invalid_edit_and_cancel_preserve_keys(isolated_keys):
    save_api_keys("old-football", "old-odds", "legacy-nba")
    at = _form()
    at.button(key="keys_change_btn").click().run()
    at.text_input(key="fd_key_input").set_value("new-football")
    _save(at)
    assert at.error and not at.exception
    assert load_api_keys().football == "old-football"
    at.button(key="keys_cancel").click().run()
    assert not at.exception
    assert load_api_keys().basketball == "legacy-nba"


def test_form_storage_failure_is_explained(isolated_keys, monkeypatch):
    import quantbot.dashboard.credentials as ui

    def fail(*args):
        raise OSError("internal details")

    monkeypatch.setattr(ui, "save_api_keys", fail)
    at = _form()
    at.text_input(key="fd_key_input").set_value("test-football")
    at.text_input(key="odds_key_input").set_value("test-odds")
    _save(at)
    assert at.error and not at.exception
    assert "internal details" not in at.error[0].value


def test_badges_never_claim_verified_basketball():
    at = AppTest.from_string(
        "from quantbot.dashboard.app import _api_status_badges\n"
        "_api_status_badges('de', fd_key='fake-football', odds_key='fake-odds', bball_key='fake-nba', live=False)\n",
        default_timeout=15,
    ).run()
    assert not at.exception
    text = " ".join(item.value for item in at.caption)
    assert "UNGEPRÜFT" in text
    assert "NBA: Demodaten" in text
    assert "fake-football" not in text
