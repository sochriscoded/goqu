using System.Collections.Generic;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;

namespace goqu.Views.Research;

public record DossierRow(
    string Symbol,
    string CompanyName,
    string Sector,
    string OutlookLabel,
    IBrush OutlookBg,
    IBrush OutlookFg,
    string ConvictionStars,
    string UpdatedAt
);

public partial class ResearchView : UserControl
{
    private static readonly IBrush BullishBg  = new SolidColorBrush(Color.Parse("#062A12"));
    private static readonly IBrush BullishFg  = new SolidColorBrush(Color.Parse("#038C4C"));
    private static readonly IBrush BearishBg  = new SolidColorBrush(Color.Parse("#2A0808"));
    private static readonly IBrush BearishFg  = new SolidColorBrush(Color.Parse("#BF1B1B"));
    private static readonly IBrush NeutralBg  = new SolidColorBrush(Color.Parse("#1E1800"));
    private static readonly IBrush NeutralFg  = new SolidColorBrush(Color.Parse("#FFE101"));

    private readonly List<DossierRow> _allDossiers = [];
    private Button? _activeTreeBtn;

    public ResearchView()
    {
        InitializeComponent();
        RecentEmpty.IsVisible = true;
        DossierEmpty.IsVisible = true;
        DossierList.IsVisible = false;
        ApplyFilter();
    }

    // ── Tree navigation ──────────────────────────────────────────────────────

    private void SetActiveTree(Button? btn)
    {
        _activeTreeBtn?.Classes.Remove("Active");
        _activeTreeBtn = btn;
        _activeTreeBtn?.Classes.Add("Active");
    }

    private void OnTreeAll(object? sender, RoutedEventArgs e)
    {
        SetActiveTree(TreeAll);
        ApplyFilter();
    }

    private void OnTreeFilter(object? sender, RoutedEventArgs e)
    {
        SetActiveTree(sender as Button);
        ApplyFilter();
    }

    // ── Search & filter ──────────────────────────────────────────────────────

    private void OnTreeSearchChanged(object? sender, TextChangedEventArgs e)
        => ApplyFilter();

    private void OnGlobalSearchChanged(object? sender, TextChangedEventArgs e)
        => ApplyFilter();

    private void OnFilterChanged(object? sender, SelectionChangedEventArgs e)
        => ApplyFilter();

    private void ApplyFilter()
    {
        // Guard: ComboBox SelectionChanged fires during InitializeComponent before x:Name fields are assigned
        if (DossierCountLabel is null) return;

        // All filtering will live here once the DB is wired up.
        // For now, _allDossiers is always empty — just sync the UI state.
        var filtered = _allDossiers;

        DossierCountLabel.Text = $"{filtered.Count} total";
        DossierList.ItemsSource = filtered;

        bool any = filtered.Count > 0;
        DossierList.IsVisible = any;
        DossierEmpty.IsVisible = !any;

        bool anyRecent = RecentCards.Children.Count > 0;
        RecentScroll.IsVisible = anyRecent;
        RecentEmpty.IsVisible = !anyRecent;
    }

    // ── Actions ──────────────────────────────────────────────────────────────

    private void OnNewDossier(object? sender, RoutedEventArgs e)
    {
        // TODO: open NewDossierWindow
    }

    private void OnDossierSelected(object? sender, SelectionChangedEventArgs e)
    {
        // TODO: open dossier detail view
    }

    // ── Public helpers ───────────────────────────────────────────────────────

    public static IBrush OutlookBackground(string outlook) => outlook switch
    {
        "bullish" => BullishBg,
        "bearish" => BearishBg,
        _ => NeutralBg,
    };

    public static IBrush OutlookForeground(string outlook) => outlook switch
    {
        "bullish" => BullishFg,
        "bearish" => BearishFg,
        _ => NeutralFg,
    };

    public static string ConvictionToStars(int? conviction) => conviction switch
    {
        1 => "◆◇◇◇◇",
        2 => "◆◆◇◇◇",
        3 => "◆◆◆◇◇",
        4 => "◆◆◆◆◇",
        5 => "◆◆◆◆◆",
        _ => "—",
    };
}
