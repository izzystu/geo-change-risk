using GeoChangeRisk.Api.Controllers;
using GeoChangeRisk.Api.Jobs;
using GeoChangeRisk.Api.Services;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Hangfire;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Moq;
using NetTopologySuite.Geometries;
using Xunit;

namespace GeoChangeRisk.Tests.Controllers;

public class AreasOfInterestScheduleTests : IDisposable
{
    private readonly GeoChangeDbContext _context;
    private readonly AreasOfInterestController _controller;
    private readonly Mock<IRecurringJobManager> _recurringJobsMock;
    private readonly GeometryFactory _factory;

    public AreasOfInterestScheduleTests()
    {
        var options = new DbContextOptionsBuilder<GeoChangeDbContext>()
            .UseInMemoryDatabase(databaseName: Guid.NewGuid().ToString())
            .Options;

        _context = new TestDbContext(options);
        _recurringJobsMock = new Mock<IRecurringJobManager>();
        _factory = new GeometryFactory(new PrecisionModel(), 4326);

        _controller = new AreasOfInterestController(
            _context,
            Mock.Of<ILogger<AreasOfInterestController>>(),
            Mock.Of<IGeometryParsingService>(),
            _recurringJobsMock.Object);
    }

    private AreaOfInterest CreateTestAoi(string aoiId = "test-aoi", string name = "Test AOI")
    {
        return new AreaOfInterest
        {
            AoiId = aoiId,
            Name = name,
            BoundingBox = _factory.CreatePolygon(new Coordinate[]
            {
                new(-121.7, 39.7), new(-121.5, 39.7), new(-121.5, 39.9),
                new(-121.7, 39.9), new(-121.7, 39.7)
            }),
            CenterPoint = _factory.CreatePoint(new Coordinate(-121.6, 39.8))
        };
    }

    [Fact]
    public async Task UpdateSchedule_ValidCron_CreatesHangfireJob()
    {
        // Arrange
        var aoi = CreateTestAoi();
        _context.AreasOfInterest.Add(aoi);
        await _context.SaveChangesAsync();

        var request = new UpdateAoiScheduleRequest
        {
            ProcessingSchedule = "0 6 * * 1",
            ProcessingEnabled = true
        };

        // Act
        var result = await _controller.UpdateSchedule("test-aoi", request);

        // Assert
        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var dto = Assert.IsType<AreaOfInterestDto>(okResult.Value);
        Assert.Equal("0 6 * * 1", dto.ProcessingSchedule);
        Assert.True(dto.ProcessingEnabled);

        _recurringJobsMock.Verify(
            m => m.AddOrUpdate(
                "scheduled-check-test-aoi",
                It.IsAny<Hangfire.Common.Job>(),
                "0 6 * * 1",
                It.IsAny<RecurringJobOptions>()),
            Times.Once);
    }

    [Fact]
    public async Task UpdateSchedule_InvalidCron_ReturnsBadRequest()
    {
        // Arrange
        var aoi = CreateTestAoi();
        _context.AreasOfInterest.Add(aoi);
        await _context.SaveChangesAsync();

        _recurringJobsMock
            .Setup(m => m.AddOrUpdate(
                It.IsAny<string>(),
                It.IsAny<Hangfire.Common.Job>(),
                It.IsAny<string>(),
                It.IsAny<RecurringJobOptions>()))
            .Throws(new ArgumentException("Invalid cron", new Exception("bad cron expression")));

        var request = new UpdateAoiScheduleRequest
        {
            ProcessingSchedule = "not-a-cron",
            ProcessingEnabled = true
        };

        // Act
        var result = await _controller.UpdateSchedule("test-aoi", request);

        // Assert
        Assert.IsType<BadRequestObjectResult>(result.Result);
    }

