using System.Text.Json;
using GeoChangeRisk.Api.Controllers;
using GeoChangeRisk.Api.Services;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Moq;
using NetTopologySuite.Geometries;
using Xunit;

namespace GeoChangeRisk.Tests.Controllers;

public class AssetsControllerTests : IDisposable
{
    private readonly GeoChangeDbContext _context;
    private readonly AssetsController _controller;
    private readonly Mock<IGeometryParsingService> _geometryServiceMock;
    private readonly GeometryFactory _factory;

    public AssetsControllerTests()
    {
        var options = new DbContextOptionsBuilder<GeoChangeDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        _context = new TestDbContext(options);
        _geometryServiceMock = new Mock<IGeometryParsingService>();
        _factory = new GeometryFactory(new PrecisionModel(), 4326);

        _controller = new AssetsController(
            _context,
            Mock.Of<ILogger<AssetsController>>(),
            _geometryServiceMock.Object);

        SeedAoi();
    }

    private void SeedAoi()
    {
        _context.AreasOfInterest.Add(new AreaOfInterest
        {
            AoiId = "test-aoi",
            Name = "Test AOI",
            BoundingBox = _factory.CreatePolygon(new Coordinate[]
            {
                new(0, 0), new(1, 0), new(1, 1), new(0, 1), new(0, 0)
            }),
            CenterPoint = _factory.CreatePoint(new Coordinate(0.5, 0.5))
        });
        _context.SaveChanges();
    }

    [Fact]
    public async Task GetAll_WhenEmpty_ReturnsEmptyList()
    {
        var result = await _controller.GetAll();

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var items = Assert.IsAssignableFrom<IEnumerable<AssetSummaryDto>>(okResult.Value);
        Assert.Empty(items);
    }

    [Fact]
    public async Task GetAll_WithAoiFilter_ReturnsFilteredAssets()
    {
        var point = _factory.CreatePoint(new Coordinate(0.5, 0.5));
        point.SRID = 4326;

        _context.Assets.AddRange(
            new Asset
            {
                AssetId = "asset-1",
                AoiId = "test-aoi",
                Name = "Asset 1",
                AssetType = AssetType.Building,
                Geometry = point
            },
            new Asset
            {
                AssetId = "asset-2",
                AoiId = "other-aoi",
                Name = "Asset 2",
                AssetType = AssetType.Building,
                Geometry = point
            });
        await _context.SaveChangesAsync();

        var result = await _controller.GetAll(aoiId: "test-aoi");

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var items = Assert.IsAssignableFrom<IEnumerable<AssetSummaryDto>>(okResult.Value);
        Assert.Single(items);
    }

    [Fact]
    public async Task GetById_WhenNotFound_ReturnsNotFound()
    {
        var result = await _controller.GetById("nonexistent");

        Assert.IsType<NotFoundObjectResult>(result.Result);
    }

    [Fact]
    public async Task GetById_WhenFound_ReturnsAssetDto()
    {
        var point = _factory.CreatePoint(new Coordinate(0.5, 0.5));
        point.SRID = 4326;

        _context.Assets.Add(new Asset
        {
            AssetId = "asset-1",
            AoiId = "test-aoi",
            Name = "Test Asset",
            AssetType = AssetType.Substation,
            Criticality = Criticality.High,
            Geometry = point
        });
        await _context.SaveChangesAsync();

        var result = await _controller.GetById("asset-1");

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var dto = Assert.IsType<AssetDto>(okResult.Value);
        Assert.Equal("asset-1", dto.AssetId);
        Assert.Equal("test-aoi", dto.AoiId);
        Assert.Equal("Test Asset", dto.Name);
    }

