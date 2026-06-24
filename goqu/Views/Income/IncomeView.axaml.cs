using System;
using System.Collections.Generic;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using goqu.Services;
using Microsoft.Data.Sqlite;

namespace goqu.Views.Income;

public record HoldingRow(
    long HoldingId,
    string Symbol,
    string SleeveLabel,
    IBrush SleeveAccent,
    IBrush SleeveBg,
    string Shares,
    string AvgCost,
    string CostBasis,
    string MktValue,
    string YOC,
    string LotCount
);

public record DividendRow(
    long DivId,
    string ExDate,
    string Symbol,
    string AmtPerShare,
    string Shares,
    string Total,
    string PayDate,
    string ReinvestedLabel,
    IBrush ReinvestedColor,
    IBrush ReinvestedBg
);

public record SweepRow(
    long SweepId,
    string Date,
    string NetPnl,
    string SweepPct,
    string Amount,
    string Destination,
    string SharesStr,
    string Notes
);

public record DGRow(
    string Symbol,
    string Company,
    string Yield,
    string Cagr5Y,
    string Streak,
    string Payout,
    string FcfCoverage,
    string SafetyLabel,
    IBrush SafetyColor,
    IBrush SafetyBg,
    string Score,
    IBrush ScoreColor
);

public partial class IncomeView : UserControl
{
    private static readonly IBrush GreenFg   = new SolidColorBrush(Color.Parse("#17A86C"));
    private static readonly IBrush RedFg     = new SolidColorBrush(Color.Parse("#BF1B1B"));
    private static readonly IBrush YellowFg  = new SolidColorBrush(Color.Parse("#FFE101"));
    private static readonly IBrush BlueFg    = new SolidColorBrush(Color.Parse("#0085CD"));
    private static readonly IBrush OrangeFg  = new SolidColorBrush(Color.Parse("#FF9500"));
    private static readonly IBrush DimFg     = new SolidColorBrush(Color.Parse("#3A4A5A"));

    private static readonly IBrush IndexAccentBg  = new SolidColorBrush(Color.Parse("#001428"));
    private static readonly IBrush DivGrowthAccentBg = new SolidColorBrush(Color.Parse("#001A0A"));
    private static readonly IBrush DripBg        = new SolidColorBrush(Color.Parse("#001A0A"));
    private static readonly IBrush NoDripBg      = new SolidColorBrush(Color.Parse("#100508"));

    private string _dbPath = "";
    private long _accountId;
    private Button? _activeTab;
    private Button? _activeSleeveChip;
    private Button? _activeDGSafetyChip;
    private string _sleeveFilter = "all";
    private readonly List<HoldingRow> _allHoldings = [];

    public IncomeView()
    {
        InitializeComponent();
        _activeTab         = TabOverview;
        _activeSleeveChip  = SleeveAll;
        _activeDGSafetyChip = DGSafetyAny;
        ShowTab("overview");
    }

    public void Initialize(string dbPath, long accountId)
    {
        _dbPath    = dbPath;
        _accountId = accountId;
        LoadAll();
    }

    private void LoadAll()
    {
        LoadOverview();
        LoadHoldings();
        LoadDividends();
        LoadSweep();
    }

    // ── OVERVIEW ─────────────────────────────────────────────────────────────

