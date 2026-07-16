"""Reference-data repository — the small lookup tables that classify assets.

Today this is just `asset_type` (Equity / ETF / Index / …), populated on demand
when metadata is downloaded. Sectors/countries/currencies are stored inline on
`assets` for now; they can graduate to their own reference tables here later.
"""

from data.database import DB_PATH, get_connection


def get_or_create_asset_type(name: str) -> int | None:
    """Return the id for an asset-type name, inserting it if new. Returns None
    for a blank name. Idempotent via the UNIQUE(name) index."""
    label = (name or "").strip()
    if not label:
        return None
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO asset_type (name) VALUES (?)", (label,)
        )
        row = conn.execute(
            "SELECT id FROM asset_type WHERE name = ?", (label,)
        ).fetchone()
        return row["id"]


def list_asset_types() -> list[dict]:
    if not DB_PATH.exists():
        return []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name FROM asset_type ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]
