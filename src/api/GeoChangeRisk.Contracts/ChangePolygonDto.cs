namespace GeoChangeRisk.Contracts;

/// <summary>
/// Data transfer object for ChangePolygon.
/// </summary>
public class ChangePolygonDto
{
    /// <summary>Unique identifier for the change polygon.</summary>
    public Guid ChangePolygonId { get; set; }

    /// <summary>Processing run that generated this polygon.</summary>
    public Guid RunId { get; set; }

    /// <summary>GeoJSON geometry object.</summary>
    public required object Geometry { get; set; }

    /// <summary>Area in square meters.</summary>
    public double AreaSqMeters { get; set; }

    /// <summary>Mean NDVI drop (negative = vegetation loss).</summary>
    public double NdviDropMean { get; set; }

    /// <summary>Maximum NDVI drop.</summary>
    public double NdviDropMax { get; set; }

    /// <summary>Change type (numeric value).</summary>
    public int ChangeType { get; set; }

    /// <summary>Change type (display name).</summary>
    public required string ChangeTypeName { get; set; }

    /// <summary>Mean slope in degrees (from DEM).</summary>
    public double? SlopeDegreeMean { get; set; }

    /// <summary>When the change was detected.</summary>
    public DateTime DetectedAt { get; set; }

    /// <summary>ML model confidence (0-1).</summary>
    public double? MlConfidence { get; set; }

    /// <summary>ML model version used.</summary>
    public string? MlModelVersion { get; set; }

    /// <summary>Number of risk events associated.</summary>
    public int RiskEventCount { get; set; }
}

/// <summary>
/// Summary DTO for listing change polygons (no geometry).
/// </summary>
public class ChangePolygonSummaryDto
{
    /// <summary>Unique identifier for the change polygon.</summary>
    public Guid ChangePolygonId { get; set; }

    /// <summary>Area in square meters.</summary>
    public double AreaSqMeters { get; set; }

    /// <summary>Mean NDVI drop.</summary>
    public double NdviDropMean { get; set; }

    /// <summary>Change type (display name).</summary>
    public required string ChangeTypeName { get; set; }

    /// <summary>When the change was detected.</summary>
    public DateTime DetectedAt { get; set; }

    /// <summary>Number of risk events associated.</summary>
    public int RiskEventCount { get; set; }
}

/// <summary>
/// Request DTO for creating a change polygon (from pipeline).
/// </summary>
public class CreateChangePolygonRequest
{
    /// <summary>Processing run ID.</summary>
    public Guid RunId { get; set; }

    /// <summary>GeoJSON geometry object.</summary>
    public required object Geometry { get; set; }

    /// <summary>Area in square meters.</summary>
    public double AreaSqMeters { get; set; }

    /// <summary>Mean NDVI drop.</summary>
    public double NdviDropMean { get; set; }

    /// <summary>Maximum NDVI drop.</summary>
    public double NdviDropMax { get; set; }

    /// <summary>Change type (numeric value).</summary>
    public int ChangeType { get; set; }

    /// <summary>Mean slope in degrees (optional).</summary>
    public double? SlopeDegreeMean { get; set; }

    /// <summary>ML model confidence (optional).</summary>
    public double? MlConfidence { get; set; }

    /// <summary>ML model version (optional).</summary>
    public string? MlModelVersion { get; set; }
}

/// <summary>
/// Request for bulk creating change polygons.
/// </summary>
public class BulkCreateChangePolygonsRequest
{
    /// <summary>Processing run ID.</summary>
    public Guid RunId { get; set; }

    /// <summary>List of change polygons to create.</summary>
    public required List<CreateChangePolygonRequest> Polygons { get; set; }
}
