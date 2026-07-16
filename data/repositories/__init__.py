"""Per-domain data-access repositories.

Each module owns the SQL for one domain (DESIGN §2's four data domains plus
infra), importing the connection factory from `data.database`:

- `assets`            — the market asset hub + company/sector metadata
- `reference`         — reference lookups (asset types)
- `market_data`       — refetchable price & options cache + gap detection
- `income`            — dividend sleeve (declared, profile, received)
- `corporate_actions` — splits/mergers/spinoffs/symbol changes
- `portfolios`        — portfolios, transaction ledger, derived holdings
- `cash`              — cash movements + derived cash balance
- `analytics`         — optimization & risk-metric reads
- `cache_meta`        — persistent-cache freshness ledger

This package re-exports every public helper so callers that touch several
domains can use one import surface (`from data import repositories as db`),
while domain-scoped callers can import the specific module they depend on.
"""

from data.repositories.analytics import (
    get_latest_optimization,
    get_latest_risk_metrics,
)
from data.repositories.assets import (
    get_asset,
    get_asset_by_symbol,
    get_or_create_asset,
    metadata_missing,
    update_asset_metadata,
)
from data.repositories.cache_meta import cache_age_seconds, cache_mark
from data.repositories.cash import (
    ADJUSTMENT,
    CASH_TYPES,
    DEPOSIT,
    FEE,
    INTEREST,
    WITHDRAWAL,
    delete_cash_transaction,
    get_cash_balance,
    get_cash_summary,
    get_cash_transactions,
    record_cash_transaction,
    signed_amount,
)
from data.repositories.corporate_actions import (
    get_actions_for_assets,
    get_corporate_actions,
    list_corporate_actions,
    record_corporate_action,
    record_merger,
    record_spinoff,
    record_split,
    record_symbol_change,
)
from data.repositories.income import (
    get_dividend_income,
    get_dividends,
    get_income_profile,
    get_income_summary,
    record_dividend,
    record_dividend_income,
    upsert_income_profile,
)
from data.repositories.market_data import (
    compute_missing_ranges,
    daily_gaps,
    get_daily_bounds,
    get_daily_prices,
    get_latest_price,
    get_option_chain,
    upsert_daily_prices,
    upsert_option_chain,
)
from data.repositories.reference import get_or_create_asset_type, list_asset_types
from data.repositories.portfolios import (
    BUY,
    SELL,
    compute_positions,
    create_portfolio,
    delete_transaction,
    get_holdings,
    get_portfolio,
    get_transaction,
    get_transactions,
    list_portfolios,
    recompute_holdings,
    recompute_portfolios_holding_asset,
    record_transaction,
    record_transactions_batch,
    update_transaction,
)

__all__ = [
    "ADJUSTMENT",
    "BUY",
    "CASH_TYPES",
    "DEPOSIT",
    "FEE",
    "INTEREST",
    "SELL",
    "WITHDRAWAL",
    "cache_age_seconds",
    "cache_mark",
    "compute_missing_ranges",
    "compute_positions",
    "create_portfolio",
    "daily_gaps",
    "delete_cash_transaction",
    "delete_transaction",
    "get_actions_for_assets",
    "get_asset",
    "get_asset_by_symbol",
    "get_cash_balance",
    "get_cash_summary",
    "get_cash_transactions",
    "get_corporate_actions",
    "get_daily_bounds",
    "get_daily_prices",
    "get_dividend_income",
    "get_dividends",
    "get_holdings",
    "get_income_profile",
    "get_income_summary",
    "get_latest_optimization",
    "get_latest_price",
    "get_latest_risk_metrics",
    "get_option_chain",
    "get_or_create_asset",
    "get_or_create_asset_type",
    "get_portfolio",
    "get_transaction",
    "get_transactions",
    "list_asset_types",
    "list_corporate_actions",
    "list_portfolios",
    "metadata_missing",
    "record_cash_transaction",
    "record_corporate_action",
    "record_dividend",
    "record_dividend_income",
    "record_merger",
    "record_spinoff",
    "record_split",
    "record_symbol_change",
    "record_transaction",
    "record_transactions_batch",
    "recompute_holdings",
    "recompute_portfolios_holding_asset",
    "signed_amount",
    "update_asset_metadata",
    "update_transaction",
    "upsert_daily_prices",
    "upsert_income_profile",
    "upsert_option_chain",
]
