"""Polygon.io provider — stub showing how to add a keyed vendor.

Polygon has strong options + real-time coverage, so it's a natural route for
those types once implemented. Fetch methods raise until filled in with real
REST calls using self.config['api_key'].
"""
from __future__ import annotations

from .base import DataProvider, DataType, ProviderError


class PolygonProvider(DataProvider):
    name = "Polygon.io"
    capabilities = frozenset({
        DataType.DAILY,
        DataType.QUOTE,
        DataType.OPTIONS,
    })

    def _api_key(self) -> str:
        key = self.config.get("api_key")
        if not key:
            raise ProviderError("Polygon.io requires an API key")
        return key

    def fetch_daily(self, symbol, start=None, end=None):
        self._api_key()
        raise ProviderError("Polygon daily fetch not yet implemented")

    def fetch_quote(self, symbol):
        self._api_key()
        raise ProviderError("Polygon quote fetch not yet implemented")

    def fetch_options(self, symbol, expiration=None):
        self._api_key()
        raise ProviderError("Polygon options fetch not yet implemented")
