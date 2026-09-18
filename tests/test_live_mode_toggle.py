"""Live-mode preference and activation gate."""

from __future__ import annotations

from pathlib import Path

from quantbot.preferences import (
    load_live_enabled,
    resolve_live_activation,
    save_live_enabled,
)


def test_live_enabled_defaults_off(tmp_path: Path) -> None:
    assert load_live_enabled(path=tmp_path / "missing") is False


def test_live_enabled_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "live_enabled"
    save_live_enabled(True, path=path)
    assert load_live_enabled(path=path) is True
    save_live_enabled(False, path=path)
    assert load_live_enabled(path=path) is False


def test_resolve_live_activation_opt_in() -> None:
    assert resolve_live_activation(want_live=False, has_keys=True) == (False, None)
    assert resolve_live_activation(want_live=True, has_keys=False) == (
        False,
        "mode.live_needs_keys",
    )
    assert resolve_live_activation(want_live=True, has_keys=True) == (True, None)


def test_app_wires_live_toggle() -> None:
    from quantbot.dashboard import app_path

    source = app_path().read_text(encoding="utf-8")
    assert "live_mode_toggle" in source
    assert "mode.live_toggle" in source
    assert "resolve_live_activation" in source
