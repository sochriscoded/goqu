using System;
using System.Collections.Generic;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using Microsoft.Data.Sqlite;

namespace goqu.Views.EdgeDiscovery;

public record HypothesisItem(
    long Id,
    string Name,
    string Status,
    string StatusLabel,
    string SignalType,
    string CreatedAt,
    IBrush BarColor,
    IBrush LabelBg,
    IBrush LabelColor,
    string StructuralReason,
    string SignalDefinition,
    string? Notes,
    double? ExpectancyR,
    double? WinRate,
    double? Sharpe,
    double? TStatistic
);

public partial class EdgeDiscoveryView : UserControl
{
    private static readonly IBrush UntestedBar  = new SolidColorBrush(Color.Parse("#1E2438"));
    private static readonly IBrush TestingBar   = new SolidColorBrush(Color.Parse("#0085CD"));
    private static readonly IBrush ValidBar     = new SolidColorBrush(Color.Parse("#038C4C"));
    private static readonly IBrush RejectedBar  = new SolidColorBrush(Color.Parse("#BF1B1B"));

    private static readonly IBrush UntestedBg   = new SolidColorBrush(Color.Parse("#141820"));
    private static readonly IBrush TestingBg    = new SolidColorBrush(Color.Parse("#001428"));
    private static readonly IBrush ValidBg      = new SolidColorBrush(Color.Parse("#001A0A"));
    private static readonly IBrush RejectedBg   = new SolidColorBrush(Color.Parse("#1A0000"));

    private static readonly IBrush UntestedFg   = new SolidColorBrush(Color.Parse("#3A4A5A"));
    private static readonly IBrush TestingFg    = new SolidColorBrush(Color.Parse("#0085CD"));
    private static readonly IBrush ValidFg      = new SolidColorBrush(Color.Parse("#038C4C"));
    private static readonly IBrush RejectedFg   = new SolidColorBrush(Color.Parse("#BF1B1B"));

    private string _dbPath = "";
    private long _accountId;
    private string _statusFilter = "all";
    private readonly List<HypothesisItem> _allItems = [];
    private Button? _activeChip;

    public EdgeDiscoveryView()
    {
        InitializeComponent();
        _activeChip = ChipAll;
    }

    public void Initialize(string dbPath, long accountId)
    {
        _dbPath = dbPath;
        _accountId = accountId;
        LoadHypotheses();
    }

    private void LoadHypotheses()
    {
        _allItems.Clear();
        try
        {
            using var conn = new SqliteConnection($"Data Source={_dbPath}");
            conn.Open();
            using var cmd = conn.CreateCommand();
            cmd.CommandText = """
                SELECT hypothesis_id, name, status, signal_type,
                       structural_reason, signal_definition, notes,
                       expectancy_r, win_rate, sharpe, t_statistic,
                       created_at
                FROM hypothesis
                WHERE account_id = $aid
                ORDER BY
                    CASE status
                        WHEN 'forward_testing' THEN 0
                        WHEN 'untested'         THEN 1
                        WHEN 'validated'        THEN 2
                        WHEN 'rejected'         THEN 3
                        ELSE 4
                    END, updated_at DESC
                """;
            cmd.Parameters.AddWithValue("$aid", _accountId);
            using var r = cmd.ExecuteReader();
            while (r.Read())
            {
                var status = r.IsDBNull(2) ? "untested" : r.GetString(2);
                _allItems.Add(new HypothesisItem(
                    Id: r.GetInt64(0),
                    Name: r.GetString(1),
                    Status: status,
                    StatusLabel: StatusToLabel(status),
                    SignalType: r.IsDBNull(3) ? "—" : FormatSignalType(r.GetString(3)),
                    CreatedAt: r.IsDBNull(11) ? "" : FormatDate(r.GetString(11)),
                    BarColor: StatusBarColor(status),
                    LabelBg: StatusLabelBg(status),
                    LabelColor: StatusLabelFg(status),
                    StructuralReason: r.IsDBNull(4) ? "" : r.GetString(4),
                    SignalDefinition: r.IsDBNull(5) ? "" : r.GetString(5),
                    Notes: r.IsDBNull(6) ? null : r.GetString(6),
                    ExpectancyR: r.IsDBNull(7) ? null : r.GetDouble(7),
                    WinRate: r.IsDBNull(8) ? null : r.GetDouble(8),
                    Sharpe: r.IsDBNull(9) ? null : r.GetDouble(9),
                    TStatistic: r.IsDBNull(10) ? null : r.GetDouble(10)
                ));
            }
        }
        catch { /* table not yet created */ }

        UpdateKpis();
        ApplyFilter();
    }

    private void UpdateKpis()
    {
        int total     = _allItems.Count;
        int validated = _allItems.Count(h => h.Status == "validated");
        int testing   = _allItems.Count(h => h.Status == "forward_testing");
        int rejected  = _allItems.Count(h => h.Status == "rejected");

        KpiTotal.Text     = total.ToString();
        KpiValidated.Text = validated.ToString();
        KpiTesting.Text   = testing.ToString();
        KpiRejected.Text  = rejected.ToString();
        KpiExplored.Text  = total.ToString();

        // FDR estimate: ~5% of non-validated hypotheses are expected false discoveries
        double fdr = total > 0 ? Math.Round(0.05 * (total - validated), 1) : 0;
        KpiFDR.Text = fdr.ToString("F1");

        EmptyState.IsVisible = total == 0;
    }

