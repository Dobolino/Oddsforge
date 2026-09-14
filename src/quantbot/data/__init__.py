"""Data ingestion layer."""

from __future__ import annotations

from quantbot.data.base import BaseDataProvider
from quantbot.data.dummy import DummyDataProvider

__all__ = ["BaseDataProvider", "DummyDataProvider"]