    private void LoadOverview()
    {
        try
        {
            // Holdings summary per sleeve
            double indexCost = 0, divCost = 0;
            int indexCount = 0, divCount = 0;
            double projIncome = 0;

            using (var conn = new SqliteConnection($"Data Source={_dbPath}"))
            {
                conn.Open();

                // Cost basis per sleeve
                using var cbCmd = conn.CreateCommand();
                cbCmd.CommandText = """
                    SELECT h.sleeve, COUNT(DISTINCT h.holding_id),
                           COALESCE(SUM(l.shares * l.cost_per_share), 0)
                    FROM income_holding h
                    LEFT JOIN income_tax_lot l ON l.holding_id = h.holding_id
                    WHERE h.account_id = $aid
                    GROUP BY h.sleeve
                    """;
                cbCmd.Parameters.AddWithValue("$aid", _accountId);
                using (var r = cbCmd.ExecuteReader())
                {
                    while (r.Read())
                    {
                        string sleeve = r.GetString(0);
                        int cnt       = (int)r.GetInt64(1);
                        double cost   = r.GetDouble(2);
                        if (sleeve == "index_core")  { indexCost = cost; indexCount = cnt; }
                        else                          { divCost   = cost; divCount   = cnt; }
                    }
                }

                // YTD dividends
                int year = DateTime.Today.Year;
                using var divCmd = conn.CreateCommand();
                divCmd.CommandText = """
                    SELECT COALESCE(SUM(total_amount), 0)
                    FROM dividend_received
                    WHERE account_id = $aid AND strftime('%Y', ex_date) = $yr
                    """;
                divCmd.Parameters.AddWithValue("$aid", _accountId);
                divCmd.Parameters.AddWithValue("$yr", year.ToString());
                double ytdDiv = (double)divCmd.ExecuteScalar()!;

                // All-time dividends (for run-rate)
                using var allDivCmd = conn.CreateCommand();
                allDivCmd.CommandText = "SELECT COALESCE(SUM(total_amount), 0), COUNT(*) FROM dividend_received WHERE account_id = $aid";
                allDivCmd.Parameters.AddWithValue("$aid", _accountId);
                double allTimeDiv = 0; int divCount2 = 0;
                using (var r = allDivCmd.ExecuteReader())
                    if (r.Read()) { allTimeDiv = r.GetDouble(0); divCount2 = (int)r.GetInt64(1); }

                // Sweep totals
                using var sweepCmd = conn.CreateCommand();
                sweepCmd.CommandText = "SELECT COALESCE(SUM(sweep_amount), 0), COALESCE(AVG(sweep_pct), 25) FROM sweep_transaction WHERE account_id = $aid";
                sweepCmd.Parameters.AddWithValue("$aid", _accountId);
                double totalSwept = 0, avgSweepPct = 25;
                using (var r = sweepCmd.ExecuteReader())
                    if (r.Read()) { totalSwept = r.GetDouble(0); avgSweepPct = r.GetDouble(1); }

                // Net P&L from journal
                double netPnl = 0;
                try
                {
                    var svc = new JournalService(_dbPath, _accountId);
                    var stats = svc.GetStats();
                    netPnl = stats.TotalPnl;
                }
                catch { }

                double yoc = divCost > 0 ? projIncome / divCost : 0;
                double runRate = divCount2 > 0 && allTimeDiv > 0
                    ? ytdDiv / Math.Max(1, DateTime.Today.DayOfYear) * 365
                    : 0;

                // Update UI
                IndexCostBasis.Text = indexCost > 0 ? $"${indexCost:N0}" : "—";
                IndexHoldings.Text  = indexCount.ToString();
                DivCostBasis.Text   = divCost > 0 ? $"${divCost:N0}" : "—";
                DivHoldings.Text    = divCount.ToString();
                DivYOC.Text         = yoc > 0 ? $"{yoc:P1}" : "—";
                DivProjIncome.Text  = projIncome > 0 ? $"${projIncome:N0}/yr" : "—";

                KpiYTDDiv.Text    = ytdDiv > 0 ? $"${ytdDiv:N0}" : "—";
                KpiRunRate.Text   = runRate > 0 ? $"${runRate:N0}" : "—";
                KpiYOC.Text       = yoc > 0 ? $"{yoc:P1}" : "—";
                KpiTotalCost.Text = (indexCost + divCost) > 0 ? $"${indexCost + divCost:N0}" : "—";
                KpiTotalSwept.Text = totalSwept > 0 ? $"${totalSwept:N0}" : "—";

                // Sweep flow strip
                SweepNetPnl.Text    = netPnl != 0 ? (netPnl >= 0 ? "+" : "") + $"${netPnl:N0}" : "—";
                SweepNetPnl.Foreground = netPnl >= 0 ? GreenFg : RedFg;
                SweepPctLabel.Text  = $"{avgSweepPct:F0}%";
                double available    = Math.Max(0, netPnl - totalSwept);
                SweepAvailable.Text = available > 0 ? $"${available:N0} available" : "$0 available";
                SweepCumulative.Text = totalSwept > 0 ? $"${totalSwept:N0}" : "—";

                UpdateCrossover(runRate);
            }
        }
        catch { }
    }

