-- ============================================================================
-- TRADE JOURNAL / LOG  —  SCHEMA + METRICS
-- ============================================================================
-- Target engine : SQLite 3.25+ (window functions required).
--                 DuckDB-compatible with trivial tweaks.
-- Purpose       : A trade journal designed not just to record P&L, but to
--                 support three analytical goals:
--                   (1) BEHAVIORAL analysis  — where do I sabotage myself?
--                   (2) KNOWLEDGE-GAP analysis — where is my analysis wrong?
--                   (3) PORTFOLIO-HEALTH metrics — is my book sound?
--
-- DESIGN PRINCIPLES
--   1. Store raw facts only. Every metric is a VIEW, never a stored column,
--      so there is a single source of truth and nothing can drift stale.
--   2. The R-MULTIPLE is the backbone: outcome / initial_risk. This makes
--      trades of wildly different sizes directly comparable.
--   3. Capture INTENTION AT ENTRY (a falsifiable prediction) before the
--      outcome is known. This is what makes calibration and gap-finding
--      possible at all.
--   4. Behavioral fields are constrained enums, so logging is fast and the
--      data is groupable. Slow logging is abandoned logging.
--   5. Linkage columns (source_type/source_ref, theme tags, benchmark table)
--      wire this journal into the larger system: screener -> trades -> edge
--      grading, and research themes -> concentration analysis.
--
-- WHAT IS DELIBERATELY *NOT* HERE (belongs in the  analysis layer,
-- because SQL cannot do it honestly):
--   - Bootstrapped confidence intervals on expectancy
--   - True correlation matrix of open positions (needs price series)
--   - Sharpe / Sortino with annualization
--   - Robust revenge-trading / regime detection
--   - Random-entry baseline simulation
-- The views below are the clean feature inputs that layer will read.
--
-- RE-RUNNABLE: tables use IF NOT EXISTS; views are dropped and recreated, so
-- you can re-apply this file after editing a formula without losing data.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ============================================================================
-- SECTION 1 — CORE TABLES
-- ============================================================================

-- ---------------------------------------------------------------------------
-- account : supports multiple accounts (e.g. your small practice account vs.
--           a live account). Keeps their statistics cleanly separable.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS account (
                                       account_id     INTEGER PRIMARY KEY,
                                       name           TEXT    NOT NULL,
                                       base_currency  TEXT    NOT NULL DEFAULT 'USD',
                                       opened_at      TEXT,                       -- ISO 8601 date
                                       notes          TEXT
);

