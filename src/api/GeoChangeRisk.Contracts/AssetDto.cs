using System.Text.Json.Serialization;

namespace GeoChangeRisk.Contracts;

/// <summary>
/// Data transfer object for Asset.
/// </summary>
public class AssetDto
{
    /// <summary>Unique identifier for the asset.</summary>
    public required string AssetId { get; set; }

    /// <summary>AOI containing this asset.</summary>
    public required string AoiId { get; set; }

    /// <summary>Display name for the asset.</summary>
    public required string Name { get; set; }

    /// <summary>Type of asset (numeric value).</summary>
    public int AssetType { get; set; }

    /// <summary>Type of asset (display name).</summary>
    public required string AssetTypeName { get; set; }

    /// <summary>Criticality level (numeric value).</summary>
    public int Criticality { get; set; }

    /// <summary>Criticality level (display name).</summary>
    public required string CriticalityName { get; set; }

    /// <summary>GeoJSON geometry object.</summary>
    public required object Geometry { get; set; }

    /// <summary>Additional properties from source data.</summary>
    public Dictionary<string, object>? Properties { get; set; }

    /// <summary>Source dataset identifier.</summary>
    public string? SourceDataset { get; set; }

    /// <summary>Timestamp when the asset was created.</summary>
    public DateTime CreatedAt { get; set; }
}

/// <summary>
/// Summary DTO for listing assets (lighter weight, no geometry).
/// </summary>
public class AssetSummaryDto
{
    /// <summary>Unique identifier for the asset.</summary>
    public required string AssetId { get; set; }

    /// <summary>Display name for the asset.</summary>
    public required string Name { get; set; }

    /// <summary>Type of asset (display name).</summary>
    public required string AssetTypeName { get; set; }

    /// <summary>Criticality level (display name).</summary>
    public required string CriticalityName { get; set; }

    /// <summary>Geometry type (Point, LineString, Polygon).</summary>
    public required string GeometryType { get; set; }
}

/// <summary>
/// Request DTO for creating an asset.
/// </summary>
public class CreateAssetRequest
{
    /// <summary>Unique identifier for the asset. Auto-generated if not provided.</summary>
    public string? AssetId { get; set; }

    /// <summary>AOI to add this asset to.</summary>
    public required string AoiId { get; set; }

    /// <summary>Display name for the asset.</summary>
    public required string Name { get; set; }

    /// <summary>Type of asset.</summary>
    public int AssetType { get; set; }

    /// <summary>Criticality level.</summary>
    public int Criticality { get; set; } = 1; // Default to Medium

    /// <summary>GeoJSON geometry object.</summary>
    public required object Geometry { get; set; }

    /// <summary>Additional properties.</summary>
    public Dictionary<string, object>? Properties { get; set; }

    /// <summary>Source dataset identifier for provenance.</summary>
    public string? SourceDataset { get; set; }

    /// <summary>Original feature ID from source dataset.</summary>
    public string? SourceFeatureId { get; set; }
}

/// <summary>
/// Request DTO for bulk creating assets.
/// </summary>
public class BulkCreateAssetsRequest
{
    /// <summary>AOI to add assets to.</summary>
    public required string AoiId { get; set; }

    /// <summary>Source dataset identifier for all assets in this batch.</summary>
    public string? SourceDataset { get; set; }

    /// <summary>List of assets to create.</summary>
    public required List<CreateAssetRequest> Assets { get; set; }
}

/// <summary>
/// Response DTO for bulk operations.
/// </summary>
public class BulkOperationResult
{
    /// <summary>Number of items successfully processed.</summary>
    public int SuccessCount { get; set; }

    /// <summary>Number of items that failed.</summary>
    public int FailureCount { get; set; }

    /// <summary>Error messages for failed items.</summary>
    public List<string>? Errors { get; set; }

    /// <summary>IDs of successfully created items.</summary>
    public List<Guid>? CreatedIds { get; set; }
}
