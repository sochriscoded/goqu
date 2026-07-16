# goqu — Roadmap

> The phased development plan (Phase 0 → 11). This supersedes the roadmap that
> lived in [README.md](README.md), reconciled against what's actually built.
> Architecture rationale lives in [DESIGN.md](DESIGN.md).

Last reviewed: 2026-07-14.

**Status legend:** `[x]` done · `[~]` partial / in progress · `[ ]` not started

---

## Where we are

We've built somewhat **breadth-first** — the data foundation and enough of the
UI to exercise it — rather than strictly phase-by-phase. Snapshot:

| Phase | Title | Status | One-line |
| --- | --- | --- | --- |
| 0 | Planning & Design | ✅ 100% | Complete — architecture, config, ERD, logging all done |
| 1 | Database Layer | 🟢 ~95% | Schema + migrations + per-domain repositories done; seed data pending |
| 2 | Market Data | 🟢 ~90% | Downloader + caching + corporate actions + metadata + gap-backfill + validation; needs a symbol-entry UI |
| 3 | Portfolio Management | 🟢 ~85% | Holdings/values/allocation + edit/delete + cash tracking done; **accounts** pending |
| 4 | Analytics Engine | 🔴 ~5% | Metrics *displayed* but not *computed* |
| 5 | Visualization | 🟡 ~25% | Dashboard shell done; no charts |
| 6 | Portfolio Optimization | 🔴 0% | Tables exist; no optimizer |
| 7 | Risk Analysis | 🔴 0% | — |
| 8 | Advanced Portfolio Theory | 🔴 0% | — |
| 9 | Backtesting | 🔴 0% | — |
| 10 | Machine Learning | 🔴 0% | — |
| 11 | Professional Polish | 🟡 ~20% | Theme system (dark/light/system) + settings + first-run wizard |

**Suggested critical path next:** finish Phase 2 (data validation; splits now
handled) → Phase 4 (the analytics engine, since Phase 5 charts and Phases 6–9
all depend on it) → Phase 3 gaps (edit/delete, cash) in parallel.

---

## Phase 0 — Planning & Design  ✅
**Goal:** Define the architecture before writing significant code.

- [x] Create the project repository
- [x] Set up `uv`
- [x] Configure Ruff, Black, MyPy
- [x] Choose PySide6 as the GUI
- [x] Decide on project architecture — *layered + provider pattern; see DESIGN.md*
- [x] Design the SQLite schema
- [x] Create ER diagram — *Mermaid ERD in [DESIGN.md](DESIGN.md) §6.1*
- [x] Define configuration system — *`config.py` + `~/.config/goqu/datasource.json`*
- [x] Decide logging strategy — *`logging_config.setup_logging()` → rotating file `~/.config/goqu/logs/goqu.log`; `GOQU_LOG_LEVEL` override; provider fetches logged at INFO as an API-call audit*
- [x] Create initial folder structure

**Deliverable:** *Empty application that launches successfully.* ✅ (`python main.py`)

---

## Phase 1 — Database Layer  🟢
**Goal:** Build the application's data foundation.

**Schema** — [x] Assets · [x] AssetTypes · [x] DailyPrices · [x] Portfolios ·
[x] Transactions · [x] Holdings · [x] OptimizationRuns · [x] OptimizationAllocations
· **[ ] Accounts** *(not yet — see Phase 3)*
Beyond the original list we also added: dividends, asset_income_profile,
dividend_income, option_contracts, risk_metrics, data_cache_meta.

**Data Access**
- [x] SQLite connection (`get_connection`, FK on, busy_timeout)
- [x] Repository layer — *per-domain repos in `data/repositories/` (assets, market_data, income, portfolios, analytics, cache_meta); `database.py` holds connection + schema + migrations*
- [x] CRUD operations
- [x] Database initialization (`init_schema`)
- [x] Migration system (`_migrate`, index-aware cache-table rebuilds)
- [ ] Seed data

**Deliverable:** `goqu.db` created automatically. ✅ (at `~/.config/goqu/`)

---

## Phase 2 — Market Data  🟢
**Goal:** Populate the database from providers, cheaply.