    private void UpdateCrossover(double runRate = 0)
    {
        double target = double.TryParse(CrossoverTargetInput?.Text, out var t) ? t : 60000;
        double growth = double.TryParse(GrowthRateInput?.Text, out var g) ? g / 100.0 : 0.07;

        CrossoverTarget.Text = $"${target:N0}";
        CrossoverCurrent.Text = runRate > 0 ? $"${runRate:N0}" : "—";

        if (runRate <= 0)
        {
            CrossoverETA.Text = "—";
            CrossoverProgress.Text = "0% of target";
            if (CrossoverBar != null)
                CrossoverBar.Width = 0;
            return;
        }

        double pct = Math.Min(1.0, runRate / target);
        CrossoverProgress.Text = $"{pct:P0} of target";

        // Estimate years: income(t) = runRate * (1+g)^t >= target
        // t = log(target/runRate) / log(1+g)
        double eta = growth > 0 && target > runRate
            ? Math.Log(target / runRate) / Math.Log(1 + growth)
            : 0;

        CrossoverETA.Text = eta > 0
            ? $"{DateTime.Today.Year + (int)Math.Ceiling(eta)}"
            : "ACHIEVED";
        CrossoverETA.Foreground = eta <= 0 ? GreenFg : YellowFg;

        // Scale progress bar — needs to be done after layout; stub width at ~0
        if (CrossoverBar != null)
            CrossoverBar.Width = double.IsNaN(CrossoverBar.Bounds.Width) || CrossoverBar.Bounds.Width <= 0
                ? 0 : CrossoverBar.Bounds.Width * pct;
    }

    // ── HOLDINGS ─────────────────────────────────────────────────────────────

    private void LoadHoldings()
    {
        _allHoldings.Clear();
        try
        {
            using var conn = new SqliteConnection($"Data Source={_dbPath}");
            conn.Open();
            using var cmd = conn.CreateCommand();
            cmd.CommandText = """
                SELECT h.holding_id, h.symbol, h.sleeve,
                       COALESCE(SUM(l.shares), 0) AS total_shares,
                       CASE WHEN SUM(l.shares) > 0
                            THEN SUM(l.shares * l.cost_per_share) / SUM(l.shares)
                            ELSE 0 END AS avg_cost,
                       COALESCE(SUM(l.shares * l.cost_per_share), 0) AS cost_basis,
                       COUNT(l.lot_id) AS lot_count
                FROM income_holding h
                LEFT JOIN income_tax_lot l ON l.holding_id = h.holding_id
                WHERE h.account_id = $aid
                GROUP BY h.holding_id, h.symbol, h.sleeve
                ORDER BY h.sleeve, cost_basis DESC
                """;
            cmd.Parameters.AddWithValue("$aid", _accountId);
            using var r = cmd.ExecuteReader();
            while (r.Read())
            {
                string sleeve = r.GetString(2);
                bool isIndex  = sleeve == "index_core";
                _allHoldings.Add(new HoldingRow(
                    HoldingId: r.GetInt64(0),
                    Symbol:     r.GetString(1),
                    SleeveLabel: isIndex ? "INDEX" : "DIV GR",
                    SleeveAccent: isIndex ? BlueFg : GreenFg,
                    SleeveBg:    isIndex ? IndexAccentBg : DivGrowthAccentBg,
                    Shares:      r.GetDouble(3) > 0 ? r.GetDouble(3).ToString("F4") : "—",
                    AvgCost:     r.GetDouble(4) > 0 ? $"${r.GetDouble(4):N2}" : "—",
                    CostBasis:   r.GetDouble(5) > 0 ? $"${r.GetDouble(5):N0}" : "—",
                    MktValue:    "—",   // requires price feed
                    YOC:         "—",   // requires price + div data
                    LotCount:    r.GetInt64(6).ToString()
                ));
            }
        }
        catch { }

        ApplySleeveFilter();
    }

    private void ApplySleeveFilter()
    {
        var filtered = _sleeveFilter == "all"
            ? _allHoldings
            : _allHoldings.Where(h =>
                (_sleeveFilter == "index_core"  && h.SleeveLabel == "INDEX") ||
                (_sleeveFilter == "div_growth"  && h.SleeveLabel == "DIV GR")
              ).ToList();

        HoldingsList.ItemsSource = filtered;
        bool any = filtered.Count > 0;
        HoldingsList.IsVisible  = any;
        HoldingsEmpty.IsVisible = !any;
    }

    // ── DIVIDENDS ─────────────────────────────────────────────────────────────

