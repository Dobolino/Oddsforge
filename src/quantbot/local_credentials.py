"""Local API credential persistence (never commit these files).

Keys are stored only on the user's machine under ``~/.quantbot/`` (outside
the git tree) or an explicit path passed in tests. Values are never logged.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from quantbot.config import Settings

_FOOTBALL_KEY = "QUANTBOT_FOOTBALL_DATA_API_KEY"
_ODDS_KEY = "QUANTBOT_THE_ODDS_API_KEY"
_BASKETBALL_KEY = "QUANTBOT_BALLDONTLIE_API_KEY"
_APIFOOTBALL_KEY = "QUANTBOT_API_FOOTBALL_API_KEY"


class StoredApiKeys(NamedTuple):
    """Persisted API keys.

    Football + Odds unlock live football. Basketball and API-Football are
    optional extras (API-Football adds Asian-handicap / totals odds).
    """

    football: str
    odds: str
    basketball: str = ""
    apifootball: str = ""


def default_credentials_path() -> Path:
    """User-local credentials file (outside the repository)."""

    return Path.home() / ".quantbot" / "credentials.env"


def save_api_keys(
    football_key: str,
    odds_key: str,
    basketball_key: str = "",
    apifootball_key: str = "",
    *,
    path: Path | None = None,
) -> Path:
    """Write API keys to a local env-style file. Returns the path used."""

    football = football_key.strip()
    odds = odds_key.strip()
    basketball = basketball_key.strip()
    apifootball = apifootball_key.strip()
    if any(
        any(char.isspace() for char in key)
        for key in (football, odds, basketball, apifootball)
    ):
        raise ValueError("API keys must not contain whitespace")
    if not football or not odds:
        raise ValueError("football and odds API keys are required")

    target = Path(path) if path is not None else default_credentials_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Local QuantBot API keys — do not commit",
        f"{_FOOTBALL_KEY}={football}",
        f"{_ODDS_KEY}={odds}",
    ]
    if basketball:
        lines.append(f"{_BASKETBALL_KEY}={basketball}")
    if apifootball:
        lines.append(f"{_APIFOOTBALL_KEY}={apifootball}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def load_api_keys(*, path: Path | None = None) -> StoredApiKeys | None:
    """Load keys from a local file. Returns None if football/odds are missing."""

    target = Path(path) if path is not None else default_credentials_path()
    if not target.exists():
        return None
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return None

    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        values[key.strip()] = raw.strip().strip(chr(34)).strip(chr(39))

    football = values.get(_FOOTBALL_KEY, "").strip()
    odds = values.get(_ODDS_KEY, "").strip()
    basketball = values.get(_BASKETBALL_KEY, "").strip()
    apifootball = values.get(_APIFOOTBALL_KEY, "").strip()
    if not football or not odds:
        return None
    return StoredApiKeys(
        football=football,
        odds=odds,
        basketball=basketball,
        apifootball=apifootball,
    )


def clear_api_keys(*, path: Path | None = None) -> bool:
    """Delete the local credentials file. Returns True if a file was removed."""

    target = Path(path) if path is not None else default_credentials_path()
    if not target.exists():
        return False
    target.unlink()
    return True


def keys_are_stored(*, path: Path | None = None) -> bool:
    """True when a complete local credentials file is present."""

    return load_api_keys(path=path) is not None


def mask_key(key: str) -> str:
    """Show only the last four characters of a key."""

    key = (key or "").strip()
    if len(key) <= 4:
        return "••••"
    return "••••" + key[-4:]


def resolve_api_keys(
    settings: Settings | None = None, *, path: Path | None = None
) -> StoredApiKeys:
    """Shared CLI/dashboard keys: environment/.env first, local file as fallback.

    Read the local file on every call so dashboard edits take effect immediately.
    Empty configuration values do not override saved keys.
    """
    if settings is None:
        from quantbot.config import get_settings

        settings = get_settings()
    stored = load_api_keys(path=path) or StoredApiKeys("", "")
    football = settings.football_data_api_key
    odds = settings.the_odds_api_key
    apifootball = settings.api_football_api_key
    return StoredApiKeys(
        (football.get_secret_value().strip() if football else "") or stored.football,
        (odds.get_secret_value().strip() if odds else "") or stored.odds,
        stored.basketball,
        (apifootball.get_secret_value().strip() if apifootball else "") or stored.apifootball,
    )
