using System.Text.Json;
using GeoChangeRisk.Api.Services;
using NetTopologySuite.Geometries;
using Xunit;

namespace GeoChangeRisk.Tests.Services;

public class GeometryParsingServiceTests
{
    private readonly GeometryParsingService _service = new();

    [Fact]
    public void CreateBoundingBox_ReturnsPolygonWithCorrectCoordinates()
    {
        var polygon = _service.CreateBoundingBox(-121.7, 39.7, -121.5, 39.9);

        Assert.NotNull(polygon);
        Assert.Equal("Polygon", polygon.GeometryType);
        Assert.Equal(4326, polygon.SRID);

        var envelope = polygon.EnvelopeInternal;
        Assert.Equal(-121.7, envelope.MinX, 6);
        Assert.Equal(39.7, envelope.MinY, 6);
        Assert.Equal(-121.5, envelope.MaxX, 6);
        Assert.Equal(39.9, envelope.MaxY, 6);
    }

    [Fact]
    public void CreateBoundingBox_ReturnsClosedRing()
    {
        var polygon = _service.CreateBoundingBox(0, 0, 1, 1);

        // A valid polygon ring must be closed (first == last coordinate)
        var ring = polygon.ExteriorRing.Coordinates;
        Assert.Equal(ring[0], ring[^1]);
        Assert.Equal(5, ring.Length); // 4 corners + closing point
    }

    [Fact]
    public void CreatePoint_ReturnsPointWithCorrectCoordinates()
    {
        var point = _service.CreatePoint(-121.6, 39.8);

        Assert.NotNull(point);
        Assert.Equal("Point", point.GeometryType);
        Assert.Equal(4326, point.SRID);
        Assert.Equal(-121.6, point.X, 6);
        Assert.Equal(39.8, point.Y, 6);
    }

    [Fact]
    public void ParseGeoJson_WithJsonElement_ReturnsGeometry()
    {
        var geoJson = """{"type":"Point","coordinates":[-121.6,39.8]}""";
        var element = JsonSerializer.Deserialize<JsonElement>(geoJson);

        var geometry = _service.ParseGeoJson(element);

        Assert.NotNull(geometry);
        Assert.Equal("Point", geometry.GeometryType);
        Assert.Equal(4326, geometry.SRID);
        Assert.Equal(-121.6, geometry.Coordinate.X, 6);
        Assert.Equal(39.8, geometry.Coordinate.Y, 6);
    }

    [Fact]
    public void ParseGeoJson_WithPolygonElement_ReturnsPolygon()
    {
        var geoJson = """
        {
            "type": "Polygon",
            "coordinates": [
                [[-121.7, 39.7], [-121.5, 39.7], [-121.5, 39.9], [-121.7, 39.9], [-121.7, 39.7]]
            ]
        }
        """;
        var element = JsonSerializer.Deserialize<JsonElement>(geoJson);

        var geometry = _service.ParseGeoJson(element);

        Assert.NotNull(geometry);
        Assert.IsType<Polygon>(geometry);
        Assert.Equal(4326, geometry.SRID);
    }

    [Fact]
    public void ParseGeoJson_WithInvalidJson_ThrowsException()
    {
        var geoJson = """{"type":"Invalid","coordinates":"bad"}""";
        var element = JsonSerializer.Deserialize<JsonElement>(geoJson);

        Assert.ThrowsAny<Exception>(() => _service.ParseGeoJson(element));
    }
}
