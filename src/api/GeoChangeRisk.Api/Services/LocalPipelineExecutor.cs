using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data.Models;

namespace GeoChangeRisk.Api.Services;

/// <summary>
/// Local subprocess pipeline executor (default for development).
/// Runs Python CLI commands as child processes.
/// </summary>
public class LocalPipelineExecutor : IPipelineExecutor
{
    private readonly IConfiguration _configuration;
    private readonly ILogger<LocalPipelineExecutor> _logger;

    public LocalPipelineExecutor(IConfiguration configuration, ILogger<LocalPipelineExecutor> logger)
    {
        _configuration = configuration;
        _logger = logger;
    }

    public async Task<int> RunProcessAsync(ProcessingRun run, CancellationToken ct = default)
    {
        var pythonExecutable = GetPythonExecutable();
        var pipelineDir = GetPipelineDir();

        var args = new List<string>
        {
            "-m", "georisk.cli",
            "process",
            $"--aoi-id={run.AoiId}",
            $"--before={run.BeforeDate:yyyy-MM-dd}",
            $"--after={run.AfterDate:yyyy-MM-dd}",
            $"--run-id={run.RunId}"
        };

        _logger.LogInformation("Starting Python pipeline for run {RunId}: {Executable} {Args}",
            run.RunId, pythonExecutable, string.Join(" ", args));

        return await RunProcessInternalAsync(pythonExecutable, pipelineDir, args, logPrefix: "Python", ct: ct);
    }

    public async Task<CheckCommandResult> RunCheckAsync(string aoiId, double maxCloudCover, CancellationToken ct = default)
    {
        var pythonExecutable = GetPythonExecutable();
        var pipelineDir = GetPipelineDir();

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
            await process.WaitForExitAsync(ct);
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
            var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
            var result = JsonSerializer.Deserialize<CheckCommandResult>(json, options);
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

    private string GetPythonExecutable()
    {
        return string.IsNullOrWhiteSpace(_configuration["Python:Executable"])
            ? "python"
            : _configuration["Python:Executable"]!;
    }

    private string GetPipelineDir()
    {
        return string.IsNullOrWhiteSpace(_configuration["Python:PipelineDir"])
            ? Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "pipeline"))
            : _configuration["Python:PipelineDir"]!;
    }

    private async Task<int> RunProcessInternalAsync(
        string pythonExecutable,
        string workingDirectory,
        List<string> arguments,
        string logPrefix,
        CancellationToken ct)
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
                _logger.LogInformation("[{Prefix}] {Output}", logPrefix, e.Data);
        };

        process.ErrorDataReceived += (sender, e) =>
        {
            if (!string.IsNullOrEmpty(e.Data))
            {
                if (e.Data.Contains("[error") || e.Data.Contains("Traceback"))
                    _logger.LogError("[{Prefix}] {Output}", logPrefix, e.Data);
                else if (e.Data.Contains("[warning"))
                    _logger.LogWarning("[{Prefix}] {Output}", logPrefix, e.Data);
                else
                    _logger.LogInformation("[{Prefix}] {Output}", logPrefix, e.Data);
            }
        };

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        await process.WaitForExitAsync(ct);

        return process.ExitCode;
    }
}
