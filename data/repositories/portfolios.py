"""Portfolio-data repository — portfolios, the transaction ledger, and the
derived holdings cache.

Transactions are the source of truth; `holdings` is a projection rebuilt by
`recompute_holdings` after any ledger change, using average-cost accounting
(ADR-002). `recompute_holdings` is the only thing that should ever write to
`holdings`.
"""

from data.database import DB_PATH, get_connection
from data.repositories import corporate_actions as ca
from data.repositories.assets import get_or_create_asset

BUY = "buy"
SELL = "sell"

_EPS = 1e-9  # share residue below this counts as a closed position
_UNSET = object()  # sentinel: "argument not provided" (distinct from None)


# --- Portfolios ---


def create_portfolio(name: str, description: str = "", benchmark_ticker: str = "") -> int:
    """Insert a portfolio row. If a benchmark ticker is given, inserts the asset stub first.
    Returns the new portfolio id.
    """
    with get_connection() as conn:
        benchmark_asset_id = None
        if benchmark_ticker:
            ticker = benchmark_ticker.strip().upper()
            conn.execute(
                "INSERT OR IGNORE INTO assets (symbol, name) VALUES (?, ?)",
                (ticker, ticker),
            )
            row = conn.execute(
                "SELECT id FROM assets WHERE symbol = ?", (ticker,)
            ).fetchone()
            if row:
                benchmark_asset_id = row["id"]

        cur = conn.execute(
            "INSERT INTO portfolio (name, description, benchmark_asset_id) VALUES (?, ?, ?)",
            (name, description, benchmark_asset_id),
        )
        return cur.lastrowid


def list_portfolios() -> list[dict]:
    if not DB_PATH.exists():
        return []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, description, created_at FROM portfolio ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]


def get_portfolio(portfolio_id: int) -> dict | None:
    if not DB_PATH.exists():
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM portfolio WHERE id = ?", (portfolio_id,)
        ).fetchone()
        return dict(row) if row else None


# --- Holdings (derived cache) ---


