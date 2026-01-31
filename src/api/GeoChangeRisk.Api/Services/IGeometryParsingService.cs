using NetTopologySuite.Geometries;

namespace GeoChangeRisk.Api.Services;

/// <summary>
/// Interface for parsing and creating NTS geometries from various inputs.
/// </summary>
public interface IGeometryParsingService
{
    /// <summary>
    /// Creates a bounding box polygon from min/max coordinates.
    /// </summary>
    Polygon CreateBoundingBox(double minLon, double minLat, double maxLon, double maxLat);

    /// <summary>
    /// Creates a point geometry.
    /// </summary>
    Point CreatePoint(double lon, double lat);

    /// <summary>
    /// Parses a GeoJSON geometry object into an NTS Geometry.
    /// Handles both System.Text.Json.JsonElement and raw objects.
    /// </summary>
    Geometry ParseGeoJson(object geoJsonObject);
}
