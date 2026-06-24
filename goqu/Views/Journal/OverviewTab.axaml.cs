using System;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Media;
using goqu.Models;
using goqu.Services;

namespace goqu.Views.Journal;

// Row VMs for AXAML DataTemplate bindings
public sealed class OpenTradeRow
{
    public string Symbol { get; init; } = "";
    public string DirGlyph { get; init; } = "";
    public IBrush DirColor { get; init; } = Brushes.White;
    public string Strategy { get; init; } = "";
    public string Risk { get; init; } = "";
    public string Opened { get; init; } = "";
    public string Thesis { get; init; } = "";
}

public sealed class ClosedTradeRow
{
    public string Symbol { get; init; } = "";
    public string DirGlyph { get; init; } = "";
    public IBrush DirColor { get; init; } = Brushes.White;
    public string Pnl { get; init; } = "";
    public IBrush PnlColor { get; init; } = Brushes.White;
    public string R { get; init; } = "";
    public IBrush RColor { get; init; } = Brushes.White;
    public string Closed { get; init; } = "";
    public string ExitReason { get; init; } = "";
    public string Thesis { get; init; } = "";
}

public partial class OverviewTab : UserControl
{
    private static readonly IBrush GreenBrush  = new SolidColorBrush(Color.Parse("#038C4C"));
    private static readonly IBrush RedBrush    = new SolidColorBrush(Color.Parse("#BF1B1B"));
    private static readonly IBrush YellowBrush = new SolidColorBrush(Color.Parse("#FFE101"));
    private static readonly IBrush DimBrush    = new SolidColorBrush(Color.Parse("#4A5568"));
    private static readonly IBrush WhiteBrush  = new SolidColorBrush(Color.Parse("#EBFFFF"));

    public OverviewTab() => InitializeComponent();

    public void Load(JournalService svc)
    {
        var stats = svc.GetStats();
        BindStats(stats);

        var open = svc.GetOpenTrades();
        BindOpenTrades(open);

        var closed = svc.GetRecentClosed(12);
        BindClosedTrades(closed);
    }

    private void BindStats(DashboardStats s)
    {
        StatNTrades.Text = s.NTrades.ToString();
        StatWinRate.Text = s.NTrades == 0 ? "—" : $"{s.WinRate * 100:F1}%";
        StatExpectR.Text = s.NTrades == 0 ? "—" : FormatR(s.ExpectancyR);
        StatExpectDollar.Text = s.NTrades == 0 ? "" : $"${s.ExpectancyDollar:+0.00;-0.00} / trade";
        StatPF.Text = s.NTrades == 0 ? "—" : $"{s.ProfitFactor:F2}×";
        StatMaxDD.Text = s.MaxDrawdown == 0 ? "—" : $"${s.MaxDrawdown:F0}";
        StatOpenPos.Text = s.OpenPositions.ToString();
        StatOpenRisk.Text = s.TotalOpenRisk > 0 ? $"${s.TotalOpenRisk:F0} at risk" : "";

        StatWinRate.Foreground = s.WinRate >= 0.5 ? GreenBrush : RedBrush;
        StatExpectR.Foreground = s.ExpectancyR >= 0 ? GreenBrush : RedBrush;
        StatPF.Foreground = s.ProfitFactor >= 1 ? GreenBrush : RedBrush;
    }

    private void BindOpenTrades(System.Collections.Generic.List<TradeRecord> trades)
    {
        var rows = trades.Select(t => new OpenTradeRow
        {
            Symbol = t.Symbol,
            DirGlyph = DirGlyph(t.Direction),
            DirColor = DirBrush(t.Direction),
            Strategy = t.StrategyType ?? t.InstrumentType,
            Risk = $"${t.InitialRisk:F0}",
            Opened = t.OpenedAt.Length >= 10 ? t.OpenedAt[..10] : t.OpenedAt,
            Thesis = t.Thesis ?? "",
        }).ToList();

        OpenList.ItemsSource = rows;
        OpenList.IsVisible = rows.Count > 0;
        NoOpenMsg.IsVisible = rows.Count == 0;
        OpenCountBadge.Text = rows.Count.ToString();
    }

    private void BindClosedTrades(System.Collections.Generic.List<TradeRecord> trades)
    {
        var rows = trades.Select(t =>
        {
            var pnl = t.RealizedPnl ?? 0;
            var r = t.RMultiple;
            return new ClosedTradeRow
            {
                Symbol = t.Symbol,
                DirGlyph = DirGlyph(t.Direction),
                DirColor = DirBrush(t.Direction),
                Pnl = $"${pnl:+0.00;-0.00}",
                PnlColor = pnl >= 0 ? GreenBrush : RedBrush,
                R = r.HasValue ? FormatR((double)r.Value) : "—",
                RColor = r.HasValue ? (r.Value >= 0 ? GreenBrush : RedBrush) : DimBrush,
                Closed = (t.ClosedAt ?? "")[(Math.Max(0, (t.ClosedAt?.Length ?? 0) - 10))..],
                ExitReason = (t.ExitReason ?? "").Replace('_', ' '),
                Thesis = t.Thesis ?? "",
            };
        }).ToList();

        ClosedList.ItemsSource = rows;
        ClosedList.IsVisible = rows.Count > 0;
        NoClosedMsg.IsVisible = rows.Count == 0;
    }

    private static string DirGlyph(string dir) => dir switch
    {
        "long"    => "↑ LONG",
        "short"   => "↓ SHORT",
        "neutral" => "→ NEUT",
        _         => dir,
    };

    private IBrush DirBrush(string dir) => dir switch
    {
        "long"    => GreenBrush,
        "short"   => RedBrush,
        "neutral" => YellowBrush,
        _         => WhiteBrush,
    };

    private static string FormatR(double r) => $"{r:+0.00;-0.00}R";
}