def get_holdings(portfolio_id: int) -> list[dict]:
    """Holdings joined with asset info and each asset's most recent price."""
    if not DB_PATH.exists():
        return []
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                h.id,
                a.symbol,
                a.name,
                a.sector,
                h.shares,
                h.cost_basis,
                h.purchase_price,
                (SELECT dp.adjusted_close
                   FROM daily_price dp
                  WHERE dp.asset_id = h.asset_id
                  ORDER BY dp.date DESC
                  LIMIT 1) AS last_price
              FROM holdings h
              JOIN assets a ON a.id = h.asset_id
             WHERE h.portfolio_id = ?
             ORDER BY a.symbol
            """,
            (portfolio_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def _position(positions: dict[int, dict], asset_id: int) -> dict:
    return positions.setdefault(asset_id, {"shares": 0.0, "cost_basis": 0.0})


def _apply_transaction(positions: dict[int, dict], txn: dict) -> None:
    """Apply one buy/sell to the running positions (average-cost)."""
    pos = _position(positions, txn["asset_id"])
    if txn["transaction_type"] == BUY:
        pos["shares"] += txn["shares"]
        pos["cost_basis"] += txn["shares"] * txn["price"] + (txn["fees"] or 0.0)
    elif txn["transaction_type"] == SELL and pos["shares"] > 0:
        avg_cost = pos["cost_basis"] / pos["shares"]
        sold = min(txn["shares"], pos["shares"])  # clamp over-sells (no shorts)
        pos["shares"] -= sold
        pos["cost_basis"] -= avg_cost * sold
        if pos["shares"] <= _EPS:  # fully closed — clear float residue
            pos["shares"] = 0.0
            pos["cost_basis"] = 0.0


def _apply_corporate_action(positions: dict[int, dict], action: dict) -> None:
    """Transform positions for one corporate action. No-op if the affected asset
    isn't held at the time. See data/repositories/corporate_actions.py for the
    accounting each type uses; total cost basis is conserved across all types.
    """
    pos = positions.get(action["asset_id"])
    if pos is None or pos["shares"] <= _EPS:
        return  # nothing held — action doesn't touch this portfolio

    kind = action["action_type"]
    if kind == ca.SPLIT:
        denom = action["denominator"] or 1.0
        ratio = (action["numerator"] or 0.0) / denom
        if ratio > 0:
            pos["shares"] *= ratio  # basis unchanged; per-share cost rescales

    elif kind in (ca.MERGER, ca.SYMBOL_CHANGE):
        target_id = action["target_asset_id"]
        if target_id:  # stock deal (or symbol change): convert into the target
            ratio = action["exchange_ratio"] or 0.0
            tgt = _position(positions, target_id)
            tgt["shares"] += pos["shares"] * ratio
            tgt["cost_basis"] += pos["cost_basis"]  # carry basis over
        # else: cash-only merger — position is realized (closed).
        pos["shares"] = 0.0
        pos["cost_basis"] = 0.0

    elif kind == ca.SPINOFF:
        target_id = action["target_asset_id"]
        ratio = action["exchange_ratio"] or 0.0
        if target_id and ratio > 0:
            moved = pos["cost_basis"] * (action["basis_allocation"] or 0.0)
            tgt = _position(positions, target_id)
            tgt["shares"] += pos["shares"] * ratio
            tgt["cost_basis"] += moved
            pos["cost_basis"] -= moved  # parent keeps its shares, less moved basis


def compute_positions(transactions: list[dict], actions: list[dict]) -> dict[int, dict]:
    """Pure position walk: fold transactions and corporate actions into
    {asset_id: {shares, cost_basis}}. Headless and DB-free so it's unit-testable
    (DESIGN principle 3).

    Events are processed in date order; on a shared date, corporate actions
    apply *before* transactions, matching the ex-date convention that trades on
    or after the effective date are already in post-action shares.
    """
    events: list[tuple] = []
    for t in transactions:
        events.append((t["date"], 1, t["id"], "txn", t))
    for a in actions:
        events.append((a["ex_date"], 0, a["id"], "action", a))
    events.sort(key=lambda e: (e[0], e[1], e[2]))

    positions: dict[int, dict] = {}
    for *_, kind, payload in events:
        if kind == "txn":
            _apply_transaction(positions, payload)
        else:
            _apply_corporate_action(positions, payload)
    return positions


def recompute_holdings(portfolio_id: int) -> None:
    """Rebuild the holdings cache for a portfolio from its transaction ledger and
    any corporate actions, using average-cost accounting. Holdings is derived
    state — this is the only thing that should ever write to it.

    Buys add shares and roll fees into cost basis. Sells reduce shares and remove
    cost basis at the current average cost. Splits/mergers/spinoffs/symbol
    changes transform positions on their effective date (see compute_positions).
    Positions that reach zero are dropped.
    """
    with get_connection() as conn:
        txns = [dict(t) for t in conn.execute(
            """
            SELECT id, date, asset_id, transaction_type, shares, price, fees
              FROM transactions
             WHERE portfolio_id = ?
             ORDER BY date ASC, id ASC
            """,
            (portfolio_id,),
        ).fetchall()]

    asset_ids = {t["asset_id"] for t in txns}
    actions = ca.get_actions_for_assets(asset_ids)
    positions = compute_positions(txns, actions)

    with get_connection() as conn:
        conn.execute("DELETE FROM holdings WHERE portfolio_id = ?", (portfolio_id,))
        for asset_id, pos in positions.items():
            if pos["shares"] <= _EPS:
                continue
            avg_price = pos["cost_basis"] / pos["shares"]
            conn.execute(
                """
                INSERT INTO holdings
                    (portfolio_id, asset_id, shares, cost_basis, purchase_price)
                VALUES (?, ?, ?, ?, ?)
                """,
                (portfolio_id, asset_id, pos["shares"], pos["cost_basis"], avg_price),
            )


def recompute_portfolios_holding_asset(asset_id: int) -> int:
    """Recompute holdings for every portfolio that has transacted `asset_id`.

    Called after new corporate actions land for an asset (e.g. a freshly-fetched
    split) so the derived holdings reflect the changed share count. Returns the
    number of portfolios recomputed.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT portfolio_id FROM transactions WHERE asset_id = ?",
            (asset_id,),
        ).fetchall()
    pids = [r["portfolio_id"] for r in rows]
    for pid in pids:
        recompute_holdings(pid)
    return len(pids)


# --- Transactions (source of truth) ---


def record_transaction(
    portfolio_id: int,
    symbol: str,
    date: str,
    transaction_type: str,
    shares: float,
    price: float,
    fees: float = 0.0,
    notes: str = "",
    account_id: int | None = None,
) -> int:
    """Record a single buy/sell. The ticker's asset row is created on demand."""
    asset_id = get_or_create_asset(symbol)
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO transactions
                (portfolio_id, asset_id, account_id, date, transaction_type, shares, price, fees, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (portfolio_id, asset_id, account_id, date, transaction_type, shares, price, fees, notes),
        )
        txn_id = cur.lastrowid
    recompute_holdings(portfolio_id)  # keep the holdings cache in sync
    return txn_id


