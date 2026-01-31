using GeoChangeRisk.Api.Services;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using NetTopologySuite.Geometries;

namespace GeoChangeRisk.Api.Controllers;

/// <summary>
/// Endpoints for managing change polygons.
/// </summary>
[ApiController]
[Route("api/changes")]
public class ChangesController : ControllerBase
{
    private readonly GeoChangeDbContext _context;
    private readonly ILogger<ChangesController> _logger;
    private readonly IGeometryParsingService _geometryService;

    public ChangesController(
        GeoChangeDbContext context,
        ILogger<ChangesController> logger,
        IGeometryParsingService geometryService)
    {
        _context = context;
        _logger = logger;
        _geometryService = geometryService;
    }

    /// <summary>
    /// Get a change polygon by ID.
    /// </summary>
    [HttpGet("{id:guid}")]
    public async Task<ActionResult<ChangePolygonDto>> GetById(Guid id)
    {
        var change = await _context.ChangePolygons
            .Include(c => c.RiskEvents)
            .FirstOrDefaultAsync(c => c.ChangePolygonId == id);

        if (change == null)
        {
            return NotFound(new { Error = $"Change polygon '{id}' not found" });
        }

        return Ok(ToDto(change));
    }

    /// <summary>
    /// Bulk create change polygons for a processing run.
    /// </summary>
    [HttpPost("bulk")]
    public async Task<ActionResult<BulkOperationResult>> BulkCreate([FromBody] BulkCreateChangePolygonsRequest request)
    {
        // Verify processing run exists
        var run = await _context.ProcessingRuns.FindAsync(request.RunId);
        if (run == null)
        {
            return NotFound(new { Error = $"Processing run '{request.RunId}' not found" });
        }

        var successCount = 0;
        var errors = new List<string>();
        var createdPolygons = new List<ChangePolygon>();

        foreach (var (polygonReq, index) in request.Polygons.Select((p, i) => (p, i)))
        {
            try
            {
                // Parse geometry from GeoJSON
                if (polygonReq.Geometry == null)
                {
                    errors.Add($"Polygon {index}: Geometry is null in request");
                    continue;
                }

                var geometry = _geometryService.ParseGeoJson(polygonReq.Geometry);

                // Handle both Polygon and MultiPolygon geometries
                Polygon polygon;
                if (geometry is Polygon p)
                {
                    polygon = p;
                }
                else if (geometry is MultiPolygon mp && mp.NumGeometries > 0)
                {
                    // Use the largest polygon from the MultiPolygon
                    polygon = (Polygon)mp.Geometries.OrderByDescending(g => g.Area).First();
                }
                else
                {
                    errors.Add($"Polygon {index}: Geometry must be a Polygon or MultiPolygon, got {geometry?.GeometryType ?? "null"}");
                    continue;
                }

                var change = new ChangePolygon
                {
                    RunId = request.RunId,
                    Geometry = polygon,
                    AreaSqMeters = polygonReq.AreaSqMeters,
                    NdviDropMean = polygonReq.NdviDropMean,
                    NdviDropMax = polygonReq.NdviDropMax,
                    ChangeType = (ChangeType)polygonReq.ChangeType,
                    SlopeDegreeMean = polygonReq.SlopeDegreeMean,
                    MlConfidence = polygonReq.MlConfidence,
                    MlModelVersion = polygonReq.MlModelVersion
                };

                _context.ChangePolygons.Add(change);
                createdPolygons.Add(change);
                successCount++;
            }
            catch (Exception ex)
            {
                errors.Add($"Polygon {index}: {ex.Message}");
            }
        }

        await _context.SaveChangesAsync();

        _logger.LogInformation(
            "Bulk created {SuccessCount} change polygons for run {RunId}, {FailureCount} failed",
            successCount, request.RunId, errors.Count);

        // Log first few errors for debugging
        if (errors.Count > 0)
        {
            _logger.LogWarning("First 5 change polygon errors: {Errors}", string.Join("; ", errors.Take(5)));
        }

        return Ok(new BulkOperationResult
        {
            SuccessCount = successCount,
            FailureCount = errors.Count,
            Errors = errors.Count > 0 ? errors : null,
            CreatedIds = createdPolygons.Select(p => p.ChangePolygonId).ToList()
        });
    }

    /// <summary>
    /// Get change polygons as GeoJSON by AOI.
    /// </summary>
    [HttpGet("geojson")]
    public async Task<IActionResult> GetGeoJson(
        [FromQuery] string aoiId,
        [FromQuery] Guid? runId = null)
    {
        var query = _context.ChangePolygons
            .Include(c => c.ProcessingRun)
            .Where(c => c.ProcessingRun!.AoiId == aoiId);

        if (runId.HasValue)
        {
            query = query.Where(c => c.RunId == runId.Value);
        }

        var changes = await query.ToListAsync();

        var features = changes.Select(c => new
        {
            type = "Feature",
            id = c.ChangePolygonId.ToString(),
            geometry = c.Geometry,
            properties = new Dictionary<string, object?>
            {
                ["changePolygonId"] = c.ChangePolygonId,
                ["runId"] = c.RunId,
                ["areaSqMeters"] = c.AreaSqMeters,
                ["ndviDropMean"] = c.NdviDropMean,
                ["ndviDropMax"] = c.NdviDropMax,
                ["changeType"] = (int)c.ChangeType,
                ["changeTypeName"] = c.ChangeType.ToString(),
                ["slopeDegreeMean"] = c.SlopeDegreeMean,
                ["detectedAt"] = c.DetectedAt
            }
        }).ToList();

        var featureCollection = new
        {
            type = "FeatureCollection",
            aoiId,
            runId,
            features
        };

        return Ok(featureCollection);
    }

    private static ChangePolygonDto ToDto(ChangePolygon change)
    {
        return new ChangePolygonDto
        {
            ChangePolygonId = change.ChangePolygonId,
            RunId = change.RunId,
            Geometry = change.Geometry,
            AreaSqMeters = change.AreaSqMeters,
            NdviDropMean = change.NdviDropMean,
            NdviDropMax = change.NdviDropMax,
            ChangeType = (int)change.ChangeType,
            ChangeTypeName = change.ChangeType.ToString(),
            SlopeDegreeMean = change.SlopeDegreeMean,
            DetectedAt = change.DetectedAt,
            MlConfidence = change.MlConfidence,
            MlModelVersion = change.MlModelVersion,
            RiskEventCount = change.RiskEvents?.Count ?? 0
        };
    }
}
