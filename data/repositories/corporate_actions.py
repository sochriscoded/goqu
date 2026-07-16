"""Corporate-actions repository — events that change share ownership.

Four action types, all stored in one table and folded into
`portfolios.recompute_holdings` in ex_date order:

- `split`         — ratio numerator/denominator (2:1 → 2/1; reverse 1:8 → 1/8).
                    Refetchable from providers; recorded idempotently.
- `merger`        — the held asset converts into `target_asset_id` at
                    `exchange_ratio` shares each (and/or `cash_per_share`). A
                    cash-only merger (no target) closes the position.
- `spinoff`       — the held asset stays; `exchange_ratio` shares of
                    `target_asset_id` are received, and `basis_allocation`
                    (0..1) of the parent's cost basis moves with them.
- `symbol_change` — a 1:1 conversion into `target_asset_id`, basis carried over.

Splits are the only type any provider feeds today; the others have no reliable
source and are entered manually (source-of-truth — see DESIGN §10).
"""

from data.database import DB_PATH, get_connection

SPLIT = "split"
MERGER = "merger"
SPINOFF = "spinoff"
SYMBOL_CHANGE = "symbol_change"

ACTION_TYPES = frozenset({SPLIT, MERGER, SPINOFF, SYMBOL_CHANGE})


def record_corporate_action(
    asset_id: int,
    action_type: str,
    ex_date: str,
    *,
    numerator: float | None = None,
    denominator: float | None = None,
    target_asset_id: int | None = None,
    exchange_ratio: float | None = None,
    cash_per_share: float | None = None,
    basis_allocation: float | None = None,
    source: str = "manual",
    notes: str = "",
) -> int | None:
    """Insert a corporate action. Idempotent on (asset_id, ex_date, action_type):
    a duplicate is ignored and returns None; otherwise returns the new row id.
    """
    if action_type not in ACTION_TYPES:
        raise ValueError(f"unknown corporate action type: {action_type!r}")
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO corporate_actions
                (asset_id, action_type, ex_date, numerator, denominator,
                 target_asset_id, exchange_ratio, cash_per_share, basis_allocation,
                 source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (asset_id, action_type, ex_date, numerator, denominator,
             target_asset_id, exchange_ratio, cash_per_share, basis_allocation,
             source, notes),
        )
        return cur.lastrowid if cur.rowcount else None


def record_split(
    asset_id: int,
    ex_date: str,
    numerator: float,
    denominator: float = 1.0,
    source: str = "manual",
    notes: str = "",
) -> int | None:
    """Record a stock split. `numerator:denominator` = new shares per old
    (2:1 → 2, 1; a 1-for-8 reverse split → 1, 8)."""
    return record_corporate_action(
        asset_id, SPLIT, ex_date,
        numerator=numerator, denominator=denominator, source=source, notes=notes,
    )


def record_merger(
    asset_id: int,
    ex_date: str,
    target_asset_id: int | None = None,
    exchange_ratio: float = 0.0,
    cash_per_share: float = 0.0,
    source: str = "manual",
    notes: str = "",
) -> int | None:
    """Record a merger/acquisition. Stock deal: give `target_asset_id` +
    `exchange_ratio` (target shares per held share). Cash deal: leave
    `target_asset_id` None and set `cash_per_share` (position is closed)."""
    return record_corporate_action(
        asset_id, MERGER, ex_date,
        target_asset_id=target_asset_id, exchange_ratio=exchange_ratio,
        cash_per_share=cash_per_share, source=source, notes=notes,
    )


def record_spinoff(
    asset_id: int,
    ex_date: str,
    target_asset_id: int,
    exchange_ratio: float,
    basis_allocation: float = 0.0,
    source: str = "manual",
    notes: str = "",
) -> int | None:
    """Record a spinoff: keep the parent, receive `exchange_ratio` shares of
    `target_asset_id` per held share, moving `basis_allocation` (0..1) of the
    parent's cost basis to the new shares."""
    return record_corporate_action(
        asset_id, SPINOFF, ex_date,
        target_asset_id=target_asset_id, exchange_ratio=exchange_ratio,
        basis_allocation=basis_allocation, source=source, notes=notes,
    )


def record_symbol_change(
    asset_id: int,
    ex_date: str,
    target_asset_id: int,
    source: str = "manual",
    notes: str = "",
) -> int | None:
    """Record a ticker/symbol change as a 1:1 conversion into `target_asset_id`
    with full cost-basis carryover."""
    return record_corporate_action(
        asset_id, SYMBOL_CHANGE, ex_date,
        target_asset_id=target_asset_id, exchange_ratio=1.0,
        source=source, notes=notes,
    )


def get_corporate_actions(asset_id: int) -> list[dict]:
    """All corporate actions affecting an asset, oldest first (application order)."""
    if not DB_PATH.exists():
        return []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM corporate_actions WHERE asset_id = ? "
            "ORDER BY ex_date ASC, id ASC",
            (asset_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_actions_for_assets(asset_ids) -> list[dict]:
    """All corporate actions affecting any of `asset_ids`, oldest first.

    Used by recompute_holdings to fold actions into the position walk. Returns
    an empty list for an empty input (no query)."""
    ids = list(asset_ids)
    if not ids or not DB_PATH.exists():
        return []
    placeholders = ", ".join("?" * len(ids))
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM corporate_actions WHERE asset_id IN ({placeholders}) "
            f"ORDER BY ex_date ASC, id ASC",
            ids,
        ).fetchall()
        return [dict(r) for r in rows]


def list_corporate_actions() -> list[dict]:
    """Every corporate action joined with the affected/target ticker symbols
    (for display / auditing)."""
    if not DB_PATH.exists():
        return []
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ca.*,
                   a.symbol  AS symbol,
                   t.symbol  AS target_symbol
              FROM corporate_actions ca
              JOIN assets a ON a.id = ca.asset_id
              LEFT JOIN assets t ON t.id = ca.target_asset_id
             ORDER BY ca.ex_date DESC, ca.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
