"""Tests for the i18n layer, the CLI --lang flag, and the language setting."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from quantbot.cli import app
from quantbot.config import Settings
from quantbot.i18n import GLOSSARY, LANGUAGES, t

runner = CliRunner()


def test_languages() -> None:
    assert LANGUAGES == ("de", "en")


def test_translation_lookup() -> None:
    assert t("col.match", "de") == "Spiel"
    assert t("col.match", "en") == "Match"


def test_api_keys_save_button_strings() -> None:
    """Sidebar keys need an explicit Save so NBA can be entered after football keys."""
    assert "speichern" in t("keys.save", "de").lower()
    assert "save" in t("keys.save", "en").lower()
    assert "nba" in t("keys.save_basketball", "de").lower()
    assert t("keys.save_need_football_odds", "de")
    assert "optional" in t("keys.hint", "de").lower() or "BallDontLie" in t("keys.hint", "de")


def test_translation_falls_back_to_german() -> None:
    # Unknown language falls back to German, unknown key returns the key.
    assert t("col.match", "fr") == "Spiel"
    assert t("does.not.exist", "de") == "does.not.exist"


def test_glossary_is_bilingual() -> None:
    assert GLOSSARY
    for section in GLOSSARY:
        assert "de" in section["title"] and "en" in section["title"]
        for term, de_def, en_def in section["items"]:
            assert term and de_def and en_def


def test_settings_language_default_and_validation() -> None:
    assert Settings().language == "de"
    assert Settings(language="EN").language == "en"
    with pytest.raises(Exception):
        Settings(language="fr")


def test_cli_info_german_and_english() -> None:
    de = runner.invoke(app, ["info", "--lang", "de"])
    en = runner.invoke(app, ["info", "--lang", "en"])
    assert de.exit_code == 0 and en.exit_code == 0
    assert "Modell" in de.stdout
    assert "Model" in en.stdout
    assert "Leitplanken" in de.stdout


def test_cli_backtest_language() -> None:
    de = runner.invoke(app, ["backtest", "--lang", "de"])
    assert de.exit_code == 0
    assert "Trefferquote" in de.stdout  # Win rate in German


def test_cli_predict_footer_language() -> None:
    en = runner.invoke(app, ["predict", "--lang", "en"])
    assert en.exit_code == 0
    assert "value signals" in en.stdout