def record_transactions_batch(portfolio_id: int, rows: list[dict],
                              account_id: int | None = None) -> int:
    """Record many transactions in one commit. Each row needs symbol, date,
    transaction_type, shares, price; fees and notes are optional. All rows are
    attributed to `account_id` (or a per-row 'account_id' if present). Returns the count.
    """
    count = 0
    with get_connection() as conn:
        for r in rows:
            ticker = r["symbol"].strip().upper()
            conn.execute(
                "INSERT OR IGNORE INTO assets (symbol, name) VALUES (?, ?)",
                (ticker, ticker),
            )
            asset_id = conn.execute(
                "SELECT id FROM assets WHERE symbol = ?", (ticker,)
            ).fetchone()["id"]
            conn.execute(
                """
                INSERT INTO transactions
                    (portfolio_id, asset_id, account_id, date, transaction_type, shares, price, fees, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    portfolio_id, asset_id, r.get("account_id", account_id), r["date"],
                    r["transaction_type"], r["shares"], r["price"],
                    r.get("fees", 0.0), r.get("notes", ""),
                ),
            )
            count += 1
    recompute_holdings(portfolio_id)  # single rebuild after the whole batch
    return count


def get_transactions(portfolio_id: int) -> list[dict]:
    """All transactions for a portfolio joined with the ticker, most recent first."""
    if not DB_PATH.exists():
        return []
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.date, t.transaction_type, t.shares, t.price, t.fees, t.notes,
                   a.symbol, a.name, t.account_id, ac.name AS account_name
              FROM transactions t
              JOIN assets a ON a.id = t.asset_id
         LEFT JOIN accounts ac ON ac.id = t.account_id
             WHERE t.portfolio_id = ?
             ORDER BY t.date DESC, t.id DESC
            """,
            (portfolio_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_transaction(txn_id: int) -> dict | None:
    """A single transaction joined with its ticker (for edit prefill)."""
    if not DB_PATH.exists():
        return None
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT t.id, t.portfolio_id, t.date, t.transaction_type, t.shares,
                   t.price, t.fees, t.notes, a.symbol, t.account_id
              FROM transactions t
              JOIN assets a ON a.id = t.asset_id
             WHERE t.id = ?
            """,
            (txn_id,),
        ).fetchone()
        return dict(row) if row else None


def delete_transaction(txn_id: int) -> int | None:
    """Delete a ledger row and rebuild the portfolio's holdings. Returns the
    affected portfolio_id, or None if the transaction didn't exist. Nothing
    references `transactions` by FK, so a delete is just a ledger edit (ADR-002)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT portfolio_id FROM transactions WHERE id = ?", (txn_id,)
        ).fetchone()
        if row is None:
            return None
        portfolio_id = row["portfolio_id"]
        conn.execute("DELETE FROM transactions WHERE id = ?", (txn_id,))
    recompute_holdings(portfolio_id)  # ledger changed — refresh the derived cache
    return portfolio_id


def update_transaction(
    txn_id: int,
    *,
    symbol: str | None = None,
    date: str | None = None,
    transaction_type: str | None = None,
    shares: float | None = None,
    price: float | None = None,
    fees: float | None = None,
    notes: str | None = None,
    account_id: int | None = _UNSET,
) -> int | None:
    """Edit any subset of a transaction's fields, then rebuild holdings. Returns
    the affected portfolio_id, or None if it didn't exist. Changing `symbol`
    re-points the row at that asset (created on demand). `account_id` uses a
    sentinel default so passing `None` explicitly *unassigns* the account."""
    asset_id = get_or_create_asset(symbol) if symbol is not None else None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT portfolio_id FROM transactions WHERE id = ?", (txn_id,)
        ).fetchone()
        if row is None:
            return None
        portfolio_id = row["portfolio_id"]

        fields: dict = {}
        if date is not None:
            fields["date"] = date
        if transaction_type is not None:
            fields["transaction_type"] = transaction_type
        if shares is not None:
            fields["shares"] = shares
        if price is not None:
            fields["price"] = price
        if fees is not None:
            fields["fees"] = fees
        if notes is not None:
            fields["notes"] = notes
        if asset_id is not None:
            fields["asset_id"] = asset_id
        if account_id is not _UNSET:
            fields["account_id"] = account_id

        if fields:
            assignments = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE transactions SET {assignments} WHERE id = ?",
                (*fields.values(), txn_id),
            )
    recompute_holdings(portfolio_id)
    return portfolio_id