-- ---------------------------------------------------------------------------
-- trade : the logical position and its full lifecycle. One row per position.
--         Money facts live in trade_leg; this row holds thesis, risk, market
--         state at entry, behavior, and exit judgment.
--
-- FIELD GROUPS (see comments inline):
--   [identity/linkage] [timing] [sizing & risk] [entry prediction]
--   [market state] [behavioral] [exit]
--
-- "core" in a comment = load-bearing; keep these mandatory in your UI.
-- Everything nullable = optional enrichment you can defer.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trade (
                                     trade_id              INTEGER PRIMARY KEY,
                                     account_id            INTEGER NOT NULL REFERENCES account(account_id),

    -- [identity / linkage] --------------------------------------------------
    symbol                TEXT    NOT NULL,                 -- underlying ticker (core)
    instrument_type       TEXT    NOT NULL DEFAULT 'equity' -- (core)
    CHECK (instrument_type IN
('equity','option','etf','future','other')),
    direction             TEXT    NOT NULL                  -- (core)
    CHECK (direction IN ('long','short','neutral')),
    strategy_type         TEXT,    -- e.g. long_equity, long_call, covered_call,
-- csp, vertical, iron_condor, calendar...
    source_type           TEXT    DEFAULT 'discretionary'
    CHECK (source_type IN
('discretionary','screener','research','tip','other')),
    source_ref            TEXT,    -- FK-style pointer into screener/research
-- layer (e.g. a candidate-snapshot id).
-- Lets you later grade research vs. gut.

-- [timing] --------------------------------------------------------------
    status                TEXT    NOT NULL DEFAULT 'open'
    CHECK (status IN ('open','closed','rolled')),
    opened_at             TEXT    NOT NULL,                 -- ISO 8601 (core)
    closed_at             TEXT,                              -- NULL while open
    planned_hold_days     INTEGER, -- expected hold; graded against actual

-- [sizing & risk] -------------------------------------------------------
    initial_risk          REAL    NOT NULL,                 -- (core) planned max
-- loss in $. DEFINES R. For spreads this is
-- the structural max loss; entered manually.
    planned_stop          REAL,    -- informational price level (mainly equity)
    planned_target        REAL,    -- informational price level
    planned_target_pnl    REAL,    -- expected $ gain if thesis works.
-- planned_rr is derived = this / initial_risk
    account_value_at_entry REAL,   -- enables risk-as-%-of-account analysis

-- [entry prediction — the falsifiable thesis] ---------------------------
    thesis                TEXT,                              -- (core, short)
    confidence_pct        REAL    CHECK (confidence_pct BETWEEN 0 AND 100),
    -- (core) probability you assign to success.
    -- This is what the calibration curve grades.
    conviction            INTEGER CHECK (conviction BETWEEN 1 AND 5),
    -- optional gut-strength, distinct from the
    -- probability estimate above.
    invalidation          TEXT,    -- (core) what would prove the thesis wrong

-- [market state at entry] -----------------------------------------------
    entry_underlying_price REAL,   -- underlying price (for options); for equity
-- this equals the leg entry price.
    iv_at_entry           REAL,    -- implied vol (options)
    iv_rank_at_entry      REAL,    -- IV rank 0..100 (options)
    vix_at_entry          REAL,
    market_regime         TEXT,    -- free/enum e.g. risk_on, risk_off, high_vol

-- [behavioral — constrained enums for fast, groupable logging] ----------
    emotional_state       TEXT    CHECK (emotional_state IN              -- (core)
('calm','confident','fomo','revenge',
                                         'bored','anxious','fearful')),
    trade_origin          TEXT    CHECK (trade_origin IN                  -- (core)
('planned','impulsive')),
    followed_plan         INTEGER CHECK (followed_plan IN (0,1)),         -- (core)
    rule_broken           TEXT,    -- which rule, if followed_plan = 0

-- [exit] ----------------------------------------------------------------
    exit_reason           TEXT    CHECK (exit_reason IN                   -- (core)
('target_hit','stop_hit','time_stop',
                                         'thesis_invalidated','thesis_wrong_timing',
                                         'mis_sized','regime_shift','exogenous_shock',
                                         'discretionary_panic','discretionary_profit_take',
                                         'rolled','expired','assigned')),
    exit_followed_plan    INTEGER CHECK (exit_followed_plan IN (0,1)),
    thesis_correct        INTEGER CHECK (thesis_correct IN (0,1)),
    -- judged at exit: in hindsight, was the
    -- analytical thesis right, REGARDLESS of P&L?
    -- Crossed with win/loss this separates
    -- analysis errors from execution errors.
    notes                 TEXT,

    -- [audit] ---------------------------------------------------------------
    created_at            TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at            TEXT    DEFAULT CURRENT_TIMESTAMP
    );

-- ---------------------------------------------------------------------------
-- trade_leg : one row per instrument in the position. Equity = exactly one
--             leg. A vertical = two legs. An iron condor = four legs. This is
--             where all the money facts live, so P&L has a single source.
--
-- Sign convention for realized P&L (see v_leg_pnl):
--   long  leg: +qty * (exit - entry) * multiplier  - fees
--   short leg: -qty * (exit - entry) * multiplier  - fees
--
-- EXTENSION POINT (deferred on purpose): to support scaling in/out, replace
-- entry_price/exit_price here with a child `leg_fill` table (one row per
-- execution) and make these prices weighted averages. Not added now to keep
-- logging fast enough that you actually do it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trade_leg (
                                         leg_id        INTEGER PRIMARY KEY,
                                         trade_id      INTEGER NOT NULL REFERENCES trade(trade_id) ON DELETE CASCADE,
    leg_type      TEXT    NOT NULL CHECK (leg_type IN ('equity','call','put')),
    side          TEXT    NOT NULL CHECK (side IN ('long','short')),
    quantity      REAL    NOT NULL CHECK (quantity > 0),   -- shares / contracts
    multiplier    REAL    NOT NULL DEFAULT 1,              -- 100 for options
    strike        REAL,                                     -- NULL for equity
    expiry        TEXT,                                     -- NULL for equity
    entry_price   REAL    NOT NULL,                         -- per share/contract
    exit_price    REAL,                                     -- NULL while open
    entry_fees    REAL    DEFAULT 0,
    exit_fees     REAL    DEFAULT 0,
    -- per-leg Greeks at entry (optional, options only) ----------------------
    entry_delta   REAL,
    entry_theta   REAL,
    entry_vega    REAL,
    entry_iv      REAL,
    dte_at_entry  INTEGER
    );

