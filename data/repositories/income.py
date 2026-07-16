"""Income-sleeve repository — declared dividends, per-asset income profile, and
realized dividend income received by a portfolio.

The sleeve straddles two domains by design (DESIGN §6.2): `dividends` and
`asset_income_profile` are market data (declared events / snapshots), while
`dividend_income` is portfolio data (cash actually received, with DRIP + tax).
They're grouped here because they read and write as one first-class feature.
"""

from data.database import DB_PATH, get_connection


# --- Declared dividend events (market data) ---


def record_dividend(
    asset_id: int,
    ex_date: str,
    amount: float,
    pay_date: str | None = None,
    record_date: str | None = None,
    frequency: str = "quarterly",
    dividend_type: str = "ordinary",
    currency: str = "USD",
) -> int | None:
    """Insert a declared per-share dividend event. Duplicate (asset, ex_date) is ignored.
    Returns the new row id, or None if it was a duplicate.
    """
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO dividends
                (asset_id, ex_date, record_date, pay_date, amount,
                 frequency, dividend_type, currency)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (asset_id, ex_date, record_date, pay_date, amount,
             frequency, dividend_type, currency),
        )
        return cur.lastrowid if cur.rowcount else None


def get_dividends(asset_id: int) -> list[dict]:
    """All declared dividend events for an asset, most recent first."""
    if not DB_PATH.exists():
        return []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM dividends WHERE asset_id = ? ORDER BY ex_date DESC",
            (asset_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# --- Per-asset income profile (market data snapshot) ---


def upsert_income_profile(asset_id: int, **fields) -> None:
    """Insert or update the income snapshot for an asset. Accepts any of:
    dividend_yield, annual_dividend_rate, payout_frequency, payout_ratio,
    ex_dividend_date, five_year_avg_yield, dividend_growth_5y.
    """
    allowed = {
        "dividend_yield", "annual_dividend_rate", "payout_frequency",
        "payout_ratio", "ex_dividend_date", "five_year_avg_yield",
        "dividend_growth_5y",
    }
    cols = {k: v for k, v in fields.items() if k in allowed}
    keys = ["asset_id", *cols.keys(), "updated_at"]
    placeholders = ", ".join(["?"] * len(cols) + ["?", "datetime('now')"])
    updates = ", ".join(f"{k} = excluded.{k}" for k in cols)
    updates = f"{updates}, updated_at = datetime('now')" if updates else "updated_at = datetime('now')"
    with get_connection() as conn:
        conn.execute(
            f"""
            INSERT INTO asset_income_profile ({', '.join(keys)})
            VALUES ({placeholders})
            ON CONFLICT(asset_id) DO UPDATE SET {updates}
            """,
            (asset_id, *cols.values()),
        )


def get_income_profile(asset_id: int) -> dict | None:
    if not DB_PATH.exists():
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM asset_income_profile WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        return dict(row) if row else None


# --- Realized income received (portfolio data) ---


def record_dividend_income(
    portfolio_id: int,
    asset_id: int,
    pay_date: str,
    shares_held: float,
    amount_per_share: float,
    dividend_id: int | None = None,
    tax_withheld: float = 0.0,
    is_reinvested: bool = False,
    currency: str = "USD",
) -> int:
    """Record dividend cash received by a portfolio. Gross/net are derived."""
    gross = shares_held * amount_per_share
    net = gross - tax_withheld
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO dividend_income
                (portfolio_id, asset_id, dividend_id, pay_date, shares_held,
                 amount_per_share, gross_amount, tax_withheld, net_amount,
                 is_reinvested, currency)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (portfolio_id, asset_id, dividend_id, pay_date, shares_held,
             amount_per_share, gross, tax_withheld, net, int(is_reinvested), currency),
        )
        return cur.lastrowid


def get_dividend_income(portfolio_id: int) -> list[dict]:
    """Realized dividend payments for a portfolio joined with asset info."""
    if not DB_PATH.exists():
        return []
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT di.*, a.symbol, a.name
              FROM dividend_income di
              JOIN assets a ON a.id = di.asset_id
             WHERE di.portfolio_id = ?
             ORDER BY di.pay_date DESC
            """,
            (portfolio_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_income_summary(portfolio_id: int) -> dict:
    """Income-sleeve totals: all-time and trailing-twelve-month net income."""
    empty = {"total_income": 0.0, "ttm_income": 0.0, "payment_count": 0}
    if not DB_PATH.exists():
        return empty
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(net_amount), 0) AS total_income,
                COALESCE(SUM(CASE WHEN pay_date >= date('now', '-1 year')
                                  THEN net_amount ELSE 0 END), 0) AS ttm_income,
                COUNT(*) AS payment_count
              FROM dividend_income
             WHERE portfolio_id = ?
            """,
            (portfolio_id,),
        ).fetchone()
        return dict(row)
