using System;
using System.Collections.Generic;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using goqu.Services;
using Microsoft.Data.Sqlite;

namespace goqu.Views.QuantAnalysis;

public record CalibrationRow(
    string Bucket,
    int N,
    int Wins,
    string ActualRate,
    IBrush RateColor,
    string Deviation,
    IBrush DeviationColor
);

public record BehavioralRow(
    string EmotionalState,
    int N,
    string WinRate,
    string AvgR,
    IBrush StateColor,
    IBrush AvgRColor
);

public record ConcentrationRow(
    string Label,
    string Risk,
    string PctOfTotal,
    string RiskLabel,
    IBrush BarColor
);

public partial class QuantAnalysisView : UserControl
{
    private static readonly IBrush GreenFg  = new SolidColorBrush(Color.Parse("#038C4C"));
    private static readonly IBrush RedFg    = new SolidColorBrush(Color.Parse("#BF1B1B"));
    private static readonly IBrush YellowFg = new SolidColorBrush(Color.Parse("#FFE101"));
    private static readonly IBrush PurpleFg = new SolidColorBrush(Color.Parse("#9D6CD4"));
    private static readonly IBrush DimFg    = new SolidColorBrush(Color.Parse("#3A4A5A"));

    private string _dbPath = "";
    private long _accountId;
    private Button? _activeTab;

    public QuantAnalysisView()
    {
        InitializeComponent();
        _activeTab = TabSignificance;
        ShowTab("significance");
    }

    public void Initialize(string dbPath, long accountId)
    {
        _dbPath = dbPath;
        _accountId = accountId;
        LoadAll();
    }

    private void LoadAll()
    {
        LoadSignificance();
        LoadCalibration();
        LoadBehavioral();
        LoadConcentration();
        LoadPlanAdherence();
    }

    // ── Significance ─────────────────────────────────────────────────────────

    private void LoadSignificance()
    {
        try
        {
            var svc = new JournalService(_dbPath, _accountId);
            var stats = svc.GetStats();

            TradeCountLabel.Text = $"based on {stats.NTrades} closed trades";

            if (stats.NTrades < 5)
            {
                SigNeedMoreData.IsVisible = true;
                SigContent.IsVisible = false;
                return;
            }

            SigNeedMoreData.IsVisible = false;
            SigContent.IsVisible = true;

            // Win rate + Wilson CI
            double wr = stats.WinRate;
            SigWinRate.Text = (wr * 100).ToString("F1") + "%";
            SigWinRate.Foreground = wr >= 0.5 ? GreenFg : RedFg;
            if (stats.NTrades >= 10)
            {
                double lo = WilsonLo(wr, (int)stats.NTrades) * 100;
                double hi = WilsonHi(wr, (int)stats.NTrades) * 100;
                SigWinRateCI.Text = $"95% CI  [{lo:F0}%, {hi:F0}%]";
            }
            else
            {
                SigWinRateCI.Text = "need ≥ 10 trades for CI";
            }

            // Expectancy R
            double expR = stats.ExpectancyR;
            SigExpR.Text = (expR >= 0 ? "+" : "") + expR.ToString("F2") + "R";
            SigExpR.Foreground = expR >= 0 ? GreenFg : RedFg;
            SigExpRNote.Text = stats.NTrades >= 30
                ? "bootstrapped CI: requires full analysis layer"
                : $"need ≥ 30 trades for robust estimate (have {stats.NTrades})";

            // Profit factor
            double pf = stats.ProfitFactor;
            SigPF.Text = pf >= 100 ? ">100" : pf.ToString("F2");
            SigPF.Foreground = pf >= 1.5 ? GreenFg : pf >= 1 ? YellowFg : RedFg;

            // Sample size
            int needed = EstimateNForSignificance(expR);
            SigSampleN.Text = stats.NTrades.ToString();
            bool sufficient = stats.NTrades >= needed;
            SigSampleAssess.Text = sufficient
                ? $"sufficient (est. need ~{needed})"
                : $"need ~{needed} — have {stats.NTrades}";
            SigSampleAssess.Foreground = sufficient ? GreenFg : YellowFg;

            // Verdict
            bool lowN = stats.NTrades < 30;
            bool positive = expR > 0;
            bool strongPF = pf >= 1.2;

            if (lowN)
            {
                SigVerdictIcon.Text = "⚠";
                SigVerdictIcon.Foreground = YellowFg;
                SigVerdictTitle.Text = "INSUFFICIENT SAMPLE SIZE";
                SigVerdictTitle.Foreground = YellowFg;
                SigVerdictBody.Text = $"You need at least 30 closed trades to draw meaningful conclusions. You have {stats.NTrades}. Keep logging — the accumulated data is the asset.";
            }
            else if (positive && strongPF)
            {
                SigVerdictIcon.Text = "✓";
                SigVerdictIcon.Foreground = GreenFg;
                SigVerdictTitle.Text = "EDGE SIGNAL PRESENT";
                SigVerdictTitle.Foreground = GreenFg;
                SigVerdictBody.Text = "Positive expectancy and profit factor > 1.2 across your trade log. Apply multiple-testing correction if this setup was discovered after reviewing many approaches.";
            }
            else
            {
                SigVerdictIcon.Text = "✗";
                SigVerdictIcon.Foreground = RedFg;
                SigVerdictTitle.Text = "NO CONFIRMED EDGE";
                SigVerdictTitle.Foreground = RedFg;
                SigVerdictBody.Text = "Current data does not show a reliable edge. Review setup selection, risk sizing, and execution quality before increasing position size.";
            }
        }
        catch
        {
            SigNeedMoreData.IsVisible = true;
            SigContent.IsVisible = false;
        }
    }