-- ---------------------------------------------------------------------------
-- trade_tag : many-to-many tags. tag_category distinguishes:
--   'setup'   - the pattern traded (breakout, mean_reversion, earnings...)
--   'mistake' - a logged error (no_stop, moved_stop, averaged_down, chased...)
--   'theme'   - a macro/sector transmission factor (ai_capex, rates, oil...)
-- Themes are what power the concentration-by-theme view (your blind spot).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trade_tag (
                                         trade_id      INTEGER NOT NULL REFERENCES trade(trade_id) ON DELETE CASCADE,
    tag           TEXT    NOT NULL,
    tag_category  TEXT    NOT NULL CHECK (tag_category IN ('setup','mistake','theme')),
    PRIMARY KEY (trade_id, tag, tag_category)
    );

-- ---------------------------------------------------------------------------
-- benchmark_price : populated by your data layer. Used to compute, per trade,
--                   the benchmark return over the same holding window = the
--                   baseline you must beat for your analysis to have value.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS benchmark_price (
                                               symbol   TEXT NOT NULL,          -- e.g. 'SPY'
                                               date     TEXT NOT NULL,          -- ISO 8601
                                               close    REAL NOT NULL,
                                               PRIMARY KEY (symbol, date)
    );

-- ---------------------------------------------------------------------------
-- price_history : per-symbol daily closes, populated by your data layer.
--                 Used by the  analysis layer to compute the TRUE
--                 (correlation-adjusted) concentration of open positions —
--                 i.e. to catch "many tickers, one bet" that the uncorrelated
--                 SQL HHI cannot see. Same shape as benchmark_price.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS price_history (
                                             symbol   TEXT NOT NULL,
                                             date     TEXT NOT NULL,
                                             close    REAL NOT NULL,
                                             PRIMARY KEY (symbol, date)
    );

-- ---------------------------------------------------------------------------
-- account_snapshot : OPTIONAL periodic equity marks. Lets you compute true
--                    portfolio drawdown including open positions and deposits.
--                    The realized-trade equity curve (v_equity_curve) is the
--                    cleaner default; use this when you want mark-to-market.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS account_snapshot (
                                                account_id    INTEGER NOT NULL REFERENCES account(account_id),
    as_of         TEXT    NOT NULL,
    total_equity  REAL    NOT NULL,
    cash          REAL,
    notes         TEXT,
    PRIMARY KEY (account_id, as_of)
    );

-- Indexes for the common slice/aggregate patterns.
CREATE INDEX IF NOT EXISTS idx_trade_symbol   ON trade(symbol);
CREATE INDEX IF NOT EXISTS idx_trade_status   ON trade(status);
CREATE INDEX IF NOT EXISTS idx_trade_opened   ON trade(opened_at);
CREATE INDEX IF NOT EXISTS idx_trade_closed   ON trade(closed_at);
CREATE INDEX IF NOT EXISTS idx_leg_trade      ON trade_leg(trade_id);
CREATE INDEX IF NOT EXISTS idx_tag_trade      ON trade_tag(trade_id);
CREATE INDEX IF NOT EXISTS idx_tag_tag        ON trade_tag(tag, tag_category);

-- ============================================================================
-- SECTION 2 — DERIVATION VIEWS (the single source of computed truth)
-- ============================================================================

-- Per-leg realized P&L and entry notional, with the long/short sign applied.
DROP VIEW IF EXISTS v_leg_pnl;
CREATE VIEW v_leg_pnl AS
SELECT
    l.leg_id,
    l.trade_id,
    CASE l.side WHEN 'long' THEN 1 ELSE -1 END                  AS side_sign,
    l.quantity * l.entry_price * l.multiplier                   AS entry_notional,
    CASE
        WHEN l.exit_price IS NULL THEN NULL
        ELSE (CASE l.side WHEN 'long' THEN 1 ELSE -1 END)
                 * l.quantity * (l.exit_price - l.entry_price) * l.multiplier
            - COALESCE(l.entry_fees, 0) - COALESCE(l.exit_fees, 0)
        END                                                         AS realized_pnl
FROM trade_leg l;

-- Enriched per-trade view: the workhorse every metric reads from.
-- Adds realized_pnl (summed from legs), r_multiple, hold_days, risk_pct,
-- planned_rr, and is_win (NULL for exact scratch trades).
DROP VIEW IF EXISTS v_trade;
CREATE VIEW v_trade AS
WITH leg_agg AS (
    SELECT trade_id,
           SUM(realized_pnl)    AS realized_pnl,
           SUM(entry_notional)  AS gross_entry_notional
    FROM v_leg_pnl
    GROUP BY trade_id
),
     fee_agg AS (
         SELECT trade_id,
                SUM(COALESCE(entry_fees,0) + COALESCE(exit_fees,0)) AS total_fees
         FROM trade_leg
         GROUP BY trade_id
     )