    [Fact]
    public async Task Create_WithValidRequest_ReturnsCreatedAtAction()
    {
        var point = _factory.CreatePoint(new Coordinate(0.5, 0.5));
        point.SRID = 4326;

        var geoJsonObj = JsonSerializer.Deserialize<JsonElement>(
            """{"type":"Point","coordinates":[0.5,0.5]}""");

        _geometryServiceMock
            .Setup(s => s.ParseGeoJson(It.IsAny<object>()))
            .Returns(point);

        var request = new CreateAssetRequest
        {
            AoiId = "test-aoi",
            Name = "New Asset",
            AssetType = (int)AssetType.Building,
            Criticality = (int)Criticality.Medium,
            Geometry = geoJsonObj
        };

        var result = await _controller.Create(request);

        var createdResult = Assert.IsType<CreatedAtActionResult>(result.Result);
        var dto = Assert.IsType<AssetDto>(createdResult.Value);
        Assert.Equal("test-aoi", dto.AoiId);
        Assert.Equal("New Asset", dto.Name);
    }

    [Fact]
    public async Task Create_WithInvalidAoi_ReturnsBadRequest()
    {
        var geoJsonObj = JsonSerializer.Deserialize<JsonElement>(
            """{"type":"Point","coordinates":[0.5,0.5]}""");

        var request = new CreateAssetRequest
        {
            AoiId = "nonexistent-aoi",
            Name = "Bad Asset",
            Geometry = geoJsonObj
        };

        var result = await _controller.Create(request);

        Assert.IsType<BadRequestObjectResult>(result.Result);
    }

    [Fact]
    public async Task Create_WithInvalidGeometry_ReturnsBadRequest()
    {
        _geometryServiceMock
            .Setup(s => s.ParseGeoJson(It.IsAny<object>()))
            .Throws(new ArgumentException("Invalid GeoJSON"));

        var geoJsonObj = JsonSerializer.Deserialize<JsonElement>("""{"type":"Invalid"}""");

        var request = new CreateAssetRequest
        {
            AoiId = "test-aoi",
            Name = "Bad Geometry Asset",
            Geometry = geoJsonObj
        };

        var result = await _controller.Create(request);

        Assert.IsType<BadRequestObjectResult>(result.Result);
    }

    [Fact]
    public async Task BulkCreate_WithValidAssets_ReturnsSuccessResult()
    {
        var point = _factory.CreatePoint(new Coordinate(0.5, 0.5));
        point.SRID = 4326;

        _geometryServiceMock
            .Setup(s => s.ParseGeoJson(It.IsAny<object>()))
            .Returns(point);

        var geoJsonObj = JsonSerializer.Deserialize<JsonElement>(
            """{"type":"Point","coordinates":[0.5,0.5]}""");

        var request = new BulkCreateAssetsRequest
        {
            AoiId = "test-aoi",
            Assets =
            [
                new CreateAssetRequest
                {
                    AssetId = "bulk-1",
                    AoiId = "test-aoi",
                    Name = "Bulk Asset 1",
                    Geometry = geoJsonObj
                },
                new CreateAssetRequest
                {
                    AssetId = "bulk-2",
                    AoiId = "test-aoi",
                    Name = "Bulk Asset 2",
                    Geometry = geoJsonObj
                }
            ]
        };

        var result = await _controller.BulkCreate(request);

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var bulkResult = Assert.IsType<BulkOperationResult>(okResult.Value);
        Assert.Equal(2, bulkResult.SuccessCount);
        Assert.Equal(0, bulkResult.FailureCount);
    }

    [Fact]
    public async Task Delete_WhenNotFound_ReturnsNotFound()
    {
        var result = await _controller.Delete("nonexistent");

        Assert.IsType<NotFoundObjectResult>(result);
    }

    [Fact]
    public async Task Delete_WhenFound_ReturnsNoContent()
    {
        var point = _factory.CreatePoint(new Coordinate(0.5, 0.5));
        point.SRID = 4326;

        _context.Assets.Add(new Asset
        {
            AssetId = "to-delete",
            AoiId = "test-aoi",
            Name = "Delete Me",
            Geometry = point
        });
        await _context.SaveChangesAsync();

        var result = await _controller.Delete("to-delete");

        Assert.IsType<NoContentResult>(result);
        Assert.False(await _context.Assets.AnyAsync(a => a.AssetId == "to-delete"));
    }

    public void Dispose()
    {
        _context.Dispose();
    }
}
