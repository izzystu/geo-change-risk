namespace GeoChangeRisk.Contracts;

/// <summary>
/// Data transfer object for ProcessingRun.
/// </summary>
public class ProcessingRunDto
{
    /// <summary>Unique identifier for the processing run.</summary>
    public Guid RunId { get; set; }

    /// <summary>AOI being processed.</summary>
    public required string AoiId { get; set; }

    /// <summary>Current status (numeric value).</summary>
    public int Status { get; set; }

    /// <summary>Current status (display name).</summary>
    public required string StatusName { get; set; }

    /// <summary>Date of "before" imagery.</summary>
    public DateTime BeforeDate { get; set; }

    /// <summary>Date of "after" imagery.</summary>
    public DateTime AfterDate { get; set; }

    /// <summary>Scene ID for "before" imagery.</summary>
    public string? BeforeSceneId { get; set; }

    /// <summary>Scene ID for "after" imagery.</summary>
    public string? AfterSceneId { get; set; }

    /// <summary>When processing started.</summary>
    public DateTime? StartedAt { get; set; }

    /// <summary>When processing completed.</summary>
    public DateTime? CompletedAt { get; set; }

    /// <summary>Error message if failed.</summary>
    public string? ErrorMessage { get; set; }

    /// <summary>Processing metadata and statistics.</summary>
    public Dictionary<string, object>? Metadata { get; set; }

    /// <summary>When the run was created.</summary>
    public DateTime CreatedAt { get; set; }

    /// <summary>Number of change polygons detected.</summary>
    public int ChangePolygonCount { get; set; }

    /// <summary>Number of risk events generated.</summary>
    public int RiskEventCount { get; set; }
}

/// <summary>
/// Summary DTO for listing processing runs (lighter weight).
/// </summary>
public class ProcessingRunSummaryDto
{
    /// <summary>Unique identifier for the processing run.</summary>
    public Guid RunId { get; set; }

    /// <summary>AOI being processed.</summary>
    public required string AoiId { get; set; }

    /// <summary>Current status (display name).</summary>
    public required string StatusName { get; set; }

    /// <summary>Date of "before" imagery.</summary>
    public DateTime BeforeDate { get; set; }

    /// <summary>Date of "after" imagery.</summary>
    public DateTime AfterDate { get; set; }

    /// <summary>Scene ID for "after" imagery.</summary>
    public string? AfterSceneId { get; set; }

    /// <summary>When the run was created.</summary>
    public DateTime CreatedAt { get; set; }

    /// <summary>Number of change polygons detected.</summary>
    public int ChangePolygonCount { get; set; }

    /// <summary>Number of risk events generated.</summary>
    public int RiskEventCount { get; set; }
}

/// <summary>
/// Request DTO for creating a processing run.
/// </summary>
public class CreateProcessingRunRequest
{
    /// <summary>AOI to process.</summary>
    public required string AoiId { get; set; }

    /// <summary>Date for "before" imagery.</summary>
    public DateTime BeforeDate { get; set; }

    /// <summary>Date for "after" imagery.</summary>
    public DateTime AfterDate { get; set; }

    /// <summary>Optional processing parameters.</summary>
    public Dictionary<string, object>? Parameters { get; set; }
}

/// <summary>
/// Request DTO for updating processing run status.
/// </summary>
public class UpdateProcessingRunStatusRequest
{
    /// <summary>New status value.</summary>
    public int Status { get; set; }

    /// <summary>Scene ID for "before" imagery (optional).</summary>
    public string? BeforeSceneId { get; set; }

    /// <summary>Scene ID for "after" imagery (optional).</summary>
    public string? AfterSceneId { get; set; }

    /// <summary>Error message if status is Failed (optional).</summary>
    public string? ErrorMessage { get; set; }

    /// <summary>Additional metadata to merge (optional).</summary>
    public Dictionary<string, object>? Metadata { get; set; }
}