- [x] Download historical prices (`DataService.get_daily`)
- [x] Update existing prices (idempotent upsert on `UNIQUE(asset_id,date)`)
- [x] Cache downloads (two-tier: memory TTL + persistent `data_cache_meta`)
- [x] **Handle stock splits** — *`corporate_actions` table + fold into `recompute_holdings`; splits auto-fetched from yfinance (`get_corporate_actions`) and applied to holdings.*
- [x] **Handle mergers / spinoffs / symbol changes** — *same corporate-actions engine; recorded manually (no reliable feed) with basis carryover/allocation.*
- [x] Handle dividends (`get_dividends` → `dividends` table)
- [x] Download metadata — *`get_metadata` enriches assets (name/sector/industry/exchange/currency/country/type) from yfinance `.info`; auto-fires for new stubs; asset types via `reference` repo*
- [x] Detect missing dates — *`compute_missing_ranges` gap detector (weekend/long-weekend tolerant) + `DataService.backfill_daily` fetches only the holes*
- [x] Validate downloaded data — *`data/validation.py` OHLCV sanity/range checks (positive prices, high≥low, open∈[low,high], finite, volume≥0) drop bad rows before upsert*

Also delivered ahead of the original scope: **multi-source provider architecture**
(yfinance live; Alpha Vantage/Polygon stubs), **per-type routing**, **options
chains** (`get_options`), and an **event bus** for reactive updates.

**Deliverable:** type `AAPL` → download 20 years of history. ⏳ (engine ready
and trustworthy — splits, validation, and gap-backfill all handled; the one
remaining gap is a **symbol-entry UI** to drive it)

---

## Phase 3 — Portfolio Management  🟡
**Goal:** Represent real portfolios.

- [x] Create portfolio
- [ ] Create account — *no `accounts` table yet*
- [x] Add transactions (single + batch)
- [x] Delete transactions — *`delete_transaction` + recompute; per-row button in the history*
- [x] Edit transactions — *`update_transaction` + recompute; edit dialog from the history*
- [x] Compute holdings (`recompute_holdings`, average-cost)
- [x] Compute current values (dashboard tiles + holdings table)
- [x] Compute allocation (weights per holding)
- [x] Cash tracking — *`cash_transactions` + derived balance (`cash` repo): deposits/withdrawals/interest/fees + trade flows + non-DRIP dividends; Cash tab + dashboard Cash/Total Value tiles*

**Deliverable:** recreate your brokerage portfolio exactly. ⏳ (edit/delete/cash
done; the one remaining gap is **accounts** — grouping holdings/cash under
brokerage accounts)

> Note: edit/delete were cheap thanks to ADR-002 — mutate the ledger, then
> `recompute_holdings()`; nothing FK-references `transactions`. Cash follows the
> same rule: the balance is *derived*, never stored.

---

## Phase 4 — Analytics Engine  🔴
**Goal:** Compute (not just display) portfolio statistics. **Headless, in
`analytics/`, no Qt.**

- **Returns:** [ ] daily · [ ] monthly · [ ] annualized
- **Risk:** [ ] volatility · [ ] covariance matrix · [ ] correlation matrix
- **Performance:** [ ] Sharpe · [ ] Sortino · [ ] Beta · [ ] Alpha · [ ] Information ratio
- **Drawdowns:** [ ] max drawdown · [ ] recovery time

**Deliverable:** every portfolio has a real statistics page.
**Dependency note:** this engine feeds Phases 5, 6, 7, and 9 — highest-leverage
next build. Persist outputs to `risk_metrics` (already displayed by the
dashboard).

---

## Phase 5 — Visualization  🟡
**Goal:** First polished GUI.

- **Dashboard:** [x] holdings table · [x] portfolio summary · [ ] allocation pie · [ ] performance chart
- **Analytics:** [ ] correlation heatmap · [ ] rolling volatility · [ ] rolling returns · [ ] drawdown chart
- **Market:** [ ] candlestick · [ ] volume · [ ] moving averages

**Deliverable:** a Bloomberg-style dashboard. ⏳ (shell exists; charts need
Phase 4 data + a chart integration — Plotly/QtCharts decision pending)

---

## Phase 6 — Portfolio Optimization  🔴
**Goal:** First optimizer. **In `optimizers/`, no Qt.**

