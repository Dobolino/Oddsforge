"""User preferences stored only on this PC (never committed)."""

from __future__ import annotations

from pathlib import Path


def _quantbot_home() -> Path:
    return Path.home() / ".quantbot"


def welcome_dismissed_path() -> Path:
    return _quantbot_home() / "welcome_dismissed"


def is_welcome_dismissed(*, path: Path | None = None) -> bool:
    target = Path(path) if path is not None else welcome_dismissed_path()
    return target.exists()


def set_welcome_dismissed(*, path: Path | None = None) -> Path:
    target = Path(path) if path is not None else welcome_dismissed_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("1\n", encoding="utf-8")
    return target


def clear_welcome_dismissed(*, path: Path | None = None) -> bool:
    target = Path(path) if path is not None else welcome_dismissed_path()
    if not target.exists():
        return False
    target.unlink()
    return True
