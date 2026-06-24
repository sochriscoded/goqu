namespace goqu.Models;

public class TradeRecord
{
    public long TradeId { get; set; }
    public long AccountId { get; set; }
    public string Symbol { get; set; } = "";
    public string InstrumentType { get; set; } = "equity";
    public string Direction { get; set; } = "long";
    public string? StrategyType { get; set; }
    public string SourceType { get; set; } = "discretionary";
    public string Status { get; set; } = "open";
    public string OpenedAt { get; set; } = "";
    public string? ClosedAt { get; set; }
    public int? PlannedHoldDays { get; set; }
    public decimal InitialRisk { get; set; }
    public decimal? PlannedStop { get; set; }
    public decimal? PlannedTarget { get; set; }
    public decimal? PlannedTargetPnl { get; set; }
    public decimal? AccountValueAtEntry { get; set; }
    public string? Thesis { get; set; }
    public decimal? ConfidencePct { get; set; }
    public int? Conviction { get; set; }
    public string? Invalidation { get; set; }
    public decimal? EntryUnderlyingPrice { get; set; }
    public decimal? IvAtEntry { get; set; }
    public decimal? IvRankAtEntry { get; set; }
    public decimal? VixAtEntry { get; set; }
    public string? MarketRegime { get; set; }
    public string? EmotionalState { get; set; }
    public string? TradeOrigin { get; set; }
    public int? FollowedPlan { get; set; }
    public string? RuleBroken { get; set; }
    public string? ExitReason { get; set; }
    public int? ExitFollowedPlan { get; set; }
    public int? ThesisCorrect { get; set; }
    public string? Notes { get; set; }
    // Computed from v_trade
    public decimal? RealizedPnl { get; set; }
    public decimal? RMultiple { get; set; }
    public decimal? HoldDays { get; set; }
    public decimal? RiskPct { get; set; }
    public int? IsWin { get; set; }
}

public class TradeLeg
{
    public long LegId { get; set; }
    public long TradeId { get; set; }
    public string LegType { get; set; } = "equity";
    public string Side { get; set; } = "long";
    public decimal Quantity { get; set; }
    public decimal Multiplier { get; set; } = 1;
    public decimal? Strike { get; set; }
    public string? Expiry { get; set; }
    public decimal EntryPrice { get; set; }
    public decimal? ExitPrice { get; set; }
    public decimal EntryFees { get; set; }
    public decimal ExitFees { get; set; }
    public decimal? EntryDelta { get; set; }
    public decimal? EntryTheta { get; set; }
    public decimal? EntryVega { get; set; }
    public decimal? EntryIv { get; set; }
    public int? DteAtEntry { get; set; }
}

public class DashboardStats
{
    public long NTrades { get; set; }
    public double WinRate { get; set; }
    public double ExpectancyR { get; set; }
    public double ExpectancyDollar { get; set; }
    public double TotalPnl { get; set; }
    public double ProfitFactor { get; set; }
    public double MaxDrawdown { get; set; }
    public long OpenPositions { get; set; }
    public double TotalOpenRisk { get; set; }
    public double BrierScore { get; set; }
}

public class AnalyticsRow
{
    public string Label { get; set; } = "";
    public int N { get; set; }
    public double ExpectancyR { get; set; }
    public double WinRate { get; set; }
    public double TotalPnl { get; set; }
}

public class RDistributionRow
{
    public string Bucket { get; set; } = "";
    public int N { get; set; }
    public double TotalPnl { get; set; }
    public int BarWidth { get; set; }
}
