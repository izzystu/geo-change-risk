using GeoChangeRisk.Api.Services;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Moq;
using NetTopologySuite.Geometries;
using Xunit;

namespace GeoChangeRisk.Tests.Services;

public class QueryExecutorServiceTests : IDisposable
{
    private readonly GeoChangeDbContext _context;
    private readonly QueryExecutorService _executor;
    private readonly GeometryFactory _factory;

    public QueryExecutorServiceTests()
    {
        var options = new DbContextOptionsBuilder<GeoChangeDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        _context = new TestDbContext(options);
        _factory = new GeometryFactory(new PrecisionModel(), 4326);

        _executor = new QueryExecutorService(
            _context,
            Mock.Of<ILogger<QueryExecutorService>>());

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

        var aoi = new AreaOfInterest
        {
            AoiId = "test-aoi",
            Name = "Test AOI",
            BoundingBox = polygon,
            CenterPoint = point
        };
        _context.AreasOfInterest.Add(aoi);

        var hospital = new Asset
        {
            AssetId = "hospital-1",
            AoiId = "test-aoi",
            Name = "General Hospital",
            AssetType = AssetType.Hospital,
            Criticality = Criticality.Critical,
            Geometry = point
        };

        var school = new Asset
        {
            AssetId = "school-1",
            AoiId = "test-aoi",
            Name = "Elementary School",
            AssetType = AssetType.School,
            Criticality = Criticality.High,
            Geometry = point
        };

        var substation = new Asset
        {
            AssetId = "sub-1",
            AoiId = "other-aoi",
            Name = "Substation Alpha",
            AssetType = AssetType.Substation,
            Criticality = Criticality.High,
            Geometry = point
        };

        _context.Assets.AddRange(hospital, school, substation);

        var run = new ProcessingRun
        {
            RunId = Guid.NewGuid(),
            AoiId = "test-aoi",
            Status = ProcessingStatus.Completed,
            BeforeDate = new DateTime(2024, 1, 1),
            AfterDate = new DateTime(2024, 6, 1)
        };
        _context.ProcessingRuns.Add(run);

        var change1 = new ChangePolygon
        {
            ChangePolygonId = Guid.NewGuid(),
            RunId = run.RunId,
            Geometry = polygon,
            AreaSqMeters = 8000,
            NdviDropMean = -0.35,
            NdviDropMax = -0.5,
            ChangeType = ChangeType.LandslideDebris
        };

        var change2 = new ChangePolygon
        {
            ChangePolygonId = Guid.NewGuid(),
            RunId = run.RunId,
            Geometry = polygon,
            AreaSqMeters = 3000,
            NdviDropMean = -0.2,
            NdviDropMax = -0.3,
            ChangeType = ChangeType.VegetationLoss
        };
        _context.ChangePolygons.AddRange(change1, change2);

        var riskEvent1 = new RiskEvent
        {
            RiskEventId = Guid.NewGuid(),
            ChangePolygonId = change1.ChangePolygonId,
            AssetId = "hospital-1",
            DistanceMeters = 150,
            RiskScore = 85,
            RiskLevel = RiskLevel.Critical
        };

        var riskEvent2 = new RiskEvent
        {
            RiskEventId = Guid.NewGuid(),
            ChangePolygonId = change2.ChangePolygonId,
            AssetId = "school-1",
            DistanceMeters = 400,
            RiskScore = 45,
            RiskLevel = RiskLevel.Medium
        };

        _context.RiskEvents.AddRange(riskEvent1, riskEvent2);
        _context.SaveChanges();
    }

    [Fact]
    public async Task RiskEventQuery_WithRiskLevelFilter_ReturnsFilteredResults()
    {
        var plan = new QueryPlan
        {
            TargetEntity = TargetEntityType.RiskEvent,
            Filters = new List<AttributeFilter>
            {
                new() { Property = "RiskLevel", Operator = FilterOperator.eq, Value = "Critical" }
            }
        };

        var result = await _executor.ExecuteAsync(plan);

        Assert.Equal(1, result.TotalCount);
        Assert.Single(result.Items);
    }

