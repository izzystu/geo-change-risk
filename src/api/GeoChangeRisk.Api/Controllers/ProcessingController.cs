using GeoChangeRisk.Api.Jobs;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Hangfire;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Controllers;

/// <summary>
/// Endpoints for managing processing runs.
/// </summary>
[ApiController]
[Route("api/processing")]
public class ProcessingController : ControllerBase
{
    private const string ImageryBucket = "georisk-imagery";

    private readonly GeoChangeDbContext _context;
    private readonly IObjectStorageService _storageService;
    private readonly ILogger<ProcessingController> _logger;
    private readonly IBackgroundJobClient _backgroundJobs;

    public ProcessingController(
        GeoChangeDbContext context,
        IObjectStorageService storageService,
        ILogger<ProcessingController> logger,
        IBackgroundJobClient backgroundJobs)
    {
        _context = context;
        _storageService = storageService;
        _logger = logger;
        _backgroundJobs = backgroundJobs;
    }

    /// <summary>
    /// Create a new processing run.
    /// </summary>
    [HttpPost("runs")]
    public async Task<ActionResult<ProcessingRunDto>> CreateRun([FromBody] CreateProcessingRunRequest request)
    {
        // Verify AOI exists
        var aoi = await _context.AreasOfInterest.FindAsync(request.AoiId);
        if (aoi == null)
        {
            return NotFound(new { Error = $"Area of Interest '{request.AoiId}' not found" });
        }

        var run = new ProcessingRun
        {
            AoiId = request.AoiId,
            BeforeDate = DateTime.SpecifyKind(request.BeforeDate, DateTimeKind.Utc),
            AfterDate = DateTime.SpecifyKind(request.AfterDate, DateTimeKind.Utc),
            Status = ProcessingStatus.Pending,
            Metadata = request.Parameters
        };

        _context.ProcessingRuns.Add(run);
        await _context.SaveChangesAsync();

        // Enqueue background job to process the run
        _backgroundJobs.Enqueue<RasterProcessingJob>(
            job => job.ExecuteAsync(run.RunId, CancellationToken.None));

        _logger.LogInformation("Created processing run {RunId} for AOI {AoiId}", run.RunId, run.AoiId);
        _logger.LogInformation("Enqueued processing job for run {RunId}", run.RunId);

        return CreatedAtAction(nameof(GetRun), new { runId = run.RunId }, ToDto(run));
    }

    /// <summary>
    /// Get a processing run by ID.
    /// </summary>
    [HttpGet("runs/{runId:guid}")]
    public async Task<ActionResult<ProcessingRunDto>> GetRun(Guid runId)
    {
        var run = await _context.ProcessingRuns
            .Include(r => r.ChangePolygons)
            .FirstOrDefaultAsync(r => r.RunId == runId);

        if (run == null)
        {
            return NotFound(new { Error = $"Processing run '{runId}' not found" });
        }

        return Ok(ToDto(run));
    }

    /// <summary>
    /// List processing runs for an AOI.
    /// </summary>
    [HttpGet("runs")]
    public async Task<ActionResult<IEnumerable<ProcessingRunSummaryDto>>> ListRuns(
        [FromQuery] string? aoiId = null,
        [FromQuery] int? status = null,
        [FromQuery] int limit = 50)
    {
        var query = _context.ProcessingRuns
            .AsQueryable();

        if (!string.IsNullOrEmpty(aoiId))
        {
            query = query.Where(r => r.AoiId == aoiId);
        }

        if (status.HasValue)
        {
            query = query.Where(r => (int)r.Status == status.Value);
        }

        var runs = await query
            .OrderByDescending(r => r.CreatedAt)
            .Take(limit)
            .Select(r => new ProcessingRunSummaryDto
            {
                RunId = r.RunId,
                AoiId = r.AoiId,
                StatusName = r.Status.ToString(),
                BeforeDate = r.BeforeDate,
                AfterDate = r.AfterDate,
                AfterSceneId = r.AfterSceneId,
                CreatedAt = r.CreatedAt,
                ChangePolygonCount = r.ChangePolygons.Count,
                RiskEventCount = r.ChangePolygons.SelectMany(c => c.RiskEvents).Count()
            })
            .ToListAsync();

        return Ok(runs);
    }

