namespace GeoChangeRisk.Data.Models;

/// <summary>
/// Represents a single processing run of the raster pipeline for an AOI.
/// Tracks imagery comparison between two dates and resulting change detection.
/// </summary>
public class ProcessingRun
{
    /// <summary>
    /// Unique identifier for the processing run.
    /// </summary>
    public Guid RunId { get; set; }

    /// <summary>
    /// Foreign key to the Area of Interest being processed.
    /// </summary>
    public required string AoiId { get; set; }

    /// <summary>
    /// Current status of the processing run.
    /// </summary>
    public ProcessingStatus Status { get; set; } = ProcessingStatus.Pending;

    /// <summary>
    /// Date of the "before" imagery for change comparison.
    /// </summary>
    public DateTime BeforeDate { get; set; }

    /// <summary>
    /// Date of the "after" imagery for change comparison.
    /// </summary>
    public DateTime AfterDate { get; set; }

    /// <summary>
    /// Scene identifier for the "before" imagery (e.g., Sentinel-2 product ID).
    /// </summary>
    public string? BeforeSceneId { get; set; }

    /// <summary>
    /// Scene identifier for the "after" imagery.
    /// </summary>
    public string? AfterSceneId { get; set; }

    /// <summary>
    /// Timestamp when processing started.
    /// </summary>
    public DateTime? StartedAt { get; set; }

    /// <summary>
    /// Timestamp when processing completed (success or failure).
    /// </summary>
    public DateTime? CompletedAt { get; set; }

    /// <summary>
    /// Error message if processing failed.
    /// </summary>
    public string? ErrorMessage { get; set; }

    /// <summary>
    /// Flexible JSON metadata for processing parameters and statistics.
    /// </summary>
    public Dictionary<string, object>? Metadata { get; set; }

    /// <summary>
    /// Timestamp when the run record was created.
    /// </summary>
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    /// <summary>
    /// Navigation property to the parent Area of Interest.
    /// </summary>
    public AreaOfInterest? AreaOfInterest { get; set; }

    /// <summary>
    /// Navigation property for change polygons detected in this run.
    /// </summary>
    public ICollection<ChangePolygon> ChangePolygons { get; set; } = new List<ChangePolygon>();
}
