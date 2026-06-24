using System.Collections.Generic;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;

namespace goqu.Views.Screener;

public record ScreenerRow(
    string Symbol,
    string Company,
    string Sector,
    string MktCap,
    string PE,      IBrush PEColor,
    string FwdPE,   IBrush FwdPEColor,
    string DivYield, IBrush DivColor,
    string RSI,     IBrush RSIColor,
    string IVRank,  IBrush IVRankColor,
    string Score,   IBrush ScoreBg, IBrush ScoreFg
);

public partial class ScreenerView : UserControl
{
    private static readonly IBrush GreenFg   = new SolidColorBrush(Color.Parse("#038C4C"));
    private static readonly IBrush RedFg     = new SolidColorBrush(Color.Parse("#BF1B1B"));
    private static readonly IBrush YellowFg  = new SolidColorBrush(Color.Parse("#FFE101"));
    private static readonly IBrush DimFg     = new SolidColorBrush(Color.Parse("#4A5568"));
    private static readonly IBrush WhiteFg   = new SolidColorBrush(Color.Parse("#EBFFFF"));
    private static readonly IBrush ScoreHighBg = new SolidColorBrush(Color.Parse("#062A12"));
    private static readonly IBrush ScoreMidBg  = new SolidColorBrush(Color.Parse("#1A1800"));
    private static readonly IBrush ScoreLowBg  = new SolidColorBrush(Color.Parse("#2A0808"));

    private bool _universeExpanded     = true;
    private bool _fundamentalsExpanded = true;
    private bool _technicalsExpanded   = false;
    private bool _optionsExpanded      = false;
    private bool _dividendsExpanded    = false;
    private bool _sentimentExpanded    = false;

    private readonly List<ScreenerRow> _results = [];
    private string _sortColumn = "score";
    private bool _sortDesc = true;
    private bool _initialized = false;

    public ScreenerView()
    {
        InitializeComponent();
        _initialized = true;
        ResultsEmpty.IsVisible   = true;
        NoResultsState.IsVisible = false;
        ResultsList.IsVisible    = false;
    }

    // ── Section toggles ──────────────────────────────────────────────────────

    private void OnToggleUniverse(object? s, RoutedEventArgs e)
    {
        _universeExpanded = !_universeExpanded;
        UniverseContent.IsVisible  = _universeExpanded;
        UniverseChevron.Text = _universeExpanded ? "▼" : "▶";
    }

    private void OnToggleFundamentals(object? s, RoutedEventArgs e)
    {
        _fundamentalsExpanded = !_fundamentalsExpanded;
        FundamentalsContent.IsVisible = _fundamentalsExpanded;
        FundChevron.Text = _fundamentalsExpanded ? "▼" : "▶";
    }

    private void OnToggleTechnicals(object? s, RoutedEventArgs e)
    {
        _technicalsExpanded = !_technicalsExpanded;
        TechnicalsContent.IsVisible = _technicalsExpanded;
        TechChevron.Text = _technicalsExpanded ? "▼" : "▶";
    }

    private void OnToggleOptions(object? s, RoutedEventArgs e)
    {
        _optionsExpanded = !_optionsExpanded;
        OptionsContent.IsVisible = _optionsExpanded;
        OptChevron.Text = _optionsExpanded ? "▼" : "▶";
    }

    private void OnToggleDividends(object? s, RoutedEventArgs e)
    {
        _dividendsExpanded = !_dividendsExpanded;
        DividendsContent.IsVisible = _dividendsExpanded;
        DivChevron.Text = _dividendsExpanded ? "▼" : "▶";
    }

    private void OnToggleSentiment(object? s, RoutedEventArgs e)
    {
        _sentimentExpanded = !_sentimentExpanded;
        SentimentContent.IsVisible = _sentimentExpanded;
        SentChevron.Text = _sentimentExpanded ? "▼" : "▶";
    }

    // ── Filter chip toggle ───────────────────────────────────────────────────