    /// <summary>
    /// Update a processing run status.
    /// </summary>
    [HttpPut("runs/{runId:guid}")]
    public async Task<ActionResult<ProcessingRunDto>> UpdateRun(
        Guid runId,
        [FromBody] UpdateProcessingRunStatusRequest request)
    {
        var run = await _context.ProcessingRuns.FindAsync(runId);
        if (run == null)
        {
            return NotFound(new { Error = $"Processing run '{runId}' not found" });
        }

        // Update status
        var newStatus = (ProcessingStatus)request.Status;
        if (newStatus != run.Status)
        {
            run.Status = newStatus;

            // Set timestamps based on status
            if (newStatus == ProcessingStatus.FetchingImagery && run.StartedAt == null)
            {
                run.StartedAt = DateTime.UtcNow;
            }
            else if (newStatus is ProcessingStatus.Completed or ProcessingStatus.Failed)
            {
                run.CompletedAt = DateTime.UtcNow;
            }
        }

        // Update optional fields
        if (!string.IsNullOrEmpty(request.BeforeSceneId))
        {
            run.BeforeSceneId = request.BeforeSceneId;
        }
        if (!string.IsNullOrEmpty(request.AfterSceneId))
        {
            run.AfterSceneId = request.AfterSceneId;
        }
        if (!string.IsNullOrEmpty(request.ErrorMessage))
        {
            run.ErrorMessage = request.ErrorMessage;
        }
        if (request.Metadata != null)
        {
            run.Metadata ??= new Dictionary<string, object>();
            foreach (var (key, value) in request.Metadata)
            {
                run.Metadata[key] = value;
            }
        }

        await _context.SaveChangesAsync();

        _logger.LogInformation("Updated processing run {RunId} to status {Status}", runId, run.Status);

        return Ok(ToDto(run));
    }

    /// <summary>
    /// Delete a processing run and all associated data (cascade delete).
    /// </summary>
    [HttpDelete("runs/{runId:guid}")]
    public async Task<IActionResult> DeleteRun(Guid runId)
    {
        var run = await _context.ProcessingRuns
            .Include(r => r.ChangePolygons)
            .FirstOrDefaultAsync(r => r.RunId == runId);

        if (run == null)
        {
            return NotFound(new { Error = $"Processing run '{runId}' not found" });
        }

        // 1. Delete risk events associated with change polygons of this run
        var changePolygonIds = run.ChangePolygons.Select(c => c.ChangePolygonId).ToList();
        if (changePolygonIds.Count > 0)
        {
            var riskEvents = await _context.RiskEvents
                .Where(e => changePolygonIds.Contains(e.ChangePolygonId))
                .ToListAsync();

            _context.RiskEvents.RemoveRange(riskEvents);
            _logger.LogInformation("Deleted {Count} risk events for run {RunId}", riskEvents.Count, runId);
        }

        // 2. Delete change polygons
        _context.ChangePolygons.RemoveRange(run.ChangePolygons);
        _logger.LogInformation("Deleted {Count} change polygons for run {RunId}", run.ChangePolygons.Count, runId);

        // 3. Delete imagery from MinIO (if scene IDs exist)
        if (!string.IsNullOrEmpty(run.BeforeSceneId))
        {
            var beforePrefix = $"{run.AoiId}/{run.BeforeSceneId}/";
            try
            {
                await _storageService.DeleteFolderAsync(ImageryBucket, beforePrefix);
                _logger.LogInformation("Deleted before imagery folder {Prefix} for run {RunId}", beforePrefix, runId);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to delete before imagery folder {Prefix} for run {RunId}", beforePrefix, runId);
            }
        }

        if (!string.IsNullOrEmpty(run.AfterSceneId))
        {
            var afterPrefix = $"{run.AoiId}/{run.AfterSceneId}/";
            try
            {
                await _storageService.DeleteFolderAsync(ImageryBucket, afterPrefix);
                _logger.LogInformation("Deleted after imagery folder {Prefix} for run {RunId}", afterPrefix, runId);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to delete after imagery folder {Prefix} for run {RunId}", afterPrefix, runId);
            }
        }

        // 4. Delete the processing run record
        _context.ProcessingRuns.Remove(run);
        await _context.SaveChangesAsync();

        _logger.LogInformation("Deleted processing run {RunId}", runId);

        return NoContent();
    }

