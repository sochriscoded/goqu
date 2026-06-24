using Avalonia.Controls;
using Avalonia.Interactivity;

namespace goqu.Views.Journal;

public partial class CloseTradeWindow : Window
{
    public bool TradeClosedSuccessfully { get; private set; }
    public string ExitReason { get; private set; } = "discretionary_profit_take";
    public decimal ExitPrice { get; private set; }
    public decimal ExitFees { get; private set; }
    public int ExitFollowedPlan { get; private set; } = 1;
    public int? ThesisCorrect { get; private set; }
    public string? Notes { get; private set; }

    public CloseTradeWindow(long tradeId, string symbol)
    {
        InitializeComponent();
        TradeSummary.Text = $"{symbol}  ·  Trade #{tradeId}";
    }

    private void OnCancel(object? sender, RoutedEventArgs e) => Close();

    private void OnClose(object? sender, RoutedEventArgs e)
    {
        ErrorMsg.IsVisible = false;

        if (!decimal.TryParse(ExitPriceInput.Text?.Trim(), out var price) || price <= 0)
        {
            ErrorMsg.Text = "Exit Price is required.";
            ErrorMsg.IsVisible = true;
            return;
        }

        decimal.TryParse(ExitFeesInput.Text?.Trim(), out var fees);
        var exitReason = ((ComboBoxItem?)ExitReasonBox.SelectedItem)?.Content?.ToString() ?? "discretionary_profit_take";
        var followed = FollowedPlanBox.SelectedIndex == 0 ? 1 : 0;
        int? thesisCorrect = ThesisCorrectBox.SelectedIndex == 2 ? null : (ThesisCorrectBox.SelectedIndex == 0 ? 1 : 0);
        var notes = string.IsNullOrWhiteSpace(NotesInput.Text) ? null : NotesInput.Text.Trim();

        ExitPrice = price;
        ExitFees = fees;
        ExitReason = exitReason;
        ExitFollowedPlan = followed;
        ThesisCorrect = thesisCorrect;
        Notes = notes;
        TradeClosedSuccessfully = true;
        Close();
    }
}