SELECT
    t.*,
    la.realized_pnl,
    la.gross_entry_notional,
    fa.total_fees,
    CASE WHEN t.initial_risk > 0
             THEN la.realized_pnl / t.initial_risk END             AS r_multiple,
    CASE WHEN t.closed_at IS NOT NULL
             THEN CAST(julianday(t.closed_at) - julianday(t.opened_at) AS REAL)
        END                                                        AS hold_days,
    CASE WHEN t.account_value_at_entry > 0
             THEN t.initial_risk / t.account_value_at_entry END    AS risk_pct,
    CASE WHEN t.initial_risk > 0 AND t.planned_target_pnl IS NOT NULL
             THEN t.planned_target_pnl / t.initial_risk END        AS planned_rr,
    CASE
        WHEN la.realized_pnl > 0 THEN 1
        WHEN la.realized_pnl < 0 THEN 0
        ELSE NULL                                              -- exact scratch
        END                                                        AS is_win
FROM trade t
         LEFT JOIN leg_agg la ON la.trade_id = t.trade_id
         LEFT JOIN fee_agg fa ON fa.trade_id = t.trade_id;

-- Convenience: closed trades only (what most metrics operate on).
DROP VIEW IF EXISTS v_closed;
CREATE VIEW v_closed AS
SELECT * FROM v_trade WHERE status = 'closed' AND realized_pnl IS NOT NULL;

-- ============================================================================
-- SECTION 3 — PORTFOLIO-HEALTH METRICS
-- ============================================================================

-- Headline expectancy and quality ratios (in both R and dollars).
DROP VIEW IF EXISTS v_expectancy;
CREATE VIEW v_expectancy AS
SELECT
    COUNT(*)                                                   AS n_trades,
    AVG(CASE WHEN is_win = 1 THEN 1.0 ELSE 0 END)              AS win_rate,
    AVG(r_multiple)                                            AS expectancy_r,
    AVG(realized_pnl)                                          AS expectancy_dollar,
    SUM(realized_pnl)                                          AS total_pnl,
    AVG(CASE WHEN is_win = 1 THEN r_multiple END)             AS avg_win_r,
    AVG(CASE WHEN is_win = 0 THEN r_multiple END)             AS avg_loss_r,
    ABS( AVG(CASE WHEN is_win = 1 THEN r_multiple END)
        / NULLIF(AVG(CASE WHEN is_win = 0 THEN r_multiple END), 0) )
                                                               AS payoff_ratio_r,
    SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END)
        / NULLIF(-SUM(CASE WHEN realized_pnl < 0 THEN realized_pnl ELSE 0 END), 0)
                                                               AS profit_factor
FROM v_closed
WHERE r_multiple IS NOT NULL;

-- Distribution of outcomes in R (are wins big and losses capped near -1R?).
DROP VIEW IF EXISTS v_r_distribution;
CREATE VIEW v_r_distribution AS
SELECT
    CASE
        WHEN r_multiple <  -2 THEN '1: < -2R'
        WHEN r_multiple <  -1 THEN '2: -2R..-1R'
        WHEN r_multiple <   0 THEN '3: -1R..0'
        WHEN r_multiple <   1 THEN '4: 0..1R'
        WHEN r_multiple <   2 THEN '5: 1R..2R'
        WHEN r_multiple <   3 THEN '6: 2R..3R'
        ELSE                       '7: >= 3R'
        END                                                        AS r_bucket,
    COUNT(*)                                                   AS n,
    SUM(realized_pnl)                                          AS total_pnl
FROM v_closed
WHERE r_multiple IS NOT NULL
GROUP BY r_bucket
ORDER BY r_bucket;

-- Realized-trade equity curve with running peak and drawdown.
DROP VIEW IF EXISTS v_equity_curve;
CREATE VIEW v_equity_curve AS
WITH base AS (
    SELECT
        closed_at, trade_id, realized_pnl,
        SUM(realized_pnl) OVER (
            ORDER BY closed_at, trade_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )                                                      AS cum_pnl
    FROM v_closed
)
SELECT
    closed_at, trade_id, realized_pnl, cum_pnl,
    MAX(cum_pnl) OVER (
        ORDER BY closed_at, trade_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )                                                          AS running_peak,
    cum_pnl - MAX(cum_pnl) OVER (
        ORDER BY closed_at, trade_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )                                                          AS drawdown
FROM base;

DROP VIEW IF EXISTS v_max_drawdown;
CREATE VIEW v_max_drawdown AS
SELECT MIN(drawdown) AS max_drawdown FROM v_equity_curve;

DROP VIEW IF EXISTS v_current_drawdown;
CREATE VIEW v_current_drawdown AS
SELECT drawdown AS current_drawdown, cum_pnl, running_peak
FROM v_equity_curve
ORDER BY closed_at DESC, trade_id DESC
    LIMIT 1;

