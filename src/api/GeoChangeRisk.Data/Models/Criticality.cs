namespace GeoChangeRisk.Data.Models;

/// <summary>
/// Criticality level of an asset for risk prioritization.
/// </summary>
public enum Criticality
{
    /// <summary>Low criticality - minimal impact if affected</summary>
    Low = 0,

    /// <summary>Medium criticality - moderate impact if affected</summary>
    Medium = 1,

    /// <summary>High criticality - significant impact if affected</summary>
    High = 2,

    /// <summary>Critical - severe impact, requires immediate attention</summary>
    Critical = 3
}
