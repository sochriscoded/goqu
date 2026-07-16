"""Headless validation for downloaded market data.

Providers coerce vendor payloads into our documented dict shapes, but nothing
guarantees the *values* are sane — a bad feed can return zero/negative prices,
NaNs, or high < low. These pure functions run between the provider and the
persistence layer (DataService), dropping unusable rows and returning the issues
so they can be logged (the log doubles as a data-quality audit, per DESIGN §13).

No Qt, no DB — trivially unit-testable (DESIGN principle 3).
"""
from __future__ import annotations

import math
from datetime import date

# Fields required on a daily OHLCV row.
_PRICE_FIELDS = ("open", "high", "low", "adjusted_close")

# Metadata fields we accept from a provider profile (asset_type is resolved to
# asset_type_id by the caller; the rest map 1:1 to `assets` columns).
_METADATA_FIELDS = (
    "name", "asset_type", "exchange", "currency", "sector", "industry", "country",
)


def _is_iso_date(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _finite_positive(value) -> bool:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f) and f > 0


def daily_row_problem(row: dict) -> str | None:
    """Return a short reason a daily bar is unusable, or None if it's valid.

    Note: `adjusted_close` is split/dividend-adjusted and may legitimately fall
    outside the raw [low, high] band, so it is only checked for positivity — the
    high/low/open consistency check applies to the raw prices only.
    """
    if not _is_iso_date(row.get("date")):
        return "missing/invalid date"
    for field in _PRICE_FIELDS:
        if not _finite_positive(row.get(field)):
            return f"non-positive/invalid {field}"
    vol = row.get("volume")
    try:
        if int(vol) < 0:
            return "negative volume"
    except (TypeError, ValueError):
        return "invalid volume"
    o, h, low = float(row["open"]), float(row["high"]), float(row["low"])
    if h < low:
        return "high < low"
    if not (low <= o <= h):
        return "open outside [low, high]"
    return None


def _coerce_daily(row: dict) -> dict:
    return {
        "date": row["date"],
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "adjusted_close": float(row["adjusted_close"]),
        "volume": int(row["volume"]),
    }


def validate_daily_rows(rows: list[dict]) -> tuple[list[dict], list[tuple[int, str]]]:
    """Split daily bars into (clean, issues).

    `clean` are coerced, ready-to-upsert rows; `issues` is a list of
    (row_index, reason) for the rows that were dropped.
    """
    clean: list[dict] = []
    issues: list[tuple[int, str]] = []
    for i, row in enumerate(rows):
        problem = daily_row_problem(row)
        if problem:
            issues.append((i, problem))
        else:
            clean.append(_coerce_daily(row))
    return clean, issues


def clean_metadata(raw: dict) -> dict:
    """Keep only known, non-empty string fields from a provider metadata dict,
    trimmed. Drops the `symbol` echo and anything blank/None."""
    out: dict[str, str] = {}
    for key in _METADATA_FIELDS:
        value = raw.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            out[key] = text
    return out
