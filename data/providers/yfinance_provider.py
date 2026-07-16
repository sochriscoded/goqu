"""yfinance-backed provider. Free, no API key; supports every data type.

yfinance is imported lazily inside each method so importing this module (e.g.
in tests) never triggers a network stack or hard-fails if the optional dep is
missing. Network/parse failures are normalized to ProviderError.
"""
from __future__ import annotations

from .base import DataProvider, DataType, ProviderError


class YFinanceProvider(DataProvider):
    name = "yfinance"
    capabilities = frozenset({
        DataType.DAILY,
        DataType.QUOTE,
        DataType.DIVIDENDS,
        DataType.OPTIONS,
        DataType.CORPORATE_ACTIONS,
        DataType.METADATA,
    })

    # yfinance `quoteType` -> our asset_type label.
    _TYPE_MAP = {
        "EQUITY": "Equity",
        "ETF": "ETF",
        "MUTUALFUND": "Mutual Fund",
        "INDEX": "Index",
        "CURRENCY": "Currency",
        "CRYPTOCURRENCY": "Crypto",
        "FUTURE": "Future",
    }

    def _ticker(self, symbol: str):
        try:
            import yfinance as yf
        except ImportError as e:  # pragma: no cover - dep is declared
            raise ProviderError(f"yfinance is not installed: {e}") from e
        return yf.Ticker(symbol)

    def fetch_daily(self, symbol, start=None, end=None):
        try:
            df = self._ticker(symbol).history(
                start=start, end=end, auto_adjust=False
            )
        except Exception as e:
            raise ProviderError(f"daily fetch failed for {symbol}: {e}") from e

        rows = []
        for idx, r in df.iterrows():
            close = r["Adj Close"] if "Adj Close" in r else r["Close"]
            rows.append({
                "date": idx.date().isoformat(),
                "open": float(r["Open"]),
                "high": float(r["High"]),
                "low": float(r["Low"]),
                "adjusted_close": float(close),
                "volume": int(r["Volume"]),
            })
        return rows

    def fetch_metadata(self, symbol):
        """Company/sector profile from yfinance `Ticker.info`. Every field is
        best-effort (yfinance omits many for ETFs/indexes), so callers clean and
        keep only what's present."""
        try:
            info = self._ticker(symbol).info or {}
        except Exception as e:
            raise ProviderError(f"metadata fetch failed for {symbol}: {e}") from e
        quote_type = (info.get("quoteType") or "").upper()
        return {
            "symbol": symbol.upper(),
            "name": info.get("longName") or info.get("shortName"),
            "asset_type": self._TYPE_MAP.get(
                quote_type, quote_type.title() if quote_type else None
            ),
            "exchange": info.get("exchange"),
            "currency": info.get("currency"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
        }

    def fetch_quote(self, symbol):
        try:
            info = self._ticker(symbol).fast_info
            price = info["last_price"]
        except Exception as e:
            raise ProviderError(f"quote fetch failed for {symbol}: {e}") from e
        return {
            "symbol": symbol.upper(),
            "price": float(price),
            "currency": getattr(info, "currency", None) or "USD",
        }

    def fetch_dividends(self, symbol):
        try:
            series = self._ticker(symbol).dividends
        except Exception as e:
            raise ProviderError(f"dividend fetch failed for {symbol}: {e}") from e
        return [
            {"ex_date": idx.date().isoformat(), "amount": float(amount)}
            for idx, amount in series.items()
        ]

    def fetch_corporate_actions(self, symbol):
        """Split history from yfinance. `Ticker.splits` is a Series of ratios
        keyed by date (2.0 for a 2:1 split, 0.125 for a 1-for-8 reverse split),
        which maps to numerator=ratio / denominator=1. yfinance does not surface
        mergers or spinoffs, so those are recorded manually."""
        try:
            series = self._ticker(symbol).splits
        except Exception as e:
            raise ProviderError(f"split fetch failed for {symbol}: {e}") from e
        actions = []
        for idx, ratio in series.items():
            ratio = float(ratio)
            if ratio <= 0:
                continue
            actions.append({
                "ex_date": idx.date().isoformat(),
                "action_type": "split",
                "numerator": ratio,
                "denominator": 1.0,
            })
        return actions

    def fetch_options(self, symbol, expiration=None):
        ticker = self._ticker(symbol)
        try:
            expirations = list(ticker.options)
            if not expirations:
                return {"symbol": symbol.upper(), "expiration": None,
                        "expirations": [], "calls": [], "puts": []}
            exp = expiration or expirations[0]
            chain = ticker.option_chain(exp)
        except Exception as e:
            raise ProviderError(f"options fetch failed for {symbol}: {e}") from e

        return {
            "symbol": symbol.upper(),
            "expiration": exp,
            "expirations": expirations,
            "calls": self._contracts(chain.calls, "call", exp),
            "puts": self._contracts(chain.puts, "put", exp),
        }

    @staticmethod
    def _contracts(df, option_type, expiration):
        out = []
        for _, r in df.iterrows():
            out.append({
                "contract_symbol": r.get("contractSymbol"),
                "expiration": expiration,
                "option_type": option_type,
                "strike": float(r["strike"]),
                "last_price": float(r.get("lastPrice") or 0.0),
                "bid": float(r.get("bid") or 0.0),
                "ask": float(r.get("ask") or 0.0),
                "volume": int(r.get("volume") or 0),
                "open_interest": int(r.get("openInterest") or 0),
                "implied_vol": float(r.get("impliedVolatility") or 0.0),
                "in_the_money": bool(r.get("inTheMoney")),
            })
        return out
