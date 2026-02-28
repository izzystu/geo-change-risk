using GeoChangeRisk.Api.Controllers;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Moq;
using NetTopologySuite.Geometries;
using Xunit;

namespace GeoChangeRisk.Tests.Controllers;

public class LidarControllerTests : IDisposable
{
    private readonly GeoChangeDbContext _context;
    private readonly LidarController _controller;
    private readonly Mock<IObjectStorageService> _storageMock;
    private readonly GeometryFactory _factory;

    public LidarControllerTests()
    {
        var options = new DbContextOptionsBuilder<GeoChangeDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        _context = new TestDbContext(options);
        _storageMock = new Mock<IObjectStorageService>();
        _factory = new GeometryFactory(new PrecisionModel(), 4326);

        var config = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Storage:BucketLidar"] = "georisk-lidar"
            })
            .Build();

        _controller = new LidarController(
            _context,
            _storageMock.Object,
            config,
            Mock.Of<ILogger<LidarController>>());

        SeedData();
    }

    private static readonly Guid TestPolygonId = Guid.Parse("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");
    private static readonly Guid TestRunId = Guid.Parse("11111111-2222-3333-4444-555555555555");

    private void SeedData()
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

        _context.ProcessingRuns.Add(new ProcessingRun
        {
            RunId = TestRunId,
            AoiId = "test-aoi",
            Status = ProcessingStatus.Completed,
            BeforeDate = new DateTime(2018, 1, 1),
            AfterDate = new DateTime(2019, 1, 1),
        });

        _context.ChangePolygons.Add(new ChangePolygon
        {
            ChangePolygonId = TestPolygonId,
            RunId = TestRunId,
            Geometry = _factory.CreatePolygon(new Coordinate[]
            {
                new(0.1, 0.1), new(0.2, 0.1), new(0.2, 0.2), new(0.1, 0.2), new(0.1, 0.1)
            }),
            AreaSqMeters = 500,
            NdviDropMean = -0.4,
            NdviDropMax = -0.6,
            ChangeType = ChangeType.LandslideDebris,
        });

        _context.SaveChanges();
    }

    [Fact]
    public async Task GetByPolygon_ReturnsBadRequest_WhenInvalidGuid()
    {
        var result = await _controller.GetByPolygon("not-a-guid");
        Assert.IsType<BadRequestObjectResult>(result.Result);
    }

    [Fact]
    public async Task GetByPolygon_ReturnsNotFound_WhenPolygonMissing()
    {
        var result = await _controller.GetByPolygon(Guid.NewGuid().ToString());
        Assert.IsType<NotFoundObjectResult>(result.Result);
    }

    [Fact]
    public async Task GetByPolygon_ReturnsNotFound_WhenNoLidarData()
    {
        _storageMock
            .Setup(s => s.ListObjectsAsync(
                It.Is<string>(b => b == "georisk-lidar"),
                It.IsAny<string?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((IList<StorageObjectInfo>)new List<StorageObjectInfo>());

        var result = await _controller.GetByPolygon(TestPolygonId.ToString());
        Assert.IsType<NotFoundObjectResult>(result.Result);
    }

    [Fact]
    public async Task GetByPolygon_ReturnsPresignedUrls()
    {
        var now = DateTime.UtcNow;
        var sourceId = $"polygon-{TestPolygonId}";
        var prefix = $"test-aoi/{sourceId}/";

        _storageMock
            .Setup(s => s.ListObjectsAsync(
                It.Is<string>(b => b == "georisk-lidar"),
                It.Is<string?>(p => p == prefix),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((IList<StorageObjectInfo>)new List<StorageObjectInfo>
            {
                new() { ObjectPath = $"test-aoi/{sourceId}/dtm.tif", Size = 1000, LastModified = now },
                new() { ObjectPath = $"test-aoi/{sourceId}/dsm.tif", Size = 2000, LastModified = now },
                new() { ObjectPath = $"test-aoi/{sourceId}/chm.tif", Size = 1500, LastModified = now },
            });

        _storageMock
            .Setup(s => s.GetPresignedUrlAsync(
                It.Is<string>(b => b == "georisk-lidar"),
                It.IsAny<string>(),
                It.IsAny<int>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((string bucket, string key, int expires, CancellationToken ct) => $"https://presigned/{key}");

        var result = await _controller.GetByPolygon(TestPolygonId.ToString());
        var ok = Assert.IsType<OkObjectResult>(result.Result);
        var detail = Assert.IsType<LidarSourceDetailDto>(ok.Value);

        Assert.Equal(sourceId, detail.SourceId);
        Assert.Equal("test-aoi", detail.AoiId);
        Assert.Equal(3, detail.Files.Count);
        Assert.Equal($"https://presigned/test-aoi/{sourceId}/dtm.tif", detail.DtmUrl);
        Assert.Equal($"https://presigned/test-aoi/{sourceId}/dsm.tif", detail.DsmUrl);
        Assert.Equal($"https://presigned/test-aoi/{sourceId}/chm.tif", detail.ChmUrl);
    }

    public void Dispose()
    {
        _context.Dispose();
    }
}