    // ── Calibration ──────────────────────────────────────────────────────────

    private void LoadCalibration()
    {
        var rows = new List<CalibrationRow>();
        int totalN = 0;
        double brierSum = 0;

        try
        {
            using var conn = new SqliteConnection($"Data Source={_dbPath}");
            conn.Open();
            using var cmd = conn.CreateCommand();
            cmd.CommandText = """
                SELECT ROUND(confidence_pct / 10.0) * 10 AS bucket,
                       COUNT(*) AS n,
                       SUM(CASE WHEN thesis_correct = 1 THEN 1 ELSE 0 END) AS wins
                FROM trade
                WHERE account_id = $aid
                  AND thesis_correct IS NOT NULL
                  AND confidence_pct IS NOT NULL
                GROUP BY bucket
                ORDER BY bucket
                """;
            cmd.Parameters.AddWithValue("$aid", _accountId);
            using var r = cmd.ExecuteReader();
            while (r.Read())
            {
                int bucket = (int)r.GetDouble(0);
                int n      = (int)r.GetInt64(1);
                int wins   = (int)r.GetInt64(2);

                double predicted = bucket / 100.0;
                double actual    = n > 0 ? (double)wins / n : 0;
                double diff      = actual - predicted;

                totalN    += n;
                brierSum  += n * Math.Pow(predicted - actual, 2);

                string devStr = diff == 0 ? "on target"
                    : (diff > 0 ? "+" : "") + (diff * 100).ToString("F0") + "pp";

                IBrush devColor = Math.Abs(diff) <= 0.10 ? GreenFg
                    : Math.Abs(diff) <= 0.20 ? YellowFg : RedFg;

                rows.Add(new CalibrationRow(
                    Bucket: $"{bucket}%",
                    N: n, Wins: wins,
                    ActualRate: $"{actual:P0}",
                    RateColor: devColor,
                    Deviation: devStr,
                    DeviationColor: devColor
                ));
            }
        }
        catch { }

        CalibrationList.ItemsSource = rows;
        bool any = rows.Count > 0;
        CalibrationList.IsVisible  = any;
        CalibrationEmpty.IsVisible = !any;

        CalibN.Text = totalN.ToString();

        if (any && totalN > 0)
        {
            double brier = brierSum / totalN;
            BrierScore.Text = brier.ToString("F3");
            BrierScore.Foreground = brier <= 0.15 ? GreenFg : brier <= 0.22 ? YellowFg : RedFg;

            // Overall direction of miscalibration
            double overallBias = rows.Sum(x => (double)x.N / totalN * (x.Wins - x.N * (double.Parse(x.Bucket.TrimEnd('%')) / 100)));
            CalibAssess.Text = Math.Abs(overallBias / totalN) < 0.05 ? "CALIBRATED"
                : overallBias > 0 ? "UNDER-CONFIDENT"
                : "OVER-CONFIDENT";
            CalibAssess.Foreground = Math.Abs(overallBias / totalN) < 0.05 ? GreenFg : YellowFg;
        }
        else
        {
            BrierScore.Text = "—";
            CalibAssess.Text = "—";
        }
    }

