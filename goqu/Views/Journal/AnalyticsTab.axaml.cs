using System.Linq;
using Avalonia.Controls;
using Avalonia.Controls.Shapes;
using Avalonia.Layout;
using Avalonia.Media;
using goqu.Services;

namespace goqu.Views.Journal;

public sealed class AnalyticsDisplayRow
{
    public string Label { get; init; } = "";
    public string NStr { get; init; } = "";
    public string ExpR { get; init; } = "";
    public IBrush ExpRColor { get; init; } = Brushes.White;
    public string WR { get; init; } = "";
    public string TotalPnl { get; init; } = "";
    public IBrush PnlColor { get; init; } = Brushes.White;
}

public partial class AnalyticsTab : UserControl
{
    private static readonly IBrush GreenBrush = new SolidColorBrush(Color.Parse("#038C4C"));
    private static readonly IBrush RedBrush   = new SolidColorBrush(Color.Parse("#BF1B1B"));
    private static readonly IBrush DimBrush   = new SolidColorBrush(Color.Parse("#4A5568"));
    private static readonly IBrush WhiteBrush = new SolidColorBrush(Color.Parse("#EBFFFF"));

    public AnalyticsTab() => InitializeComponent();

    public void Load(JournalService svc)
    {
        var stats = svc.GetStats();

        // Summary boxes
        ExpR.Text      = stats.NTrades == 0 ? "—" : FormatR(stats.ExpectancyR);
        ExpR.Foreground = stats.ExpectancyR >= 0 ? GreenBrush : RedBrush;
        ExpDollar.Text = stats.NTrades == 0 ? "" : $"${stats.ExpectancyDollar:+0.00;-0.00} avg / trade";
        PF.Text        = stats.NTrades == 0 ? "—" : $"{stats.ProfitFactor:F2}×";
        PF.Foreground  = stats.ProfitFactor >= 1 ? GreenBrush : RedBrush;

        // Half-Kelly: wr - (1-wr)/payoffR; payoffR ≈ avg_win/|avg_loss| estimated from stats
        // Simple approximation shown as "need more data" below a threshold
        Kelly.Text = "—";
        if (stats.NTrades >= 10 && stats.ProfitFactor > 0 && stats.WinRate > 0)
        {
            double loseRate = 1 - stats.WinRate;
            double payoff = stats.ProfitFactor;
            double fullKelly = stats.WinRate - loseRate / payoff;
            double halfKelly = fullKelly / 2.0;
            Kelly.Text = halfKelly > 0 ? $"{halfKelly * 100:F1}%" : "—";
        }

        WR.Text     = stats.NTrades == 0 ? "—" : $"{stats.WinRate * 100:F1}%";
        NClosed.Text = (stats.NTrades - stats.OpenPositions).ToString();
        AvgWin.Text  = "—";
        AvgLoss.Text = "—";

        // R Distribution
        var rDist = svc.GetRDistribution();
        RDistPanel.Children.Clear();
        RDistEmpty.IsVisible = rDist.Count == 0;
        foreach (var row in rDist)
        {
            bool isPositive = row.Bucket.StartsWith('0') || row.Bucket.StartsWith('1') || row.Bucket.StartsWith('2') || row.Bucket == ">= 3R";
            var barColor = isPositive ? GreenBrush : RedBrush;
            var rowPanel = new Grid
            {
                ColumnDefinitions = new ColumnDefinitions("55,*,30"),
                Height = 18,
            };
            rowPanel.Children.Add(new TextBlock
            {
                Text = row.Bucket,
                FontSize = 9,
                Foreground = new SolidColorBrush(Color.Parse("#4A5568")),
                VerticalAlignment = VerticalAlignment.Center,
                [Grid.ColumnProperty] = 0,
            });
            var bar = new Rectangle
            {
                Height = 10,
                Width = System.Math.Max(2, row.BarWidth * 4),
                Fill = barColor,
                HorizontalAlignment = HorizontalAlignment.Left,
                VerticalAlignment = VerticalAlignment.Center,
                [Grid.ColumnProperty] = 1,
            };
            rowPanel.Children.Add(bar);
            rowPanel.Children.Add(new TextBlock
            {
                Text = row.N.ToString(),
                FontSize = 9,
                Foreground = new SolidColorBrush(Color.Parse("#4A5568")),
                VerticalAlignment = VerticalAlignment.Center,
                HorizontalAlignment = HorizontalAlignment.Right,
                [Grid.ColumnProperty] = 2,
            });
            RDistPanel.Children.Add(rowPanel);
        }

        // By emotion
        var byEmotion = svc.GetByEmotion();
        EmotionEmpty.IsVisible = byEmotion.Count == 0;
        EmotionList.IsVisible = byEmotion.Count > 0;
        EmotionList.ItemsSource = byEmotion.Select(r => ToDisplayRow(r)).ToList();

        // By setup
        var bySetup = svc.GetBySetup();
        SetupEmpty.IsVisible = bySetup.Count == 0;
        SetupList.IsVisible = bySetup.Count > 0;
        SetupList.ItemsSource = bySetup.Select(r => ToDisplayRow(r)).ToList();
    }

    private AnalyticsDisplayRow ToDisplayRow(goqu.Models.AnalyticsRow r) => new()
    {
        Label = r.Label,
        NStr = r.N.ToString(),
        ExpR = FormatR(r.ExpectancyR),
        ExpRColor = r.ExpectancyR >= 0 ? GreenBrush : RedBrush,
        WR = $"{r.WinRate * 100:F1}%",
        TotalPnl = $"${r.TotalPnl:+0.00;-0.00}",
        PnlColor = r.TotalPnl >= 0 ? GreenBrush : RedBrush,
    };

    private static string FormatR(double r) => $"{r:+0.00;-0.00}R";
}