    private void LoadDividends()
    {
        var rows = new List<DividendRow>();
        try
        {
            using var conn = new SqliteConnection($"Data Source={_dbPath}");
            conn.Open();

            // Stats
            int year = DateTime.Today.Year;
            using var statsCmd = conn.CreateCommand();
            statsCmd.CommandText = """
                SELECT
                    COALESCE(SUM(CASE WHEN strftime('%Y', ex_date)=$yr THEN total_amount ELSE 0 END),0) AS ytd,
                    COALESCE(SUM(total_amount),0) AS all_time,
                    COALESCE(SUM(CASE WHEN strftime('%Y', ex_date)=$yr AND reinvested=1 THEN drip_shares ELSE 0 END),0) AS drip_shares,
                    COUNT(*) AS cnt
                FROM dividend_received WHERE account_id=$aid
                """;
            statsCmd.Parameters.AddWithValue("$aid", _accountId);
            statsCmd.Parameters.AddWithValue("$yr", year.ToString());
            using (var r = statsCmd.ExecuteReader())
            {
                if (r.Read())
                {
                    double ytd  = r.GetDouble(0);
                    double drip = r.GetDouble(2);
                    int cnt     = (int)r.GetInt64(3);
                    double runRate = ytd / Math.Max(1, DateTime.Today.DayOfYear) * 365;

                    DivYTDTotal.Text   = ytd > 0 ? $"${ytd:N0}" : "—";
                    DivRunRate.Text    = runRate > 0 ? $"${runRate:N0}" : "—";
                    DivDripShares.Text = drip > 0 ? drip.ToString("F4") : "—";
                    DivCount.Text      = cnt.ToString();
                }
            }

            // Log rows
            using var logCmd = conn.CreateCommand();
            logCmd.CommandText = """
                SELECT d.div_id, d.ex_date, h.symbol, d.amount_per_share,
                       d.shares_held, d.total_amount, d.pay_date, d.reinvested, d.drip_shares
                FROM dividend_received d
                JOIN income_holding h ON h.holding_id = d.holding_id
                WHERE d.account_id = $aid
                ORDER BY d.ex_date DESC
                LIMIT 200
                """;
            logCmd.Parameters.AddWithValue("$aid", _accountId);
            using var lr = logCmd.ExecuteReader();
            while (lr.Read())
            {
                bool reInv = !lr.IsDBNull(7) && lr.GetInt64(7) == 1;
                rows.Add(new DividendRow(
                    DivId:            lr.GetInt64(0),
                    ExDate:           FormatDate(lr.IsDBNull(1) ? "" : lr.GetString(1)),
                    Symbol:           lr.GetString(2),
                    AmtPerShare:      $"${lr.GetDouble(3):N4}",
                    Shares:           lr.GetDouble(4).ToString("F4"),
                    Total:            $"${lr.GetDouble(5):N2}",
                    PayDate:          lr.IsDBNull(6) ? "—" : FormatDate(lr.GetString(6)),
                    ReinvestedLabel:  reInv ? "DRIP" : "CASH",
                    ReinvestedColor:  reInv ? GreenFg : DimFg,
                    ReinvestedBg:     reInv ? DripBg : NoDripBg
                ));
            }
        }
        catch { }

        DividendsList.ItemsSource = rows;
        bool any = rows.Count > 0;
        DividendsList.IsVisible = any;
        DividendsEmpty.IsVisible = !any;
    }

    // ── SWEEP LEDGER ─────────────────────────────────────────────────────────

    private void LoadSweep()
    {
        var rows = new List<SweepRow>();
        try
        {
            using var conn = new SqliteConnection($"Data Source={_dbPath}");
            conn.Open();

            // History rows
            using var cmd = conn.CreateCommand();
            cmd.CommandText = """
                SELECT sweep_id, sweep_date, net_trading_pnl, sweep_pct,
                       sweep_amount, destination_symbol, destination_sleeve,
                       shares_purchased, notes
                FROM sweep_transaction
                WHERE account_id = $aid
                ORDER BY sweep_date DESC
                """;
            cmd.Parameters.AddWithValue("$aid", _accountId);
            using var r = cmd.ExecuteReader();
            while (r.Read())
            {
                string sym    = r.IsDBNull(5) ? "" : r.GetString(5);
                string sleeve = r.IsDBNull(6) ? "" : r.GetString(6);
                string dest   = string.IsNullOrEmpty(sym) ? sleeve : $"{sym} ({sleeve})";
                rows.Add(new SweepRow(
                    SweepId:    r.GetInt64(0),
                    Date:       FormatDate(r.GetString(1)),
                    NetPnl:     $"${r.GetDouble(2):N0}",
                    SweepPct:   $"{r.GetDouble(3):F0}%",
                    Amount:     $"${r.GetDouble(4):N0}",
                    Destination: dest,
                    SharesStr:  r.IsDBNull(7) ? "—" : r.GetDouble(7).ToString("F4"),
                    Notes:      r.IsDBNull(8) ? "" : r.GetString(8)
                ));
            }
        }
        catch { }

        SweepList.ItemsSource = rows;
        bool any = rows.Count > 0;
        SweepList.IsVisible = any;
        SweepEmpty.IsVisible = !any;

        RefreshSweepCalc();
    }

