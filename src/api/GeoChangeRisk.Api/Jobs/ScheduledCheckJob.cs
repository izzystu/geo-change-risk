using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Hangfire;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Jobs;

/// <summary>
/// Hangfire job that checks for new satellite imagery and triggers processing runs.
/// </summary>
public class ScheduledCheckJob
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<ScheduledCheckJob> _logger;
    private readonly IConfiguration _configuration;
    private readonly IBackgroundJobClient _backgroundJobs;

    public ScheduledCheckJob(
        IServiceScopeFactory scopeFactory,
        ILogger<ScheduledCheckJob> logger,
        IConfiguration configuration,
        IBackgroundJobClient backgroundJobs)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;
        _configuration = configuration;
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

            // Run georisk check command
            var checkResult = await RunCheckCommandAsync(aoiId, aoi.MaxCloudCover, cancellationToken);

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

    private async Task<CheckCommandResult> RunCheckCommandAsync(
        string aoiId, double maxCloudCover, CancellationToken cancellationToken)
    {
        var pythonExecutable = string.IsNullOrWhiteSpace(_configuration["Python:Executable"])
            ? "python"
            : _configuration["Python:Executable"]!;
        var pipelineDir = string.IsNullOrWhiteSpace(_configuration["Python:PipelineDir"])
            ? Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "pipeline"))
            : _configuration["Python:PipelineDir"]!;

        var arguments = $"-m georisk.cli check --aoi-id={aoiId} --max-cloud={maxCloudCover} --json";

        _logger.LogDebug("Running: {Executable} {Arguments} in {WorkingDir}",
            pythonExecutable, arguments, pipelineDir);

        var startInfo = new ProcessStartInfo
        {
            FileName = pythonExecutable,
            Arguments = arguments,
            WorkingDirectory = pipelineDir,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        using var process = new Process { StartInfo = startInfo };

        var stdout = new System.Text.StringBuilder();
        var stderr = new System.Text.StringBuilder();

        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data != null) stdout.AppendLine(e.Data);
        };
        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data != null)
            {
                stderr.AppendLine(e.Data);
                _logger.LogDebug("[georisk check] {Line}", e.Data);
            }
        };

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        try
        {
            await process.WaitForExitAsync(cancellationToken);
        }
        catch (OperationCanceledException)
        {
            try { process.Kill(true); } catch { /* process may have already exited */ }
            throw;
        }

        var exitCode = process.ExitCode;

        if (exitCode == 0)
        {
            var json = stdout.ToString().Trim();
            var result = JsonSerializer.Deserialize<CheckCommandResult>(json);
            return result ?? new CheckCommandResult();
        }

        if (exitCode == 1)
        {
            // No new data — not an error
            return new CheckCommandResult();
        }

        // Exit code 2 or other = error
        throw new InvalidOperationException(
            $"georisk check failed (exit code {exitCode}): {stderr.ToString().Trim()}");
    }

    private class CheckCommandResult
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
}
