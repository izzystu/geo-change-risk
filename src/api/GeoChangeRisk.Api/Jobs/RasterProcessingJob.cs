using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Jobs;

public class RasterProcessingJob
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<RasterProcessingJob> _logger;
    private readonly IPipelineExecutor _executor;

    public RasterProcessingJob(
        IServiceScopeFactory scopeFactory,
        ILogger<RasterProcessingJob> logger,
        IPipelineExecutor executor)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;
        _executor = executor;
    }

    public async Task ExecuteAsync(Guid runId, CancellationToken cancellationToken = default)
    {
        // Use a new scope for database access (Hangfire jobs run outside request scope)
        using var scope = _scopeFactory.CreateScope();
        var context = scope.ServiceProvider.GetRequiredService<GeoChangeDbContext>();

        var run = await context.ProcessingRuns
            .Include(r => r.AreaOfInterest)
            .FirstOrDefaultAsync(r => r.RunId == runId, cancellationToken);

        if (run == null)
        {
            _logger.LogError("Processing run {RunId} not found", runId);
            return;
        }

        try
        {
            // Update status to FetchingImagery (first step)
            run.Status = ProcessingStatus.FetchingImagery;
            run.StartedAt = DateTime.UtcNow;
            await context.SaveChangesAsync(cancellationToken);

            // Execute pipeline via abstracted executor
            var exitCode = await _executor.RunProcessAsync(run, cancellationToken);

            if (exitCode == 0)
            {
                // Python CLI updates status to Completed on success, just log here
                _logger.LogInformation("Processing run {RunId} completed successfully", runId);
                return; // No need to save - Python already updated the status
            }
            else
            {
                // On failure, ensure status is set (Python may have crashed before updating)
                run.Status = ProcessingStatus.Failed;
                run.CompletedAt = DateTime.UtcNow;
                run.ErrorMessage = $"Python pipeline exited with code {exitCode}";
                _logger.LogError("Processing run {RunId} failed with exit code {ExitCode}", runId, exitCode);
            }
        }
        catch (Exception ex)
        {
            run.Status = ProcessingStatus.Failed;
            run.CompletedAt = DateTime.UtcNow;
            run.ErrorMessage = ex.Message;
            _logger.LogError(ex, "Processing run {RunId} failed with exception", runId);
        }

        await context.SaveChangesAsync(cancellationToken);
    }
}