    private void ApplyFilter()
    {
        var search = HypothesisSearch?.Text?.Trim().ToLowerInvariant() ?? "";

        var filtered = _allItems.Where(h =>
        {
            bool statusOk = _statusFilter == "all" || h.Status == _statusFilter;
            bool searchOk = string.IsNullOrEmpty(search)
                            || h.Name.ToLowerInvariant().Contains(search)
                            || h.SignalType.ToLowerInvariant().Contains(search);
            return statusOk && searchOk;
        }).ToList();

        HypothesisList.ItemsSource = filtered;
    }

    // ── Filter chips ─────────────────────────────────────────────────────────

    private void OnStatusFilter(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button btn) return;
        _activeChip?.Classes.Remove("Active");
        _activeChip = btn;
        _activeChip.Classes.Add("Active");
        _statusFilter = btn.Tag as string ?? "all";
        ApplyFilter();
    }

    private void OnSearchChanged(object? sender, TextChangedEventArgs e)
        => ApplyFilter();

    // ── Selection / detail ────────────────────────────────────────────────────

    private void OnHypothesisSelected(object? sender, SelectionChangedEventArgs e)
    {
        if (HypothesisList.SelectedItem is HypothesisItem item)
            ShowDetail(item);
    }

    private void ShowDetail(HypothesisItem h)
    {
        OverviewPanel.IsVisible = false;
        DetailPanel.IsVisible   = true;

        DetailBreadcrumb.Text            = h.Name;
        DetailNameLabel.Text             = h.Name;
        DetailStatusBadge.Background     = h.LabelBg;
        DetailStatusBadge.BorderBrush    = h.LabelColor;
        DetailStatusBadge.BorderThickness = new Avalonia.Thickness(1);
        DetailStatusLabel.Text           = h.StatusLabel;
        DetailStatusLabel.Foreground     = h.LabelColor;
        DetailSignalTypeLabel.Text       = h.SignalType;
        DetailMeta.Text                  = $"Created {h.CreatedAt}";

        DetailStructuralReason.Text = string.IsNullOrWhiteSpace(h.StructuralReason)
            ? "Not specified yet." : h.StructuralReason;
        DetailSignalDef.Text = string.IsNullOrWhiteSpace(h.SignalDefinition)
            ? "Not defined yet." : h.SignalDefinition;
        DetailNotes.Text = string.IsNullOrWhiteSpace(h.Notes)
            ? "No notes." : h.Notes;

        bool hasEval = h.ExpectancyR.HasValue;
        EvalGrid.IsVisible = hasEval;
        EvalNote.IsVisible = !hasEval;

        if (hasEval)
        {
            EvalExpR.Text   = h.ExpectancyR.HasValue
                ? (h.ExpectancyR.Value >= 0 ? "+" : "") + h.ExpectancyR.Value.ToString("F2") + "R" : "—";
            EvalWR.Text     = h.WinRate.HasValue
                ? (h.WinRate.Value * 100).ToString("F1") + "%" : "—";
            EvalSharpe.Text = h.Sharpe.HasValue ? h.Sharpe.Value.ToString("F2") : "—";
            EvalTStat.Text  = h.TStatistic.HasValue ? h.TStatistic.Value.ToString("F2") : "—";
        }
    }

    private void OnBackToOverview(object? sender, RoutedEventArgs e)
    {
        OverviewPanel.IsVisible = true;
        DetailPanel.IsVisible   = false;
        HypothesisList.SelectedItem = null;
    }

    // ── Actions (stubs for now) ───────────────────────────────────────────────

    private void OnNewHypothesis(object? sender, RoutedEventArgs e)
    {
        // TODO: open NewHypothesisWindow
    }

    private void OnEditHypothesis(object? sender, RoutedEventArgs e)
    {
        // TODO: open edit form pre-filled with selected hypothesis
    }

    private void OnChangeStatus(object? sender, RoutedEventArgs e)
    {
        // TODO: status change dropdown/dialog
    }

    // ── Static helpers ────────────────────────────────────────────────────────

    private static string StatusToLabel(string s) => s switch
    {
        "forward_testing" => "TESTING",
        "validated"       => "VALIDATED",
        "rejected"        => "REJECTED",
        _                 => "UNTESTED",
    };

    private static string FormatSignalType(string t) => t switch
    {
        "price_action" => "Price Action",
        "fundamental"  => "Fundamental",
        "options"      => "Options",
        "macro"        => "Macro",
        "composite"    => "Composite",
        _              => t,
    };

    private static string FormatDate(string iso)
        => DateTime.TryParse(iso, out var d) ? d.ToString("MMM d, yyyy") : iso;

    private static IBrush StatusBarColor(string s) => s switch
    {
        "forward_testing" => TestingBar,
        "validated"       => ValidBar,
        "rejected"        => RejectedBar,
        _                 => UntestedBar,
    };

    private static IBrush StatusLabelBg(string s) => s switch
    {
        "forward_testing" => TestingBg,
        "validated"       => ValidBg,
        "rejected"        => RejectedBg,
        _                 => UntestedBg,
    };

    private static IBrush StatusLabelFg(string s) => s switch
    {
        "forward_testing" => TestingFg,
        "validated"       => ValidFg,
        "rejected"        => RejectedFg,
        _                 => UntestedFg,
    };
}
