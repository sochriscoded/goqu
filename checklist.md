# Trading System — Build Checklist

A living tracker for the full system: an active edge-seeking engine (options /
swing / momentum), a passive compounding engine (index core + dividend-growth
income sleeve), and a profit sweep connecting them — all on a shared data layer.

Check items off and update status as we build. The reasoning behind each item
lives in our design conversation and the code comments.

## Status key
- `[x]` done
- `[ ]` open, with a tag:
    - **(decide)** — needs a decision before work can start
    - **(design)** — needs designing
    - **(build)** — designed, needs building
    - **(data-dep)** — blocked on the data layer

---

## 0. Decisions that unblock the rest — do these first

- [X] **Data source & budget** — Will use Alphavantage free tier, however will make a screen that 
allows me to pick data source.

- [X] **Account & tax structure**  Can set up multiple accounts based on tax situation. Will start in an non-tax advantaged account
- [X] **Sweep rule parameters** — 20% of P/L is swept into income, 20% is swept into long-term dividend.
- [X] **Front-end ↔ back-end boundary** — C# calls  for
  stats / runs it as a report generator / reimplements a subset.

---

## 1. Data layer — the foundation (build first)  **(design + build)**

- [ ] Choose/validate provider(s) for price history, fundamentals, options &
  IV, and the benchmark series.
- [ ] Ingestion: idempotent, as-of timestamped, point-in-time (never overwrite
  history — so future analysis stays honest).
- [ ] Populate `benchmark_price` (SPY) → unblocks the analysis **baseline**.
- [ ] Populate `price_history` → unblocks **correlation/concentration**.
- [ ] Fundamentals + catalysts/event feed → feeds the research dossiers.
- [ ] Options chain / IV / Greeks snapshots → feeds the journal's entry
  market-state fields.
- [ ] Scheduling (cron) for the pulls.

---

## 2. Pillar 1 — Trade journal

- [x] Schema: `account`, `trade`, `trade_leg`, `trade_tag`, `benchmark_price`,
  `price_history`, `account_snapshot` (`trade_journal_schema.sql`).
- [ ] ~25 metric views: expectancy/payoff/profit-factor, R-distribution, equity
  curve & drawdown, open heat, Kelly, cost drag, calibration + Brier,
  failure modes, thesis-vs-outcome quadrant, concentration by symbol & theme.
- [ ] **START LOGGING REAL TRADES BY HAND — now, before any tooling.** The
  accumulated data is the asset. ⟵ *do this immediately*
- [ ] Fast logging front-end so an entry takes < 1 minute (see §8). **(build)**
- [ ] Optional `leg_fill` child table for scaling in/out. **(design — deferred)**

---

## 3. Statistical analysis layer

- [ ] 7 analyses: edge significance, baseline, Monte
  Carlo paths, Sharpe, calibration significance, correlation-adjusted
  concentration, revenge scan. numpy/pandas only.
- [ ] Baseline + correlation sections light up once the data layer populates
  prices. **(data-dep)**
- [ ] Later: deflated-Sharpe / multiple-testing corrections (migrates toward
  edge discovery). **(design)**
- [ ] Optional: persist analysis snapshots over time + scheduled report. **(design)**

---

## 4. Pillar 2 — Research (per-symbol dossiers)  **(design + build)**

- [ ] Dossier format: markdown + YAML frontmatter (multiples, margins,
  catalysts, event dates, factor exposures) + prose bull/bear thesis.
- [ ] Encode **transmission mechanisms**: factor → chain → *observable leading
  indicator* (e.g. AI capex → component demand → revenue line → price; watch
  hyperscaler capex guidance).
- [ ] Link dossiers to the journal via `source_ref` and `theme` tags.
- [ ] Optional Hugo rendering (reuse your existing setup).
- [ ] Current-events/macro intake — organize it, but remember news ≠ edge.

---

## 5. Pillar 3 — Edge discovery (the falsification machine)  **(design + build)**

- [ ] **Hypothesis registry**: structured records — the idea, the structural
  reason it should exist, the exact signal definition, status
  (untested/forward-testing/validated/rejected), results.
- [ ] **Signal evaluation harness**: forward / walk-forward grading +
  multiple-testing correction (deflated Sharpe / FDR) + purged CV.
- [ ] **Snapshot grading**: did screener-sourced candidates beat baseline?
- [ ] Calibration significance + thesis-vs-outcome quadrant (already in the
  analysis layer / schema).
- [ ] Discipline: log *everything* tried — the audit trail is the main defense
  against fooling yourself.

---

## 6. Screener / candidate system  **(design + build)**

- [ ] Candidate snapshot tables (dated, ranked) — gives `source_ref` a target.
- [ ] Screener logic: filters + factor scoring over the data.
- [ ] Screen specs: large-cap core + small-cap satellite sleeve.
- [ ] Forward-test grading hook (ties into §5).

---

## 7. Pillar 4 — Income & sweep engine  **(design + build)**

- [ ] Holdings + **tax-lot** schema (cost basis).
- [ ] Dividends received + reinvestment (DRIP) tracking.
- [ ] **Sweep ledger**: net trading P&L → income buys (the pump linking the
  two engines).
- [ ] Metrics: projected annual income (run-rate), yield-on-cost, dividend
  growth, total return vs benchmark, cumulative "locked-in", crossover
  projection (years until dividends cover a target take-home).
- [ ] Index-core accumulation sleeve — *doubles as the benchmark/control* that
  keeps the active side honest.
- [ ] Dividend-growth screen: optimize **safety + growth**, not headline yield
  (avoid the yield trap).
- [ ] Implement sweep-from-**net** rule (not per-winner gross).

---

## 8. Front-end / UI (Avalonia, C#)  **(design + build)**

- [ ] Fast trade-entry form (behavioral fields as one-tap enums).
- [ ] Dashboard reading `v_dashboard` and friends.
- [ ] Research-dossier viewer/editor.
- [ ] Income/sweep tracker view.

---

## 9. Trading rules & risk policy — the rules you actually trade by  **(design)**

*Flagged because the journal's `followed_plan` / `rule_broken` fields are
meaningless until the rules they reference actually exist.*

- [ ] Position-sizing rule (fractional Kelly; max risk % per trade).
- [ ] Portfolio heat cap (max total open risk at once).
- [ ] Concentration cap (max risk per symbol and per theme).
- [ ] Entry/exit rule definitions per strategy (options / swing / momentum).

---

## Immediate next actions (this week)

1. **Start logging real trades by hand** into the schema. Don't wait for tooling.
2. **Decide the data source** (§0) — the single fork that unblocks the most.
3. **Build the data layer** (§1) — the keystone the rest depends on.