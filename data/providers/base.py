"""Provider abstraction for market data.

Each provider implements only the capabilities it supports; the DataService
routes each data type to a provider that can serve it. Providers return plain
Python dicts (documented per method) so nothing downstream is coupled to a
particular vendor SDK (yfinance, Alpha Vantage, Polygon, …).
"""
from __future__ import annotations

from abc import ABC
from enum import Enum


class DataType(str, Enum):
    DAILY = "daily"          # historical OHLCV bars
    QUOTE = "quote"          # latest / real-time price
    DIVIDENDS = "dividends"  # dividend history
    OPTIONS = "options"      # options chain
    CORPORATE_ACTIONS = "corporate_actions"  # splits, mergers, spinoffs
    METADATA = "metadata"    # company/sector profile (name, exchange, sector, …)


class ProviderError(Exception):
    """A provider failed to fetch (network error, bad symbol, rate limit …)."""


class NotSupported(ProviderError):
    """A provider was asked for a data type it doesn't offer."""


class DataProvider(ABC):
    """Base class. Subclasses set `name` + `capabilities` and override the
    fetch methods for the types they support.

    Return shapes:
      fetch_daily     -> [{date, open, high, low, adjusted_close, volume}, ...]
      fetch_quote     -> {symbol, price, currency?, time?}
      fetch_dividends -> [{ex_date, amount}, ...]
      fetch_options   -> {symbol, expiration, expirations: [...],
                          calls: [contract...], puts: [contract...]}
        contract      -> {contract_symbol, strike, option_type, last_price,
                          bid, ask, volume, open_interest, implied_vol,
                          in_the_money}
      fetch_corporate_actions
                      -> [{ex_date, action_type, numerator, denominator}, ...]
                         (providers typically only surface 'split'; mergers and
                          spinoffs are entered manually)
      fetch_metadata  -> {symbol, name?, asset_type?, exchange?, currency?,
                          sector?, industry?, country?}  (any field may be absent)
    """

    name: str = "base"
    capabilities: frozenset[DataType] = frozenset()

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def supports(self, data_type: DataType) -> bool:
        return data_type in self.capabilities

    def fetch_daily(self, symbol: str, start: str | None = None,
                    end: str | None = None) -> list[dict]:
        raise NotSupported(f"{self.name} does not provide daily data")

    def fetch_quote(self, symbol: str) -> dict:
        raise NotSupported(f"{self.name} does not provide quotes")

    def fetch_dividends(self, symbol: str) -> list[dict]:
        raise NotSupported(f"{self.name} does not provide dividend data")

    def fetch_options(self, symbol: str, expiration: str | None = None) -> dict:
        raise NotSupported(f"{self.name} does not provide options data")

    def fetch_corporate_actions(self, symbol: str) -> list[dict]:
        raise NotSupported(f"{self.name} does not provide corporate-action data")

    def fetch_metadata(self, symbol: str) -> dict:
        raise NotSupported(f"{self.name} does not provide metadata")