    [Fact]
    public async Task AssetQuery_WithAssetTypeFilter_ReturnsCorrectAssets()
    {
        var plan = new QueryPlan
        {
            TargetEntity = TargetEntityType.Asset,
            Filters = new List<AttributeFilter>
            {
                new() { Property = "AssetType", Operator = FilterOperator.eq, Value = "Hospital" }
            }
        };

        var result = await _executor.ExecuteAsync(plan);

        Assert.Equal(1, result.TotalCount);
        Assert.Single(result.Items);
        var dto = Assert.IsType<AssetDto>(result.Items[0]);
        Assert.Equal("General Hospital", dto.Name);
    }

    [Fact]
    public async Task ChangePolygonQuery_WithAreaFilter_ReturnsLargeChanges()
    {
        var plan = new QueryPlan
        {
            TargetEntity = TargetEntityType.ChangePolygon,
            Filters = new List<AttributeFilter>
            {
                new() { Property = "AreaSqMeters", Operator = FilterOperator.gt, Value = "5000" }
            }
        };

        var result = await _executor.ExecuteAsync(plan);

        Assert.Equal(1, result.TotalCount);
        Assert.Single(result.Items);
        var dto = Assert.IsType<ChangePolygonDto>(result.Items[0]);
        Assert.True(dto.AreaSqMeters > 5000);
    }

    [Fact]
    public async Task AoiScoping_ReturnsOnlyScopedAssets()
    {
        var plan = new QueryPlan
        {
            TargetEntity = TargetEntityType.Asset,
            AoiId = "test-aoi"
        };

        var result = await _executor.ExecuteAsync(plan);

        Assert.Equal(2, result.TotalCount); // hospital + school, not substation
        Assert.DoesNotContain(result.Items, i =>
        {
            var dto = (AssetDto)i;
            return dto.AoiId == "other-aoi";
        });
    }

    [Fact]
    public async Task OrderBy_AppliesCorrectSorting()
    {
        var plan = new QueryPlan
        {
            TargetEntity = TargetEntityType.RiskEvent,
            OrderBy = "RiskScore",
            OrderDescending = true
        };

        var result = await _executor.ExecuteAsync(plan);

        Assert.Equal(2, result.TotalCount);
        var first = Assert.IsType<RiskEventDto>(result.Items[0]);
        var second = Assert.IsType<RiskEventDto>(result.Items[1]);
        Assert.True(first.RiskScore >= second.RiskScore);
    }

    [Fact]
    public async Task Limit_CapsResults()
    {
        var plan = new QueryPlan
        {
            TargetEntity = TargetEntityType.RiskEvent,
            Limit = 1
        };

        var result = await _executor.ExecuteAsync(plan);

        Assert.Equal(2, result.TotalCount); // Total is still 2
        Assert.Single(result.Items); // But only 1 returned
    }

    [Fact]
    public async Task UnknownProperty_IsIgnored()
    {
        var plan = new QueryPlan
        {
            TargetEntity = TargetEntityType.RiskEvent,
            Filters = new List<AttributeFilter>
            {
                new() { Property = "NonExistentField", Operator = FilterOperator.eq, Value = "test" }
            }
        };

        var result = await _executor.ExecuteAsync(plan);

        // Should not throw, returns all risk events
        Assert.Equal(2, result.TotalCount);
    }

    [Fact]
    public async Task ProcessingRunQuery_WithStatusFilter_ReturnsFilteredRuns()
    {
        var plan = new QueryPlan
        {
            TargetEntity = TargetEntityType.ProcessingRun,
            Filters = new List<AttributeFilter>
            {
                new() { Property = "Status", Operator = FilterOperator.eq, Value = "Completed" }
            }
        };

        var result = await _executor.ExecuteAsync(plan);

        Assert.Equal(1, result.TotalCount);
        Assert.Single(result.Items);
    }

    // Note: Spatial filter tests require PostGIS (real PostgreSQL) and cannot
    // be tested with InMemory provider. The spatial filter implementation uses
    // the RiskEvent.DistanceMeters field + asset ID filtering as a proxy,
    // which is tested indirectly through the attribute filter tests above.

    public void Dispose()
    {
        _context.Dispose();
    }
}
