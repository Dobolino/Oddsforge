"""Local API key save/load (temporary files only — never real secrets)."""

from __future__ import annotations

from pathlib import Path

from quantbot.local_credentials import StoredApiKeys, clear_api_keys, load_api_keys, save_api_keys


def test_dashboard_unpacks_four_credential_fields() -> None:
    """Regression: StoredApiKeys gained apifootball; 3-way unpack crashed startup."""
    from quantbot.dashboard import app_path
    from quantbot.local_credentials import StoredApiKeys

    keys = StoredApiKeys("fb", "odds", "bb", "apif")
    assert len(keys) == 4
    fd_key, odds_key, bball_key, apif_key = (
        keys.football,
        keys.odds,
        keys.basketball,
        keys.apifootball,
    )
    assert (fd_key, odds_key, bball_key, apif_key) == ("fb", "odds", "bb", "apif")

    source = app_path().read_text(encoding="utf-8")
    assert "fd_key, odds_key, bball_key = credential_controls" not in source
    assert "keys.apifootball" in source or "keys.apifootball" in source
    assert "keys.football" in source
    assert "apif_key" in source


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


def test_save_and_load_with_basketball_key(tmp_path: Path) -> None:
    path = tmp_path / "credentials.env"
    save_api_keys("fb-key-aaaa", "odds-key-bbbb", "nba-key-cccc", path=path)
    loaded = load_api_keys(path=path)
    assert loaded is not None
    assert loaded.basketball == "nba-key-cccc"
