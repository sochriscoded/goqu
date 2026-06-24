using System.Collections.Generic;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using goqu.Models;
using goqu.Services;

namespace goqu.Views.Journal;

public sealed class LogTradeRow
{
    public long TradeId { get; init; }
    public string Symbol { get; init; } = "";
    public string DirGlyph { get; init; } = "";
    public IBrush DirColor { get; init; } = Brushes.White;
    public string Strategy { get; init; } = "";
    public string StatusLabel { get; init; } = "";
    public IBrush StatusColor { get; init; } = Brushes.White;
    public string Risk { get; init; } = "";
    public string Pnl { get; init; } = "";
    public IBrush PnlColor { get; init; } = Brushes.White;
    public string R { get; init; } = "";
    public IBrush RColor { get; init; } = Brushes.White;
    public string Date { get; init; } = "";
    public bool IsOpen { get; init; }
}

public partial class TradeLogTab : UserControl
{
    private static readonly IBrush GreenBrush  = new SolidColorBrush(Color.Parse("#038C4C"));
    private static readonly IBrush RedBrush    = new SolidColorBrush(Color.Parse("#BF1B1B"));
    private static readonly IBrush YellowBrush = new SolidColorBrush(Color.Parse("#FFE101"));
    private static readonly IBrush BlueBrush   = new SolidColorBrush(Color.Parse("#0085CD"));
    private static readonly IBrush DimBrush    = new SolidColorBrush(Color.Parse("#4A5568"));
    private static readonly IBrush WhiteBrush  = new SolidColorBrush(Color.Parse("#EBFFFF"));

    private JournalService? _svc;
    private List<TradeRecord> _allTrades = [];
    private LogTradeRow? _selectedRow;

    public TradeLogTab() => InitializeComponent();

    public void Load(JournalService svc)
    {
        _svc = svc;
        _allTrades = svc.GetAllTrades();
        ApplyFilter();
    }

    private void ApplyFilter()
    {
        var statusFilter = FilterStatus.SelectedIndex;
        var dirFilter = FilterDirection.SelectedIndex;
        var symFilter = (FilterSymbol.Text ?? "").Trim().ToUpperInvariant();

        var rows = _allTrades
            .Where(t => statusFilter == 0 || (statusFilter == 1 && t.Status == "open") || (statusFilter == 2 && t.Status == "closed"))
            .Where(t => dirFilter == 0 || (dirFilter == 1 && t.Direction == "long") || (dirFilter == 2 && t.Direction == "short") || (dirFilter == 3 && t.Direction == "neutral"))
            .Where(t => symFilter == "" || t.Symbol.Contains(symFilter))
            .Select(t =>
            {
                var pnl = t.RealizedPnl ?? 0;
                return new LogTradeRow
                {
                    TradeId = t.TradeId,
                    Symbol = t.Symbol,
                    DirGlyph = DirGlyph(t.Direction),
                    DirColor = DirBrush(t.Direction),
                    Strategy = t.StrategyType ?? t.InstrumentType,
                    StatusLabel = t.Status.ToUpperInvariant(),
                    StatusColor = t.Status == "open" ? BlueBrush : t.Status == "closed" ? DimBrush : YellowBrush,
                    Risk = $"${t.InitialRisk:F0}",
                    Pnl = t.Status == "open" ? "—" : $"${pnl:+0.00;-0.00}",
                    PnlColor = pnl >= 0 ? GreenBrush : RedBrush,
                    R = t.RMultiple.HasValue ? $"{t.RMultiple.Value:+0.00;-0.00}R" : "—",
                    RColor = t.RMultiple.HasValue ? (t.RMultiple.Value >= 0 ? GreenBrush : RedBrush) : DimBrush,
                    Date = (t.Status == "open" ? t.OpenedAt : t.ClosedAt ?? t.OpenedAt)[..System.Math.Min(10, (t.Status == "open" ? t.OpenedAt : t.ClosedAt ?? t.OpenedAt).Length)],
                    IsOpen = t.Status == "open",
                };
            }).ToList();

        TradeList.ItemsSource = rows;
        TradeCountLabel.Text = $"{rows.Count} trade{(rows.Count != 1 ? "s" : "")}";
        BtnClose.IsEnabled = false;
        _selectedRow = null;
    }

    private void OnApplyFilter(object? sender, RoutedEventArgs e) => ApplyFilter();

    private void OnTradeSelected(object? sender, SelectionChangedEventArgs e)
    {
        _selectedRow = TradeList.SelectedItem as LogTradeRow;
        BtnClose.IsEnabled = _selectedRow?.IsOpen == true;
    }

    private async void OnCloseTrade(object? sender, RoutedEventArgs e)
    {
        if (_selectedRow is null || _svc is null) return;
        var win = new CloseTradeWindow(_selectedRow.TradeId, _selectedRow.Symbol);
        await win.ShowDialog(TopLevel.GetTopLevel(this) as Window ?? throw new System.Exception("No window"));
        if (win.TradeClosedSuccessfully)
        {
            _svc.CloseTrade(_selectedRow.TradeId, win.ExitReason, win.ExitPrice, win.ExitFees,
                win.ExitFollowedPlan, win.ThesisCorrect, win.Notes);
            Load(_svc);
        }
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
}