    // ── Behavioral ────────────────────────────────────────────────────────────

    private void LoadBehavioral()
    {
        var rows = new List<BehavioralRow>();
        try
        {
            using var conn = new SqliteConnection($"Data Source={_dbPath}");
            conn.Open();
            using var cmd = conn.CreateCommand();
            cmd.CommandText = """
                SELECT t.emotional_state,
                       COUNT(DISTINCT t.trade_id) AS n,
                       SUM(CASE WHEN t.thesis_correct = 1 THEN 1 ELSE 0 END) AS wins,
                       AVG(
                           (SELECT COALESCE(SUM(
                               CASE WHEN tl2.exit_price IS NOT NULL THEN
                                   CASE WHEN tl2.side = 'long' THEN 1.0 ELSE -1.0 END *
                                   (tl2.exit_price - tl2.entry_price) * tl2.quantity * tl2.multiplier
                               ELSE 0 END
                           ), 0) FROM trade_leg tl2 WHERE tl2.trade_id = t.trade_id
                           ) / NULLIF(t.initial_risk, 0)
                       ) AS avg_r
                FROM trade t
                WHERE t.account_id = $aid
                  AND t.status = 'closed'
                  AND t.emotional_state IS NOT NULL
                GROUP BY t.emotional_state
                ORDER BY avg_r DESC
                """;
            cmd.Parameters.AddWithValue("$aid", _accountId);
            using var r = cmd.ExecuteReader();
            while (r.Read())
            {
                string state = r.GetString(0);
                int n        = (int)r.GetInt64(1);
                int wins     = r.IsDBNull(2) ? 0 : (int)r.GetInt64(2);
                double avgR  = r.IsDBNull(3) ? 0 : r.GetDouble(3);
                double wr    = n > 0 ? (double)wins / n : 0;

                IBrush sc = state switch
                {
                    "calm" or "confident" => GreenFg,
                    "fomo" or "revenge"   => RedFg,
                    "anxious" or "fearful" => YellowFg,
                    _                     => DimFg,
                };

                string label = state.Length > 0
                    ? char.ToUpper(state[0]) + state[1..]
                    : state;

                rows.Add(new BehavioralRow(
                    EmotionalState: label,
                    N: n,
                    WinRate: n > 0 ? (wr * 100).ToString("F0") + "%" : "—",
                    AvgR: avgR != 0 ? (avgR >= 0 ? "+" : "") + avgR.ToString("F2") + "R" : "—",
                    StateColor: sc,
                    AvgRColor: avgR >= 0 ? GreenFg : RedFg
                ));
            }
        }
        catch { }

        BehavioralList.ItemsSource = rows;
        bool any = rows.Count > 0;
        BehavioralList.IsVisible  = any;
        BehavioralEmpty.IsVisible = !any;
    }

    // ── Concentration ─────────────────────────────────────────────────────────

    private void LoadConcentration()
    {
        var rows = new List<ConcentrationRow>();
        try
        {
            using var conn = new SqliteConnection($"Data Source={_dbPath}");
            conn.Open();
            using var cmd = conn.CreateCommand();
            cmd.CommandText = """
                SELECT symbol, SUM(initial_risk) AS total_risk
                FROM trade
                WHERE account_id = $aid
                GROUP BY symbol
                ORDER BY total_risk DESC
                LIMIT 20
                """;
            cmd.Parameters.AddWithValue("$aid", _accountId);
            using var r = cmd.ExecuteReader();
            var raw = new List<(string sym, double risk)>();
            while (r.Read())
                raw.Add((r.GetString(0), r.GetDouble(1)));

            double totalRisk = raw.Sum(x => x.risk);
            foreach (var (sym, risk) in raw)
            {
                double pct = totalRisk > 0 ? risk / totalRisk : 0;
                IBrush color = pct > 0.30 ? RedFg : pct > 0.15 ? YellowFg : GreenFg;
                string label = pct > 0.30 ? "HIGH" : pct > 0.15 ? "ELEVATED" : "OK";

                rows.Add(new ConcentrationRow(
                    Label: sym,
                    Risk: $"${risk:N0}",
                    PctOfTotal: $"{pct:P1}",
                    RiskLabel: label,
                    BarColor: color
                ));
            }
        }
        catch { }

        ConcentrationList.ItemsSource = rows;
        bool any = rows.Count > 0;
        ConcentrationList.IsVisible  = any;
        ConcentrationEmpty.IsVisible = !any;
    }

