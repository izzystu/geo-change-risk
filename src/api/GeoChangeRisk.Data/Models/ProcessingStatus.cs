namespace GeoChangeRisk.Data.Models;

/// <summary>
/// Status of a processing run through the raster pipeline.
/// </summary>
public enum ProcessingStatus
{
    /// <summary>Run is queued but not yet started</summary>
    Pending = 0,

    /// <summary>Fetching satellite imagery from STAC catalog</summary>
    FetchingImagery = 1,

    /// <summary>Calculating NDVI from imagery bands</summary>
    CalculatingNdvi = 2,

    /// <summary>Detecting changes between before/after imagery</summary>
    DetectingChanges = 3,

    /// <summary>Scoring risk for detected changes</summary>
    ScoringRisk = 4,

    /// <summary>Processing completed successfully</summary>
    Completed = 5,

    /// <summary>Processing failed with error</summary>
    Failed = 6
}
