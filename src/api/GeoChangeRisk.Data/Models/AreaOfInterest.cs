using NetTopologySuite.Geometries;

namespace GeoChangeRisk.Data.Models;

/// <summary>
/// Represents a geographic area of interest for monitoring.
/// An AOI defines the spatial extent for asset monitoring and change detection.
/// </summary>
public class AreaOfInterest
{
    /// <summary>
    /// Unique identifier for the AOI (e.g., "paradise-ca").
    /// </summary>
    public required string AoiId { get; set; }

    /// <summary>
    /// Display name for the AOI.
    /// </summary>
    public required string Name { get; set; }

    /// <summary>
    /// Description of the AOI and its significance.
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Bounding box polygon defining the geographic extent.
    /// Stored as a PostGIS geometry (SRID 4326 - WGS84).
    /// </summary>
    public required Polygon BoundingBox { get; set; }

    /// <summary>
    /// Center point of the AOI for map navigation.
    /// </summary>
    public required Point CenterPoint { get; set; }

    /// <summary>
    /// Timestamp when the AOI was created.
    /// </summary>
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    /// <summary>
    /// Timestamp when the AOI was last updated.
    /// </summary>
    public DateTime? UpdatedAt { get; set; }

    /// <summary>
    /// Navigation property for assets within this AOI.
    /// </summary>
    public ICollection<Asset> Assets { get; set; } = new List<Asset>();

    /// <summary>
    /// Navigation property for processing runs on this AOI.
    /// </summary>
    public ICollection<ProcessingRun> ProcessingRuns { get; set; } = new List<ProcessingRun>();

    // Scheduling fields for automated processing

    /// <summary>
    /// Cron expression for automated processing schedule (e.g., "0 6 * * 1" = 6am Mondays).
    /// Null means no automatic scheduling.
    /// </summary>
    public string? ProcessingSchedule { get; set; }

    /// <summary>
    /// Whether automated processing is enabled for this AOI.
    /// </summary>
    public bool ProcessingEnabled { get; set; } = true;

    /// <summary>
    /// Timestamp of the last completed processing run.
    /// </summary>
    public DateTime? LastProcessedAt { get; set; }

    /// <summary>
    /// Default number of days to look back for "before" imagery.
    /// </summary>
    public int DefaultLookbackDays { get; set; } = 90;
}
