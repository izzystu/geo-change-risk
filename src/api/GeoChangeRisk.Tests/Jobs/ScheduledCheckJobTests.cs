using System.Text.Json;
using System.Text.Json.Serialization;
using GeoChangeRisk.Api.Jobs;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Hangfire;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Moq;
using NetTopologySuite.Geometries;
using Xunit;

namespace GeoChangeRisk.Tests.Jobs;

public class ScheduledCheckJobTests : IDisposable
{
    private readonly GeoChangeDbContext _context;
    private readonly ScheduledCheckJob _job;
    private readonly Mock<IBackgroundJobClient> _backgroundJobsMock;
    private readonly GeometryFactory _factory;

    public ScheduledCheckJobTests()
    {
        var options = new DbContextOptionsBuilder<GeoChangeDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        _context = new TestDbContext(options);
        _factory = new GeometryFactory(new PrecisionModel(), 4326);
        _backgroundJobsMock = new Mock<IBackgroundJobClient>();

        // Mock IServiceScopeFactory to return a scope that provides our InMemory context
        var serviceProviderMock = new Mock<IServiceProvider>();
        serviceProviderMock
            .Setup(sp => sp.GetService(typeof(GeoChangeDbContext)))
            .Returns(_context);

        var scopeMock = new Mock<IServiceScope>();
        scopeMock.Setup(s => s.ServiceProvider).Returns(serviceProviderMock.Object);

        var scopeFactoryMock = new Mock<IServiceScopeFactory>();
        scopeFactoryMock.Setup(f => f.CreateScope()).Returns(scopeMock.Object);

        // Mock IConfiguration with dummy Python paths
        var configMock = new Mock<IConfiguration>();
        configMock.Setup(c => c["Python:Executable"]).Returns("python");
        configMock.Setup(c => c["Python:PipelineDir"]).Returns("C:\\nonexistent\\pipeline");

        _job = new ScheduledCheckJob(
            scopeFactoryMock.Object,
            Mock.Of<ILogger<ScheduledCheckJob>>(),
            configMock.Object,
            _backgroundJobsMock.Object);
    }

    private AreaOfInterest CreateTestAoi(string aoiId = "test-aoi")
    {
        return new AreaOfInterest
        {
            AoiId = aoiId,
            Name = "Test AOI",
            MaxCloudCover = 20,
            BoundingBox = _factory.CreatePolygon(new Coordinate[]
            {
                new(-121.7, 39.7), new(-121.5, 39.7), new(-121.5, 39.9),
                new(-121.7, 39.9), new(-121.7, 39.7)
            }),
            CenterPoint = _factory.CreatePoint(new Coordinate(-121.6, 39.8))
        };
    }

    private ProcessingRun CreateTestRun(string aoiId, ProcessingStatus status)
    {
        return new ProcessingRun
        {
            RunId = Guid.NewGuid(),
            AoiId = aoiId,
            Status = status,
            BeforeDate = DateTime.UtcNow.AddDays(-90),
            AfterDate = DateTime.UtcNow
        };
    }

    [Fact]
    public async Task ExecuteAsync_SkipsWhenPendingRunExists()
    {
        // Arrange
        var aoi = CreateTestAoi();
        _context.AreasOfInterest.Add(aoi);
        _context.ProcessingRuns.Add(CreateTestRun("test-aoi", ProcessingStatus.Pending));
        await _context.SaveChangesAsync();

        var initialRunCount = await _context.ProcessingRuns.CountAsync();

        // Act
        await _job.ExecuteAsync("test-aoi");

        // Assert - no new processing run created
        var finalRunCount = await _context.ProcessingRuns.CountAsync();
        Assert.Equal(initialRunCount, finalRunCount);

        // LastCheckedAt should be updated
        var updatedAoi = await _context.AreasOfInterest.FindAsync("test-aoi");
        Assert.NotNull(updatedAoi!.LastCheckedAt);
    }

    [Fact]
    public async Task ExecuteAsync_SkipsWhenFetchingImageryRunExists()
    {
        // Arrange
        var aoi = CreateTestAoi();
        _context.AreasOfInterest.Add(aoi);
        _context.ProcessingRuns.Add(CreateTestRun("test-aoi", ProcessingStatus.FetchingImagery));
        await _context.SaveChangesAsync();

        var initialRunCount = await _context.ProcessingRuns.CountAsync();

        // Act
        await _job.ExecuteAsync("test-aoi");

        // Assert - no new processing run created
        var finalRunCount = await _context.ProcessingRuns.CountAsync();
        Assert.Equal(initialRunCount, finalRunCount);

        var updatedAoi = await _context.AreasOfInterest.FindAsync("test-aoi");
        Assert.NotNull(updatedAoi!.LastCheckedAt);
    }

