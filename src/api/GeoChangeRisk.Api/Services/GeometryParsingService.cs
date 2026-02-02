using System.Text.Json;
using NetTopologySuite.Geometries;
using NetTopologySuite.IO;
using Newtonsoft.Json;

namespace GeoChangeRisk.Api.Services;

/// <summary>
/// Service for parsing and creating NTS geometries.
/// Uses SRID 4326 (WGS84) for all geometries.
/// </summary>
public class GeometryParsingService : IGeometryParsingService
{
    private readonly GeometryFactory _geometryFactory;
    private readonly GeoJsonReader _geoJsonReader;

    public GeometryParsingService()
    {
        _geometryFactory = new GeometryFactory(new PrecisionModel(), 4326);
        _geoJsonReader = new GeoJsonReader(_geometryFactory, new JsonSerializerSettings());
    }

    public Polygon CreateBoundingBox(double minLon, double minLat, double maxLon, double maxLat)
    {
        var coordinates = new Coordinate[]
        {
            new(minLon, minLat),
            new(maxLon, minLat),
            new(maxLon, maxLat),
            new(minLon, maxLat),
            new(minLon, minLat)
        };
        return _geometryFactory.CreatePolygon(coordinates);
    }

    public Point CreatePoint(double lon, double lat)
    {
        return _geometryFactory.CreatePoint(new Coordinate(lon, lat));
    }

    public Geometry ParseGeoJson(object geoJsonObject)
    {
        string json;
        if (geoJsonObject is JsonElement jsonElement)
        {
            json = jsonElement.GetRawText();
        }
        else
        {
            json = JsonConvert.SerializeObject(geoJsonObject);
        }

        var geometry = _geoJsonReader.Read<Geometry>(json);

        // Validate coordinates are in valid WGS84 range
        var envelope = geometry.EnvelopeInternal;
        if (envelope.MinX < -180 || envelope.MaxX > 180 ||
            envelope.MinY < -90 || envelope.MaxY > 90)
        {
            throw new ArgumentException(
                $"Geometry coordinates outside valid WGS84 range. " +
                $"Bounds: [{envelope.MinX:F4}, {envelope.MinY:F4}, {envelope.MaxX:F4}, {envelope.MaxY:F4}]. " +
                $"Data may be in a projected CRS (e.g., Web Mercator EPSG:3857).");
        }

        geometry.SRID = 4326;
        return geometry;
    }
}
