"""Accounts repository — brokerage accounts within a portfolio.

An account groups transactions and cash movements (e.g. "Fidelity Taxable",
"Vanguard Roth IRA"). It's an optional *dimension* on the ledger: holdings and
the cash balance stay portfolio-aggregated, while each trade/cash row may be
attributed to an account for filtering and record-keeping. Deleting an account
un-attributes its rows (sets `account_id` NULL) rather than losing them.
"""

from data.database import DB_PATH, get_connection

# account_type value -> display label.
ACCOUNT_TYPES = {
    "taxable": "Taxable",
    "traditional_ira": "Traditional IRA",
    "roth_ira": "Roth IRA",
    "401k": "401(k)",
    "hsa": "HSA",
    "brokerage": "Brokerage",
    "other": "Other",
}


def create_account(
    portfolio_id: int,
    name: str,
    account_type: str = "taxable",
    institution: str = "",
) -> int:
    """Create an account under a portfolio. Names are unique per portfolio."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO accounts (portfolio_id, name, account_type, institution) "
            "VALUES (?, ?, ?, ?)",
            (portfolio_id, name.strip(), account_type, institution.strip()),
        )
        return cur.lastrowid


def list_accounts(portfolio_id: int) -> list[dict]:
    """Accounts for a portfolio, ordered by name."""
    if not DB_PATH.exists():
        return []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, portfolio_id, name, account_type, institution, created_at "
            "FROM accounts WHERE portfolio_id = ? ORDER BY name",
            (portfolio_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_account(account_id: int) -> dict | None:
    if not DB_PATH.exists():
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        return dict(row) if row else None


def update_account(
    account_id: int,
    *,
    name: str | None = None,
    account_type: str | None = None,
    institution: str | None = None,
) -> None:
    """Edit any subset of an account's fields."""
    fields: dict = {}
    if name is not None:
        fields["name"] = name.strip()
    if account_type is not None:
        fields["account_type"] = account_type
    if institution is not None:
        fields["institution"] = institution.strip()
    if not fields:
        return
    assignments = ", ".join(f"{k} = ?" for k in fields)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE accounts SET {assignments} WHERE id = ?",
            (*fields.values(), account_id),
        )


def delete_account(account_id: int) -> int | None:
    """Delete an account, un-attributing (not deleting) its ledger rows. Returns
    the affected portfolio_id, or None if the account didn't exist."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT portfolio_id FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row is None:
            return None
        # Null the references first so the FK (RESTRICT) doesn't block the delete.
        conn.execute(
            "UPDATE transactions SET account_id = NULL WHERE account_id = ?", (account_id,)
        )
        conn.execute(
            "UPDATE cash_transactions SET account_id = NULL WHERE account_id = ?", (account_id,)
        )
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        return row["portfolio_id"]
