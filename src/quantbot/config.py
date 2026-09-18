"""Central configuration for QuantBot.

Loaded once at startup via :func:`get_settings`. All values are overridable
through environment variables (prefix ``QUANTBOT_``) or a local ``.env`` file.
Settings are immutable at runtime to keep backtests reproducible.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from quantbot.schemas.enums import MarginMethod


class Environment(str, Enum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


# Project directory anchors. ``config.py`` lives at src/quantbot/config.py,
# so the project root is three levels up.
PACKAGE_ROOT: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = PACKAGE_ROOT.parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"
MODEL_DIR: Path = PROJECT_ROOT / "models"


class Settings(BaseSettings):
    """Application settings sourced from environment and ``.env``.

    Guardrail: version 1 never places bets. ``allow_automated_betting`` exists
    only as an explicit, hard-coded ``False`` so the flag cannot be flipped by
    an environment variable.
    """

    model_config = SettingsConfigDict(
        env_prefix="QUANTBOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- Runtime ---
    env: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"
    log_json: bool = False
    language: str = "de"

    # --- Data provider credentials ---
    football_data_api_key: SecretStr | None = None
    api_football_api_key: SecretStr | None = None
    the_odds_api_key: SecretStr | None = None

    # --- Value & decision thresholds ---
    min_edge: float = Field(default=0.03, ge=0.0, le=1.0)
    min_data_quality: float = Field(default=60.0, ge=0.0, le=100.0)
    min_model_confidence: float = Field(default=55.0, ge=0.0, le=100.0)
    # Conservative fractional Kelly (Gemini: 0.25× was still aggressive for sharp markets).
    kelly_fraction: float = Field(default=0.10, gt=0.0, le=1.0)

    # --- Market engine ---
    # Shin remains default for 1X2; totals engines may override to Power.
    margin_method: MarginMethod = MarginMethod.SHIN
    totals_margin_method: MarginMethod = MarginMethod.POWER

    # --- Hard guardrail: never automate betting in v1 ---
    allow_automated_betting: bool = Field(default=False, frozen=True)

    # --- Experimental markets (P2) ---
    # Asian Handicap signals stay off until an AH ValidationArtifact exists.
    enable_ah_experimental: bool = False

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str) -> str:
        lang = value.lower()
        if lang not in {"de", "en"}:
            raise ValueError("language must be 'de' or 'en'")
        return lang

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        level = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}, got {value!r}")
        return level

    @field_validator("allow_automated_betting")
    @classmethod
    def _enforce_no_automated_betting(cls, value: bool) -> bool:
        if value:
            raise ValueError(
                "Automated betting is disabled in v1. QuantBot is a decision-support "
                "system only."
            )
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached, immutable settings instance."""

    return Settings()
