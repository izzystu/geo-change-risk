namespace GeoChangeRisk.Contracts;

/// <summary>
/// Data transfer object for Area of Interest.
/// </summary>
public class AreaOfInterestDto
{
    /// <summary>Unique identifier for the AOI.</summary>
    public required string AoiId { get; set; }

    /// <summary>Display name for the AOI.</summary>
    public required string Name { get; set; }

    /// <summary>Description of the AOI.</summary>
    public string? Description { get; set; }

    /// <summary>Bounding box as [minLon, minLat, maxLon, maxLat].</summary>
    public required double[] BoundingBox { get; set; }

    /// <summary>Center point as [lon, lat].</summary>
    public required double[] Center { get; set; }

    /// <summary>Number of assets in this AOI.</summary>
    public int AssetCount { get; set; }

    /// <summary>Timestamp when the AOI was created.</summary>
    public DateTime CreatedAt { get; set; }

    // Scheduling fields
    /// <summary>Cron expression for automated processing schedule.</summary>
    public string? ProcessingSchedule { get; set; }

    /// <summary>Whether automated processing is enabled.</summary>
    public bool ProcessingEnabled { get; set; }

    /// <summary>Timestamp of last completed processing run.</summary>
    public DateTime? LastProcessedAt { get; set; }

    /// <summary>Default lookback days for before imagery.</summary>
    public int DefaultLookbackDays { get; set; }

    /// <summary>Maximum cloud cover percentage for imagery search (0-100).</summary>
    public double MaxCloudCover { get; set; }

    /// <summary>Timestamp of last scheduled check for new imagery.</summary>
    public DateTime? LastCheckedAt { get; set; }
}

/// <summary>
/// Summary DTO for listing AOIs (lighter weight).
/// </summary>
public class AreaOfInterestSummaryDto
{
    /// <summary>Unique identifier for the AOI.</summary>
    public required string AoiId { get; set; }

    /// <summary>Display name for the AOI.</summary>
    public required string Name { get; set; }

    /// <summary>Number of assets in this AOI.</summary>
    public int AssetCount { get; set; }
}

/// <summary>
/// Request DTO for creating/updating an AOI.
/// </summary>
public class CreateAreaOfInterestRequest
{
    /// <summary>Unique identifier for the AOI.</summary>
    public required string AoiId { get; set; }

    /// <summary>Display name for the AOI.</summary>
    public required string Name { get; set; }

    /// <summary>Description of the AOI.</summary>
    public string? Description { get; set; }

    /// <summary>Bounding box as [minLon, minLat, maxLon, maxLat].</summary>
    public required double[] BoundingBox { get; set; }

    /// <summary>Center point as [lon, lat]. If not provided, calculated from bounding box.</summary>
    public double[]? Center { get; set; }
}

/// <summary>
/// Request DTO for updating AOI scheduling configuration.
/// </summary>
public class UpdateAoiScheduleRequest
{
    /// <summary>Cron expression for automated processing schedule (null to disable).</summary>
    public string? ProcessingSchedule { get; set; }

    /// <summary>Whether automated processing is enabled.</summary>
    public bool? ProcessingEnabled { get; set; }

    /// <summary>Default lookback days for before imagery.</summary>
    public int? DefaultLookbackDays { get; set; }

    /// <summary>Maximum cloud cover percentage for imagery search (0-100).</summary>
    public double? MaxCloudCover { get; set; }
}
