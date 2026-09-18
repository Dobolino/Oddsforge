"""Tests for optional local Ollama tip-slip explanations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from quantbot.dashboard.slip import BettingSlip, SlipLeg
from quantbot.ollama_explain import (
    OllamaSettings,
    build_explain_messages,
    explain_slip,
    ping_ollama,
)
from quantbot.preferences import load_ollama_settings, save_ollama_settings
from quantbot.schemas import MatchOutcome


def _sample_slip() -> BettingSlip:
    return BettingSlip(
        legs=(
            SlipLeg(
                match_id="1",
                match="A vs B",
                tip="Tipp: Heimsieg",
                outcome=MatchOutcome.HOME,
                odds=1.85,
                model_prob=0.55,
                edge=0.04,
                role="core",
                league="Premier League",
                kickoff_date="2026-09-20",
                stance="with",
            ),
            SlipLeg(
                match_id="2",
                match="C vs D",
                tip="Tipp: Unentschieden",
                outcome=MatchOutcome.DRAW,
                odds=3.40,
                model_prob=0.35,
                edge=0.08,
                role="core",
                league="Serie A",
                kickoff_date="2026-09-21",
                stance="against",
            ),
        ),
        style="safe",
    )


def test_ollama_settings_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "ollama.json"
    assert load_ollama_settings(path=path).enabled is False
    save_ollama_settings(
        OllamaSettings(enabled=True, base_url="http://127.0.0.1:11434", model="llama3.2"),
        path=path,
    )
    loaded = load_ollama_settings(path=path)
    assert loaded.enabled is True
    assert loaded.model == "llama3.2"


def test_build_explain_messages_contains_facts_only() -> None:
    msgs = build_explain_messages(_sample_slip(), lang="de", stake=10.0)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert "KEINE Tipps ändern" in msgs[0]["content"]
    user = msgs[1]["content"]
    assert "A vs B" in user
    assert "combined_odds=" in user
    assert "stance=with" in user


def test_explain_slip_disabled_returns_error() -> None:
    result = explain_slip(
        _sample_slip(),
        settings=OllamaSettings(enabled=False),
        lang="de",
    )
    assert result.ok is False
    assert "ausgeschaltet" in result.error.lower() or "disabled" in result.error.lower()


def test_ping_ollama_success() -> None:
    settings = OllamaSettings(enabled=True, model="llama3.2")
    fake = MagicMock()
    fake.get.return_value.status_code = 200
    fake.get.return_value.raise_for_status = MagicMock()
    fake.get.return_value.json.return_value = {
        "models": [{"name": "llama3.2:latest"}, {"name": "mistral:latest"}]
    }
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    with patch("quantbot.ollama_explain.httpx.Client", return_value=fake):
        result = ping_ollama(settings)
    assert result.ok is True
    assert "llama3.2" in result.text


def test_explain_slip_posts_chat_and_returns_text() -> None:
    settings = OllamaSettings(enabled=True, model="llama3.2")
    fake = MagicMock()
    # ping
    tags = MagicMock()
    tags.raise_for_status = MagicMock()
    tags.json.return_value = {"models": [{"name": "llama3.2:latest"}]}
    # chat
    chat = MagicMock()
    chat.raise_for_status = MagicMock()
    chat.json.return_value = {
        "message": {"role": "assistant", "content": "Kurze Erklärung des Scheins."}
    }
    fake.get.return_value = tags
    fake.post.return_value = chat
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    with patch("quantbot.ollama_explain.httpx.Client", return_value=fake):
        result = explain_slip(_sample_slip(), settings=settings, lang="de", stake=10.0)
    assert result.ok is True
    assert "Erklärung" in result.text
    fake.post.assert_called_once()
    payload = fake.post.call_args.kwargs.get("json") or fake.post.call_args[1].get("json")
    assert payload["stream"] is False
    assert payload["model"] == "llama3.2"
