using NetTopologySuite.Geometries;

namespace GeoChangeRisk.Data.Models;

/// <summary>
/// Represents an infrastructure asset that can be monitored for risk.
/// Assets can be points (substations), lines (pipelines), or polygons (buildings).
/// </summary>
public class Asset
{
    /// <summary>
    /// Unique identifier for the asset.
    /// </summary>
    public required string AssetId { get; set; }

    /// <summary>
    /// Foreign key to the Area of Interest containing this asset.
    /// </summary>
    public required string AoiId { get; set; }

    /// <summary>
    /// Display name for the asset.
    /// </summary>
    public required string Name { get; set; }

    /// <summary>
    /// Type of infrastructure asset.
    /// </summary>
    public AssetType AssetType { get; set; }

    /// <summary>
    /// Spatial geometry of the asset (Point, LineString, or Polygon).
    /// Stored as a PostGIS geometry (SRID 4326 - WGS84).
    /// </summary>
    public required Geometry Geometry { get; set; }

    /// <summary>
    /// Criticality level for risk prioritization.
    /// </summary>
    public Criticality Criticality { get; set; } = Criticality.Medium;

    /// <summary>
    /// Flexible JSON properties for additional asset attributes.
    /// Stored as JSONB in PostgreSQL.
    /// </summary>
    public Dictionary<string, object>? Properties { get; set; }

    /// <summary>
    /// Source dataset identifier for provenance tracking.
    /// Examples: "osm-buildings", "cec-transmission", "hifld-fire-stations"
    /// </summary>
    public string? SourceDataset { get; set; }

    /// <summary>
    /// Original feature ID from the source dataset.
    /// </summary>
    public string? SourceFeatureId { get; set; }

    /// <summary>
    /// Timestamp when the asset was created.
    /// </summary>
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    /// <summary>
    /// Timestamp when the asset was last updated.
    /// </summary>
    public DateTime? UpdatedAt { get; set; }

    /// <summary>
    /// Navigation property to the parent Area of Interest.
    /// </summary>
    public AreaOfInterest? AreaOfInterest { get; set; }

    /// <summary>
    /// Navigation property for risk events affecting this asset.
    /// </summary>
    public ICollection<RiskEvent> RiskEvents { get; set; } = new List<RiskEvent>();
}
