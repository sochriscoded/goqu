"""Cash repository — cash movements and the *derived* cash balance.

Like holdings, the cash balance is never stored; it's derived (ADR-002) from
three flows:

1. explicit cash movements (this table): deposits, withdrawals, interest, fees;
2. trade cash flows: a buy spends `shares*price + fees`, a sell receives
   `shares*price - fees`;
3. non-reinvested dividend income (DRIP dividends were spent on shares, so they
   don't add to cash).

`amount` on a `cash_transactions` row is a **signed** delta (deposit/interest
positive; withdrawal/fee negative). `signed_amount()` turns a user-entered
magnitude + type into that signed value.
"""

from data.database import DB_PATH, get_connection

DEPOSIT = "deposit"
WITHDRAWAL = "withdrawal"
INTEREST = "interest"
FEE = "fee"
ADJUSTMENT = "adjustment"
CASH_TYPES = (DEPOSIT, WITHDRAWAL, INTEREST, FEE, ADJUSTMENT)

# Canonical sign per type; 'adjustment' keeps whatever sign it is given.
_SIGN = {DEPOSIT: 1, INTEREST: 1, WITHDRAWAL: -1, FEE: -1}


def signed_amount(cash_type: str, magnitude: float) -> float:
    """Turn a (usually positive) magnitude into a signed cash delta for `cash_type`.
    An 'adjustment' passes through unchanged so it can correct in either direction."""
    if cash_type in _SIGN:
        return _SIGN[cash_type] * abs(magnitude)
    return magnitude


def record_cash_transaction(
    portfolio_id: int, date: str, cash_type: str, amount: float, notes: str = "",
    account_id: int | None = None,
) -> int:
    """Insert a cash movement. `amount` is stored as a signed delta — derive it
    from a magnitude with `signed_amount(cash_type, magnitude)`."""
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO cash_transactions (portfolio_id, account_id, date, cash_type, amount, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (portfolio_id, account_id, date, cash_type, amount, notes),
        )
        return cur.lastrowid


def get_cash_transactions(portfolio_id: int) -> list[dict]:
    """Cash movements for a portfolio, most recent first (with account name)."""
    if not DB_PATH.exists():
        return []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT c.id, c.date, c.cash_type, c.amount, c.notes, "
            "       c.account_id, ac.name AS account_name "
            "  FROM cash_transactions c "
            "  LEFT JOIN accounts ac ON ac.id = c.account_id "
            " WHERE c.portfolio_id = ? ORDER BY c.date DESC, c.id DESC",
            (portfolio_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_cash_transaction(cash_id: int) -> int | None:
    """Delete a cash movement. Returns its portfolio_id, or None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT portfolio_id FROM cash_transactions WHERE id = ?", (cash_id,)
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM cash_transactions WHERE id = ?", (cash_id,))
        return row["portfolio_id"]


def get_cash_summary(portfolio_id: int) -> dict:
    """The derived cash balance and its component flows.

    balance = explicit cash movements + trade cash flows + non-reinvested
    dividend income. Deposits/withdrawals are the positive/negative halves of the
    explicit movements, for display.
    """
    empty = {
        "balance": 0.0, "cash_flows": 0.0, "trade_flows": 0.0,
        "dividend_cash": 0.0, "deposits": 0.0, "withdrawals": 0.0,
    }
    if not DB_PATH.exists():
        return empty
    with get_connection() as conn:
        cash = conn.execute(
            """
            SELECT
                COALESCE(SUM(amount), 0) AS total,
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS deposits,
                COALESCE(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 0) AS withdrawals
              FROM cash_transactions WHERE portfolio_id = ?
            """,
            (portfolio_id,),
        ).fetchone()
        trade = conn.execute(
            """
            SELECT COALESCE(SUM(
                CASE WHEN transaction_type = 'sell' THEN shares * price - fees
                     ELSE -(shares * price + fees) END), 0) AS flow
              FROM transactions WHERE portfolio_id = ?
            """,
            (portfolio_id,),
        ).fetchone()
        div = conn.execute(
            "SELECT COALESCE(SUM(net_amount), 0) AS cash FROM dividend_income "
            "WHERE portfolio_id = ? AND is_reinvested = 0",
            (portfolio_id,),
        ).fetchone()

    cash_flows, trade_flows, dividend_cash = cash["total"], trade["flow"], div["cash"]
    return {
        "balance": cash_flows + trade_flows + dividend_cash,
        "cash_flows": cash_flows,
        "trade_flows": trade_flows,
        "dividend_cash": dividend_cash,
        "deposits": cash["deposits"],
        "withdrawals": cash["withdrawals"],
    }


def get_cash_balance(portfolio_id: int) -> float:
    return get_cash_summary(portfolio_id)["balance"]
