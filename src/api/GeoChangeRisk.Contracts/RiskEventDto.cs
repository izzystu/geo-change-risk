namespace GeoChangeRisk.Contracts;

/// <summary>
/// Data transfer object for RiskEvent.
/// </summary>
public class RiskEventDto
{
    /// <summary>Unique identifier for the risk event.</summary>
    public Guid RiskEventId { get; set; }

    /// <summary>Change polygon that triggered this risk.</summary>
    public Guid ChangePolygonId { get; set; }

    /// <summary>Asset at risk.</summary>
    public required string AssetId { get; set; }

    /// <summary>Asset name.</summary>
    public required string AssetName { get; set; }

    /// <summary>Asset type (display name).</summary>
    public required string AssetTypeName { get; set; }

    /// <summary>Distance in meters from change to asset.</summary>
    public double DistanceMeters { get; set; }

    /// <summary>Computed risk score (0-100).</summary>
    public int RiskScore { get; set; }

    /// <summary>Risk level (numeric value).</summary>
    public int RiskLevel { get; set; }

    /// <summary>Risk level (display name).</summary>
    public required string RiskLevelName { get; set; }

    /// <summary>Breakdown of scoring factors.</summary>
    public Dictionary<string, object>? ScoringFactors { get; set; }

    /// <summary>When the event was created.</summary>
    public DateTime CreatedAt { get; set; }

    /// <summary>When notification was sent.</summary>
    public DateTime? NotificationSentAt { get; set; }

    /// <summary>When the event was acknowledged.</summary>
    public DateTime? AcknowledgedAt { get; set; }

    /// <summary>Who acknowledged the event.</summary>
    public string? AcknowledgedBy { get; set; }

    /// <summary>AOI ID (from change polygon -> processing run).</summary>
    public string? AoiId { get; set; }

    /// <summary>Change polygon geometry for display.</summary>
    public object? ChangeGeometry { get; set; }

    /// <summary>Asset geometry for display.</summary>
    public object? AssetGeometry { get; set; }
}

/// <summary>
/// Summary DTO for listing risk events (lighter weight).
/// </summary>
public class RiskEventSummaryDto
{
    /// <summary>Unique identifier for the risk event.</summary>
    public Guid RiskEventId { get; set; }

    /// <summary>Asset at risk.</summary>
    public required string AssetId { get; set; }

    /// <summary>Asset name.</summary>
    public required string AssetName { get; set; }

    /// <summary>Asset type (display name).</summary>
    public required string AssetTypeName { get; set; }

    /// <summary>Computed risk score (0-100).</summary>
    public int RiskScore { get; set; }

    /// <summary>Risk level (display name).</summary>
    public required string RiskLevelName { get; set; }

    /// <summary>Distance in meters from change to asset.</summary>
    public double DistanceMeters { get; set; }

    /// <summary>When the event was created.</summary>
    public DateTime CreatedAt { get; set; }

    /// <summary>Whether the event has been acknowledged.</summary>
    public bool IsAcknowledged { get; set; }
}

/// <summary>
/// Request DTO for creating a risk event (from pipeline).
/// </summary>
public class CreateRiskEventRequest
{
    /// <summary>Change polygon ID (nullable if polygon mapping failed).</summary>
    public Guid? ChangePolygonId { get; set; }

    /// <summary>Asset ID.</summary>
    public required string AssetId { get; set; }

    /// <summary>Distance in meters.</summary>
    public double DistanceMeters { get; set; }

    /// <summary>Risk score (0-100).</summary>
    public int RiskScore { get; set; }

    /// <summary>Risk level (numeric value).</summary>
    public int RiskLevel { get; set; }

    /// <summary>Scoring factor breakdown.</summary>
    public Dictionary<string, object>? ScoringFactors { get; set; }
}

/// <summary>
/// Request for bulk creating risk events.
/// </summary>
public class BulkCreateRiskEventsRequest
{
    /// <summary>List of risk events to create.</summary>
    public required List<CreateRiskEventRequest> Events { get; set; }
}

/// <summary>
/// Request DTO for acknowledging a risk event.
/// </summary>
public class AcknowledgeRiskEventRequest
{
    /// <summary>User identifier acknowledging the event.</summary>
    public required string AcknowledgedBy { get; set; }

    /// <summary>Optional notes about the acknowledgment.</summary>
    public string? Notes { get; set; }
}

/// <summary>
/// Query parameters for filtering risk events.
/// </summary>
public class RiskEventQueryParams
{
    /// <summary>Filter by AOI ID.</summary>
    public string? AoiId { get; set; }

    /// <summary>Filter by minimum risk score.</summary>
    public int? MinScore { get; set; }

    /// <summary>Filter by risk level.</summary>
    public int? RiskLevel { get; set; }

    /// <summary>Filter by asset ID.</summary>
    public string? AssetId { get; set; }

    /// <summary>Filter by processing run ID.</summary>
    public Guid? RunId { get; set; }

    /// <summary>Filter by acknowledgment status.</summary>
    public bool? IsAcknowledged { get; set; }

    /// <summary>Maximum number of results.</summary>
    public int Limit { get; set; } = 100;

    /// <summary>Number of results to skip.</summary>
    public int Offset { get; set; } = 0;
}
