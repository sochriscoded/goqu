"""Assets repository — the reference/market-data hub every other table points at.

Assets are created on demand as lightweight stubs (symbol + name) and later
enriched with company/sector metadata by the DataService (`get_metadata`).
"""

from data.database import DB_PATH, get_connection

# Columns `update_asset_metadata` is allowed to write (the enrichable profile).
_METADATA_COLUMNS = frozenset({
    "name", "asset_type_id", "exchange", "currency", "sector", "industry", "country",
})


def get_or_create_asset(symbol: str, name: str | None = None) -> int:
    """Return the asset id for a ticker, inserting a stub row if it doesn't exist."""
    ticker = symbol.strip().upper()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO assets (symbol, name) VALUES (?, ?)",
            (ticker, name or ticker),
        )
        row = conn.execute(
            "SELECT id FROM assets WHERE symbol = ?", (ticker,)
        ).fetchone()
        return row["id"]


def get_asset(asset_id: int) -> dict | None:
    if not DB_PATH.exists():
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        return dict(row) if row else None


def get_asset_by_symbol(symbol: str) -> dict | None:
    if not DB_PATH.exists():
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM assets WHERE symbol = ?", (symbol.strip().upper(),)
        ).fetchone()
        return dict(row) if row else None


def update_asset_metadata(asset_id: int, **fields) -> None:
    """Write enrichment fields (name, sector, industry, exchange, currency,
    country, asset_type_id) onto an asset. Unknown/empty keys are ignored; a call
    with nothing to set is a no-op."""
    cols = {k: v for k, v in fields.items() if k in _METADATA_COLUMNS and v is not None}
    if not cols:
        return
    assignments = ", ".join(f"{k} = ?" for k in cols)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE assets SET {assignments} WHERE id = ?",
            (*cols.values(), asset_id),
        )


def metadata_missing(asset_id: int) -> bool:
    """True if an asset is still an unenriched stub (name equals its symbol, or
    no sector recorded) — used to trigger a one-off metadata fetch."""
    asset = get_asset(asset_id)
    if asset is None:
        return False
    return asset["name"] == asset["symbol"] or not asset["sector"]
