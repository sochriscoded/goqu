using System;
using System.IO;
using Avalonia.Controls;
using Avalonia.Interactivity;
using goqu.Views;
using goqu.Views.EdgeDiscovery;
using goqu.Views.Income;
using goqu.Views.Journal;
using goqu.Views.QuantAnalysis;
using goqu.Views.Research;
using goqu.Views.Screener;
using Microsoft.Data.Sqlite;

namespace goqu;

public partial class MainWindow : Window
{
    private static readonly string DbDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "goqu");

    internal static readonly string DbPath = Path.Combine(DbDir, "goqu.db");

    private long _accountId;
    private string _accountName = "";
    private HomeView? _homeView;
    private JournalView? _journalView;
    private ResearchView? _researchView;
    private EdgeDiscoveryView? _edgeView;
    private QuantAnalysisView? _quantView;
    private ScreenerView? _screenerView;
    private IncomeView? _incomeView;
    private Button? _activeNavBtn;

    public MainWindow()
    {
        InitializeComponent();
        EnsureDatabase();
        RefreshView();
    }

    private static readonly string[] SchemaDdl =
    [
        "PRAGMA journal_mode=WAL",
        "PRAGMA foreign_keys=ON",
        "CREATE TABLE IF NOT EXISTS account (account_id INTEGER PRIMARY KEY, name TEXT NOT NULL, base_currency TEXT NOT NULL DEFAULT 'USD', opened_at TEXT, notes TEXT)",
        "CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)",
        "CREATE TABLE IF NOT EXISTS trade (trade_id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES account(account_id), symbol TEXT NOT NULL, instrument_type TEXT NOT NULL DEFAULT 'equity' CHECK(instrument_type IN('equity','option','etf','future','other')), direction TEXT NOT NULL CHECK(direction IN('long','short','neutral')), strategy_type TEXT, source_type TEXT DEFAULT 'discretionary' CHECK(source_type IN('discretionary','screener','research','tip','other')), status TEXT NOT NULL DEFAULT 'open' CHECK(status IN('open','closed','rolled')), opened_at TEXT NOT NULL, closed_at TEXT, planned_hold_days INTEGER, initial_risk REAL NOT NULL, planned_stop REAL, planned_target REAL, planned_target_pnl REAL, account_value_at_entry REAL, thesis TEXT, confidence_pct REAL CHECK(confidence_pct BETWEEN 0 AND 100), conviction INTEGER CHECK(conviction BETWEEN 1 AND 5), invalidation TEXT, entry_underlying_price REAL, iv_at_entry REAL, iv_rank_at_entry REAL, vix_at_entry REAL, market_regime TEXT, emotional_state TEXT CHECK(emotional_state IN('calm','confident','fomo','revenge','bored','anxious','fearful')), trade_origin TEXT CHECK(trade_origin IN('planned','impulsive')), followed_plan INTEGER CHECK(followed_plan IN(0,1)), rule_broken TEXT, exit_reason TEXT CHECK(exit_reason IN('target_hit','stop_hit','time_stop','thesis_invalidated','thesis_wrong_timing','mis_sized','regime_shift','exogenous_shock','discretionary_panic','discretionary_profit_take','rolled','expired','assigned')), exit_followed_plan INTEGER CHECK(exit_followed_plan IN(0,1)), thesis_correct INTEGER CHECK(thesis_correct IN(0,1)), notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS trade_leg (leg_id INTEGER PRIMARY KEY, trade_id INTEGER NOT NULL REFERENCES trade(trade_id) ON DELETE CASCADE, leg_type TEXT NOT NULL CHECK(leg_type IN('equity','call','put')), side TEXT NOT NULL CHECK(side IN('long','short')), quantity REAL NOT NULL CHECK(quantity > 0), multiplier REAL NOT NULL DEFAULT 1, strike REAL, expiry TEXT, entry_price REAL NOT NULL, exit_price REAL, entry_fees REAL DEFAULT 0, exit_fees REAL DEFAULT 0, entry_delta REAL, entry_theta REAL, entry_vega REAL, entry_iv REAL, dte_at_entry INTEGER)",
        "CREATE TABLE IF NOT EXISTS trade_tag (trade_id INTEGER NOT NULL REFERENCES trade(trade_id) ON DELETE CASCADE, tag TEXT NOT NULL, tag_category TEXT NOT NULL CHECK(tag_category IN('setup','mistake','theme')), PRIMARY KEY(trade_id,tag,tag_category))",
        "CREATE TABLE IF NOT EXISTS benchmark_price (symbol TEXT NOT NULL, date TEXT NOT NULL, close REAL NOT NULL, PRIMARY KEY(symbol,date))",
        "CREATE TABLE IF NOT EXISTS price_history (symbol TEXT NOT NULL, date TEXT NOT NULL, close REAL NOT NULL, PRIMARY KEY(symbol,date))",
        "CREATE TABLE IF NOT EXISTS account_snapshot (account_id INTEGER NOT NULL REFERENCES account(account_id), as_of TEXT NOT NULL, total_equity REAL NOT NULL, cash REAL, notes TEXT, PRIMARY KEY(account_id,as_of))",
        "CREATE INDEX IF NOT EXISTS idx_trade_symbol ON trade(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_trade_status ON trade(status)",
        "CREATE INDEX IF NOT EXISTS idx_trade_opened ON trade(opened_at)",
        "CREATE INDEX IF NOT EXISTS idx_trade_closed ON trade(closed_at)",
        "CREATE INDEX IF NOT EXISTS idx_leg_trade ON trade_leg(trade_id)",
        "CREATE INDEX IF NOT EXISTS idx_tag_trade ON trade_tag(trade_id)",
        """
        CREATE TABLE IF NOT EXISTS hypothesis (
            hypothesis_id   INTEGER PRIMARY KEY,
            account_id      INTEGER NOT NULL REFERENCES account(account_id),
            name            TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'untested'
                CHECK(status IN('untested','forward_testing','validated','rejected')),
            signal_type     TEXT CHECK(signal_type IN(
                                'price_action','fundamental','options','macro','composite','other')),
            structural_reason TEXT,
            signal_definition TEXT,
            universe        TEXT,
            n_trades        INTEGER,
            expectancy_r    REAL,
            win_rate        REAL,
            sharpe          REAL,
            t_statistic     REAL,
            p_value         REAL,
            notes           TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_hypothesis_account ON hypothesis(account_id)",
        """
        CREATE TABLE IF NOT EXISTS income_holding (
            holding_id   INTEGER PRIMARY KEY,
            account_id   INTEGER NOT NULL REFERENCES account(account_id),
            symbol       TEXT NOT NULL,
            sleeve       TEXT NOT NULL CHECK(sleeve IN('index_core','div_growth')),
            notes        TEXT,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id, symbol, sleeve)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS income_tax_lot (
            lot_id          INTEGER PRIMARY KEY,
            holding_id      INTEGER NOT NULL REFERENCES income_holding(holding_id) ON DELETE CASCADE,
            acquired_at     TEXT NOT NULL,
            shares          REAL NOT NULL CHECK(shares > 0),
            cost_per_share  REAL NOT NULL CHECK(cost_per_share >= 0),
            source          TEXT DEFAULT 'purchase'
                CHECK(source IN('purchase','drip','sweep','transfer','other')),
            notes           TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS dividend_received (
            div_id          INTEGER PRIMARY KEY,
            holding_id      INTEGER NOT NULL REFERENCES income_holding(holding_id),
            account_id      INTEGER NOT NULL REFERENCES account(account_id),
            ex_date         TEXT NOT NULL,
            pay_date        TEXT,
            amount_per_share REAL NOT NULL CHECK(amount_per_share >= 0),
            shares_held     REAL NOT NULL CHECK(shares_held > 0),
            total_amount    REAL NOT NULL,
            reinvested      INTEGER DEFAULT 0 CHECK(reinvested IN(0,1)),
            drip_shares     REAL,
            drip_price      REAL,
            notes           TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sweep_transaction (
            sweep_id            INTEGER PRIMARY KEY,
            account_id          INTEGER NOT NULL REFERENCES account(account_id),
            sweep_date          TEXT NOT NULL,
            gross_trading_pnl   REAL NOT NULL,
            net_trading_pnl     REAL NOT NULL,
            sweep_pct           REAL NOT NULL CHECK(sweep_pct > 0 AND sweep_pct <= 100),
            sweep_amount        REAL NOT NULL CHECK(sweep_amount > 0),
            destination_symbol  TEXT,
            destination_sleeve  TEXT CHECK(destination_sleeve IN('index_core','div_growth')),
            shares_purchased    REAL,
            purchase_price      REAL,
            notes               TEXT,
            created_at          TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_income_holding_account ON income_holding(account_id)",
        "CREATE INDEX IF NOT EXISTS idx_dividend_account ON dividend_received(account_id, ex_date)",
        "CREATE INDEX IF NOT EXISTS idx_sweep_account ON sweep_transaction(account_id, sweep_date)",
    ];

    private static void EnsureDatabase()
    {
        Directory.CreateDirectory(DbDir);
        using var conn = new SqliteConnection($"Data Source={DbPath}");
        conn.Open();
        foreach (var sql in SchemaDdl)
        {
            using var cmd = conn.CreateCommand();
            cmd.CommandText = sql;
            cmd.ExecuteNonQuery();
        }
    }

    private void RefreshView()
    {
        bool hasAccount;

        using (var conn = new SqliteConnection($"Data Source={DbPath}"))
        {
            conn.Open();

            using var countCmd = conn.CreateCommand();
            countCmd.CommandText = "SELECT COUNT(*) FROM account";
            hasAccount = (long)countCmd.ExecuteScalar()! > 0;

            SetupPanel.IsVisible = !hasAccount;
            DashboardPanel.IsVisible = hasAccount;

            if (hasAccount)
            {
                using var nameCmd = conn.CreateCommand();
                nameCmd.CommandText = "SELECT account_id, name FROM account ORDER BY account_id LIMIT 1";
                using var r = nameCmd.ExecuteReader();
                if (r.Read())
                {
                    _accountId = r.GetInt64(0);
                    _accountName = r.GetString(1);
                    SidebarAccountName.Text = _accountName;
                }
            }
        }

        if (hasAccount)
            ShowHome();
    }

    // ── Navigation ───────────────────────────────────────────────────────────

    private void SetActiveNav(Button? btn)
    {
        if (_activeNavBtn != null)
            _activeNavBtn.Classes.Remove("Active");
        _activeNavBtn = btn;
        if (_activeNavBtn != null)
            _activeNavBtn.Classes.Add("Active");
    }

    private void ShowHome()
    {
        _homeView ??= new HomeView();
        _homeView.OpenJournal = () =>
        {
            SetActiveNav(NavJournal);
            ShowJournal();
        };
        _homeView.Initialize(DbPath, _accountId, _accountName);
        MainContent.Content = _homeView;
        SetActiveNav(NavHome);
    }

    private void ShowJournal()
    {
        _journalView ??= new JournalView();
        _journalView.Initialize(DbPath, _accountId);
        MainContent.Content = _journalView;
    }

    // ── Nav handlers ─────────────────────────────────────────────────────────

    private void OnNavHome(object? sender, RoutedEventArgs e)
    {
        SetActiveNav(NavHome);
        ShowHome();
    }

    private void OnNavJournal(object? sender, RoutedEventArgs e)
    {
        SetActiveNav(NavJournal);
        ShowJournal();
    }

    private void OnNavResearch(object? sender, RoutedEventArgs e)
    {
        SetActiveNav(NavResearch);
        _researchView ??= new ResearchView();
        MainContent.Content = _researchView;
    }

    private void OnNavEdge(object? sender, RoutedEventArgs e)
    {
        SetActiveNav(NavEdge);
        _edgeView ??= new EdgeDiscoveryView();
        _edgeView.Initialize(DbPath, _accountId);
        MainContent.Content = _edgeView;
    }

    private void OnNavQuant(object? sender, RoutedEventArgs e)
    {
        SetActiveNav(NavQuant);
        _quantView ??= new QuantAnalysisView();
        _quantView.Initialize(DbPath, _accountId);
        MainContent.Content = _quantView;
    }

    private void OnNavScreener(object? sender, RoutedEventArgs e)
    {
        SetActiveNav(NavScreener);
        _screenerView ??= new ScreenerView();
        MainContent.Content = _screenerView;
    }

    private void OnNavIncome(object? sender, RoutedEventArgs e)
    {
        SetActiveNav(NavIncome);
        _incomeView ??= new IncomeView();
        _incomeView.Initialize(DbPath, _accountId);
        MainContent.Content = _incomeView;
    }

    private void OnNavPlaceholder(object? sender, RoutedEventArgs e)
    {
        var btn = sender as Button;
        SetActiveNav(btn);

        var label = btn?.Content?.ToString() ?? "Module";
        MainContent.Content = new Grid
        {
            Children =
            {
                new StackPanel
                {
                    VerticalAlignment = Avalonia.Layout.VerticalAlignment.Center,
                    HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Center,
                    Spacing = 8,
                    Children =
                    {
                        new TextBlock
                        {
                            Text = label.ToUpperInvariant(),
                            FontSize = 18, FontWeight = Avalonia.Media.FontWeight.Bold,
                            Foreground = new Avalonia.Media.SolidColorBrush(Avalonia.Media.Color.Parse("#1C2028")),
                            HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Center,
                        },
                        new TextBlock
                        {
                            Text = "Coming soon.",
                            FontSize = 12,
                            Foreground = new Avalonia.Media.SolidColorBrush(Avalonia.Media.Color.Parse("#1C2028")),
                            HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Center,
                        },
                    },
                },
            },
        };
    }

    // ── Account setup ─────────────────────────────────────────────────────────

    private void OnCreateAccount(object? sender, RoutedEventArgs e)
    {
        var name = AccountNameInput.Text?.Trim();
        if (string.IsNullOrEmpty(name))
        {
            SetupError.Text = "Account name is required.";
            SetupError.IsVisible = true;
            return;
        }

        var currencyRaw = ((ComboBoxItem?)CurrencyComboBox.SelectedItem)?.Content?.ToString() ?? "USD";
        var currency = currencyRaw.Length >= 3 ? currencyRaw[..3] : "USD";
        var apiKey = ApiKeyInput.Text?.Trim() ?? "";
        var notes = NotesInput.Text?.Trim() ?? "";

        try
        {
            using var conn = new SqliteConnection($"Data Source={DbPath}");
            conn.Open();

            using var accountCmd = conn.CreateCommand();
            accountCmd.CommandText = """
                INSERT INTO account (name, base_currency, opened_at, notes)
                VALUES ($name, $currency, $date, $notes)
                """;
            accountCmd.Parameters.AddWithValue("$name", name);
            accountCmd.Parameters.AddWithValue("$currency", currency);
            accountCmd.Parameters.AddWithValue("$date", DateTime.Today.ToString("yyyy-MM-dd"));
            accountCmd.Parameters.AddWithValue("$notes", string.IsNullOrEmpty(notes) ? DBNull.Value : (object)notes);
            accountCmd.ExecuteNonQuery();

            if (!string.IsNullOrEmpty(apiKey))
            {
                using var keyCmd = conn.CreateCommand();
                keyCmd.CommandText = """
                    INSERT INTO app_settings (key, value) VALUES ('alpha_vantage_api_key', $key)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """;
                keyCmd.Parameters.AddWithValue("$key", apiKey);
                keyCmd.ExecuteNonQuery();
            }

            SetupError.IsVisible = false;
            RefreshView();
        }
        catch (Exception ex)
        {
            SetupError.Text = $"Error: {ex.Message}";
            SetupError.IsVisible = true;
        }
    }
}
