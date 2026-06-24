using System;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using goqu.Services;

namespace goqu.Views;

public partial class HomeView : UserControl
{
    public Action? OpenJournal { get; set; }
    public Action? OpenResearch { get; set; }

    public HomeView()
    {
        InitializeComponent();
    }

    public void Initialize(string dbPath, long accountId, string accountName)
    {
        AccountLabel.Text = accountName.ToUpperInvariant();
        RefreshClock();
        LoadStats(dbPath, accountId);
    }

    public void RefreshClock()
    {
        var now = DateTime.Now;
        var hour = now.Hour;
        GreetingLabel.Text = hour < 12 ? "GOOD MORNING" : hour < 17 ? "GOOD AFTERNOON" : "GOOD EVENING";
        DateLabel.Text = now.ToString("dddd, MMMM d").ToUpperInvariant() + "  ·  " + now.Year;
        TimeLabel.Text = now.ToString("h:mm tt");
    }

    private void LoadStats(string dbPath, long accountId)
    {
        try
        {
            var svc = new JournalService(dbPath, accountId);
            var stats = svc.GetStats();

            // Total P&L — color the top accent bar
            if (stats.TotalPnl != 0)
            {
                var pnlColor = stats.TotalPnl >= 0 ? "#06301A" : "#2A0808";
                PnlAccent.Fill = new SolidColorBrush(Color.Parse(pnlColor));
                StatPnl.Text = (stats.TotalPnl >= 0 ? "+" : "") + stats.TotalPnl.ToString("C0");
                StatPnl.Foreground = new SolidColorBrush(
                    Color.Parse(stats.TotalPnl >= 0 ? "#038C4C" : "#BF1B1B"));
            }
            else
            {
                StatPnl.Text = "—";
            }
            StatPnlSub.Text = stats.NTrades > 0 ? $"{stats.NTrades} trades" : "no trades yet";

            // Win rate
            if (stats.NTrades > 0 && stats.WinRate > 0)
            {
                StatWR.Text = (stats.WinRate * 100).ToString("F1") + "%";
                StatWR.Foreground = new SolidColorBrush(
                    Color.Parse(stats.WinRate >= 0.5 ? "#038C4C" : "#BF1B1B"));
            }
            else
            {
                StatWR.Text = "—";
            }
            StatWRSub.Text = stats.NTrades > 0 ? $"profit factor  {stats.ProfitFactor:F2}" : "";

            // Expectancy
            if (stats.NTrades > 0 && stats.ExpectancyR != 0)
            {
                StatExp.Text = (stats.ExpectancyR >= 0 ? "+" : "") + stats.ExpectancyR.ToString("F2") + "R";
                StatExp.Foreground = new SolidColorBrush(
                    Color.Parse(stats.ExpectancyR >= 0 ? "#038C4C" : "#BF1B1B"));
            }
            else
            {
                StatExp.Text = "—";
            }
            StatExpSub.Text = stats.ExpectancyDollar != 0
                ? (stats.ExpectancyDollar >= 0 ? "+" : "") + stats.ExpectancyDollar.ToString("C0") + " / trade"
                : "";

            // Open positions
            StatOpenPos.Text = stats.OpenPositions.ToString();
            StatOpenRisk.Text = stats.TotalOpenRisk > 0
                ? $"${stats.TotalOpenRisk:N0} at risk"
                : stats.OpenPositions > 0 ? "positions open" : "no open trades";

            // Journal module card stat
            CardJournalStat.Text = $"{stats.NTrades} trade{(stats.NTrades == 1 ? "" : "s")}";
            CardJournalR.Text = stats.NTrades > 0 && stats.ExpectancyR != 0
                ? "·  " + (stats.ExpectancyR >= 0 ? "+" : "") + stats.ExpectancyR.ToString("F2") + "R avg"
                : "";
        }
        catch
        {
            // Stats unavailable — leave defaults
        }
    }

    private void OnOpenJournal(object? sender, RoutedEventArgs e)
        => OpenJournal?.Invoke();
}
