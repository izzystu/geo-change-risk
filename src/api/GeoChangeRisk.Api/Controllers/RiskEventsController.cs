using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Controllers;

/// <summary>
/// Endpoints for managing risk events.
/// </summary>
[ApiController]
[Route("api/risk-events")]
public class RiskEventsController : ControllerBase
{
    private readonly GeoChangeDbContext _context;
    private readonly ILogger<RiskEventsController> _logger;

    public RiskEventsController(GeoChangeDbContext context, ILogger<RiskEventsController> logger)
    {
        _context = context;
        _logger = logger;
    }

    /// <summary>
    /// Get a risk event by ID.
    /// </summary>
    [HttpGet("{id:guid}")]
    public async Task<ActionResult<RiskEventDto>> GetById(Guid id)
    {
        var riskEvent = await _context.RiskEvents
            .Include(e => e.ChangePolygon)
                .ThenInclude(c => c!.ProcessingRun)
            .Include(e => e.Asset)
            .FirstOrDefaultAsync(e => e.RiskEventId == id);

        if (riskEvent == null)
        {
            return NotFound(new { Error = $"Risk event '{id}' not found" });
        }

        return Ok(ToDto(riskEvent));
    }

    /// <summary>
    /// List risk events with filters.
    /// </summary>
    [HttpGet]
    public async Task<ActionResult<IEnumerable<RiskEventSummaryDto>>> List(
        [FromQuery] string? aoiId = null,
        [FromQuery] int? minScore = null,
        [FromQuery] int? riskLevel = null,
        [FromQuery] string? assetId = null,
        [FromQuery] Guid? runId = null,
        [FromQuery] bool? isAcknowledged = null,
        [FromQuery] bool? isDismissed = false,
        [FromQuery] int limit = 100,
        [FromQuery] int offset = 0)
    {
        var query = _context.RiskEvents
            .Include(e => e.ChangePolygon)
                .ThenInclude(c => c!.ProcessingRun)
            .Include(e => e.Asset)
            .AsQueryable();

        // Apply filters
        if (!string.IsNullOrEmpty(aoiId))
        {
            query = query.Where(e => e.ChangePolygon!.ProcessingRun!.AoiId == aoiId);
        }
        if (minScore.HasValue)
        {
            query = query.Where(e => e.RiskScore >= minScore.Value);
        }
        if (riskLevel.HasValue)
        {
            query = query.Where(e => (int)e.RiskLevel == riskLevel.Value);
        }
        if (!string.IsNullOrEmpty(assetId))
        {
            query = query.Where(e => e.AssetId == assetId);
        }
        if (runId.HasValue)
        {
            query = query.Where(e => e.ChangePolygon!.RunId == runId.Value);
        }
        if (isAcknowledged.HasValue)
        {
            query = isAcknowledged.Value
                ? query.Where(e => e.AcknowledgedAt != null)
                : query.Where(e => e.AcknowledgedAt == null);
        }
        if (isDismissed.HasValue)
        {
            query = isDismissed.Value
                ? query.Where(e => e.DismissedAt != null)
                : query.Where(e => e.DismissedAt == null);
        }

        var events = await query
            .OrderByDescending(e => e.RiskScore)
            .ThenByDescending(e => e.CreatedAt)
            .Skip(offset)
            .Take(limit)
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
                IsAcknowledged = e.AcknowledgedAt != null,
                IsDismissed = e.DismissedAt != null
            })
            .ToListAsync();

        return Ok(events);
    }

    /// <summary>
    /// Get unacknowledged risk events.
    /// </summary>
    [HttpGet("unacknowledged")]
    public async Task<ActionResult<IEnumerable<RiskEventSummaryDto>>> GetUnacknowledged(
        [FromQuery] string? aoiId = null,
        [FromQuery] int? minLevel = null,
        [FromQuery] int limit = 50)
    {
        var query = _context.RiskEvents
            .Include(e => e.ChangePolygon)
                .ThenInclude(c => c!.ProcessingRun)
            .Include(e => e.Asset)
            .Where(e => e.AcknowledgedAt == null);

        if (!string.IsNullOrEmpty(aoiId))
        {
            query = query.Where(e => e.ChangePolygon!.ProcessingRun!.AoiId == aoiId);
        }
        if (minLevel.HasValue)
        {
            query = query.Where(e => (int)e.RiskLevel >= minLevel.Value);
        }

        var events = await query
            .OrderByDescending(e => e.RiskScore)
            .Take(limit)
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
                IsAcknowledged = false,
                IsDismissed = e.DismissedAt != null
            })
            .ToListAsync();

        return Ok(events);
    }

    /// <summary>
    /// Get risk events by asset ID.
    /// </summary>
    [HttpGet("by-asset/{assetId}")]
    public async Task<ActionResult<IEnumerable<RiskEventSummaryDto>>> GetByAsset(
        string assetId,
        [FromQuery] int limit = 50)
    {
        var asset = await _context.Assets.FindAsync(assetId);
        if (asset == null)
        {
            return NotFound(new { Error = $"Asset '{assetId}' not found" });
        }

        var events = await _context.RiskEvents
            .Where(e => e.AssetId == assetId)
            .OrderByDescending(e => e.CreatedAt)
            .Take(limit)
            .Select(e => new RiskEventSummaryDto
            {
                RiskEventId = e.RiskEventId,
                AssetId = e.AssetId,
                AssetName = asset.Name,
                AssetTypeName = asset.AssetType.ToString(),
                RiskScore = e.RiskScore,
                RiskLevelName = e.RiskLevel.ToString(),
                DistanceMeters = e.DistanceMeters,
                CreatedAt = e.CreatedAt,
                IsAcknowledged = e.AcknowledgedAt != null,
                IsDismissed = e.DismissedAt != null
            })
            .ToListAsync();

        return Ok(events);
    }

    /// <summary>
    /// Bulk create risk events.
    /// </summary>
    [HttpPost("bulk")]
    public async Task<ActionResult<BulkOperationResult>> BulkCreate([FromBody] BulkCreateRiskEventsRequest request)
    {
        var successCount = 0;
        var errors = new List<string>();

        // Pre-load valid IDs for efficient validation (instead of querying per-event)
        var requestedPolygonIds = request.Events
            .Where(e => e.ChangePolygonId.HasValue)
            .Select(e => e.ChangePolygonId!.Value)
            .Distinct()
            .ToHashSet();

        var requestedAssetIds = request.Events
            .Select(e => e.AssetId)
            .Distinct()
            .ToHashSet();

        var validPolygonIds = (await _context.ChangePolygons
            .Where(c => requestedPolygonIds.Contains(c.ChangePolygonId))
            .Select(c => c.ChangePolygonId)
            .ToListAsync())
            .ToHashSet();

        var validAssetIds = (await _context.Assets
            .Where(a => requestedAssetIds.Contains(a.AssetId))
            .Select(a => a.AssetId)
            .ToListAsync())
            .ToHashSet();

        _logger.LogInformation(
            "Bulk create: {TotalEvents} events, {ValidPolygons}/{RequestedPolygons} polygons valid, {ValidAssets}/{RequestedAssets} assets valid",
            request.Events.Count, validPolygonIds.Count, requestedPolygonIds.Count, validAssetIds.Count, requestedAssetIds.Count);

        var riskEvents = new List<RiskEvent>();

        foreach (var (eventReq, index) in request.Events.Select((e, i) => (e, i)))
        {
            // Skip events without a polygon ID
            if (!eventReq.ChangePolygonId.HasValue)
            {
                if (errors.Count < 100) errors.Add($"Event {index}: Missing change polygon ID");
                continue;
            }

            // Validate polygon exists
            if (!validPolygonIds.Contains(eventReq.ChangePolygonId.Value))
            {
                if (errors.Count < 100) errors.Add($"Event {index}: Change polygon not found");
                continue;
            }

            // Validate asset exists
            if (!validAssetIds.Contains(eventReq.AssetId))
            {
                if (errors.Count < 100) errors.Add($"Event {index}: Asset not found");
                continue;
            }

            riskEvents.Add(new RiskEvent
            {
                ChangePolygonId = eventReq.ChangePolygonId.Value,
                AssetId = eventReq.AssetId,
                DistanceMeters = eventReq.DistanceMeters,
                RiskScore = eventReq.RiskScore,
                RiskLevel = (RiskLevel)eventReq.RiskLevel,
                ScoringFactors = eventReq.ScoringFactors
            });
        }

        // Batch insert
        if (riskEvents.Count > 0)
        {
            _context.RiskEvents.AddRange(riskEvents);
            await _context.SaveChangesAsync();
            successCount = riskEvents.Count;
        }

        _logger.LogInformation("Bulk created {SuccessCount} risk events, {FailureCount} failed", successCount, errors.Count);

        // Log first few errors for debugging
        if (errors.Count > 0)
        {
            _logger.LogWarning("First 5 risk event errors: {Errors}", string.Join("; ", errors.Take(5)));
        }

        return Ok(new BulkOperationResult
        {
            SuccessCount = successCount,
            FailureCount = errors.Count,
            Errors = errors.Count > 0 ? errors : null
        });
    }

    /// <summary>
    /// Acknowledge a risk event.
    /// </summary>
    [HttpPost("{id:guid}/acknowledge")]
    public async Task<ActionResult<RiskEventDto>> Acknowledge(
        Guid id,
        [FromBody] AcknowledgeRiskEventRequest request)
    {
        var riskEvent = await _context.RiskEvents
            .Include(e => e.ChangePolygon)
                .ThenInclude(c => c!.ProcessingRun)
            .Include(e => e.Asset)
            .FirstOrDefaultAsync(e => e.RiskEventId == id);

        if (riskEvent == null)
        {
            return NotFound(new { Error = $"Risk event '{id}' not found" });
        }

        if (riskEvent.AcknowledgedAt != null)
        {
            return BadRequest(new { Error = "Risk event has already been acknowledged" });
        }

        riskEvent.AcknowledgedAt = DateTime.UtcNow;
        riskEvent.AcknowledgedBy = request.AcknowledgedBy;

        // Store notes in scoring factors if provided
        if (!string.IsNullOrEmpty(request.Notes))
        {
            riskEvent.ScoringFactors ??= new Dictionary<string, object>();
            riskEvent.ScoringFactors["acknowledgmentNotes"] = request.Notes;
        }

        await _context.SaveChangesAsync();

        _logger.LogInformation(
            "Risk event {EventId} acknowledged by {User}",
            id, request.AcknowledgedBy);

        return Ok(ToDto(riskEvent));
    }

    /// <summary>
    /// Dismiss a risk event (soft-delete).
    /// </summary>
    [HttpPost("{id:guid}/dismiss")]
    public async Task<ActionResult<RiskEventDto>> Dismiss(
        Guid id,
        [FromBody] DismissRiskEventRequest request)
    {
        var riskEvent = await _context.RiskEvents
            .Include(e => e.ChangePolygon)
                .ThenInclude(c => c!.ProcessingRun)
            .Include(e => e.Asset)
            .FirstOrDefaultAsync(e => e.RiskEventId == id);

        if (riskEvent == null)
        {
            return NotFound(new { Error = $"Risk event '{id}' not found" });
        }

        if (riskEvent.DismissedAt != null)
        {
            return BadRequest(new { Error = "Risk event has already been dismissed" });
        }

        riskEvent.DismissedAt = DateTime.UtcNow;
        riskEvent.DismissedBy = request.DismissedBy;

        if (!string.IsNullOrEmpty(request.Reason))
        {
            riskEvent.ScoringFactors ??= new Dictionary<string, object>();
            riskEvent.ScoringFactors["dismissalReason"] = request.Reason;
        }

        await _context.SaveChangesAsync();

        _logger.LogInformation(
            "Risk event {EventId} dismissed by {User}",
            id, request.DismissedBy);

        return Ok(ToDto(riskEvent));
    }

    /// <summary>
    /// Get risk event statistics for an AOI.
    /// </summary>
    [HttpGet("stats")]
    public async Task<ActionResult<object>> GetStats([FromQuery] string aoiId)
    {
        var query = _context.RiskEvents
            .Include(e => e.ChangePolygon)
                .ThenInclude(c => c!.ProcessingRun)
            .Where(e => e.ChangePolygon!.ProcessingRun!.AoiId == aoiId);

        var total = await query.CountAsync();
        var unacknowledged = await query.Where(e => e.AcknowledgedAt == null).CountAsync();
        var byLevel = await query
            .GroupBy(e => e.RiskLevel)
            .Select(g => new { Level = g.Key.ToString(), Count = g.Count() })
            .ToListAsync();

        return Ok(new
        {
            aoiId,
            totalEvents = total,
            unacknowledgedEvents = unacknowledged,
            byRiskLevel = byLevel.ToDictionary(x => x.Level, x => x.Count)
        });
    }

    private static RiskEventDto ToDto(RiskEvent riskEvent)
    {
        return new RiskEventDto
        {
            RiskEventId = riskEvent.RiskEventId,
            ChangePolygonId = riskEvent.ChangePolygonId,
            AssetId = riskEvent.AssetId,
            AssetName = riskEvent.Asset?.Name ?? "Unknown",
            AssetTypeName = riskEvent.Asset?.AssetType.ToString() ?? "Unknown",
            DistanceMeters = riskEvent.DistanceMeters,
            RiskScore = riskEvent.RiskScore,
            RiskLevel = (int)riskEvent.RiskLevel,
            RiskLevelName = riskEvent.RiskLevel.ToString(),
            ScoringFactors = riskEvent.ScoringFactors,
            CreatedAt = riskEvent.CreatedAt,
            NotificationSentAt = riskEvent.NotificationSentAt,
            AcknowledgedAt = riskEvent.AcknowledgedAt,
            AcknowledgedBy = riskEvent.AcknowledgedBy,
            DismissedAt = riskEvent.DismissedAt,
            DismissedBy = riskEvent.DismissedBy,
            AoiId = riskEvent.ChangePolygon?.ProcessingRun?.AoiId,
            ChangeGeometry = riskEvent.ChangePolygon?.Geometry,
            AssetGeometry = riskEvent.Asset?.Geometry
        };
    }
}