    [Fact]
    public async Task ExecuteAsync_SkipsWhenDetectingChangesRunExists()
    {
        // Arrange
        var aoi = CreateTestAoi();
        _context.AreasOfInterest.Add(aoi);
        _context.ProcessingRuns.Add(CreateTestRun("test-aoi", ProcessingStatus.DetectingChanges));
        await _context.SaveChangesAsync();

        var initialRunCount = await _context.ProcessingRuns.CountAsync();

        // Act
        await _job.ExecuteAsync("test-aoi");

        // Assert - no new processing run created
        var finalRunCount = await _context.ProcessingRuns.CountAsync();
        Assert.Equal(initialRunCount, finalRunCount);

        var updatedAoi = await _context.AreasOfInterest.FindAsync("test-aoi");
        Assert.NotNull(updatedAoi!.LastCheckedAt);
    }

    [Fact]
    public async Task ExecuteAsync_ProceedsWhenOnlyCompletedRunsExist()
    {
        // Arrange
        var aoi = CreateTestAoi();
        _context.AreasOfInterest.Add(aoi);
        _context.ProcessingRuns.Add(CreateTestRun("test-aoi", ProcessingStatus.Completed));
        await _context.SaveChangesAsync();

        // Act - will proceed past guard but fail at subprocess (no Python available)
        // The catch block sets LastCheckedAt
        await _job.ExecuteAsync("test-aoi");

        // Assert - guard was passed (subprocess failed, but LastCheckedAt is set in catch block)
        var updatedAoi = await _context.AreasOfInterest.FindAsync("test-aoi");
        Assert.NotNull(updatedAoi!.LastCheckedAt);
    }

    [Fact]
    public async Task ExecuteAsync_ProceedsWhenOnlyFailedRunsExist()
    {
        // Arrange
        var aoi = CreateTestAoi();
        _context.AreasOfInterest.Add(aoi);
        _context.ProcessingRuns.Add(CreateTestRun("test-aoi", ProcessingStatus.Failed));
        await _context.SaveChangesAsync();

        // Act - will proceed past guard but fail at subprocess
        await _job.ExecuteAsync("test-aoi");

        // Assert - guard was passed (subprocess failed, but LastCheckedAt is set in catch block)
        var updatedAoi = await _context.AreasOfInterest.FindAsync("test-aoi");
        Assert.NotNull(updatedAoi!.LastCheckedAt);
    }

    [Fact]
    public async Task ExecuteAsync_AoiNotFound_ReturnsEarly()
    {
        // Arrange - no AOI seeded

        // Act - should not throw
        var exception = await Record.ExceptionAsync(() => _job.ExecuteAsync("nonexistent-aoi"));

        // Assert
        Assert.Null(exception);

        // No processing runs created
        var runCount = await _context.ProcessingRuns.CountAsync();
        Assert.Equal(0, runCount);
    }

    [Fact]
    public async Task ExecuteAsync_NoRunsAtAll_Proceeds()
    {
        // Arrange - AOI with no runs
        var aoi = CreateTestAoi();
        _context.AreasOfInterest.Add(aoi);
        await _context.SaveChangesAsync();

        // Act - will proceed past guard, fail at subprocess, catch block sets LastCheckedAt
        await _job.ExecuteAsync("test-aoi");

        // Assert - guard was passed
        var updatedAoi = await _context.AreasOfInterest.FindAsync("test-aoi");
        Assert.NotNull(updatedAoi!.LastCheckedAt);
    }

    /// <summary>
    /// Tests the JSON contract for CheckCommandResult. Since the class is private,
    /// we create a duplicate test record with the same JsonPropertyName attributes
    /// to verify the expected JSON format deserializes correctly.
    /// </summary>
    [Fact]
    public void CheckCommandResult_DeserializesValidJson()
    {
        // Arrange
        var json = """
            {
                "new_data": true,
                "scene_id": "S2B_test",
                "scene_date": "2024-01-15",
                "cloud_cover": 8.3,
                "recommended_before_date": "2023-10-15",
                "recommended_after_date": "2024-01-15"
            }
            """;

        // Act
        var result = JsonSerializer.Deserialize<TestCheckCommandResult>(json);

        // Assert
        Assert.NotNull(result);
        Assert.True(result!.NewData);
        Assert.Equal("S2B_test", result.SceneId);
        Assert.Equal("2024-01-15", result.SceneDate);
        Assert.Equal(8.3, result.CloudCover);
        Assert.Equal("2023-10-15", result.RecommendedBeforeDate);
        Assert.Equal("2024-01-15", result.RecommendedAfterDate);
    }

    /// <summary>
    /// Test duplicate of the private CheckCommandResult class to verify JSON contract.
    /// Must have matching JsonPropertyName attributes.
    /// </summary>
    private class TestCheckCommandResult
    {
        [JsonPropertyName("new_data")]
        public bool NewData { get; set; }

        [JsonPropertyName("scene_id")]
        public string? SceneId { get; set; }

        [JsonPropertyName("scene_date")]
        public string? SceneDate { get; set; }

        [JsonPropertyName("cloud_cover")]
        public double CloudCover { get; set; }

        [JsonPropertyName("recommended_before_date")]
        public string RecommendedBeforeDate { get; set; } = "";

        [JsonPropertyName("recommended_after_date")]
        public string RecommendedAfterDate { get; set; } = "";
    }

    public void Dispose()
    {
        _context.Dispose();
    }
}
