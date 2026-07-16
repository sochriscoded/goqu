"""Cache-metadata repository — the freshness ledger for the persistent (DB)
cache tier (`data_cache_meta`).

Keyed by an opaque string (e.g. 'daily:AAPL', 'options:AAPL:2026-07-18'); see
`data/cache.py` for the TTL policy that consumes these ages.
"""

from data.database import DB_PATH, get_connection


def cache_mark(cache_key: str) -> None:
    """Record that `cache_key` was just fetched (freshness for the DB cache tier)."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO data_cache_meta (cache_key, fetched_at) "
            "VALUES (?, datetime('now')) "
            "ON CONFLICT(cache_key) DO UPDATE SET fetched_at=datetime('now')",
            (cache_key,),
        )


def cache_age_seconds(cache_key: str) -> float | None:
    """Seconds since `cache_key` was last fetched, or None if never."""
    if not DB_PATH.exists():
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT (julianday('now') - julianday(fetched_at)) * 86400.0 AS age "
            "FROM data_cache_meta WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        return row["age"] if row else None
