"""Streamlit dashboard package.

The app module (``quantbot.dashboard.app``) runs its UI only as the Streamlit
entry script, so importing this package is side-effect free. ``app_path``
locates the script for the ``quantbot dashboard`` launcher.
"""

from __future__ import annotations

from pathlib import Path


def app_path() -> Path:
    """Absolute path to the Streamlit entry script."""

    return Path(__file__).resolve().parent / "app.py"


__all__ = ["app_path"]
