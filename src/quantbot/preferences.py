"""User preferences stored only on this PC (never committed)."""

from __future__ import annotations

import json
from pathlib import Path

from quantbot.ollama_explain import (
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL,
    DEFAULT_TIMEOUT_S,
    OllamaSettings,
)


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


def glossary_seen_path() -> Path:
    return _quantbot_home() / "glossary_seen"


def is_glossary_seen(*, path: Path | None = None) -> bool:
    """Whether the user has opened the glossary at least once (slip gate)."""

    target = Path(path) if path is not None else glossary_seen_path()
    return target.exists()


def set_glossary_seen(*, path: Path | None = None) -> Path:
    target = Path(path) if path is not None else glossary_seen_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("1\n", encoding="utf-8")
    return target


def ollama_settings_path() -> Path:
    return _quantbot_home() / "ollama.json"


def load_ollama_settings(*, path: Path | None = None) -> OllamaSettings:
    """Load optional Ollama prefs; missing/invalid file → disabled defaults."""

    target = Path(path) if path is not None else ollama_settings_path()
    if not target.exists():
        return OllamaSettings()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return OllamaSettings()
    if not isinstance(raw, dict):
        return OllamaSettings()
    try:
        timeout = float(raw.get("timeout_s", DEFAULT_TIMEOUT_S))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_S
    return OllamaSettings(
        enabled=bool(raw.get("enabled", False)),
        base_url=str(raw.get("base_url") or DEFAULT_OLLAMA_URL).strip() or DEFAULT_OLLAMA_URL,
        model=str(raw.get("model") or DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL,
        timeout_s=max(5.0, min(timeout, 180.0)),
    )


def save_ollama_settings(settings: OllamaSettings, *, path: Path | None = None) -> Path:
    target = Path(path) if path is not None else ollama_settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": bool(settings.enabled),
        "base_url": settings.base_url,
        "model": settings.model,
        "timeout_s": float(settings.timeout_s),
    }
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target
