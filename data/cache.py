"""Two-tier caching to minimize (paid) API calls.

Tier 1 — this module: a thread-safe in-memory TTL cache for volatile data
(quotes, option chains) so repeated reads within a short window hit memory, not
the network.

Tier 2 — the database: historical data (daily bars, dividends, option
snapshots) is persisted and reused across sessions. The `data_cache_meta` table
records when each key was last fetched so the DataService can apply a TTL to
persisted data too. See data/database.py (cache_mark / cache_age_seconds).
"""
from __future__ import annotations

import threading
import time

from data.providers.base import DataType

# TTLs (seconds) for the in-memory tier — tuned to how fast each type moves.
MEMORY_TTL = {
    DataType.QUOTE: 15,       # near-real-time
    DataType.OPTIONS: 600,    # 10 minutes
    DataType.DAILY: 3600,     # 1 hour (also persisted in DB)
    DataType.DIVIDENDS: 86400,
    DataType.CORPORATE_ACTIONS: 86400,
    DataType.METADATA: 7 * 86400,
}

# TTLs (seconds) for the persistent tier — how long DB data is "fresh" before
# we re-fetch from the provider.
PERSIST_TTL = {
    DataType.DAILY: 12 * 3600,       # intraday-stale is fine for daily bars
    DataType.DIVIDENDS: 24 * 3600,
    DataType.OPTIONS: 10 * 60,
    DataType.CORPORATE_ACTIONS: 24 * 3600,
    DataType.METADATA: 30 * 86400,   # company profiles change rarely
}


class TTLCache:
    """Simple thread-safe key -> (value, expiry) store."""

    def __init__(self):
        self._store: dict = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            value, expires_at = item
            if expires_at < time.monotonic():
                self._store.pop(key, None)
                return None
            return value

    def set(self, key, value, ttl_seconds: float):
        with self._lock:
            self._store[key] = (value, time.monotonic() + ttl_seconds)

    def invalidate(self, key=None):
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)