- **Algorithms:** [ ] equal weight · [ ] minimum variance · [ ] maximum Sharpe · [ ] efficient frontier
- **Constraints:** [ ] long-only · [ ] weight limits · [ ] sector limits · [ ] asset-class limits
- **Results:** [ ] suggested allocation · [ ] expected return · [ ] expected volatility · [ ] Sharpe
- **Visualization:** [ ] efficient frontier · [ ] random portfolios · [ ] recommended allocation

**Deliverable:** a working optimizer. Persist to
`optimization_runs`/`optimization_allocations` (already displayed + compared to
current weights in the dashboard's rebalancing panel).

---

## Phase 7 — Risk Analysis  🔴
**Goal:** A risk analyzer.
[ ] Historical VaR · [ ] Parametric VaR · [ ] Conditional VaR (CVaR) ·
[ ] Monte Carlo simulation · [ ] stress testing.
**Deliverable:** institutional-quality risk report. (`simulations/` for Monte Carlo.)

---

## Phase 8 — Advanced Portfolio Theory  🔴
**Goal:** Apply advanced concepts.
- **Algorithms:** [ ] Black-Litterman · [ ] Risk Parity · [ ] Hierarchical Risk Parity · [ ] Minimum Tracking Error · [ ] Factor Optimization
- **Factors:** [ ] CAPM · [ ] Fama-French 3 · [ ] Fama-French 5 · [ ] Momentum · [ ] Quality
**Deliverable:** professional quantitative optimizer.

---

## Phase 9 — Backtesting  🔴
**Goal:** Test strategies on history. **In `simulations/`.**
- **Engine:** [ ] historical simulation · [ ] rebalancing · [ ] transaction costs · [ ] slippage
- **Strategies:** [ ] Buy & Hold · [ ] Equal Weight · [ ] Momentum · [ ] Mean Reversion
- **Results:** [ ] CAGR · [ ] drawdowns · [ ] risk metrics · [ ] benchmark comparison
**Deliverable:** test strategies before investing.

---

## Phase 10 — Machine Learning  🔴
**Goal:** A small ML research capability.
[ ] Feature engineering · [ ] forecast returns · [ ] forecast volatility ·
[ ] market-regime detection · [ ] portfolio recommendations ·
[ ] reinforcement-learning experiments.
**Deliverable:** an AI-assisted research platform.

---

## Phase 11 — Professional Polish  🟡
**Goal:** Make it feel complete.
- [ ] Import brokerage statements (CSV)
- [ ] Export reports (PDF/CSV)
- [~] Settings dialog — *data-source dialog exists; needs per-type routing + keys UI*
- [x] Dark/light themes — *`ui/theme.py` design system ("Ledger"); dark + light + follow-system, Settings → Appearance toggle, persisted in `ui.json`*
- [ ] Keyboard shortcuts (partial: menu accelerators)
- [ ] Autosave *(writes are immediate; N/A or session-state only)*
- [ ] Plugin architecture — *provider registry is a first step*
- [ ] Unit tests · [ ] Integration tests — *patterns exist (fakes + temp DB); no suite*
- [ ] Documentation — *DESIGN.md + ROADMAP.md started here*

**Deliverable:** a polished desktop application.

---

## Cross-cutting goals (all phases)

- [~] Unit tests for all calculation modules — *ad hoc today; formalize with `pytest`*
- [x] Keep the quant engine independent of the GUI — *enforced by package layout; keep `analytics/`/`optimizers/` Qt-free*
- [x] Separate data access, business logic, presentation — *see DESIGN §4*
- [x] Type hints everywhere + static analysis — *Ruff/Black/MyPy configured*
- [ ] Document formulas and cite references for financial models
- [ ] Sample datasets + reproducible examples

---

## Immediate next steps (proposed)

1. **Analytics engine v1** (Phase 4) — returns + volatility + Sharpe from
   `daily_price`, persisted to `risk_metrics`. Unblocks charts and optimizers.
2. **Edit/delete transactions** (Phase 3) — cheap given the hybrid model; big UX win.
3. **"Refresh prices" action** — wire `refresh_symbol_async` to a portfolio's
   holdings so valuation goes live (small, high-visibility). This also refreshes
   splits, so freshly-split positions self-correct.
4. **Corporate-actions UI** — a form to record mergers/spinoffs/symbol changes
   (the engine + repository exist; only manual entry lacks a view).
