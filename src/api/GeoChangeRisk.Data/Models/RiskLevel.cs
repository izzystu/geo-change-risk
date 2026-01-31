namespace GeoChangeRisk.Data.Models;

/// <summary>
/// Risk level classification based on computed risk score.
/// </summary>
public enum RiskLevel
{
    /// <summary>Low risk (score 0-24)</summary>
    Low = 0,

    /// <summary>Medium risk (score 25-49)</summary>
    Medium = 1,

    /// <summary>High risk (score 50-74)</summary>
    High = 2,

    /// <summary>Critical risk (score 75-100)</summary>
    Critical = 3
}
