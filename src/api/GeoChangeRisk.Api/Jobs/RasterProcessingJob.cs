using System.Diagnostics;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Jobs;

public class RasterProcessingJob
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<RasterProcessingJob> _logger;
    private readonly IConfiguration _configuration;

    public RasterProcessingJob(
        IServiceScopeFactory scopeFactory,
        ILogger<RasterProcessingJob> logger,
        IConfiguration configuration)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;
        _configuration = configuration;
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

            // Get Python configuration
            var pythonExecutable = string.IsNullOrWhiteSpace(_configuration["Python:Executable"])
                ? "python"
                : _configuration["Python:Executable"]!;
            var pipelineDir = string.IsNullOrWhiteSpace(_configuration["Python:PipelineDir"])
                ? Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "pipeline"))
                : _configuration["Python:PipelineDir"]!;

            // Build arguments
            var args = BuildArguments(run);

            _logger.LogInformation("Starting Python pipeline for run {RunId}: {Executable} {Args}",
                runId, pythonExecutable, string.Join(" ", args));

            // Execute Python process
            var exitCode = await RunPythonProcessAsync(pythonExecutable, pipelineDir, args, cancellationToken);

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

    private List<string> BuildArguments(ProcessingRun run)
    {
        var args = new List<string>
        {
            "-m", "georisk.cli",
            "process",
            $"--aoi-id={run.AoiId}",
            $"--before={run.BeforeDate:yyyy-MM-dd}",
            $"--after={run.AfterDate:yyyy-MM-dd}",
            $"--run-id={run.RunId}"  // Use the existing run instead of creating a new one
        };

        return args;
    }

    private async Task<int> RunPythonProcessAsync(
        string pythonExecutable,
        string workingDirectory,
        List<string> arguments,
        CancellationToken cancellationToken)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = pythonExecutable,
            Arguments = string.Join(" ", arguments),
            WorkingDirectory = workingDirectory,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        using var process = new Process { StartInfo = startInfo };

        process.OutputDataReceived += (sender, e) =>
        {
            if (!string.IsNullOrEmpty(e.Data))
                _logger.LogInformation("[Python] {Output}", e.Data);
        };

        process.ErrorDataReceived += (sender, e) =>
        {
            if (!string.IsNullOrEmpty(e.Data))
            {
                // structlog writes to stderr; route by actual log level
                if (e.Data.Contains("[error") || e.Data.Contains("Traceback"))
                    _logger.LogError("[Python] {Output}", e.Data);
                else if (e.Data.Contains("[warning"))
                    _logger.LogWarning("[Python] {Output}", e.Data);
                else
                    _logger.LogInformation("[Python] {Output}", e.Data);
            }
        };

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        await process.WaitForExitAsync(cancellationToken);

        return process.ExitCode;
    }
}