    // ── Plan adherence ────────────────────────────────────────────────────────

    private void LoadPlanAdherence()
    {
        try
        {
            using var conn = new SqliteConnection($"Data Source={_dbPath}");
            conn.Open();
            using var cmd = conn.CreateCommand();
            cmd.CommandText = """
                SELECT t.followed_plan,
                       AVG(
                           (SELECT COALESCE(SUM(
                               CASE WHEN tl2.exit_price IS NOT NULL THEN
                                   CASE WHEN tl2.side = 'long' THEN 1.0 ELSE -1.0 END *
                                   (tl2.exit_price - tl2.entry_price) * tl2.quantity * tl2.multiplier
                               ELSE 0 END
                           ), 0) FROM trade_leg tl2 WHERE tl2.trade_id = t.trade_id
                           ) / NULLIF(t.initial_risk, 0)
                       ) AS avg_r
                FROM trade t
                WHERE t.account_id = $aid
                  AND t.status = 'closed'
                  AND t.followed_plan IS NOT NULL
                GROUP BY t.followed_plan
                """;
            cmd.Parameters.AddWithValue("$aid", _accountId);
            using var r = cmd.ExecuteReader();
            while (r.Read())
            {
                bool followed = r.GetInt64(0) == 1;
                double avgR   = r.IsDBNull(1) ? 0 : r.GetDouble(1);
                string text   = avgR != 0 ? (avgR >= 0 ? "+" : "") + avgR.ToString("F2") + "R" : "—";
                IBrush color  = avgR >= 0 ? GreenFg : RedFg;

                if (followed)
                {
                    FollowedPlanR.Text       = text;
                    FollowedPlanR.Foreground = color;
                }
                else
                {
                    BrokeRuleR.Text       = text;
                    BrokeRuleR.Foreground = color;
                }
            }
        }
        catch { }
    }

    // ── Tab navigation ────────────────────────────────────────────────────────

    private void OnTabClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button btn || btn.Tag is not string tab) return;
        _activeTab?.Classes.Remove("Active");
        _activeTab = btn;
        _activeTab.Classes.Add("Active");
        ShowTab(tab);
    }

    private void ShowTab(string tab)
    {
        SignificancePanel.IsVisible  = tab == "significance";
        BenchmarkPanel.IsVisible     = tab == "benchmark";
        MonteCarloPanel.IsVisible    = tab == "montecarlo";
        CalibrationPanel.IsVisible   = tab == "calibration";
        BehavioralPanel.IsVisible    = tab == "behavioral";
        ConcentrationPanel.IsVisible = tab == "concentration";
    }

    private void OnRefresh(object? sender, RoutedEventArgs e)
        => LoadAll();

    private void OnRunSimulation(object? sender, RoutedEventArgs e)
    {
        // TODO: run bootstrap Monte Carlo from closed trade R-multiples
        McMedian.Text = "—";
        McP5.Text     = "—";
        McP95.Text    = "—";
        McRuin.Text   = "—";
    }

    // ── Statistical helpers ───────────────────────────────────────────────────

    private static double WilsonLo(double p, int n)
    {
        const double z = 1.96;
        double denom = 1 + z * z / n;
        double center = (p + z * z / (2 * n)) / denom;
        double margin = z * Math.Sqrt(p * (1 - p) / n + z * z / (4.0 * n * n)) / denom;
        return Math.Max(0, center - margin);
    }

    private static double WilsonHi(double p, int n)
    {
        const double z = 1.96;
        double denom = 1 + z * z / n;
        double center = (p + z * z / (2 * n)) / denom;
        double margin = z * Math.Sqrt(p * (1 - p) / n + z * z / (4.0 * n * n)) / denom;
        return Math.Min(1, center + margin);
    }

    private static int EstimateNForSignificance(double expectancyR)
    {
        // Assuming σ ≈ 1R, one-sided test at 5%: N ≈ (1.65 / |E[R]|)²
        if (Math.Abs(expectancyR) < 0.01) return 1000;
        return (int)Math.Ceiling(Math.Max(30, Math.Pow(1.65 / Math.Abs(expectancyR), 2)));
    }
}
