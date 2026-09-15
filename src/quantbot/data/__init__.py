"""Data ingestion layer."""

from __future__ import annotations

from quantbot.data.base import BaseDataProvider
from quantbot.data.basketball import BasketballDataProvider
from quantbot.data.composite import CompositeDataProvider
from quantbot.data.dummy import DummyDataProvider

__all__ = [
    "BaseDataProvider",
    "BasketballDataProvider",
    "CompositeDataProvider",
    "DummyDataProvider",
]
