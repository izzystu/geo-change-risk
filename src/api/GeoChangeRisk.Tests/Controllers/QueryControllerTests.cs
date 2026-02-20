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

public class QueryControllerTests : IDisposable
{
    private readonly GeoChangeDbContext _context;
    private readonly Mock<ILlmService> _llmServiceMock;
    private readonly QueryExecutorService _queryExecutor;
    private readonly QueryController _controller;
    private readonly GeometryFactory _factory;

    public QueryControllerTests()
    {
        var options = new DbContextOptionsBuilder<GeoChangeDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        _context = new TestDbContext(options);
        _factory = new GeometryFactory(new PrecisionModel(), 4326);
        _llmServiceMock = new Mock<ILlmService>();

        _queryExecutor = new QueryExecutorService(
            _context,
            Mock.Of<ILogger<QueryExecutorService>>());

        _controller = new QueryController(
            _llmServiceMock.Object,
            _queryExecutor,
            _context,
            Mock.Of<ILogger<QueryController>>());

        SeedData();
    }

    private void SeedData()
    {
        var point = _factory.CreatePoint(new Coordinate(-121.6, 39.76));
        point.SRID = 4326;
        var polygon = _factory.CreatePolygon(new[]
        {
            new Coordinate(-121.61, 39.75),
            new Coordinate(-121.60, 39.75),
            new Coordinate(-121.60, 39.76),
            new Coordinate(-121.61, 39.76),
            new Coordinate(-121.61, 39.75)
        });
        polygon.SRID = 4326;

        _context.AreasOfInterest.Add(new AreaOfInterest
        {
            AoiId = "test-aoi",
            Name = "Test AOI",
            BoundingBox = polygon,
            CenterPoint = point
        });

        var asset = new Asset
        {
            AssetId = "hospital-1",
            AoiId = "test-aoi",
            Name = "General Hospital",
            AssetType = AssetType.Hospital,
            Criticality = Criticality.Critical,
            Geometry = point
        };
        _context.Assets.Add(asset);

        var run = new ProcessingRun
        {
            RunId = Guid.NewGuid(),
            AoiId = "test-aoi",
            Status = ProcessingStatus.Completed,
            BeforeDate = new DateTime(2024, 1, 1),
            AfterDate = new DateTime(2024, 6, 1)
        };
        _context.ProcessingRuns.Add(run);

        var change = new ChangePolygon
        {
            ChangePolygonId = Guid.NewGuid(),
            RunId = run.RunId,
            Geometry = polygon,
            AreaSqMeters = 5000,
            NdviDropMean = -0.3,
            NdviDropMax = -0.5,
            ChangeType = ChangeType.VegetationLoss
        };
        _context.ChangePolygons.Add(change);

        var riskEvent = new RiskEvent
        {
            RiskEventId = Guid.NewGuid(),
            ChangePolygonId = change.ChangePolygonId,
            AssetId = "hospital-1",
            DistanceMeters = 200,
            RiskScore = 80,
            RiskLevel = RiskLevel.Critical
        };
        _context.RiskEvents.Add(riskEvent);

        _context.SaveChanges();
    }

    [Fact]
    public async Task Query_WithValidRequest_ReturnsSuccessResponse()
    {
        _llmServiceMock
            .Setup(s => s.TranslateQueryAsync(
                It.IsAny<string>(),
                It.IsAny<QueryContext?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new LlmQueryResult
            {
                Success = true,
                Interpretation = "Find all critical risk events",
                Plan = new QueryPlan
                {
                    TargetEntity = TargetEntityType.RiskEvent,
                    Filters = new List<AttributeFilter>
                    {
                        new() { Property = "RiskLevel", Operator = FilterOperator.eq, Value = "Critical" }
                    }
                }
            });

        var request = new NaturalLanguageQueryRequest { Query = "show critical risk events" };

        var result = await _controller.Query(request, CancellationToken.None);

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var response = Assert.IsType<NaturalLanguageQueryResponse>(okResult.Value);
        Assert.True(response.Success);
        Assert.Equal("Find all critical risk events", response.Interpretation);
        Assert.True(response.TotalCount > 0);
    }

    [Fact]
    public async Task Query_WhenLlmFails_ReturnsErrorResponse()
    {
        _llmServiceMock
            .Setup(s => s.TranslateQueryAsync(
                It.IsAny<string>(),
                It.IsAny<QueryContext?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new LlmQueryResult
            {
                Success = false,
                Interpretation = "",
                ErrorMessage = "Failed to parse LLM response"
            });

        var request = new NaturalLanguageQueryRequest { Query = "gibberish query" };

        var result = await _controller.Query(request, CancellationToken.None);

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var response = Assert.IsType<NaturalLanguageQueryResponse>(okResult.Value);
        Assert.False(response.Success);
        Assert.Contains("Failed to parse", response.ErrorMessage);
    }

    [Fact]
    public async Task Health_WhenAvailable_ReturnsTrue()
    {
        _llmServiceMock
            .Setup(s => s.IsAvailableAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(true);

        var result = await _controller.Health(CancellationToken.None);

        var okResult = Assert.IsType<OkObjectResult>(result);
        // The anonymous type has an "available" property
        var json = System.Text.Json.JsonSerializer.Serialize(okResult.Value);
        Assert.Contains("true", json, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Health_WhenUnavailable_ReturnsFalse()
    {
        _llmServiceMock
            .Setup(s => s.IsAvailableAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(false);

        var result = await _controller.Health(CancellationToken.None);

        var okResult = Assert.IsType<OkObjectResult>(result);
        var json = System.Text.Json.JsonSerializer.Serialize(okResult.Value);
        Assert.Contains("false", json, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Query_WithAoiId_ScopesResults()
    {
        _llmServiceMock
            .Setup(s => s.TranslateQueryAsync(
                It.IsAny<string>(),
                It.IsAny<QueryContext?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new LlmQueryResult
            {
                Success = true,
                Interpretation = "Find all risk events in test AOI",
                Plan = new QueryPlan
                {
                    TargetEntity = TargetEntityType.RiskEvent
                    // AoiId intentionally left null — controller should set it from request
                }
            });

        var request = new NaturalLanguageQueryRequest
        {
            Query = "show risk events",
            AoiId = "test-aoi"
        };

        var result = await _controller.Query(request, CancellationToken.None);

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var response = Assert.IsType<NaturalLanguageQueryResponse>(okResult.Value);
        Assert.True(response.Success);
        Assert.Equal("test-aoi", response.QueryPlan?.AoiId);
    }

    public void Dispose()
    {
        _context.Dispose();
    }
}
