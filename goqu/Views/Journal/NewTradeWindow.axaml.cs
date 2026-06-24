using System;
using System.Collections.Generic;
using Avalonia.Controls;
using Avalonia.Interactivity;
using goqu.Models;
using goqu.Services;

namespace goqu.Views.Journal;

public partial class NewTradeWindow : Window
{
    public bool TradeCreated { get; private set; }

    private readonly string _dbPath;
    private readonly long _accountId;
    private string _direction = "long";

    public NewTradeWindow(string dbPath, long accountId)
    {
        _dbPath = dbPath;
        _accountId = accountId;
        InitializeComponent();
        EntryDateInput.Text = DateTime.Today.ToString("yyyy-MM-dd");
        MultiplierInput.Text = "1";
        EntryFeesInput.Text = "0";
    }

    private void OnDirClick(object? sender, RoutedEventArgs e)
    {
        DirLong.Classes.Remove("Selected");
        DirShort.Classes.Remove("Selected");
        DirNeutral.Classes.Remove("Selected");

        if (sender == DirLong)    { DirLong.Classes.Add("Selected");    _direction = "long";    }
        else if (sender == DirShort)   { DirShort.Classes.Add("Selected");   _direction = "short";   }
        else if (sender == DirNeutral) { DirNeutral.Classes.Add("Selected"); _direction = "neutral"; }
    }

    private void OnCancel(object? sender, RoutedEventArgs e) => Close();

    private void OnLogTrade(object? sender, RoutedEventArgs e)
    {
        ErrorMsg.IsVisible = false;

        // Validate required fields
        var symbol = SymbolInput.Text?.Trim().ToUpperInvariant() ?? "";
        if (symbol.Length == 0) { ShowError("Symbol is required."); return; }

        if (!decimal.TryParse(RiskInput.Text?.Trim(), out var risk) || risk <= 0)
        { ShowError("Initial Risk must be a positive number."); return; }

        if (!decimal.TryParse(QtyInput.Text?.Trim(), out var qty) || qty <= 0)
        { ShowError("Quantity must be a positive number."); return; }

        if (!decimal.TryParse(EntryPriceInput.Text?.Trim(), out var entryPrice) || entryPrice <= 0)
        { ShowError("Entry Price must be a positive number."); return; }

        // Optional numerics
        decimal.TryParse(AcctValueInput.Text?.Trim(), out var acctValue);
        decimal.TryParse(StopInput.Text?.Trim(), out var stop);
        decimal.TryParse(TargetInput.Text?.Trim(), out var target);
        decimal.TryParse(EntryFeesInput.Text?.Trim(), out var fees);
        decimal.TryParse(MultiplierInput.Text?.Trim(), out var mult);
        if (mult <= 0) mult = 1;
        decimal.TryParse(ConfidenceInput.Text?.Trim(), out var confidence);
        int.TryParse(HoldDaysInput.Text?.Trim(), out var holdDays);
        decimal.TryParse(UnderlyingPriceInput.Text?.Trim(), out var underlying);
        decimal.TryParse(IvRankInput.Text?.Trim(), out var ivRank);
        decimal.TryParse(IvInput.Text?.Trim(), out var iv);
        decimal.TryParse(VixInput.Text?.Trim(), out var vix);
        decimal.TryParse(StrikeInput.Text?.Trim(), out var strike);
        int.TryParse(DteInput.Text?.Trim(), out var dte);
        decimal.TryParse(DeltaInput.Text?.Trim(), out var delta);

        var instrType = ((ComboBoxItem?)InstrumentBox.SelectedItem)?.Content?.ToString() ?? "equity";
        var source = ((ComboBoxItem?)SourceBox.SelectedItem)?.Content?.ToString() ?? "discretionary";
        var emotion = ((ComboBoxItem?)EmotionBox.SelectedItem)?.Content?.ToString();
        var origin = ((ComboBoxItem?)OriginBox.SelectedItem)?.Content?.ToString();

        // Determine leg type
        var legType = instrType switch
        {
            "option" when StrategyInput.Text?.Contains("call", StringComparison.OrdinalIgnoreCase) == true => "call",
            "option" when StrategyInput.Text?.Contains("put", StringComparison.OrdinalIgnoreCase) == true => "put",
            "option" => "call",
            _ => "equity",
        };
        var legSide = _direction == "short" ? "short" : "long";

        var trade = new TradeRecord
        {
            AccountId = _accountId,
            Symbol = symbol,
            InstrumentType = instrType,
            Direction = _direction,
            StrategyType = NullIfEmpty(StrategyInput.Text),
            SourceType = source,
            OpenedAt = EntryDateInput.Text?.Trim() ?? DateTime.Today.ToString("yyyy-MM-dd"),
            PlannedHoldDays = holdDays > 0 ? holdDays : null,
            InitialRisk = risk,
            PlannedStop = stop > 0 ? stop : null,
            PlannedTarget = target > 0 ? target : null,
            AccountValueAtEntry = acctValue > 0 ? acctValue : null,
            Thesis = NullIfEmpty(ThesisInput.Text),
            ConfidencePct = confidence > 0 ? confidence : null,
            Invalidation = NullIfEmpty(InvalidationInput.Text),
            EntryUnderlyingPrice = underlying > 0 ? underlying : null,
            IvAtEntry = iv > 0 ? iv : null,
            IvRankAtEntry = ivRank > 0 ? ivRank : null,
            VixAtEntry = vix > 0 ? vix : null,
            EmotionalState = emotion,
            TradeOrigin = origin,
            FollowedPlan = 1,
        };

        var leg = new TradeLeg
        {
            LegType = legType,
            Side = legSide,
            Quantity = qty,
            Multiplier = mult,
            Strike = strike > 0 ? strike : null,
            Expiry = NullIfEmpty(ExpiryInput.Text),
            EntryPrice = entryPrice,
            EntryFees = fees,
            DteAtEntry = dte > 0 ? dte : null,
            EntryDelta = delta != 0 ? delta : null,
        };

        var tags = BuildTags(SetupTagsInput.Text, "setup");
        tags.AddRange(BuildTags(ThemeTagsInput.Text, "theme"));

        try
        {
            var svc = new JournalService(_dbPath, _accountId);
            svc.InsertTrade(trade, leg, tags);
            TradeCreated = true;
            Close();
        }
        catch (Exception ex)
        {
            ShowError($"Database error: {ex.Message}");
        }
    }

    private void ShowError(string msg)
    {
        ErrorMsg.Text = msg;
        ErrorMsg.IsVisible = true;
    }

    private static string? NullIfEmpty(string? s) =>
        string.IsNullOrWhiteSpace(s) ? null : s.Trim();

    private static List<(string, string)> BuildTags(string? raw, string category)
    {
        var list = new List<(string, string)>();
        if (string.IsNullOrWhiteSpace(raw)) return list;
        foreach (var tag in raw.Split(','))
        {
            var t = tag.Trim().ToLowerInvariant().Replace(' ', '_');
            if (t.Length > 0) list.Add((t, category));
        }
        return list;
    }
}
