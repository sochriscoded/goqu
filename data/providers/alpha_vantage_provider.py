"""Alpha Vantage provider — stub showing how to add a keyed vendor.

Declares the capabilities Alpha Vantage offers; fetch methods raise until
implemented. Fill these in with real REST calls using self.config['api_key'].
"""
from __future__ import annotations

from .base import DataProvider, DataType, ProviderError


class AlphaVantageProvider(DataProvider):
    name = "Alpha Vantage"
    capabilities = frozenset({DataType.DAILY, DataType.QUOTE, DataType.DIVIDENDS})

    def _api_key(self) -> str:
        key = self.config.get("api_key")
        if not key:
            raise ProviderError("Alpha Vantage requires an API key")
        return key

    def fetch_daily(self, symbol, start=None, end=None):
        self._api_key()
        raise ProviderError("Alpha Vantage daily fetch not yet implemented")

    def fetch_quote(self, symbol):
        self._api_key()
        raise ProviderError("Alpha Vantage quote fetch not yet implemented")

    def fetch_dividends(self, symbol):
        self._api_key()
        raise ProviderError("Alpha Vantage dividend fetch not yet implemented")
