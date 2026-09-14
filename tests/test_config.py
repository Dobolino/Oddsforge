"""Tests for configuration loading and guardrails."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from quantbot.config import MarginMethod, Settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.min_edge == 0.03
    assert settings.kelly_fraction == 0.10
    assert settings.margin_method is MarginMethod.SHIN
    assert settings.totals_margin_method is MarginMethod.POWER
    assert settings.allow_automated_betting is False


def test_log_level_normalized() -> None:
    assert Settings(log_level="debug").log_level == "DEBUG"


def test_invalid_log_level_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="verbose")


def test_automated_betting_cannot_be_enabled() -> None:
    with pytest.raises(ValidationError):
        Settings(allow_automated_betting=True)


def test_min_edge_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings(min_edge=1.5)
