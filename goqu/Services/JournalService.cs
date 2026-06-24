using System;
using System.Collections.Generic;
using System.Linq;
using goqu.Models;
using Microsoft.Data.Sqlite;

namespace goqu.Services;

public class JournalService
{
    private readonly string _dbPath;
    private readonly long _accountId;

    public JournalService(string dbPath, long accountId)
    {
        _dbPath = dbPath;
        _accountId = accountId;
    }

    private SqliteConnection Open()
    {
        var c = new SqliteConnection($"Data Source={_dbPath}");
        c.Open();
        return c;
    }

    private void EnsureSchema()
    {
        using var c = Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS account (
                account_id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                base_currency TEXT NOT NULL DEFAULT 'USD', opened_at TEXT, notes TEXT);
            CREATE TABLE IF NOT EXISTS trade (
                trade_id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES account(account_id),
                symbol TEXT NOT NULL, instrument_type TEXT NOT NULL DEFAULT 'equity'
                    CHECK(instrument_type IN('equity','option','etf','future','other')),
                direction TEXT NOT NULL CHECK(direction IN('long','short','neutral')),
                strategy_type TEXT,
                source_type TEXT DEFAULT 'discretionary'
                    CHECK(source_type IN('discretionary','screener','research','tip','other')),
                status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','closed','rolled')),
                opened_at TEXT NOT NULL, closed_at TEXT, planned_hold_days INTEGER,
                initial_risk REAL NOT NULL, planned_stop REAL, planned_target REAL,
                planned_target_pnl REAL, account_value_at_entry REAL,
                thesis TEXT, confidence_pct REAL CHECK(confidence_pct BETWEEN 0 AND 100),
                conviction INTEGER CHECK(conviction BETWEEN 1 AND 5), invalidation TEXT,
                entry_underlying_price REAL, iv_at_entry REAL, iv_rank_at_entry REAL,
                vix_at_entry REAL, market_regime TEXT,
                emotional_state TEXT CHECK(emotional_state IN('calm','confident','fomo','revenge','bored','anxious','fearful')),
                trade_origin TEXT CHECK(trade_origin IN('planned','impulsive')),
                followed_plan INTEGER CHECK(followed_plan IN(0,1)), rule_broken TEXT,
                exit_reason TEXT CHECK(exit_reason IN('target_hit','stop_hit','time_stop',
                    'thesis_invalidated','thesis_wrong_timing','mis_sized','regime_shift',
                    'exogenous_shock','discretionary_panic','discretionary_profit_take',
                    'rolled','expired','assigned')),
                exit_followed_plan INTEGER CHECK(exit_followed_plan IN(0,1)),
                thesis_correct INTEGER CHECK(thesis_correct IN(0,1)), notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS trade_leg (
                leg_id INTEGER PRIMARY KEY, trade_id INTEGER NOT NULL REFERENCES trade(trade_id) ON DELETE CASCADE,
                leg_type TEXT NOT NULL CHECK(leg_type IN('equity','call','put')),
                side TEXT NOT NULL CHECK(side IN('long','short')),
                quantity REAL NOT NULL CHECK(quantity > 0), multiplier REAL NOT NULL DEFAULT 1,
                strike REAL, expiry TEXT, entry_price REAL NOT NULL, exit_price REAL,
                entry_fees REAL DEFAULT 0, exit_fees REAL DEFAULT 0,
                entry_delta REAL, entry_theta REAL, entry_vega REAL, entry_iv REAL, dte_at_entry INTEGER);
            CREATE TABLE IF NOT EXISTS trade_tag (
                trade_id INTEGER NOT NULL REFERENCES trade(trade_id) ON DELETE CASCADE,
                tag TEXT NOT NULL, tag_category TEXT NOT NULL CHECK(tag_category IN('setup','mistake','theme')),
                PRIMARY KEY(trade_id, tag, tag_category));
            CREATE TABLE IF NOT EXISTS benchmark_price (
                symbol TEXT NOT NULL, date TEXT NOT NULL, close REAL NOT NULL, PRIMARY KEY(symbol,date));
            CREATE TABLE IF NOT EXISTS price_history (
                symbol TEXT NOT NULL, date TEXT NOT NULL, close REAL NOT NULL, PRIMARY KEY(symbol,date));
            CREATE TABLE IF NOT EXISTS account_snapshot (
                account_id INTEGER NOT NULL REFERENCES account(account_id),
                as_of TEXT NOT NULL, total_equity REAL NOT NULL, cash REAL, notes TEXT,
                PRIMARY KEY(account_id, as_of));
            CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE INDEX IF NOT EXISTS idx_trade_symbol ON trade(symbol);
            CREATE INDEX IF NOT EXISTS idx_trade_status ON trade(status);
            CREATE INDEX IF NOT EXISTS idx_trade_opened ON trade(opened_at);
            CREATE INDEX IF NOT EXISTS idx_leg_trade ON trade_leg(trade_id);
            """;
        cmd.ExecuteNonQuery();
    }

    // ── Dashboard stats ──────────────────────────────────────────────────────

    public DashboardStats GetStats()
    {
        using var c = Open();

        var stats = new DashboardStats();

        // Counts and open-position totals
        using (var cmd = c.CreateCommand())
        {
            cmd.CommandText = """
                SELECT COUNT(*),
                       COALESCE(SUM(CASE WHEN status='open' THEN 1 ELSE 0 END), 0),
                       COALESCE(SUM(CASE WHEN status='open' THEN initial_risk ELSE 0 END), 0)
                FROM trade WHERE account_id=$aid
                """;
            cmd.Parameters.AddWithValue("$aid", _accountId);
            using var r = cmd.ExecuteReader();
            if (r.Read())
            {
                stats.NTrades = r.GetInt64(0);
                stats.OpenPositions = r.GetInt64(1);
                stats.TotalOpenRisk = r.GetDouble(2);
            }
        }

        // Per-trade P&L for closed trades — computed in C# to avoid complex nested SQL
        var tradePnls = new System.Collections.Generic.List<(double pnl, double risk)>();
        using (var cmd = c.CreateCommand())
        {
            cmd.CommandText = """
                SELECT t.initial_risk,
                       SUM(CASE WHEN tl.side='long' THEN 1.0 ELSE -1.0 END
                           * tl.quantity * (tl.exit_price - tl.entry_price) * tl.multiplier
                           - COALESCE(tl.entry_fees,0) - COALESCE(tl.exit_fees,0)) AS pnl
                FROM trade t
                JOIN trade_leg tl ON tl.trade_id = t.trade_id
                WHERE t.account_id=$aid AND t.status='closed' AND tl.exit_price IS NOT NULL
                GROUP BY t.trade_id, t.initial_risk
                ORDER BY t.closed_at
                """;
            cmd.Parameters.AddWithValue("$aid", _accountId);
            using var r = cmd.ExecuteReader();
            while (r.Read())
                tradePnls.Add((r.GetDouble(1), r.GetDouble(0)));
        }

        if (tradePnls.Count > 0)
        {
            int wins = tradePnls.Count(x => x.pnl > 0);
            stats.WinRate = (double)wins / tradePnls.Count;
            stats.TotalPnl = tradePnls.Sum(x => x.pnl);
            stats.ExpectancyDollar = stats.TotalPnl / tradePnls.Count;

            var rMultiples = tradePnls.Where(x => x.risk > 0).Select(x => x.pnl / x.risk).ToList();
            stats.ExpectancyR = rMultiples.Count > 0 ? rMultiples.Average() : 0;

            double grossWin  = tradePnls.Where(x => x.pnl > 0).Sum(x => x.pnl);
            double grossLoss = Math.Abs(tradePnls.Where(x => x.pnl < 0).Sum(x => x.pnl));
            stats.ProfitFactor = grossLoss > 0 ? grossWin / grossLoss : 0;

            // Max drawdown from running cumulative P&L
            double cum = 0, peak = 0, maxDD = 0;
            foreach (var (pnl, _) in tradePnls)
            {
                cum += pnl;
                if (cum > peak) peak = cum;
                double dd = cum - peak;
                if (dd < maxDD) maxDD = dd;
            }
            stats.MaxDrawdown = maxDD;
        }

        return stats;
    }

    // ── Trade queries ────────────────────────────────────────────────────────

    public List<TradeRecord> GetOpenTrades()
    {
        using var c = Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = """
            SELECT trade_id, symbol, instrument_type, direction, strategy_type,
                   status, opened_at, initial_risk, account_value_at_entry, thesis,
                   confidence_pct, emotional_state, trade_origin
            FROM trade WHERE account_id=$aid AND status='open'
            ORDER BY opened_at DESC
            """;
        cmd.Parameters.AddWithValue("$aid", _accountId);
        return ReadTradeList(cmd);
    }

    public List<TradeRecord> GetRecentClosed(int limit = 10)
    {
        using var c = Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = $"""
            SELECT t.trade_id, t.symbol, t.instrument_type, t.direction, t.strategy_type,
                   t.status, t.opened_at, t.closed_at, t.initial_risk, t.thesis,
                   t.exit_reason, t.thesis_correct, t.followed_plan,
                   COALESCE(legs.pnl, 0) AS realized_pnl,
                   CASE WHEN t.initial_risk > 0 THEN COALESCE(legs.pnl,0)/t.initial_risk END AS r_multiple,
                   CASE WHEN COALESCE(legs.pnl,0)>0 THEN 1 WHEN COALESCE(legs.pnl,0)<0 THEN 0 END AS is_win
            FROM trade t
            LEFT JOIN (
                SELECT tl.trade_id,
                    SUM(CASE WHEN tl.side='long' THEN 1 ELSE -1 END
                        * tl.quantity*(tl.exit_price-tl.entry_price)*tl.multiplier
                        - COALESCE(tl.entry_fees,0)-COALESCE(tl.exit_fees,0)) AS pnl
                FROM trade_leg tl WHERE tl.exit_price IS NOT NULL GROUP BY tl.trade_id
            ) legs ON legs.trade_id = t.trade_id
            WHERE t.account_id=$aid AND t.status='closed'
            ORDER BY t.closed_at DESC LIMIT {limit}
            """;
        cmd.Parameters.AddWithValue("$aid", _accountId);
        return ReadTradeListFull(cmd);
    }

    public List<TradeRecord> GetAllTrades()
    {
        using var c = Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = """
            SELECT t.trade_id, t.symbol, t.instrument_type, t.direction, t.strategy_type,
                   t.status, t.opened_at, t.closed_at, t.initial_risk, t.thesis,
                   t.exit_reason, t.thesis_correct, t.followed_plan,
                   COALESCE(legs.pnl, 0) AS realized_pnl,
                   CASE WHEN t.initial_risk>0 THEN COALESCE(legs.pnl,0)/t.initial_risk END AS r_multiple,
                   CASE WHEN COALESCE(legs.pnl,0)>0 THEN 1 WHEN COALESCE(legs.pnl,0)<0 THEN 0 END AS is_win
            FROM trade t
            LEFT JOIN (
                SELECT tl.trade_id,
                    SUM(CASE WHEN tl.side='long' THEN 1 ELSE -1 END
                        * tl.quantity*(tl.exit_price-tl.entry_price)*tl.multiplier
                        - COALESCE(tl.entry_fees,0)-COALESCE(tl.exit_fees,0)) AS pnl
                FROM trade_leg tl WHERE tl.exit_price IS NOT NULL GROUP BY tl.trade_id
            ) legs ON legs.trade_id = t.trade_id
            WHERE t.account_id=$aid
            ORDER BY t.opened_at DESC
            """;
        cmd.Parameters.AddWithValue("$aid", _accountId);
        return ReadTradeListFull(cmd);
    }

    private static List<TradeRecord> ReadTradeList(SqliteCommand cmd)
    {
        var list = new List<TradeRecord>();
        using var r = cmd.ExecuteReader();
        while (r.Read())
        {
            list.Add(new TradeRecord
            {
                TradeId = r.GetInt64(0),
                Symbol = r.IsDBNull(1) ? "" : r.GetString(1),
                InstrumentType = r.IsDBNull(2) ? "equity" : r.GetString(2),
                Direction = r.IsDBNull(3) ? "long" : r.GetString(3),
                StrategyType = r.IsDBNull(4) ? null : r.GetString(4),
                Status = r.IsDBNull(5) ? "open" : r.GetString(5),
                OpenedAt = r.IsDBNull(6) ? "" : r.GetString(6),
                InitialRisk = r.IsDBNull(7) ? 0 : (decimal)r.GetDouble(7),
                AccountValueAtEntry = r.IsDBNull(8) ? null : (decimal?)r.GetDouble(8),
                Thesis = r.IsDBNull(9) ? null : r.GetString(9),
                ConfidencePct = r.IsDBNull(10) ? null : (decimal?)r.GetDouble(10),
                EmotionalState = r.IsDBNull(11) ? null : r.GetString(11),
                TradeOrigin = r.IsDBNull(12) ? null : r.GetString(12),
            });
        }
        return list;
    }

    private static List<TradeRecord> ReadTradeListFull(SqliteCommand cmd)
    {
        var list = new List<TradeRecord>();
        using var r = cmd.ExecuteReader();
        while (r.Read())
        {
            list.Add(new TradeRecord
            {
                TradeId = r.GetInt64(0),
                Symbol = r.IsDBNull(1) ? "" : r.GetString(1),
                InstrumentType = r.IsDBNull(2) ? "equity" : r.GetString(2),
                Direction = r.IsDBNull(3) ? "long" : r.GetString(3),
                StrategyType = r.IsDBNull(4) ? null : r.GetString(4),
                Status = r.IsDBNull(5) ? "open" : r.GetString(5),
                OpenedAt = r.IsDBNull(6) ? "" : r.GetString(6),
                ClosedAt = r.IsDBNull(7) ? null : r.GetString(7),
                InitialRisk = r.IsDBNull(8) ? 0 : (decimal)r.GetDouble(8),
                Thesis = r.IsDBNull(9) ? null : r.GetString(9),
                ExitReason = r.IsDBNull(10) ? null : r.GetString(10),
                ThesisCorrect = r.IsDBNull(11) ? null : (int?)r.GetInt32(11),
                FollowedPlan = r.IsDBNull(12) ? null : (int?)r.GetInt32(12),
                RealizedPnl = r.IsDBNull(13) ? null : (decimal?)r.GetDouble(13),
                RMultiple = r.IsDBNull(14) ? null : (decimal?)r.GetDouble(14),
                IsWin = r.IsDBNull(15) ? null : (int?)r.GetInt32(15),
            });
        }
        return list;
    }

    // ── Analytics queries ────────────────────────────────────────────────────

    public List<AnalyticsRow> GetByEmotion()
    {
        using var c = Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = """
            WITH legs AS (
                SELECT tl.trade_id,
                    SUM(CASE WHEN tl.side='long' THEN 1 ELSE -1 END
                        * tl.quantity*(tl.exit_price-tl.entry_price)*tl.multiplier
                        - COALESCE(tl.entry_fees,0)-COALESCE(tl.exit_fees,0)) AS pnl
                FROM trade_leg tl WHERE tl.exit_price IS NOT NULL GROUP BY tl.trade_id)
            SELECT COALESCE(t.emotional_state,'(unlogged)') AS state,
                   COUNT(*) AS n,
                   COALESCE(AVG(CASE WHEN t.initial_risk>0 THEN l.pnl/t.initial_risk END),0) AS expect_r,
                   COALESCE(AVG(CASE WHEN l.pnl>0 THEN 1.0 ELSE 0 END),0) AS win_rate,
                   COALESCE(SUM(l.pnl),0) AS total_pnl
            FROM trade t LEFT JOIN legs l ON l.trade_id=t.trade_id
            WHERE t.account_id=$aid AND t.status='closed'
            GROUP BY state ORDER BY expect_r
            """;
        cmd.Parameters.AddWithValue("$aid", _accountId);
        return ReadAnalyticsRows(cmd);
    }

    public List<AnalyticsRow> GetBySetup()
    {
        using var c = Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = """
            WITH legs AS (
                SELECT tl.trade_id,
                    SUM(CASE WHEN tl.side='long' THEN 1 ELSE -1 END
                        * tl.quantity*(tl.exit_price-tl.entry_price)*tl.multiplier
                        - COALESCE(tl.entry_fees,0)-COALESCE(tl.exit_fees,0)) AS pnl
                FROM trade_leg tl WHERE tl.exit_price IS NOT NULL GROUP BY tl.trade_id)
            SELECT COALESCE(tg.tag,'(untagged)') AS setup,
                   COUNT(*) AS n,
                   COALESCE(AVG(CASE WHEN t.initial_risk>0 THEN l.pnl/t.initial_risk END),0) AS expect_r,
                   COALESCE(AVG(CASE WHEN l.pnl>0 THEN 1.0 ELSE 0 END),0) AS win_rate,
                   COALESCE(SUM(l.pnl),0) AS total_pnl
            FROM trade t
            LEFT JOIN legs l ON l.trade_id=t.trade_id
            LEFT JOIN trade_tag tg ON tg.trade_id=t.trade_id AND tg.tag_category='setup'
            WHERE t.account_id=$aid AND t.status='closed'
            GROUP BY setup ORDER BY expect_r DESC
            """;
        cmd.Parameters.AddWithValue("$aid", _accountId);
        return ReadAnalyticsRows(cmd);
    }

    public List<RDistributionRow> GetRDistribution()
    {
        using var c = Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = """
            WITH legs AS (
                SELECT tl.trade_id,
                    SUM(CASE WHEN tl.side='long' THEN 1 ELSE -1 END
                        * tl.quantity*(tl.exit_price-tl.entry_price)*tl.multiplier
                        - COALESCE(tl.entry_fees,0)-COALESCE(tl.exit_fees,0)) AS pnl
                FROM trade_leg tl WHERE tl.exit_price IS NOT NULL GROUP BY tl.trade_id),
            r AS (
                SELECT CASE WHEN t.initial_risk>0 THEN l.pnl/t.initial_risk END AS r_mult,
                       l.pnl
                FROM trade t JOIN legs l ON l.trade_id=t.trade_id
                WHERE t.account_id=$aid AND t.status='closed' AND t.initial_risk>0)
            SELECT CASE
                WHEN r_mult < -2 THEN '< -2R'
                WHEN r_mult < -1 THEN '-2..-1R'
                WHEN r_mult <  0 THEN '-1..0R'
                WHEN r_mult <  1 THEN '0..1R'
                WHEN r_mult <  2 THEN '1..2R'
                WHEN r_mult <  3 THEN '2..3R'
                ELSE '>= 3R' END AS bucket,
                COUNT(*) AS n, COALESCE(SUM(pnl),0) AS total_pnl
            FROM r GROUP BY bucket ORDER BY bucket
            """;
        cmd.Parameters.AddWithValue("$aid", _accountId);
        var rows = new List<RDistributionRow>();
        using var r2 = cmd.ExecuteReader();
        int maxN = 1;
        var raw = new List<(string b, int n, double pnl)>();
        while (r2.Read())
        {
            int n = r2.GetInt32(1);
            raw.Add((r2.GetString(0), n, r2.GetDouble(2)));
            if (n > maxN) maxN = n;
        }
        foreach (var (b, n, pnl) in raw)
            rows.Add(new RDistributionRow { Bucket = b, N = n, TotalPnl = pnl, BarWidth = (int)(20.0 * n / maxN) });
        return rows;
    }

    private static List<AnalyticsRow> ReadAnalyticsRows(SqliteCommand cmd)
    {
        var list = new List<AnalyticsRow>();
        using var r = cmd.ExecuteReader();
        while (r.Read())
            list.Add(new AnalyticsRow
            {
                Label = r.IsDBNull(0) ? "" : r.GetString(0),
                N = r.GetInt32(1),
                ExpectancyR = r.GetDouble(2),
                WinRate = r.GetDouble(3),
                TotalPnl = r.GetDouble(4),
            });
        return list;
    }

    // ── Write operations ─────────────────────────────────────────────────────

    public long InsertTrade(TradeRecord t, TradeLeg leg, List<(string tag, string cat)>? tags = null)
    {
        using var c = Open();
        using var tx = c.BeginTransaction();

        using var cmd = c.CreateCommand();
        cmd.Transaction = tx;
        cmd.CommandText = """
            INSERT INTO trade (account_id, symbol, instrument_type, direction, strategy_type,
                source_type, status, opened_at, planned_hold_days, initial_risk, planned_stop,
                planned_target, planned_target_pnl, account_value_at_entry, thesis, confidence_pct,
                conviction, invalidation, entry_underlying_price, iv_at_entry, iv_rank_at_entry,
                vix_at_entry, emotional_state, trade_origin, followed_plan)
            VALUES ($aid,$sym,$itype,$dir,$strat,$src,'open',$opened,$hold,$risk,$stop,$tgt,
                    $tgtpnl,$acct,$thesis,$conf,$conv,$inval,$uprice,$iv,$ivr,$vix,$emo,$org,$fplan)
            RETURNING trade_id
            """;
        Param(cmd, "$aid", _accountId);
        Param(cmd, "$sym", t.Symbol.ToUpperInvariant());
        Param(cmd, "$itype", t.InstrumentType);
        Param(cmd, "$dir", t.Direction);
        Param(cmd, "$strat", t.StrategyType);
        Param(cmd, "$src", t.SourceType);
        Param(cmd, "$opened", t.OpenedAt);
        Param(cmd, "$hold", t.PlannedHoldDays);
        Param(cmd, "$risk", (double)t.InitialRisk);
        Param(cmd, "$stop", t.PlannedStop);
        Param(cmd, "$tgt", t.PlannedTarget);
        Param(cmd, "$tgtpnl", t.PlannedTargetPnl);
        Param(cmd, "$acct", t.AccountValueAtEntry);
        Param(cmd, "$thesis", t.Thesis);
        Param(cmd, "$conf", t.ConfidencePct);
        Param(cmd, "$conv", t.Conviction);
        Param(cmd, "$inval", t.Invalidation);
        Param(cmd, "$uprice", t.EntryUnderlyingPrice);
        Param(cmd, "$iv", t.IvAtEntry);
        Param(cmd, "$ivr", t.IvRankAtEntry);
        Param(cmd, "$vix", t.VixAtEntry);
        Param(cmd, "$emo", t.EmotionalState);
        Param(cmd, "$org", t.TradeOrigin);
        Param(cmd, "$fplan", t.FollowedPlan);

        var tradeId = (long)cmd.ExecuteScalar()!;

        using var legCmd = c.CreateCommand();
        legCmd.Transaction = tx;
        legCmd.CommandText = """
            INSERT INTO trade_leg (trade_id, leg_type, side, quantity, multiplier,
                strike, expiry, entry_price, entry_fees,
                entry_delta, entry_theta, entry_vega, entry_iv, dte_at_entry)
            VALUES ($tid,$ltype,$side,$qty,$mult,$strike,$expiry,$price,$fees,
                    $delta,$theta,$vega,$iv,$dte)
            """;
        Param(legCmd, "$tid", tradeId);
        Param(legCmd, "$ltype", leg.LegType);
        Param(legCmd, "$side", leg.Side);
        Param(legCmd, "$qty", (double)leg.Quantity);
        Param(legCmd, "$mult", (double)leg.Multiplier);
        Param(legCmd, "$strike", leg.Strike);
        Param(legCmd, "$expiry", leg.Expiry);
        Param(legCmd, "$price", (double)leg.EntryPrice);
        Param(legCmd, "$fees", (double)leg.EntryFees);
        Param(legCmd, "$delta", leg.EntryDelta);
        Param(legCmd, "$theta", leg.EntryTheta);
        Param(legCmd, "$vega", leg.EntryVega);
        Param(legCmd, "$iv", leg.EntryIv);
        Param(legCmd, "$dte", leg.DteAtEntry);
        legCmd.ExecuteNonQuery();

        if (tags is { Count: > 0 })
        {
            using var tagCmd = c.CreateCommand();
            tagCmd.Transaction = tx;
            tagCmd.CommandText = "INSERT OR IGNORE INTO trade_tag(trade_id,tag,tag_category) VALUES($tid,$tag,$cat)";
            tagCmd.Parameters.AddWithValue("$tid", tradeId);
            tagCmd.Parameters.Add("$tag", SqliteType.Text);
            tagCmd.Parameters.Add("$cat", SqliteType.Text);
            foreach (var (tag, cat) in tags)
            {
                tagCmd.Parameters["$tag"].Value = tag;
                tagCmd.Parameters["$cat"].Value = cat;
                tagCmd.ExecuteNonQuery();
            }
        }

        tx.Commit();
        return tradeId;
    }

    public void CloseTrade(long tradeId, string exitReason, decimal exitPrice, decimal exitFees,
        int exitFollowedPlan, int? thesisCorrect, string? notes)
    {
        using var c = Open();
        using var tx = c.BeginTransaction();

        using var cmd = c.CreateCommand();
        cmd.Transaction = tx;
        cmd.CommandText = """
            UPDATE trade SET
                status='closed', closed_at=$date, exit_reason=$reason,
                exit_followed_plan=$efp, thesis_correct=$tc, notes=COALESCE($notes, notes),
                updated_at=CURRENT_TIMESTAMP
            WHERE trade_id=$tid AND account_id=$aid
            """;
        Param(cmd, "$date", DateTime.Today.ToString("yyyy-MM-dd"));
        Param(cmd, "$reason", exitReason);
        Param(cmd, "$efp", exitFollowedPlan);
        Param(cmd, "$tc", thesisCorrect);
        Param(cmd, "$notes", notes);
        Param(cmd, "$tid", tradeId);
        Param(cmd, "$aid", _accountId);
        cmd.ExecuteNonQuery();

        // Update legs — for equity single-leg, update first leg
        using var legCmd = c.CreateCommand();
        legCmd.Transaction = tx;
        legCmd.CommandText = """
            UPDATE trade_leg SET exit_price=$price, exit_fees=$fees
            WHERE trade_id=$tid
            """;
        Param(legCmd, "$price", (double)exitPrice);
        Param(legCmd, "$fees", (double)exitFees);
        Param(legCmd, "$tid", tradeId);
        legCmd.ExecuteNonQuery();

        tx.Commit();
    }

    private static void Param(SqliteCommand cmd, string name, object? value)
        => cmd.Parameters.AddWithValue(name, value ?? DBNull.Value);
}
