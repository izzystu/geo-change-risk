using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Hangfire;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Jobs;

/// <summary>
/// Hangfire job that checks for new satellite imagery and triggers processing runs.
/// In EventBridge mode, this job is only used locally — on AWS, EventBridge triggers ECS directly.
/// </summary>
public class ScheduledCheckJob
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<ScheduledCheckJob> _logger;
    private readonly IPipelineExecutor _executor;
    private readonly IBackgroundJobClient _backgroundJobs;

    public ScheduledCheckJob(
        IServiceScopeFactory scopeFactory,
        ILogger<ScheduledCheckJob> logger,
        IPipelineExecutor executor,
        IBackgroundJobClient backgroundJobs)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;
        _executor = executor;
        _backgroundJobs = backgroundJobs;
    }

    [DisableConcurrentExecution(timeoutInSeconds: 300)]
    public async Task ExecuteAsync(string aoiId, CancellationToken cancellationToken = default)
    {
        using var scope = _scopeFactory.CreateScope();
        var context = scope.ServiceProvider.GetRequiredService<GeoChangeDbContext>();

        var aoi = await context.AreasOfInterest.FindAsync([aoiId], cancellationToken);
        if (aoi == null)
        {
            _logger.LogError("AOI {AoiId} not found for scheduled check", aoiId);
            return;
        }

        _logger.LogInformation("Running scheduled imagery check for AOI {AoiId}", aoiId);

        try
        {
            // Guard: skip if any processing run is in progress for this AOI
            var inProgressStatuses = new[]
            {
                ProcessingStatus.Pending,
                ProcessingStatus.FetchingImagery,
                ProcessingStatus.CalculatingNdvi,
                ProcessingStatus.DetectingChanges,
                ProcessingStatus.ScoringRisk
            };

            var hasInProgressRun = await context.ProcessingRuns
                .AnyAsync(r => r.AoiId == aoiId && inProgressStatuses.Contains(r.Status), cancellationToken);

            if (hasInProgressRun)
            {
                _logger.LogInformation(
                    "Skipping scheduled check for AOI {AoiId} — processing run already in progress", aoiId);
                aoi.LastCheckedAt = DateTime.UtcNow;
                await context.SaveChangesAsync(cancellationToken);
                return;
            }

            // Run georisk check command via executor
            var checkResult = await _executor.RunCheckAsync(aoiId, aoi.MaxCloudCover, cancellationToken);

            aoi.LastCheckedAt = DateTime.UtcNow;

            if (checkResult.NewData)
            {
                if (string.IsNullOrWhiteSpace(checkResult.RecommendedBeforeDate) ||
                    string.IsNullOrWhiteSpace(checkResult.RecommendedAfterDate))
                {
                    _logger.LogError("Check command returned new_data=true but missing date recommendations for AOI {AoiId}", aoiId);
                    await context.SaveChangesAsync(cancellationToken);
                    return;
                }

                _logger.LogInformation(
                    "New imagery found for AOI {AoiId}: scene {SceneId} ({SceneDate}, {CloudCover}% cloud)",
                    aoiId, checkResult.SceneId, checkResult.SceneDate, checkResult.CloudCover);

                var run = new ProcessingRun
                {
                    AoiId = aoiId,
                    BeforeDate = DateTime.SpecifyKind(
                        DateTime.Parse(checkResult.RecommendedBeforeDate), DateTimeKind.Utc),
                    AfterDate = DateTime.SpecifyKind(
                        DateTime.Parse(checkResult.RecommendedAfterDate), DateTimeKind.Utc),
                    Status = ProcessingStatus.Pending,
                    Metadata = new Dictionary<string, object>
                    {
                        ["triggered_by"] = "scheduled_check",
                        ["scene_id"] = checkResult.SceneId ?? "",
                        ["cloud_cover"] = checkResult.CloudCover
                    }
                };

                context.ProcessingRuns.Add(run);
                aoi.LastProcessedAt = DateTime.UtcNow;
                await context.SaveChangesAsync(cancellationToken);

                _backgroundJobs.Enqueue<RasterProcessingJob>(
                    job => job.ExecuteAsync(run.RunId, CancellationToken.None));

                _logger.LogInformation(
                    "Created processing run {RunId} for AOI {AoiId} from scheduled check", run.RunId, aoiId);
            }
            else
            {
                _logger.LogInformation("No new imagery for AOI {AoiId}", aoiId);
                await context.SaveChangesAsync(cancellationToken);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Scheduled check failed for AOI {AoiId}", aoiId);
            context.ChangeTracker.Clear();
            // Re-fetch AOI since we cleared the tracker
            aoi = await context.AreasOfInterest.FindAsync([aoiId], cancellationToken);
            if (aoi != null)
            {
                aoi.LastCheckedAt = DateTime.UtcNow;
                await context.SaveChangesAsync(cancellationToken);
            }
        }
    }
}
