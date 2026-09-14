"""Local API key save/load (temporary files only — never real secrets)."""

from __future__ import annotations

from pathlib import Path

from quantbot.local_credentials import clear_api_keys, load_api_keys, save_api_keys


def test_save_and_load_api_keys(tmp_path: Path) -> None:
    path = tmp_path / "credentials.env"
    # Deliberately fake placeholder values — not real secrets.
    save_api_keys("test-football-key", "test-odds-key", path=path)

    loaded = load_api_keys(path=path)
    assert loaded is not None
    football, odds = loaded
    assert football == "test-football-key"
    assert odds == "test-odds-key"
    assert "test-football-key" in path.read_text(encoding="utf-8")


def test_load_missing_file_returns_none(tmp_path: Path) -> None:
    assert load_api_keys(path=tmp_path / "missing.env") is None


def test_clear_api_keys(tmp_path: Path) -> None:
    path = tmp_path / "credentials.env"
    save_api_keys("aaa", "bbb", path=path)
    assert path.exists()
    assert clear_api_keys(path=path) is True
    assert not path.exists()
    assert load_api_keys(path=path) is None


def test_incomplete_file_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "credentials.env"
    path.write_text("QUANTBOT_FOOTBALL_DATA_API_KEY=only-one\n", encoding="utf-8")
    assert load_api_keys(path=path) is None
