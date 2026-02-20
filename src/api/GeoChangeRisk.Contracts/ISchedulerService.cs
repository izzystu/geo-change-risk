namespace GeoChangeRisk.Contracts;

/// <summary>
/// Abstracts job scheduling (Hangfire locally, EventBridge on AWS).
/// </summary>
public interface ISchedulerService
{
    /// <summary>
    /// Creates or updates a recurring schedule for an AOI.
    /// </summary>
    Task AddOrUpdateScheduleAsync(string aoiId, string cronExpression, CancellationToken ct = default);

    /// <summary>
    /// Removes a recurring schedule for an AOI.
    /// </summary>
    Task RemoveScheduleAsync(string aoiId, CancellationToken ct = default);

    /// <summary>
    /// Reconciles all DB schedules with the scheduler backend. Called on startup.
    /// </summary>
    Task SyncAllSchedulesAsync(CancellationToken ct = default);
}
