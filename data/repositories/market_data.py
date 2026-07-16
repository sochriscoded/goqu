"""Market-data repository — the refetchable price/options cache.

`daily_price` and `option_contracts` are caches (DESIGN §6.2): they can always
be re-fetched, so these helpers are pure read/upsert with no source-of-truth
guarantees. Written by the DataService (`data/downloader.py`).
"""

from datetime import date, timedelta

from data.database import DB_PATH, get_connection


def upsert_daily_prices(asset_id: int, rows: list[dict]) -> int:
    """Insert/replace daily bars. Each row: date, open, high, low,
    adjusted_close, volume. Idempotent on (asset_id, date)."""
    if not rows:
        return 0
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO daily_price
                (asset_id, date, open, high, low, adjusted_close, volume)
            VALUES (:asset_id, :date, :open, :high, :low, :adjusted_close, :volume)
            ON CONFLICT(asset_id, date) DO UPDATE SET
                open=excluded.open, high=excluded.high, low=excluded.low,
                adjusted_close=excluded.adjusted_close, volume=excluded.volume
            """,
            [{"asset_id": asset_id, **r} for r in rows],
        )
    return len(rows)


def get_daily_prices(asset_id: int, start: str | None = None,
                     end: str | None = None) -> list[dict]:
    if not DB_PATH.exists():
        return []
    clauses = ["asset_id = ?"]
    params: list = [asset_id]
    if start:
        clauses.append("date >= ?")
        params.append(start)
    if end:
        clauses.append("date <= ?")
        params.append(end)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT date, open, high, low, adjusted_close, volume "
            f"FROM daily_price WHERE {' AND '.join(clauses)} ORDER BY date ASC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def compute_missing_ranges(
    existing_dates,
    start: str | None = None,
    end: str | None = None,
    max_gap_days: int = 4,
) -> list[tuple[str, str]]:
    """Pure gap detector over stored daily-bar dates.

    Returns inclusive ISO `(gap_start, gap_end)` ranges worth backfilling:
    - a leading gap if `start` precedes the earliest stored date,
    - a trailing gap if `end` follows the latest stored date,
    - internal gaps where consecutive stored dates are more than `max_gap_days`
      apart. The default 4 tolerates weekends and long weekends (Fri→Tue) — normal
      non-trading days — so only real holes (outages, never-fetched spans) surface,
      without needing a market-holiday calendar.

    Detected ranges are clamped to `[start, end]` when those bounds are given.
    """
    dates = sorted({date.fromisoformat(d) for d in existing_dates})
    s = date.fromisoformat(start) if start else None
    e = date.fromisoformat(end) if end else None
    day = timedelta(days=1)

    gaps: list[tuple[date, date]] = []
    if not dates:
        if s and e and s <= e:
            gaps.append((s, e))
    else:
        if s and s < dates[0]:
            gaps.append((s, dates[0] - day))
        for prev, nxt in zip(dates, dates[1:]):
            if (nxt - prev).days > max_gap_days:
                gaps.append((prev + day, nxt - day))
        if e and e > dates[-1]:
            gaps.append((dates[-1] + day, e))

    out: list[tuple[str, str]] = []
    for a, b in gaps:
        if s:
            a = max(a, s)
        if e:
            b = min(b, e)
        if a <= b:
            out.append((a.isoformat(), b.isoformat()))
    return out


def get_daily_bounds(asset_id: int) -> tuple[str | None, str | None, int]:
    """(earliest_date, latest_date, row_count) for an asset's stored daily bars."""
    if not DB_PATH.exists():
        return (None, None, 0)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MIN(date) AS lo, MAX(date) AS hi, COUNT(*) AS n "
            "FROM daily_price WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        return (row["lo"], row["hi"], row["n"])


def daily_gaps(asset_id: int, start: str | None = None, end: str | None = None,
               max_gap_days: int = 4) -> list[tuple[str, str]]:
    """Missing ISO date ranges in an asset's stored daily history (see
    `compute_missing_ranges`), for the DataService to backfill."""
    if not DB_PATH.exists():
        return [(start, end)] if start and end and start <= end else []
    with get_connection() as conn:
        dates = [r["date"] for r in conn.execute(
            "SELECT date FROM daily_price WHERE asset_id = ? ORDER BY date ASC",
            (asset_id,),
        ).fetchall()]
    return compute_missing_ranges(dates, start, end, max_gap_days)


def get_latest_price(asset_id: int) -> float | None:
    """Most recent adjusted close for an asset, if any."""
    if not DB_PATH.exists():
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT adjusted_close FROM daily_price WHERE asset_id = ? "
            "ORDER BY date DESC LIMIT 1",
            (asset_id,),
        ).fetchone()
        return row["adjusted_close"] if row else None


def upsert_option_chain(asset_id: int, chain: dict) -> int:
    """Replace the stored contracts for this (asset, expiration) with a fresh
    snapshot. `chain` has 'expiration' and 'calls'/'puts' contract lists."""
    expiration = chain.get("expiration")
    if not expiration:
        return 0
    contracts = [*chain.get("calls", []), *chain.get("puts", [])]
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM option_contracts WHERE asset_id = ? AND expiration = ?",
            (asset_id, expiration),
        )
        conn.executemany(
            """
            INSERT INTO option_contracts
                (asset_id, contract_symbol, expiration, option_type, strike,
                 last_price, bid, ask, volume, open_interest, implied_vol,
                 in_the_money, fetched_at)
            VALUES
                (:asset_id, :contract_symbol, :expiration, :option_type, :strike,
                 :last_price, :bid, :ask, :volume, :open_interest, :implied_vol,
                 :in_the_money, datetime('now'))
            ON CONFLICT(asset_id, expiration, option_type, strike) DO UPDATE SET
                contract_symbol=excluded.contract_symbol,
                last_price=excluded.last_price, bid=excluded.bid, ask=excluded.ask,
                volume=excluded.volume, open_interest=excluded.open_interest,
                implied_vol=excluded.implied_vol, in_the_money=excluded.in_the_money,
                fetched_at=excluded.fetched_at
            """,
            [{"asset_id": asset_id, **c, "in_the_money": int(bool(c.get("in_the_money")))}
             for c in contracts],
        )
    return len(contracts)


def get_option_chain(asset_id: int, expiration: str | None = None) -> dict:
    """Return the stored chain for an expiration (defaults to the nearest one),
    grouped into calls/puts, plus the list of expirations we have on file."""
    empty = {"expiration": expiration, "expirations": [], "calls": [], "puts": []}
    if not DB_PATH.exists():
        return empty
    with get_connection() as conn:
        expirations = [r["expiration"] for r in conn.execute(
            "SELECT DISTINCT expiration FROM option_contracts "
            "WHERE asset_id = ? ORDER BY expiration ASC",
            (asset_id,),
        ).fetchall()]
        if not expirations:
            return empty
        exp = expiration if expiration in expirations else expirations[0]
        rows = conn.execute(
            "SELECT * FROM option_contracts WHERE asset_id = ? AND expiration = ? "
            "ORDER BY strike ASC",
            (asset_id, exp),
        ).fetchall()
    calls = [dict(r) for r in rows if r["option_type"] == "call"]
    puts = [dict(r) for r in rows if r["option_type"] == "put"]
    return {"expiration": exp, "expirations": expirations, "calls": calls, "puts": puts}