    private void OnChipToggle(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button btn) return;
        if (btn.Classes.Contains("Active"))
            btn.Classes.Remove("Active");
        else
            btn.Classes.Add("Active");
        UpdateActiveFilterCount();
    }

    // ── Range preset shortcuts ───────────────────────────────────────────────

    private void OnMktCapPreset(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button btn || btn.Tag is not string tag) return;
        var parts = tag.Split(',');
        MktCapMin.Text = parts.Length > 0 && parts[0].Length > 0 ? parts[0] : "";
        MktCapMax.Text = parts.Length > 1 && parts[1].Length > 0 ? parts[1] : "";
    }

    private void OnRSIPreset(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button btn || btn.Tag is not string tag) return;
        var parts = tag.Split(',');
        RSIMin.Text = parts.Length > 0 ? parts[0] : "";
        RSIMax.Text = parts.Length > 1 ? parts[1] : "";
    }

    private void OnIVRankPreset(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button btn || btn.Tag is not string tag) return;
        var parts = tag.Split(',');
        IVRankMin.Text = parts.Length > 0 ? parts[0] : "";
        IVRankMax.Text = parts.Length > 1 ? parts[1] : "";
    }

    // ── Range / dropdown change tracking ─────────────────────────────────────

    private void OnRangeChanged(object? sender, TextChangedEventArgs e)
    {
        if (!_initialized) return;
        UpdateActiveFilterCount();
    }

    private void OnPresetSelected(object? sender, SelectionChangedEventArgs e)
    {
        if (!_initialized) return;
        // TODO: populate filter controls from preset definition
    }

    private void UpdateActiveFilterCount()
    {
        if (!_initialized || ActiveFilterCount is null) return;
        int count = CountActiveFilters();
        ActiveFilterCount.Text = count == 0 ? "no filters active" : $"{count} filter{(count == 1 ? "" : "s")} active";
    }

    private int CountActiveFilters()
    {
        int n = 0;
        // Count non-empty range inputs
        TextBox[] ranges = [
            MktCapMin, MktCapMax, PEMin, PEMax, FwdPEMin, FwdPEMax, PEGMin, PEGMax,
            PBMin, PBMax, PSMin, PSMax, EVEBITDAMin, EVEBITDAMax,
            GrossMarginMin, GrossMarginMax, OpMarginMin, OpMarginMax,
            NetMarginMin, NetMarginMax, ROEMin, ROEMax, ROAMin, ROAMax, FCFYieldMin, FCFYieldMax,
            RevGrowthMin, RevGrowthMax, EPSGrowthMin, EPSGrowthMax, Rev3YMin, Rev3YMax,
            DEMin, DEMax, CRMin, CRMax, ICMin, ICMax,
            HighPctMin, HighPctMax, LowPctMin, LowPctMax,
            RSIMin, RSIMax, StochRSIMin, StochRSIMax,
            BetaMin, BetaMax, ATRMin, ATRMax, RSvsSpyMin, RSvsSpyMax,
            IVMin, IVMax, IVRankMin, IVRankMax, IVPctMin, IVPctMax,
            PCVolMin, PCVolMax, PCOIMin, PCOIMax, AvgOptVolMin,
            DivYieldMin, DivYieldMax, PayoutMin, PayoutMax,
            DivGrowthMin, DivGrowthMax, DivStreakMin, ExDivDays,
            PTUpsideMin, InstOwnMin, InstOwnMax, ShortFloatMin, ShortFloatMax,
            EarnSurpriseMin, EarnSurpriseMax,
        ];
        foreach (var tb in ranges)
            if (!string.IsNullOrWhiteSpace(tb.Text)) n++;

        // Count non-default ComboBox selections
        ComboBox[] combos = [SMA20Filter, SMA50Filter, SMA200Filter, MACDFilter, VolumeFilter, AnalystFilter, InsiderFilter];
        foreach (var cb in combos)
            if (cb.SelectedIndex > 0) n++;

        return n;
    }

    // ── Main actions ─────────────────────────────────────────────────────────

    private void OnRunScreen(object? sender, RoutedEventArgs e)
    {
        // TODO: query the database with active filters and populate _results
        // For now: show empty no-results state
        ResultsList.IsVisible    = false;
        ResultsEmpty.IsVisible   = false;
        NoResultsState.IsVisible = true;
        ResultsCountLabel.Text = "0 results";
        LastRunLabel.Text = "Last run: just now";
    }

    private void OnClearAll(object? sender, RoutedEventArgs e)
    {
        TextBox[] ranges = [
            MktCapMin, MktCapMax, PEMin, PEMax, FwdPEMin, FwdPEMax, PEGMin, PEGMax,
            PBMin, PBMax, PSMin, PSMax, EVEBITDAMin, EVEBITDAMax,
            GrossMarginMin, GrossMarginMax, OpMarginMin, OpMarginMax,
            NetMarginMin, NetMarginMax, ROEMin, ROEMax, ROAMin, ROAMax, FCFYieldMin, FCFYieldMax,
            RevGrowthMin, RevGrowthMax, EPSGrowthMin, EPSGrowthMax, Rev3YMin, Rev3YMax,
            DEMin, DEMax, CRMin, CRMax, ICMin, ICMax,
            HighPctMin, HighPctMax, LowPctMin, LowPctMax,
            RSIMin, RSIMax, StochRSIMin, StochRSIMax,
            BetaMin, BetaMax, ATRMin, ATRMax, RSvsSpyMin, RSvsSpyMax,
            IVMin, IVMax, IVRankMin, IVRankMax, IVPctMin, IVPctMax,
            PCVolMin, PCVolMax, PCOIMin, PCOIMax, AvgOptVolMin,
            DivYieldMin, DivYieldMax, PayoutMin, PayoutMax,
            DivGrowthMin, DivGrowthMax, DivStreakMin, ExDivDays,
            PTUpsideMin, InstOwnMin, InstOwnMax, ShortFloatMin, ShortFloatMax,
            EarnSurpriseMin, EarnSurpriseMax,
        ];
        foreach (var tb in ranges) tb.Text = "";

        ComboBox[] combos = [SMA20Filter, SMA50Filter, SMA200Filter, MACDFilter, VolumeFilter, AnalystFilter, InsiderFilter, SectorFilter];
        foreach (var cb in combos) cb.SelectedIndex = 0;

        PresetCombo.SelectedIndex = 0;
        ActiveFilterCount.Text = "no filters active";
    }

    private void OnSaveScreen(object? sender, RoutedEventArgs e)
    {
        // TODO: save current filter configuration with a name
    }

    private void OnConfigureColumns(object? sender, RoutedEventArgs e)
    {
        // TODO: show column visibility panel
    }

    private void OnSortColumn(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button btn || btn.Tag is not string col) return;
        if (_sortColumn == col)
            _sortDesc = !_sortDesc;
        else
        {
            _sortColumn = col;
            _sortDesc = true;
        }
        // TODO: re-sort _results
    }

    private void OnResultSelected(object? sender, SelectionChangedEventArgs e)
    {
        // TODO: open research dossier or detail panel for selected ticker
    }

    // ── Score color helpers ───────────────────────────────────────────────────

    public static IBrush ScoreBackground(int score) => score >= 70 ? ScoreHighBg : score >= 40 ? ScoreMidBg : ScoreLowBg;
    public static IBrush ScoreForeground(int score) => score >= 70 ? GreenFg    : score >= 40 ? YellowFg  : RedFg;
    public static IBrush RSIBrush(double rsi)        => rsi < 30   ? GreenFg    : rsi > 70   ? RedFg      : WhiteFg;
    public static IBrush IVRankBrush(double rank)    => rank > 70  ? RedFg      : rank > 40  ? YellowFg   : DimFg;
}
