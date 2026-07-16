"""Database core: connection factory, schema, and migrations.

This module owns the low-level storage concerns shared by every domain:
opening a tuned connection, creating the schema, and running the one-off
migrations that `CREATE TABLE IF NOT EXISTS` can't express.

Per-domain SQL helpers (the repository layer) live in `data/repositories/`,
each importing `get_connection` / `DB_PATH` from here. See DESIGN.md §5.
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_DIR = Path.home() / ".config" / "goqu"
DB_PATH = _DB_DIR / "goqu.db"

# SQLite translation of data/data.sql (MySQL syntax not compatible with SQLite)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS asset_type (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL DEFAULT '',
    asset_type_id INTEGER,
    exchange      TEXT NOT NULL DEFAULT '',
    currency      TEXT NOT NULL DEFAULT 'USD',
    sector        TEXT NOT NULL DEFAULT '',
    industry      TEXT NOT NULL DEFAULT '',
    country       TEXT NOT NULL DEFAULT '',
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (asset_type_id) REFERENCES asset_type(id)
);

CREATE TABLE IF NOT EXISTS portfolio (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT NOT NULL,
    description        TEXT NOT NULL DEFAULT '',
    benchmark_asset_id INTEGER,
    created_at         DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at         DATETIME NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (benchmark_asset_id) REFERENCES assets(id)
);

-- Derived cache of current positions, rebuilt from transactions (never edited
-- directly). One row per (portfolio, asset).
CREATE TABLE IF NOT EXISTS holdings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id   INTEGER NOT NULL,
    asset_id       INTEGER NOT NULL,
    shares         REAL NOT NULL,
    cost_basis     REAL NOT NULL,
    purchase_price REAL NOT NULL,
    created_at     DATETIME NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (portfolio_id) REFERENCES portfolio(id),
    FOREIGN KEY (asset_id) REFERENCES assets(id),
    UNIQUE (portfolio_id, asset_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id     INTEGER NOT NULL,
    asset_id         INTEGER NOT NULL,
    date             DATE NOT NULL,
    transaction_type TEXT NOT NULL,
    shares           REAL NOT NULL,
    price            REAL NOT NULL,
    fees             REAL NOT NULL DEFAULT 0.0,
    notes            TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (portfolio_id) REFERENCES portfolio(id),
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

CREATE TABLE IF NOT EXISTS daily_price (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id       INTEGER NOT NULL,
    date           DATE NOT NULL,
    open           REAL NOT NULL,
    high           REAL NOT NULL,
    low            REAL NOT NULL,
    adjusted_close REAL NOT NULL,
    volume         INTEGER NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id),
    UNIQUE (asset_id, date)
);

CREATE TABLE IF NOT EXISTS optimization_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id        INTEGER NOT NULL,
    algorithm           TEXT NOT NULL,
    expected_return     REAL NOT NULL,
    expected_volatility REAL NOT NULL,
    sharpe_ratio        REAL NOT NULL,
    created_at          DATETIME NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (portfolio_id) REFERENCES portfolio(id)
);

CREATE TABLE IF NOT EXISTS optimization_allocations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    optimization_run_id INTEGER NOT NULL,
    asset_id            INTEGER NOT NULL,
    recommended_weight  REAL NOT NULL,
    FOREIGN KEY (optimization_run_id) REFERENCES optimization_runs(id),
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

CREATE TABLE IF NOT EXISTS risk_metrics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL,
    date         DATE NOT NULL,
    volatility   REAL NOT NULL,
    sharpe       REAL NOT NULL,
    sortino      REAL NOT NULL,
    max_drawdown REAL NOT NULL,
    var95        REAL NOT NULL,
    cvar95       REAL NOT NULL,
    FOREIGN KEY (portfolio_id) REFERENCES portfolio(id)
);

-- Declared per-share dividend events for an asset (market data, e.g. yfinance).
CREATE TABLE IF NOT EXISTS dividends (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id      INTEGER NOT NULL,
    ex_date       DATE NOT NULL,
    record_date   DATE,
    pay_date      DATE,
    amount        REAL NOT NULL,                       -- cash paid per share
    frequency     TEXT NOT NULL DEFAULT 'quarterly',   -- monthly|quarterly|semi_annual|annual|special
    dividend_type TEXT NOT NULL DEFAULT 'ordinary',    -- ordinary|qualified|special|return_of_capital
    currency      TEXT NOT NULL DEFAULT 'USD',
    created_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (asset_id) REFERENCES assets(id),
    UNIQUE (asset_id, ex_date)
);

-- Current income snapshot per asset (1:1 with assets) for screening / projection.
CREATE TABLE IF NOT EXISTS asset_income_profile (
    asset_id             INTEGER PRIMARY KEY,
    dividend_yield       REAL,     -- trailing/forward yield as a fraction (0.035 = 3.5%)
    annual_dividend_rate REAL,     -- indicated $ per share per year
    payout_frequency     TEXT,     -- monthly|quarterly|semi_annual|annual
    payout_ratio         REAL,     -- fraction of earnings distributed
    ex_dividend_date     DATE,     -- next (or most recent) ex-date
    five_year_avg_yield  REAL,
    dividend_growth_5y   REAL,     -- 5-yr dividend CAGR as a fraction
    updated_at           DATETIME NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

-- Realized dividend income received by a portfolio (with DRIP + tax withholding).
CREATE TABLE IF NOT EXISTS dividend_income (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id     INTEGER NOT NULL,
    asset_id         INTEGER NOT NULL,
    dividend_id      INTEGER,                       -- source dividend event (nullable if entered manually)
    pay_date         DATE NOT NULL,
    shares_held      REAL NOT NULL,                 -- shares held on the record date
    amount_per_share REAL NOT NULL,
    gross_amount     REAL NOT NULL,                 -- shares_held * amount_per_share
    tax_withheld     REAL NOT NULL DEFAULT 0.0,
    net_amount       REAL NOT NULL,                 -- gross_amount - tax_withheld
    is_reinvested    INTEGER NOT NULL DEFAULT 0,    -- DRIP flag (0/1)
    currency         TEXT NOT NULL DEFAULT 'USD',
    created_at       DATETIME NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (portfolio_id) REFERENCES portfolio(id),
    FOREIGN KEY (asset_id) REFERENCES assets(id),
    FOREIGN KEY (dividend_id) REFERENCES dividends(id)
);

-- Corporate actions that change share ownership: splits, mergers, spinoffs,
-- and symbol changes. Splits are refetchable market data (yfinance) and upsert
-- idempotently; mergers/spinoffs/symbol changes have no reliable feed and are
-- entered manually, so this is a *source-of-truth* table (never dropped in a
-- migration). Folded into recompute_holdings in ex_date order to keep the
-- derived holdings cache correct across the event.
CREATE TABLE IF NOT EXISTS corporate_actions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id         INTEGER NOT NULL,        -- the affected ("from") asset
    action_type      TEXT NOT NULL,           -- split | merger | spinoff | symbol_change
    ex_date          DATE NOT NULL,           -- effective date (applied at open)
    numerator        REAL,                    -- split: new shares per old (2 for 2:1)
    denominator      REAL,                    -- split: old shares (1 for 2:1)
    target_asset_id  INTEGER,                 -- merger/spinoff/symbol_change: the "to" asset
    exchange_ratio   REAL,                    -- target shares received per held share
    cash_per_share   REAL,                    -- cash component per held share
    basis_allocation REAL,                    -- spinoff: fraction (0..1) of basis moved to target
    source           TEXT NOT NULL DEFAULT 'manual',
    notes            TEXT NOT NULL DEFAULT '',
    created_at       DATETIME NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (asset_id) REFERENCES assets(id),
    FOREIGN KEY (target_asset_id) REFERENCES assets(id),
    UNIQUE (asset_id, ex_date, action_type)
);
CREATE INDEX IF NOT EXISTS idx_corporate_actions_asset
    ON corporate_actions(asset_id, ex_date);

-- Cash movements not tied to a trade: deposits, withdrawals, interest, fees.
-- `amount` is a SIGNED cash delta (deposits/interest positive; withdrawals/fees
-- negative). Source-of-truth (never dropped in a migration); the portfolio's cash
-- balance is *derived* from this plus trade cash flows and non-reinvested
-- dividend income (see data/repositories/cash.py) — holdings-style, per ADR-002.
CREATE TABLE IF NOT EXISTS cash_transactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL,
    date         DATE NOT NULL,
    cash_type    TEXT NOT NULL,        -- deposit | withdrawal | interest | fee | adjustment
    amount       REAL NOT NULL,        -- signed cash delta
    notes        TEXT NOT NULL DEFAULT '',
    created_at   DATETIME NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (portfolio_id) REFERENCES portfolio(id)
);
CREATE INDEX IF NOT EXISTS idx_cash_txn_portfolio
    ON cash_transactions(portfolio_id, date);

-- Options chain snapshots (one row per contract). Refreshed as a unit per
-- (asset, expiration); fetched_at drives cache freshness.
CREATE TABLE IF NOT EXISTS option_contracts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL,
    contract_symbol TEXT,
    expiration      DATE NOT NULL,
    option_type     TEXT NOT NULL,          -- call | put
    strike          REAL NOT NULL,
    last_price      REAL,
    bid             REAL,
    ask             REAL,
    volume          INTEGER,
    open_interest   INTEGER,
    implied_vol     REAL,
    in_the_money    INTEGER,
    fetched_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (asset_id) REFERENCES assets(id),
    UNIQUE (asset_id, expiration, option_type, strike)
);
CREATE INDEX IF NOT EXISTS idx_option_contracts
    ON option_contracts(asset_id, expiration, option_type);

-- Freshness ledger for the persistent cache tier. cache_key is e.g.
-- 'daily:AAPL', 'dividends:AAPL', 'options:AAPL:2026-07-18'.
CREATE TABLE IF NOT EXISTS data_cache_meta (
    cache_key  TEXT PRIMARY KEY,
    fetched_at DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_dividends_asset
    ON dividends(asset_id, ex_date);
CREATE INDEX IF NOT EXISTS idx_dividend_income_portfolio
    ON dividend_income(portfolio_id, pay_date);

-- Reference data: asset types are looked up by name (get_or_create_asset_type).
CREATE UNIQUE INDEX IF NOT EXISTS idx_asset_type_name
    ON asset_type(name);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")  # tolerate concurrent background fetches
    conn.row_factory = sqlite3.Row
    return conn


def is_first_run() -> bool:
    return not DB_PATH.exists()


def init_schema() -> None:
    first_run = not DB_PATH.exists()
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        _migrate(conn)
        conn.executescript(_SCHEMA)  # CREATE TABLE IF NOT EXISTS — recreates dropped tables
        conn.commit()
    finally:
        conn.close()
    logger.info("Schema %s at %s", "created" if first_run else "verified", DB_PATH)


def _migrate(conn: sqlite3.Connection) -> None:
    """One-off structural fixes that CREATE TABLE IF NOT EXISTS can't apply.

    Both `holdings` (derived from transactions) and `daily_price` (re-fetchable
    market data) are caches, so it's safe to drop and let init_schema recreate
    them with corrected constraints.
    """
    # holdings: legacy DBs used UNIQUE(asset_id) (one portfolio per asset
    # table-wide); rebuild with the correct UNIQUE(portfolio_id, asset_id).
    if _has_unique_index(conn, "holdings", ["asset_id"]):
        logger.info("Migrating: rebuilding legacy 'holdings' table (derived cache)")
        conn.execute("DROP TABLE holdings")

    # daily_price: earlier versions had no UNIQUE(asset_id, date), which upserts
    # rely on. Rebuild it if that constraint is absent.
    if _table_exists(conn, "daily_price") and not _has_unique_index(
        conn, "daily_price", ["asset_id", "date"]
    ):
        logger.info("Migrating: rebuilding 'daily_price' table (refetchable cache)")
        conn.execute("DROP TABLE daily_price")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _has_unique_index(conn: sqlite3.Connection, table: str, columns: list[str]) -> bool:
    if not _table_exists(conn, table):
        return False
    for _seq, index_name, is_unique, *_ in conn.execute(
        f"PRAGMA index_list({table})"
    ).fetchall():
        if not is_unique:
            continue
        cols = [info[2] for info in conn.execute(
            f"PRAGMA index_info({index_name})"
        ).fetchall()]
        if cols == columns:
            return True
    return False