    [Fact]
    public async Task UpdateSchedule_DisableProcessing_RemovesHangfireJob()
    {
        // Arrange
        var aoi = CreateTestAoi();
        aoi.ProcessingSchedule = "0 6 * * 1";
        aoi.ProcessingEnabled = true;
        _context.AreasOfInterest.Add(aoi);
        await _context.SaveChangesAsync();

        var request = new UpdateAoiScheduleRequest
        {
            ProcessingEnabled = false
        };

        // Act
        var result = await _controller.UpdateSchedule("test-aoi", request);

        // Assert
        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var dto = Assert.IsType<AreaOfInterestDto>(okResult.Value);
        Assert.False(dto.ProcessingEnabled);

        _recurringJobsMock.Verify(
            m => m.RemoveIfExists("scheduled-check-test-aoi"),
            Times.Once);
    }

    [Fact]
    public async Task UpdateSchedule_PartialUpdate_OnlyChangesProvidedFields()
    {
        // Arrange
        var aoi = CreateTestAoi();
        aoi.ProcessingSchedule = "0 6 * * 1";
        aoi.ProcessingEnabled = true;
        aoi.MaxCloudCover = 20;
        aoi.DefaultLookbackDays = 90;
        _context.AreasOfInterest.Add(aoi);
        await _context.SaveChangesAsync();

        var request = new UpdateAoiScheduleRequest
        {
            MaxCloudCover = 30
        };

        // Act
        var result = await _controller.UpdateSchedule("test-aoi", request);

        // Assert
        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var dto = Assert.IsType<AreaOfInterestDto>(okResult.Value);

        Assert.Equal(30, dto.MaxCloudCover);
        // Verify other fields unchanged
        Assert.Equal("0 6 * * 1", dto.ProcessingSchedule);
        Assert.True(dto.ProcessingEnabled);
        Assert.Equal(90, dto.DefaultLookbackDays);
    }

    [Fact]
    public async Task UpdateSchedule_AoiNotFound_Returns404()
    {
        // Arrange
        var request = new UpdateAoiScheduleRequest
        {
            ProcessingSchedule = "0 6 * * 1",
            ProcessingEnabled = true
        };

        // Act
        var result = await _controller.UpdateSchedule("nonexistent-aoi", request);

        // Assert
        Assert.IsType<NotFoundObjectResult>(result.Result);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(101)]
    public async Task UpdateSchedule_MaxCloudCoverOutOfRange_ReturnsBadRequest(double cloudCover)
    {
        // Arrange
        var aoi = CreateTestAoi();
        _context.AreasOfInterest.Add(aoi);
        await _context.SaveChangesAsync();

        var request = new UpdateAoiScheduleRequest
        {
            MaxCloudCover = cloudCover
        };

        // Act
        var result = await _controller.UpdateSchedule("test-aoi", request);

        // Assert
        Assert.IsType<BadRequestObjectResult>(result.Result);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(500)]
    public async Task UpdateSchedule_DefaultLookbackDaysOutOfRange_ReturnsBadRequest(int lookbackDays)
    {
        // Arrange
        var aoi = CreateTestAoi();
        _context.AreasOfInterest.Add(aoi);
        await _context.SaveChangesAsync();

        var request = new UpdateAoiScheduleRequest
        {
            DefaultLookbackDays = lookbackDays
        };

        // Act
        var result = await _controller.UpdateSchedule("test-aoi", request);

        // Assert
        Assert.IsType<BadRequestObjectResult>(result.Result);
    }

    [Fact]
    public async Task UpdateSchedule_EmptySchedule_ClearsToNullAndRemovesJob()
    {
        // Arrange
        var aoi = CreateTestAoi();
        aoi.ProcessingSchedule = "0 6 * * 1";
        aoi.ProcessingEnabled = true;
        _context.AreasOfInterest.Add(aoi);
        await _context.SaveChangesAsync();

        var request = new UpdateAoiScheduleRequest
        {
            ProcessingSchedule = ""
        };

        // Act
        var result = await _controller.UpdateSchedule("test-aoi", request);

        // Assert
        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        var dto = Assert.IsType<AreaOfInterestDto>(okResult.Value);
        Assert.Null(dto.ProcessingSchedule);

        // Should call RemoveIfExists because schedule is now null (even though enabled=true)
        _recurringJobsMock.Verify(
            m => m.RemoveIfExists("scheduled-check-test-aoi"),
            Times.Once);
    }

    public void Dispose()
    {
        _context.Dispose();
    }
}
