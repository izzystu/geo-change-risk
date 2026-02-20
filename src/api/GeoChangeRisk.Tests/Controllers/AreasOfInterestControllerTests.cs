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

public class AreasOfInterestControllerTests : IDisposable
{
    private readonly GeoChangeDbContext _context;
    private readonly AreasOfInterestController _controller;
    private readonly Mock<IGeometryParsingService> _geometryServiceMock;

    public AreasOfInterestControllerTests()
    {
        var options = new DbContextOptionsBuilder<GeoChangeDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        _context = new TestDbContext(options);
        _geometryServiceMock = new Mock<IGeometryParsingService>();

        _controller = new AreasOfInterestController(
            _context,
            Mock.Of<ILogger<AreasOfInterestController>>(),
            _geometryServiceMock.Object,
            Mock.Of<ISchedulerService>());
    }

    [Fact]
    public async Task GetAll_WhenEmpty_ReturnsEmptyList()
    {
        var result = await _controller.GetAll();

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var items = Assert.IsAssignableFrom<IEnumerable<AreaOfInterestSummaryDto>>(okResult.Value);
        Assert.Empty(items);
    }

    [Fact]
    public async Task GetAll_WithData_ReturnsSummaries()
    {
        var factory = new GeometryFactory(new PrecisionModel(), 4326);
        _context.AreasOfInterest.Add(new AreaOfInterest
        {
            AoiId = "test-aoi",
            Name = "Test AOI",
            BoundingBox = factory.CreatePolygon(new Coordinate[]
            {
                new(0, 0), new(1, 0), new(1, 1), new(0, 1), new(0, 0)
            }),
            CenterPoint = factory.CreatePoint(new Coordinate(0.5, 0.5))
        });
        await _context.SaveChangesAsync();

        var result = await _controller.GetAll();

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var items = Assert.IsAssignableFrom<IEnumerable<AreaOfInterestSummaryDto>>(okResult.Value);
        var list = items.ToList();
        Assert.Single(list);
        Assert.Equal("test-aoi", list[0].AoiId);
        Assert.Equal("Test AOI", list[0].Name);
    }

    [Fact]
    public async Task GetById_WhenNotFound_ReturnsNotFound()
    {
        var result = await _controller.GetById("nonexistent");

        Assert.IsType<NotFoundObjectResult>(result.Result);
    }

    [Fact]
    public async Task GetById_WhenFound_ReturnsDto()
    {
        var factory = new GeometryFactory(new PrecisionModel(), 4326);
        _context.AreasOfInterest.Add(new AreaOfInterest
        {
            AoiId = "test-aoi",
            Name = "Test AOI",
            Description = "A test area",
            BoundingBox = factory.CreatePolygon(new Coordinate[]
            {
                new(-121.7, 39.7), new(-121.5, 39.7), new(-121.5, 39.9),
                new(-121.7, 39.9), new(-121.7, 39.7)
            }),
            CenterPoint = factory.CreatePoint(new Coordinate(-121.6, 39.8))
        });
        await _context.SaveChangesAsync();

        var result = await _controller.GetById("test-aoi");

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var dto = Assert.IsType<AreaOfInterestDto>(okResult.Value);
        Assert.Equal("test-aoi", dto.AoiId);
        Assert.Equal("Test AOI", dto.Name);
        Assert.Equal("A test area", dto.Description);
    }

    [Fact]
    public async Task Create_WithValidRequest_ReturnsCreatedAtAction()
    {
        var bbox = new Polygon(
            new LinearRing(new Coordinate[]
            {
                new(-121.7, 39.7), new(-121.5, 39.7), new(-121.5, 39.9),
                new(-121.7, 39.9), new(-121.7, 39.7)
            }));
        bbox.SRID = 4326;

        var center = new Point(-121.6, 39.8) { SRID = 4326 };

        _geometryServiceMock
            .Setup(s => s.CreateBoundingBox(-121.7, 39.7, -121.5, 39.9))
            .Returns(bbox);
        _geometryServiceMock
            .Setup(s => s.CreatePoint(-121.6, 39.8))
            .Returns(center);

        var request = new CreateAreaOfInterestRequest
        {
            AoiId = "new-aoi",
            Name = "New AOI",
            BoundingBox = [-121.7, 39.7, -121.5, 39.9]
        };

        var result = await _controller.Create(request);

        var createdResult = Assert.IsType<CreatedAtActionResult>(result.Result);
        var dto = Assert.IsType<AreaOfInterestDto>(createdResult.Value);
        Assert.Equal("new-aoi", dto.AoiId);
        Assert.Equal("New AOI", dto.Name);

        // Verify it was saved
        Assert.True(await _context.AreasOfInterest.AnyAsync(a => a.AoiId == "new-aoi"));
    }

    [Fact]
    public async Task Create_WithInvalidBbox_ReturnsBadRequest()
    {
        var request = new CreateAreaOfInterestRequest
        {
            AoiId = "bad-aoi",
            Name = "Bad AOI",
            BoundingBox = [1.0, 2.0] // Only 2 elements, need 4
        };

        var result = await _controller.Create(request);

        Assert.IsType<BadRequestObjectResult>(result.Result);
    }

    [Fact]
    public async Task Create_WhenDuplicate_ReturnsConflict()
    {
        var factory = new GeometryFactory(new PrecisionModel(), 4326);
        _context.AreasOfInterest.Add(new AreaOfInterest
        {
            AoiId = "existing-aoi",
            Name = "Existing AOI",
            BoundingBox = factory.CreatePolygon(new Coordinate[]
            {
                new(0, 0), new(1, 0), new(1, 1), new(0, 1), new(0, 0)
            }),
            CenterPoint = factory.CreatePoint(new Coordinate(0.5, 0.5))
        });
        await _context.SaveChangesAsync();

        var request = new CreateAreaOfInterestRequest
        {
            AoiId = "existing-aoi",
            Name = "Duplicate",
            BoundingBox = [0, 0, 1, 1]
        };

        var result = await _controller.Create(request);

        Assert.IsType<ConflictObjectResult>(result.Result);
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
        var factory = new GeometryFactory(new PrecisionModel(), 4326);
        _context.AreasOfInterest.Add(new AreaOfInterest
        {
            AoiId = "to-delete",
            Name = "Delete Me",
            BoundingBox = factory.CreatePolygon(new Coordinate[]
            {
                new(0, 0), new(1, 0), new(1, 1), new(0, 1), new(0, 0)
            }),
            CenterPoint = factory.CreatePoint(new Coordinate(0.5, 0.5))
        });
        await _context.SaveChangesAsync();

        var result = await _controller.Delete("to-delete");

        Assert.IsType<NoContentResult>(result);
        Assert.False(await _context.AreasOfInterest.AnyAsync(a => a.AoiId == "to-delete"));
    }

    public void Dispose()
    {
        _context.Dispose();
    }
}