    private void RefreshSweepCalc()
    {
        try
        {
            double netPnl = 0;
            try
            {
                var svc = new JournalService(_dbPath, _accountId);
                netPnl = svc.GetStats().TotalPnl;
            }
            catch { }

            double totalSwept = 0;
            try
            {
                using var conn = new SqliteConnection($"Data Source={_dbPath}");
                conn.Open();
                using var cmd = conn.CreateCommand();
                cmd.CommandText = "SELECT COALESCE(SUM(sweep_amount),0) FROM sweep_transaction WHERE account_id=$aid";
                cmd.Parameters.AddWithValue("$aid", _accountId);
                totalSwept = (double)cmd.ExecuteScalar()!;
            }
            catch { }

            double available = Math.Max(0, netPnl - totalSwept);
            double sweepPct  = double.TryParse(SweepPctInput?.Text, out var p) ? p / 100.0 : 0.25;
            double thisSweep = available * sweepPct;

            SweepCalcNetPnl.Text    = $"{(netPnl >= 0 ? "+" : "")}${Math.Abs(netPnl):N0}";
            SweepCalcNetPnl.Foreground = netPnl >= 0 ? GreenFg : RedFg;
            SweepCalcSwept.Text     = $"-${totalSwept:N0}";
            SweepCalcAvailable.Text = $"${available:N0}";
            SweepCalcAvailable.Foreground = available > 0 ? GreenFg : DimFg;
            SweepCalcThisSweep.Text = $"${thisSweep:N0}  at {sweepPct:P0} sweep rate";

            if (ExecuteSweepBtn != null)
                ExecuteSweepBtn.IsEnabled = available > 0 && thisSweep >= 1;
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
        OverviewPanel.IsVisible  = tab == "overview";
        HoldingsPanel.IsVisible  = tab == "holdings";
        DividendsPanel.IsVisible = tab == "dividends";
        SweepPanel.IsVisible     = tab == "sweep";
        DGPanel.IsVisible        = tab == "dgscreen";
    }

    // ── Sleeve filter ─────────────────────────────────────────────────────────

    private void OnSleeveFilter(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button btn) return;
        _activeSleeveChip?.Classes.Remove("Active");
        _activeSleeveChip = btn;
        _activeSleeveChip.Classes.Add("Active");
        _sleeveFilter = btn.Tag as string ?? "all";
        ApplySleeveFilter();
    }

    // ── Crossover calc ────────────────────────────────────────────────────────

    private void OnTargetChanged(object? sender, TextChangedEventArgs e)
        => UpdateCrossover();

    // ── Sweep controls ────────────────────────────────────────────────────────

    private void OnSweepPctChanged(object? sender, TextChangedEventArgs e)
        => RefreshSweepCalc();

    private void OnSaveRule(object? sender, RoutedEventArgs e)
    {
        // TODO: persist sweep_pct to app_settings
    }

    private void OnExecuteSweep(object? sender, RoutedEventArgs e)
    {
        // TODO: open sweep confirmation dialog and write sweep_transaction row
    }

    // ── DG Screen filters ─────────────────────────────────────────────────────

    private void OnDGPreset(object? sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string v)
            DGStreakMin.Text = v;
    }

    private void OnDGCAGRPreset(object? sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string v)
            DGCAGRMin.Text = v;
    }

    private void OnDGPayoutPreset(object? sender, RoutedEventArgs e)
    {
        if (sender is Button btn && btn.Tag is string v)
            DGPayoutMax.Text = v;
    }

    private void OnDGSafetyFilter(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button btn) return;
        _activeDGSafetyChip?.Classes.Remove("Active");
        _activeDGSafetyChip = btn;
        _activeDGSafetyChip.Classes.Add("Active");
    }

    private void OnRunDGScreen(object? sender, RoutedEventArgs e)
    {
        // TODO: query screener DB or external data source for dividend growth candidates
        DGList.IsVisible   = false;
        DGEmpty.IsVisible  = true;
    }

    // ── General actions (stubs) ───────────────────────────────────────────────

    private void OnAddPosition(object? sender, RoutedEventArgs e)
    {
        // TODO: open AddPositionWindow (symbol, sleeve, shares, cost_per_share, acquired_at)
    }

    private void OnLogDividend(object? sender, RoutedEventArgs e)
    {
        // TODO: open LogDividendWindow
    }

    private void OnRefresh(object? sender, RoutedEventArgs e)
        => LoadAll();

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static string FormatDate(string iso)
        => DateTime.TryParse(iso, out var d) ? d.ToString("MMM d, yyyy") : iso;
}
