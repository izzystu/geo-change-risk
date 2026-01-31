namespace GeoChangeRisk.Data.Models;

/// <summary>
/// Represents a risk event generated when a detected change is near an asset.
/// Links change polygons to affected assets with risk scoring.
/// </summary>
public class RiskEvent
{
    /// <summary>
    /// Unique identifier for the risk event.
    /// </summary>
    public Guid RiskEventId { get; set; }

    /// <summary>
    /// Foreign key to the change polygon that triggered this risk.
    /// </summary>
    public Guid ChangePolygonId { get; set; }

    /// <summary>
    /// Foreign key to the asset at risk.
    /// </summary>
    public required string AssetId { get; set; }

    /// <summary>
    /// Distance in meters from the change polygon to the asset.
    /// </summary>
    public double DistanceMeters { get; set; }

    /// <summary>
    /// Computed risk score (0-100).
    /// </summary>
    public int RiskScore { get; set; }

    /// <summary>
    /// Risk level classification based on score.
    /// </summary>
    public RiskLevel RiskLevel { get; set; }

    /// <summary>
    /// JSON breakdown of factors contributing to the risk score.
    /// Contains scoring component details for explainability.
    /// </summary>
    public Dictionary<string, object>? ScoringFactors { get; set; }

    /// <summary>
    /// Timestamp when the risk event was created.
    /// </summary>
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    /// <summary>
    /// Timestamp when notification was sent for this event.
    /// </summary>
    public DateTime? NotificationSentAt { get; set; }

    /// <summary>
    /// Timestamp when the event was acknowledged by a user.
    /// </summary>
    public DateTime? AcknowledgedAt { get; set; }

    /// <summary>
    /// User identifier who acknowledged the event.
    /// </summary>
    public string? AcknowledgedBy { get; set; }

    /// <summary>
    /// Navigation property to the source change polygon.
    /// </summary>
    public ChangePolygon? ChangePolygon { get; set; }

    /// <summary>
    /// Navigation property to the affected asset.
    /// </summary>
    public Asset? Asset { get; set; }
}
