using Avalonia.Controls;
using Avalonia.Interactivity;
using goqu.Services;

namespace goqu.Views.Journal;

public partial class JournalView : UserControl
{
    private JournalService? _svc;
    private string _dbPath = "";
    private long _accountId;

    public JournalView() => InitializeComponent();

    public void Initialize(string dbPath, long accountId)
    {
        _dbPath = dbPath;
        _accountId = accountId;
        _svc = new JournalService(dbPath, accountId);
        Refresh();
    }

    public void Refresh()
    {
        if (_svc is null) return;
        PanelOverview.Load(_svc);
        if (PanelTradeLog.IsVisible) PanelTradeLog.Load(_svc);
        if (PanelAnalytics.IsVisible) PanelAnalytics.Load(_svc);
    }

    private void OnTabClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button btn) return;

        // Deactivate all tabs
        TabOverview.Classes.Remove("Active");
        TabTradeLog.Classes.Remove("Active");
        TabAnalytics.Classes.Remove("Active");

        PanelOverview.IsVisible = false;
        PanelTradeLog.IsVisible = false;
        PanelAnalytics.IsVisible = false;

        if (btn == TabOverview)
        {
            TabOverview.Classes.Add("Active");
            PanelOverview.IsVisible = true;
            PanelOverview.Load(_svc!);
        }
        else if (btn == TabTradeLog)
        {
            TabTradeLog.Classes.Add("Active");
            PanelTradeLog.IsVisible = true;
            PanelTradeLog.Load(_svc!);
        }
        else if (btn == TabAnalytics)
        {
            TabAnalytics.Classes.Add("Active");
            PanelAnalytics.IsVisible = true;
            PanelAnalytics.Load(_svc!);
        }
    }

    private async void OnNewTrade(object? sender, RoutedEventArgs e)
    {
        if (_svc is null) return;
        var win = new NewTradeWindow(_dbPath, _accountId);
        await win.ShowDialog(TopLevel.GetTopLevel(this) as Window ?? throw new System.Exception("No window"));
        if (win.TradeCreated) Refresh();
    }
}
