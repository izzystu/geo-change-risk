using GeoChangeRisk.Api.Jobs;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using Hangfire;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Services;

/// <summary>
/// Hangfire implementation of ISchedulerService for local development.
/// </summary>
public class HangfireSchedulerService : ISchedulerService
{
    private readonly IRecurringJobManager _recurringJobs;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<HangfireSchedulerService> _logger;

    public HangfireSchedulerService(
        IRecurringJobManager recurringJobs,
        IServiceScopeFactory scopeFactory,
        ILogger<HangfireSchedulerService> logger)
    {
        _recurringJobs = recurringJobs;
        _scopeFactory = scopeFactory;
        _logger = logger;
    }

    public Task AddOrUpdateScheduleAsync(string aoiId, string cronExpression, CancellationToken ct = default)
    {
        _recurringJobs.AddOrUpdate<ScheduledCheckJob>(
            $"scheduled-check-{aoiId}",
            job => job.ExecuteAsync(aoiId, CancellationToken.None),
            cronExpression,
            new RecurringJobOptions { TimeZone = TimeZoneInfo.Utc });

        _logger.LogInformation("Registered Hangfire recurring job for AOI {AoiId} with schedule {Schedule}",
            aoiId, cronExpression);

        return Task.CompletedTask;
    }

    public Task RemoveScheduleAsync(string aoiId, CancellationToken ct = default)
    {
        _recurringJobs.RemoveIfExists($"scheduled-check-{aoiId}");
        _logger.LogInformation("Removed Hangfire recurring job for AOI {AoiId}", aoiId);

        return Task.CompletedTask;
    }

    public async Task SyncAllSchedulesAsync(CancellationToken ct = default)
    {
        using var scope = _scopeFactory.CreateScope();
        var context = scope.ServiceProvider.GetRequiredService<GeoChangeDbContext>();

        var scheduledAois = await context.AreasOfInterest
            .Where(a => a.ProcessingEnabled && a.ProcessingSchedule != null)
            .ToListAsync(ct);

        var registeredCount = 0;
        foreach (var aoi in scheduledAois)
        {
            try
            {
                _recurringJobs.AddOrUpdate<ScheduledCheckJob>(
                    $"scheduled-check-{aoi.AoiId}",
                    job => job.ExecuteAsync(aoi.AoiId, CancellationToken.None),
                    aoi.ProcessingSchedule!,
                    new RecurringJobOptions { TimeZone = TimeZoneInfo.Utc });
                registeredCount++;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex,
                    "Failed to register recurring job for AOI {AoiId} with schedule '{Schedule}'",
                    aoi.AoiId, aoi.ProcessingSchedule);
            }
        }

        _logger.LogInformation("Registered {Count}/{Total} recurring check jobs",
            registeredCount, scheduledAois.Count);
    }
}
