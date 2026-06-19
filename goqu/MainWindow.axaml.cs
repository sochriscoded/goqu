using System;
using System.IO;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Microsoft.Data.Sqlite;

namespace goqu;

public partial class MainWindow : Window
{
    private static readonly string DbDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "goqu");

    private static readonly string DbPath = Path.Combine(DbDir, "goqu.db");

    public MainWindow()
    {
        InitializeComponent();
        EnsureDatabase();
        RefreshView();
    }

    private static void EnsureDatabase()
    {
        Directory.CreateDirectory(DbDir);
        using var conn = new SqliteConnection($"Data Source={DbPath}");
        conn.Open();
        using var cmd = conn.CreateCommand();
        cmd.CommandText = """
            CREATE TABLE IF NOT EXISTS account (
                account_id    INTEGER PRIMARY KEY,
                name          TEXT    NOT NULL,
                base_currency TEXT    NOT NULL DEFAULT 'USD',
                opened_at     TEXT,
                notes         TEXT
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            """;
        cmd.ExecuteNonQuery();
    }

    private void RefreshView()
    {
        using var conn = new SqliteConnection($"Data Source={DbPath}");
        conn.Open();

        using var countCmd = conn.CreateCommand();
        countCmd.CommandText = "SELECT COUNT(*) FROM account";
        var count = (long)countCmd.ExecuteScalar()!;

        var hasAccount = count > 0;
        SetupPanel.IsVisible = !hasAccount;
        DashboardPanel.IsVisible = hasAccount;

        if (hasAccount)
        {
            using var nameCmd = conn.CreateCommand();
            nameCmd.CommandText = "SELECT name FROM account ORDER BY account_id LIMIT 1";
            SidebarAccountName.Text = nameCmd.ExecuteScalar()?.ToString() ?? "Account";
        }
    }

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
