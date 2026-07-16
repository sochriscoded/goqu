"""DataService — the single entry point the app uses to get market data.

It ties together:
  * providers (data/providers/)     — where data comes from, per type
  * caching   (data/cache.py + DB)  — so we don't pay for the same call twice
  * the event bus (data/events.py)  — so the UI stays responsive to changes

Read paths (get_*) are cache-first: they serve fresh cached/persisted data and
only hit a provider when data is missing or stale, then persist the result and
announce it on the bus. Every fetch can also be run in the background via
run_async / refresh_symbol_async so the UI thread never blocks.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import config as app_config
from data import repositories as db
from data.cache import TTLCache, MEMORY_TTL, PERSIST_TTL
from data.events import event_bus
from data.providers import build_provider
from data.providers.base import DataProvider, DataType, ProviderError
from data.providers.yfinance_provider import YFinanceProvider
from data.validation import clean_metadata, validate_daily_rows

logger = logging.getLogger(__name__)


class DataService:
    def __init__(self, bus=None, providers=None, routes=None, max_workers=4):
        self._bus = bus if bus is not None else event_bus()
        self._cache = TTLCache()
        self._pool = ThreadPoolExecutor(max_workers=max_workers,
                                        thread_name_prefix="goqu-data")
        self._providers: dict[str, DataProvider] = {}

        if providers is not None:
            for p in providers:
                self.register_provider(p)
        else:
            self._load_providers_from_config()

        # routes: DataType -> provider name
        self._routes: dict[DataType, str] = routes or self._routes_from_config()

    # ---- provider registry / routing ----

    def register_provider(self, provider: DataProvider) -> None:
        self._providers[provider.name] = provider

    def _load_providers_from_config(self) -> None:
        # Always have yfinance available (free, no key); add any others named in
        # config routes/source so overrides can resolve.
        self.register_provider(
            YFinanceProvider(app_config.get_provider_config("yfinance"))
        )
        wanted = {app_config.load_datasource_config().get("source", "yfinance")}
        wanted.update((app_config.get_routes()).values())
        for name in wanted:
            if name and name not in self._providers:
                provider = build_provider(name, app_config.get_provider_config(name))
                if provider is not None:
                    self.register_provider(provider)

    def _routes_from_config(self) -> dict[DataType, str]:
        cfg_routes = app_config.get_routes()  # str -> str
        return {dt: cfg_routes.get(dt.value, "yfinance") for dt in DataType}

    def _provider_for(self, data_type: DataType) -> DataProvider:
        """Resolve the configured provider for a data type, falling back to any
        registered provider that supports it (preferring yfinance)."""
        name = self._routes.get(data_type)
        provider = self._providers.get(name)
        if provider is not None and provider.supports(data_type):
            return provider
        # Fallback: first capable provider, yfinance first.
        ordered = sorted(self._providers.values(),
                         key=lambda p: 0 if p.name == "yfinance" else 1)
        for p in ordered:
            if p.supports(data_type):
                return p
        raise ProviderError(f"No provider available for {data_type.value}")

    # ---- read paths (cache-first) ----

    def get_daily(self, symbol, start=None, end=None, force=False) -> list[dict]:
        symbol = symbol.upper()
        asset_id = db.get_or_create_asset(symbol)
        self._maybe_enrich_metadata(symbol, asset_id)
        key = f"daily:{symbol}"
        if not force and self._persist_fresh(key, DataType.DAILY):
            cached = db.get_daily_prices(asset_id, start, end)
            if cached:
                logger.debug("daily %s served from cache (%d rows)", symbol, len(cached))
                return cached
        try:
            provider = self._provider_for(DataType.DAILY)
            logger.info("Fetching daily %s via %s", symbol, provider.name)
            rows = provider.fetch_daily(symbol, start, end)
        except ProviderError as e:
            logger.warning("Daily fetch failed for %s: %s", symbol, e)
            self._bus.data_error.emit(key, str(e))
            return db.get_daily_prices(asset_id, start, end)  # serve stale if any
        clean, issues = validate_daily_rows(rows)
        if issues:
            logger.warning("Dropped %d invalid daily row(s) for %s (e.g. %s)",
                           len(issues), symbol, issues[0][1])
        db.upsert_daily_prices(asset_id, clean)
        db.cache_mark(key)
        logger.debug("Stored %d daily rows for %s", len(clean), symbol)
        self._bus.daily_updated.emit(symbol)
        return db.get_daily_prices(asset_id, start, end)

    def get_quote(self, symbol, force=False) -> dict | None:
        symbol = symbol.upper()
        key = ("quote", symbol)
        if not force:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
        try:
            provider = self._provider_for(DataType.QUOTE)
            logger.debug("Fetching quote %s via %s", symbol, provider.name)
            quote = provider.fetch_quote(symbol)
        except ProviderError as e:
            logger.warning("Quote fetch failed for %s: %s", symbol, e)
            self._bus.data_error.emit(f"quote:{symbol}", str(e))
            return self._cache.get(key)  # possibly stale/None
        self._cache.set(key, quote, MEMORY_TTL[DataType.QUOTE])
        price = quote.get("price")
        if price is not None:
            self._bus.quote_updated.emit(symbol, float(price))
        return quote

    def get_dividends(self, symbol, force=False) -> list[dict]:
        symbol = symbol.upper()
        asset_id = db.get_or_create_asset(symbol)
        key = f"dividends:{symbol}"
        if not force and self._persist_fresh(key, DataType.DIVIDENDS):
            logger.debug("dividends %s served from cache", symbol)
            return db.get_dividends(asset_id)
        try:
            provider = self._provider_for(DataType.DIVIDENDS)
            logger.info("Fetching dividends %s via %s", symbol, provider.name)
            events = provider.fetch_dividends(symbol)
        except ProviderError as e:
            logger.warning("Dividend fetch failed for %s: %s", symbol, e)
            self._bus.data_error.emit(key, str(e))
            return db.get_dividends(asset_id)
        for ev in events:
            db.record_dividend(asset_id, ev["ex_date"], ev["amount"])
        db.cache_mark(key)
        self._bus.dividends_updated.emit(symbol)
        return db.get_dividends(asset_id)

    def get_options(self, symbol, expiration=None, force=False) -> dict:
        symbol = symbol.upper()
        asset_id = db.get_or_create_asset(symbol)
        key = f"options:{symbol}:{expiration or 'nearest'}"
        if not force and self._persist_fresh(key, DataType.OPTIONS):
            cached = db.get_option_chain(asset_id, expiration)
            if cached["calls"] or cached["puts"]:
                logger.debug("options %s served from cache", symbol)
                return cached
        try:
            provider = self._provider_for(DataType.OPTIONS)
            logger.info("Fetching options %s via %s", symbol, provider.name)
            chain = provider.fetch_options(symbol, expiration)
        except ProviderError as e:
            logger.warning("Options fetch failed for %s: %s", symbol, e)
            self._bus.data_error.emit(key, str(e))
            return db.get_option_chain(asset_id, expiration)
        db.upsert_option_chain(asset_id, chain)
        db.cache_mark(key)
        self._bus.options_updated.emit(symbol)
        return db.get_option_chain(asset_id, chain.get("expiration", expiration))

    def get_corporate_actions(self, symbol, force=False) -> list[dict]:
        """Cache-first corporate actions (splits, and any merger/spinoff rows
        already recorded). Newly-fetched splits change share counts, so after
        ingesting them we rebuild the holdings of every portfolio that holds the
        asset before announcing the change."""
        symbol = symbol.upper()
        asset_id = db.get_or_create_asset(symbol)
        key = f"corporate_actions:{symbol}"
        if not force and self._persist_fresh(key, DataType.CORPORATE_ACTIONS):
            logger.debug("corporate actions %s served from cache", symbol)
            return db.get_corporate_actions(asset_id)
        try:
            provider = self._provider_for(DataType.CORPORATE_ACTIONS)
            logger.info("Fetching corporate actions %s via %s", symbol, provider.name)
            events = provider.fetch_corporate_actions(symbol)
        except ProviderError as e:
            logger.warning("Corporate-action fetch failed for %s: %s", symbol, e)
            self._bus.data_error.emit(key, str(e))
            return db.get_corporate_actions(asset_id)
        new_count = 0
        for ev in events:
            rid = db.record_corporate_action(
                asset_id,
                ev.get("action_type", "split"),
                ev["ex_date"],
                numerator=ev.get("numerator"),
                denominator=ev.get("denominator", 1.0),
                source=provider.name,
            )
            if rid is not None:
                new_count += 1
        db.cache_mark(key)
        if new_count:
            affected = db.recompute_portfolios_holding_asset(asset_id)
            logger.info("Applied %d new corporate action(s) for %s; recomputed %d portfolio(s)",
                        new_count, symbol, affected)
        self._bus.corporate_actions_updated.emit(symbol)
        return db.get_corporate_actions(asset_id)

    def get_metadata(self, symbol, force=False) -> dict | None:
        """Cache-first company/sector metadata. Enriches the asset row (name,
        sector, industry, exchange, currency, country, asset type) and returns
        it. Profiles change rarely, so the persistent TTL is long."""
        symbol = symbol.upper()
        asset_id = db.get_or_create_asset(symbol)
        key = f"metadata:{symbol}"
        if not force and self._persist_fresh(key, DataType.METADATA):
            logger.debug("metadata %s served from cache", symbol)
            return db.get_asset(asset_id)
        try:
            provider = self._provider_for(DataType.METADATA)
            logger.info("Fetching metadata %s via %s", symbol, provider.name)
            raw = provider.fetch_metadata(symbol)
        except ProviderError as e:
            logger.warning("Metadata fetch failed for %s: %s", symbol, e)
            self._bus.data_error.emit(key, str(e))
            return db.get_asset(asset_id)
        fields = clean_metadata(raw)
        asset_type = fields.pop("asset_type", None)
        if asset_type:
            fields["asset_type_id"] = db.get_or_create_asset_type(asset_type)
        db.update_asset_metadata(asset_id, **fields)
        db.cache_mark(key)
        logger.debug("Enriched %s metadata: %s", symbol, ", ".join(fields) or "none")
        self._bus.metadata_updated.emit(symbol)
        return db.get_asset(asset_id)

    def backfill_daily(self, symbol, start=None, end=None) -> int:
        """Detect missing date ranges in the stored daily history and fetch only
        those from the provider — a cost-minimizing complement to `get_daily`
        (Principle 4). Rows are validated before upsert. Returns bars added."""
        symbol = symbol.upper()
        asset_id = db.get_or_create_asset(symbol)
        ranges = db.daily_gaps(asset_id, start, end)
        if not ranges:
            logger.debug("No daily gaps for %s in [%s, %s]", symbol, start, end)
            return 0
        try:
            provider = self._provider_for(DataType.DAILY)
        except ProviderError as e:
            self._bus.data_error.emit(f"daily:{symbol}", str(e))
            return 0
        filled = 0
        for gap_start, gap_end in ranges:
            # yfinance's `end` is exclusive; extend a day so gap_end is included.
            fetch_end = (date.fromisoformat(gap_end) + timedelta(days=1)).isoformat()
            try:
                logger.info("Backfilling daily %s %s→%s via %s",
                            symbol, gap_start, gap_end, provider.name)
                rows = provider.fetch_daily(symbol, gap_start, fetch_end)
            except ProviderError as e:
                logger.warning("Backfill fetch failed for %s %s→%s: %s",
                               symbol, gap_start, gap_end, e)
                self._bus.data_error.emit(f"daily:{symbol}", str(e))
                continue
            clean, issues = validate_daily_rows(rows)
            if issues:
                logger.warning("Dropped %d invalid backfill row(s) for %s",
                               len(issues), symbol)
            # Provider may return extra dates; keep only the requested gap.
            clean = [r for r in clean if gap_start <= r["date"] <= gap_end]
            filled += db.upsert_daily_prices(asset_id, clean)
        if filled:
            self._bus.daily_updated.emit(symbol)
            logger.info("Backfilled %d daily bar(s) for %s", filled, symbol)
        return filled

    def _maybe_enrich_metadata(self, symbol, asset_id):
        """Fire a one-off background metadata fetch for a not-yet-enriched asset.
        Guarded by the metadata cache marker so it runs at most once per TTL."""
        if db.cache_age_seconds(f"metadata:{symbol}") is not None:
            return
        if not db.metadata_missing(asset_id):
            return
        self.run_async(self.get_metadata, symbol)

    # ---- async ----

    def run_async(self, fn, *args, **kwargs):
        """Run a get_* (or any callable) on the background pool. Errors are
        surfaced on the bus rather than raised into a dead worker thread."""
        return self._pool.submit(self._safe_call, fn, *args, **kwargs)

    def _safe_call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # never let a worker die silently
            name = getattr(fn, "__name__", "async")
            logger.exception("Background task %s failed", name)
            self._bus.data_error.emit(name, str(e))

    def refresh_symbol_async(self, symbol):
        """Kick off a background refresh of the common data types for a symbol.
        Each completion emits on the bus, so open views update as data lands."""
        self.run_async(self.get_quote, symbol, force=True)
        self.run_async(self.get_daily, symbol, force=True)
        # Refresh splits too — a new one silently corrupts share counts otherwise.
        self.run_async(self.get_corporate_actions, symbol, force=True)
        # Enrich company/sector metadata (respects its long TTL — not forced).
        self.run_async(self.get_metadata, symbol)

    def shutdown(self):
        self._pool.shutdown(wait=False)

    # ---- helpers ----

    def _persist_fresh(self, key: str, data_type: DataType) -> bool:
        age = db.cache_age_seconds(key)
        return age is not None and age < PERSIST_TTL[data_type]


_service: DataService | None = None


def data_service() -> DataService:
    """Process-wide DataService (created lazily)."""
    global _service
    if _service is None:
        _service = DataService()
    return _service