-- Open risk ("heat") right now: how much you could lose, and capital deployed.
DROP VIEW IF EXISTS v_open_risk;
CREATE VIEW v_open_risk AS
SELECT
    COUNT(*)                    AS open_positions,
    SUM(initial_risk)           AS total_open_risk,
    SUM(gross_entry_notional)   AS capital_deployed
FROM v_trade
WHERE status = 'open';

-- Position-sizing consistency. (stdev = sqrt(variance) in your app layer;
-- variance kept here to avoid depending on SQLite's math extension.)
DROP VIEW IF EXISTS v_sizing;
CREATE VIEW v_sizing AS
SELECT
    COUNT(risk_pct)             AS n,
    AVG(risk_pct)              AS avg_risk_pct,
    MAX(risk_pct)              AS max_risk_pct,
    CASE WHEN COUNT(risk_pct) > 1 THEN
             (SUM(risk_pct*risk_pct) - SUM(risk_pct)*SUM(risk_pct)/COUNT(risk_pct))
                 / (COUNT(risk_pct) - 1)
        END                         AS variance_risk_pct
FROM v_trade
WHERE risk_pct IS NOT NULL;

-- Concentration by SYMBOL among open positions, weighted by risk.
DROP VIEW IF EXISTS v_exposure_by_symbol;
CREATE VIEW v_exposure_by_symbol AS
SELECT
    symbol,
    COUNT(*)            AS positions,
    SUM(initial_risk)   AS risk,
    SUM(initial_risk)
        / NULLIF((SELECT SUM(initial_risk) FROM v_trade WHERE status='open'), 0)
                        AS risk_share
FROM v_trade
WHERE status = 'open'
GROUP BY symbol
ORDER BY risk DESC;

-- Concentration by THEME (macro/sector transmission factor) among open
-- positions. THIS is the direct check on the "many names, one bet" trap:
-- it shows how much of your open risk loads onto a single factor like ai_capex.
DROP VIEW IF EXISTS v_exposure_by_theme;
CREATE VIEW v_exposure_by_theme AS
SELECT
    tg.tag              AS theme,
    COUNT(DISTINCT t.trade_id) AS positions,
    SUM(t.initial_risk) AS risk,
    SUM(t.initial_risk)
        / NULLIF((SELECT SUM(initial_risk) FROM v_trade WHERE status='open'), 0)
        AS risk_share
FROM v_trade t
         JOIN trade_tag tg
              ON tg.trade_id = t.trade_id AND tg.tag_category = 'theme'
WHERE t.status = 'open'
GROUP BY tg.tag
ORDER BY risk DESC;

-- Herfindahl concentration index + "effective number of independent bets".
-- NOTE: treats positions as uncorrelated; a true correlation-adjusted version
-- needs a price-return matrix and lives in the  layer.
DROP VIEW IF EXISTS v_concentration;
CREATE VIEW v_concentration AS
SELECT
    SUM(risk_share * risk_share)                AS herfindahl_index,
    1.0 / NULLIF(SUM(risk_share * risk_share), 0) AS effective_positions
FROM v_exposure_by_symbol;

-- Cost drag: how much fees eat into gross results.
DROP VIEW IF EXISTS v_cost_drag;
CREATE VIEW v_cost_drag AS
SELECT
    SUM(total_fees)                                            AS total_fees,
    SUM(realized_pnl)                                          AS net_pnl,
    SUM(realized_pnl) + SUM(total_fees)                        AS gross_pnl_pre_fees,
    SUM(total_fees)
        / NULLIF(ABS(SUM(realized_pnl) + SUM(total_fees)), 0)    AS fee_pct_of_gross
FROM v_closed;

-- Implied Kelly fraction from realized edge vs. how much you actually risk.
-- Full Kelly is aggressive and assumes you've estimated edge perfectly; trade
-- a fraction of it. half_kelly column provided for convenience.
DROP VIEW IF EXISTS v_kelly;
CREATE VIEW v_kelly AS
SELECT
    e.win_rate                                                 AS win_rate,
    e.payoff_ratio_r                                           AS payoff_b,
    e.win_rate - (1 - e.win_rate) / NULLIF(e.payoff_ratio_r, 0)
                                                               AS full_kelly_fraction,
    0.5 * (e.win_rate - (1 - e.win_rate) / NULLIF(e.payoff_ratio_r, 0))
                                                               AS half_kelly_fraction,
    s.avg_risk_pct                                             AS actual_avg_risk_pct
FROM v_expectancy e
         CROSS JOIN v_sizing s;

-- ============================================================================
-- SECTION 4 — BEHAVIORAL ANALYSIS
-- ============================================================================

-- Rule adherence, and the P&L cost of breaking your own plan.
-- (Expect expectancy_when_broken to be worse — that gap is leakage.)
DROP VIEW IF EXISTS v_rule_adherence;
CREATE VIEW v_rule_adherence AS
SELECT
    AVG(followed_plan * 1.0)                                   AS adherence_rate,
    AVG(CASE WHEN followed_plan = 1 THEN r_multiple END)      AS expectancy_when_followed,
    AVG(CASE WHEN followed_plan = 0 THEN r_multiple END)      AS expectancy_when_broken
FROM v_closed
WHERE followed_plan IS NOT NULL AND r_multiple IS NOT NULL;

-- Expectancy by emotional state at entry (do FOMO/revenge trades bleed?).
DROP VIEW IF EXISTS v_by_emotion;
CREATE VIEW v_by_emotion AS
SELECT
    COALESCE(emotional_state, '(unlogged)')                   AS emotional_state,
    COUNT(*)                                                   AS n,
    AVG(r_multiple)                                            AS expectancy_r,
    AVG(CASE WHEN is_win = 1 THEN 1.0 ELSE 0 END)             AS win_rate
FROM v_closed
WHERE r_multiple IS NOT NULL
GROUP BY emotional_state
ORDER BY expectancy_r;

-- Planned vs. impulsive: does your process actually beat your impulses?
DROP VIEW IF EXISTS v_planned_vs_impulsive;
CREATE VIEW v_planned_vs_impulsive AS
SELECT
    COALESCE(trade_origin, '(unlogged)')                      AS trade_origin,
    COUNT(*)                                                   AS n,
    AVG(r_multiple)                                            AS expectancy_r,
    AVG(CASE WHEN is_win = 1 THEN 1.0 ELSE 0 END)             AS win_rate
FROM v_closed
WHERE r_multiple IS NOT NULL
GROUP BY trade_origin
ORDER BY expectancy_r;

-- Disposition effect: if you hold losers LONGER than winners, you are cutting
-- winners early and hoping on losers — the classic, costly retail reflex.
DROP VIEW IF EXISTS v_disposition;
CREATE VIEW v_disposition AS
SELECT
    AVG(CASE WHEN is_win = 1 THEN hold_days END)              AS avg_hold_winners,
    AVG(CASE WHEN is_win = 0 THEN hold_days END)              AS avg_hold_losers,
    AVG(CASE WHEN is_win = 1 THEN r_multiple END)            AS avg_r_winners,
    AVG(CASE WHEN is_win = 0 THEN r_multiple END)            AS avg_r_losers
FROM v_closed
WHERE hold_days IS NOT NULL;

-- Trade activity per ISO week (overtrading shows up as frequency spikes).
DROP VIEW IF EXISTS v_activity_by_week;
CREATE VIEW v_activity_by_week AS
SELECT
    strftime('%Y-%W', opened_at)  AS year_week,
    COUNT(*)                       AS trades_opened
FROM trade
WHERE opened_at IS NOT NULL
GROUP BY year_week
ORDER BY year_week;

-- Possible revenge trades: entries opened within 3 days AFTER a losing exit.
-- Best-effort flag; robust detection (size escalation, clustering) is .
DROP VIEW IF EXISTS v_post_loss_entries;
CREATE VIEW v_post_loss_entries AS
SELECT
    e.trade_id      AS entered_trade,
    e.symbol        AS entered_symbol,
    e.opened_at     AS entered_at,
    x.trade_id      AS prior_loss_trade,
    x.closed_at     AS prior_loss_closed_at,
    julianday(e.opened_at) - julianday(x.closed_at) AS days_after_loss
FROM trade e
         JOIN v_closed x
              ON x.is_win = 0
                  AND julianday(e.opened_at) > julianday(x.closed_at)
                  AND julianday(e.opened_at) - julianday(x.closed_at) <= 3;

-- ============================================================================
-- SECTION 5 — KNOWLEDGE-GAP ANALYSIS
-- ============================================================================

-- Calibration: bucket trades by stated confidence, compare to realized win
-- rate. A negative calibration_gap means you are OVERCONFIDENT in that band.
DROP VIEW IF EXISTS v_calibration;
CREATE VIEW v_calibration AS
SELECT
    CASE
        WHEN confidence_pct < 50 THEN '00-50'
        WHEN confidence_pct < 60 THEN '50-60'
        WHEN confidence_pct < 70 THEN '60-70'
        WHEN confidence_pct < 80 THEN '70-80'
        WHEN confidence_pct < 90 THEN '80-90'
        ELSE                          '90-100'
        END                                                        AS confidence_bucket,
    COUNT(*)                                                   AS n,
    AVG(confidence_pct) / 100.0                                AS avg_stated_confidence,
    AVG(CASE WHEN is_win = 1 THEN 1.0 ELSE 0 END)             AS realized_win_rate,
    AVG(CASE WHEN is_win = 1 THEN 1.0 ELSE 0 END)
        - AVG(confidence_pct) / 100.0                            AS calibration_gap
FROM v_closed
WHERE confidence_pct IS NOT NULL AND is_win IS NOT NULL
GROUP BY confidence_bucket
ORDER BY confidence_bucket;

-- Brier score: single-number forecast quality. 0 = perfect, 0.25 = no skill
-- (equivalent to always saying 50%). Lower is better.
DROP VIEW IF EXISTS v_brier;
CREATE VIEW v_brier AS
SELECT
    AVG( (confidence_pct/100.0 - is_win) * (confidence_pct/100.0 - is_win) )
                                                               AS brier_score,
    COUNT(*)                                                   AS n_scored
FROM v_closed
WHERE confidence_pct IS NOT NULL AND is_win IS NOT NULL;

-- Where your losses come from. Sort by total_pnl to see the costliest modes.
DROP VIEW IF EXISTS v_failure_modes;
CREATE VIEW v_failure_modes AS
SELECT
    COALESCE(exit_reason, '(unlogged)')                       AS exit_reason,
    COUNT(*)                                                   AS n,
    SUM(realized_pnl)                                          AS total_pnl,
    AVG(r_multiple)                                            AS avg_r
FROM v_closed
GROUP BY exit_reason
ORDER BY total_pnl;

-- The four-quadrant diagnostic — the most important gap-finder.
--   thesis_right + made_money  -> skill working as intended
--   thesis_right + lost_money  -> EXECUTION problem (timing/sizing/stops)
--   thesis_wrong + made_money  -> LUCK (don't bank on it)
--   thesis_wrong + lost_money  -> ANALYSIS problem (the gap to study)
DROP VIEW IF EXISTS v_thesis_vs_outcome;
CREATE VIEW v_thesis_vs_outcome AS
SELECT
    CASE WHEN thesis_correct = 1 THEN 'thesis_right' ELSE 'thesis_wrong' END AS thesis,
    CASE WHEN is_win = 1 THEN 'made_money' ELSE 'lost_money' END             AS outcome,
    COUNT(*)            AS n,
    AVG(r_multiple)     AS avg_r,
    SUM(realized_pnl)   AS total_pnl
FROM v_closed
WHERE thesis_correct IS NOT NULL AND is_win IS NOT NULL
GROUP BY thesis, outcome;

-- Expectancy by SETUP tag: which patterns are real edge vs. anti-edge to drop.
DROP VIEW IF EXISTS v_expectancy_by_setup;
CREATE VIEW v_expectancy_by_setup AS
SELECT
    tg.tag              AS setup,
    COUNT(*)            AS n,
    AVG(t.r_multiple)   AS expectancy_r,
    AVG(CASE WHEN t.is_win = 1 THEN 1.0 ELSE 0 END) AS win_rate,
    SUM(t.realized_pnl) AS total_pnl
FROM v_closed t
         JOIN trade_tag tg
              ON tg.trade_id = t.trade_id AND tg.tag_category = 'setup'
WHERE t.r_multiple IS NOT NULL
GROUP BY tg.tag
ORDER BY expectancy_r DESC;

-- ============================================================================
-- SECTION 6 — BASELINE (did your analysis beat just holding the index?)
-- ============================================================================
-- Per closed trade, benchmark return over the SAME holding window.
-- Compare trade_return_on_notional vs bench_return. Aggregate alpha and the
-- random-entry comparison belong in the  layer; this is the primitive.
-- Date alignment assumes exact trading-day matches in benchmark_price; the
-- analysis layer should snap to nearest trading day.
DROP VIEW IF EXISTS v_trade_vs_benchmark;
CREATE VIEW v_trade_vs_benchmark AS
SELECT
    t.trade_id,
    t.symbol,
    t.opened_at,
    t.closed_at,
    t.r_multiple,
    t.realized_pnl / NULLIF(t.gross_entry_notional, 0)        AS trade_return_on_notional,
    bo.close                                                   AS bench_open,
    bc.close                                                   AS bench_close,
    (bc.close - bo.close) / NULLIF(bo.close, 0)               AS bench_return
FROM v_closed t
         LEFT JOIN benchmark_price bo
                   ON bo.symbol = 'SPY' AND bo.date = date(t.opened_at)
        LEFT JOIN benchmark_price bc
        ON bc.symbol = 'SPY' AND bc.date = date(t.closed_at);

-- ============================================================================
-- SECTION 7 — ONE-ROW DASHBOARD (headline portfolio-health snapshot)
-- ============================================================================
DROP VIEW IF EXISTS v_dashboard;
CREATE VIEW v_dashboard AS
SELECT
    e.n_trades,
    e.win_rate,
    e.expectancy_r,
    e.expectancy_dollar,
    e.total_pnl,
    e.payoff_ratio_r,
    e.profit_factor,
    d.max_drawdown,
    cd.current_drawdown,
    o.open_positions,
    o.total_open_risk,
    o.capital_deployed,
    c.effective_positions,
    b.brier_score
FROM v_expectancy e
         CROSS JOIN v_max_drawdown      d
         CROSS JOIN v_current_drawdown  cd
         CROSS JOIN v_open_risk         o
         CROSS JOIN v_concentration     c
         CROSS JOIN v_brier             b;

-- ============================================================================
-- SECTION 8 — EXAMPLE USAGE (delete or keep as reference)
-- ============================================================================
-- An equity trade (one leg) and a put-credit spread (two legs), showing how
-- the entry prediction + behavioral fields + legs fit together.
--
-- INSERT INTO account (account_id, name) VALUES (1, 'Practice');
--
-- -- 1) Long equity, came from the screener, planned, hit target ------------
-- INSERT INTO trade
--   (trade_id, account_id, symbol, instrument_type, direction, strategy_type,
--    source_type, source_ref, status, opened_at, closed_at, planned_hold_days,
--    initial_risk, planned_target_pnl, account_value_at_entry,
--    thesis, confidence_pct, invalidation,
--    entry_underlying_price, market_regime,
--    emotional_state, trade_origin, followed_plan,
--    exit_reason, exit_followed_plan, thesis_correct)
-- VALUES
--   (1, 1, 'NOK', 'equity', 'long', 'long_equity',
--    'screener', 'cand_2026_06_01_017', 'closed', '2026-06-01', '2026-06-09', 10,
--    200, 400, 5000,
--    'Oversold bounce into earnings; AI-capex tailwind underpriced', 65,
--    'Close below 3.80 on volume',
--    4.05, 'risk_on',
--    'calm', 'planned', 1,
--    'target_hit', 1, 1);
-- INSERT INTO trade_leg
--   (trade_id, leg_type, side, quantity, multiplier, entry_price, exit_price, entry_fees, exit_fees)
-- VALUES
--   (1, 'equity', 'long', 100, 1, 4.05, 4.55, 0, 0);
-- INSERT INTO trade_tag (trade_id, tag, tag_category) VALUES
--   (1, 'mean_reversion', 'setup'),
--   (1, 'ai_capex',       'theme');
--
-- -- 2) Put credit spread (short 1 put, long 1 lower put) -------------------
-- INSERT INTO trade
--   (trade_id, account_id, symbol, instrument_type, direction, strategy_type,
--    source_type, status, opened_at, closed_at,
--    initial_risk, planned_target_pnl, account_value_at_entry,
--    thesis, confidence_pct, invalidation,
--    iv_rank_at_entry, emotional_state, trade_origin, followed_plan,
--    exit_reason, exit_followed_plan, thesis_correct)
-- VALUES
--   (2, 1, 'XYZ', 'option', 'neutral', 'vertical',
--    'discretionary', 'closed', '2026-05-20', '2026-06-03',
--    400, 100, 5000,
--    'Elevated IV rank; sell premium above support', 70,
--    'Underlying breaks support at 95',
--    82, 'confident', 'planned', 1,
--    'discretionary_profit_take', 1, 1);
-- INSERT INTO trade_leg
--   (trade_id, leg_type, side, quantity, multiplier, strike, expiry,
--    entry_price, exit_price, entry_fees, exit_fees, entry_delta, dte_at_entry)
-- VALUES
--   (2, 'put', 'short', 1, 100, 100, '2026-06-20', 5.00, 2.00, 0.65, 0.65, -0.30, 31),
--   (2, 'put', 'long',  1, 100,  95, '2026-06-20', 1.00, 0.40, 0.65, 0.65, -0.15, 31);
-- INSERT INTO trade_tag (trade_id, tag, tag_category) VALUES
--   (2, 'premium_selling', 'setup'),
--   (2, 'high_iv_rank',    'setup');
--
-- Then inspect:  SELECT * FROM v_dashboard;
--                SELECT * FROM v_calibration;
--                SELECT * FROM v_thesis_vs_outcome;
--                SELECT * FROM v_exposure_by_theme;
-- ============================================================================