    /// <summary>
    /// Get change polygons for a processing run.
    /// </summary>
    [HttpGet("runs/{runId:guid}/changes")]
    public async Task<ActionResult<IEnumerable<ChangePolygonSummaryDto>>> GetChanges(Guid runId)
    {
        var run = await _context.ProcessingRuns.FindAsync(runId);
        if (run == null)
        {
            return NotFound(new { Error = $"Processing run '{runId}' not found" });
        }

        var changes = await _context.ChangePolygons
            .Where(c => c.RunId == runId)
            .Include(c => c.RiskEvents)
            .Select(c => new ChangePolygonSummaryDto
            {
                ChangePolygonId = c.ChangePolygonId,
                AreaSqMeters = c.AreaSqMeters,
                NdviDropMean = c.NdviDropMean,
                ChangeTypeName = c.ChangeType.ToString(),
                DetectedAt = c.DetectedAt,
                RiskEventCount = c.RiskEvents.Count
            })
            .ToListAsync();

        return Ok(changes);
    }

    /// <summary>
    /// Get change polygons as GeoJSON.
    /// </summary>
    [HttpGet("runs/{runId:guid}/changes/geojson")]
    public async Task<IActionResult> GetChangesGeoJson(Guid runId)
    {
        var run = await _context.ProcessingRuns.FindAsync(runId);
        if (run == null)
        {
            return NotFound(new { Error = $"Processing run '{runId}' not found" });
        }

        var changes = await _context.ChangePolygons
            .Where(c => c.RunId == runId)
            .ToListAsync();

        var features = changes.Select(c => new
        {
            type = "Feature",
            id = c.ChangePolygonId.ToString(),
            geometry = c.Geometry,
            properties = new Dictionary<string, object?>
            {
                ["changePolygonId"] = c.ChangePolygonId,
                ["areaSqMeters"] = c.AreaSqMeters,
                ["ndviDropMean"] = c.NdviDropMean,
                ["ndviDropMax"] = c.NdviDropMax,
                ["changeType"] = (int)c.ChangeType,
                ["changeTypeName"] = c.ChangeType.ToString(),
                ["detectedAt"] = c.DetectedAt
            }
        }).ToList();

        var featureCollection = new
        {
            type = "FeatureCollection",
            runId,
            features
        };

        return Ok(featureCollection);
    }

    /// <summary>
    /// Get risk events for a processing run.
    /// </summary>
    [HttpGet("runs/{runId:guid}/risk-events")]
    public async Task<ActionResult<IEnumerable<RiskEventSummaryDto>>> GetRiskEvents(Guid runId)
    {
        var run = await _context.ProcessingRuns.FindAsync(runId);
        if (run == null)
        {
            return NotFound(new { Error = $"Processing run '{runId}' not found" });
        }

        var events = await _context.RiskEvents
            .Where(e => e.ChangePolygon!.RunId == runId)
            .Include(e => e.Asset)
            .Select(e => new RiskEventSummaryDto
            {
                RiskEventId = e.RiskEventId,
                AssetId = e.AssetId,
                AssetName = e.Asset!.Name,
                AssetTypeName = e.Asset.AssetType.ToString(),
                RiskScore = e.RiskScore,
                RiskLevelName = e.RiskLevel.ToString(),
                DistanceMeters = e.DistanceMeters,
                CreatedAt = e.CreatedAt,
                IsAcknowledged = e.AcknowledgedAt != null
            })
            .OrderByDescending(e => e.RiskScore)
            .ToListAsync();

        return Ok(events);
    }

    private static ProcessingRunDto ToDto(ProcessingRun run)
    {
        return new ProcessingRunDto
        {
            RunId = run.RunId,
            AoiId = run.AoiId,
            Status = (int)run.Status,
            StatusName = run.Status.ToString(),
            BeforeDate = run.BeforeDate,
            AfterDate = run.AfterDate,
            BeforeSceneId = run.BeforeSceneId,
            AfterSceneId = run.AfterSceneId,
            StartedAt = run.StartedAt,
            CompletedAt = run.CompletedAt,
            ErrorMessage = run.ErrorMessage,
            Metadata = run.Metadata,
            CreatedAt = run.CreatedAt,
            ChangePolygonCount = run.ChangePolygons?.Count ?? 0,
            RiskEventCount = run.ChangePolygons?.Sum(c => c.RiskEvents?.Count ?? 0) ?? 0
        };
    }
}
