"""Analytics repository — reads over optimization runs and risk metrics.

These tables are populated by future engines (`analytics/`, `optimizers/`);
today the dashboard only reads the most-recent row of each. Writes will land
here when Phase 4/6 land.
"""

from data.database import DB_PATH, get_connection


def get_latest_optimization(portfolio_id: int) -> dict | None:
    """Most recent optimization run and its recommended allocations, or None."""
    if not DB_PATH.exists():
        return None
    with get_connection() as conn:
        run = conn.execute(
            """
            SELECT * FROM optimization_runs
             WHERE portfolio_id = ?
             ORDER BY created_at DESC, id DESC
             LIMIT 1
            """,
            (portfolio_id,),
        ).fetchone()
        if not run:
            return None
        allocations = conn.execute(
            """
            SELECT a.symbol, oa.recommended_weight
              FROM optimization_allocations oa
              JOIN assets a ON a.id = oa.asset_id
             WHERE oa.optimization_run_id = ?
             ORDER BY oa.recommended_weight DESC
            """,
            (run["id"],),
        ).fetchall()
        return {"run": dict(run), "allocations": [dict(r) for r in allocations]}


def get_latest_risk_metrics(portfolio_id: int) -> dict | None:
    """Most recent risk_metrics row for the portfolio, or None."""
    if not DB_PATH.exists():
        return None
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM risk_metrics
             WHERE portfolio_id = ?
             ORDER BY date DESC, id DESC
             LIMIT 1
            """,
            (portfolio_id,),
        ).fetchone()
        return dict(row) if row else None
