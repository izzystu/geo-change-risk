using GeoChangeRisk.Api.Services;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Controllers;

/// <summary>
/// Endpoints for managing Areas of Interest.
/// </summary>
[ApiController]
[Route("api/areas-of-interest")]
public class AreasOfInterestController : ControllerBase
{
    private readonly GeoChangeDbContext _context;
    private readonly ILogger<AreasOfInterestController> _logger;
    private readonly IGeometryParsingService _geometryService;

    public AreasOfInterestController(
        GeoChangeDbContext context,
        ILogger<AreasOfInterestController> logger,
        IGeometryParsingService geometryService)
    {
        _context = context;
        _logger = logger;
        _geometryService = geometryService;
    }

    /// <summary>
    /// List all Areas of Interest.
    /// </summary>
    [HttpGet]
    public async Task<ActionResult<IEnumerable<AreaOfInterestSummaryDto>>> GetAll()
    {
        var aois = await _context.AreasOfInterest
            .Select(a => new AreaOfInterestSummaryDto
            {
                AoiId = a.AoiId,
                Name = a.Name,
                AssetCount = a.Assets.Count
            })
            .ToListAsync();

        return Ok(aois);
    }

    /// <summary>
    /// Get a single Area of Interest by ID.
    /// </summary>
    [HttpGet("{id}")]
    public async Task<ActionResult<AreaOfInterestDto>> GetById(string id)
    {
        var aoi = await _context.AreasOfInterest
            .Include(a => a.Assets)
            .FirstOrDefaultAsync(a => a.AoiId == id);

        if (aoi == null)
        {
            return NotFound(new { Error = $"Area of Interest '{id}' not found" });
        }

        var envelope = aoi.BoundingBox.EnvelopeInternal;
        return Ok(new AreaOfInterestDto
        {
            AoiId = aoi.AoiId,
            Name = aoi.Name,
            Description = aoi.Description,
            BoundingBox = [envelope.MinX, envelope.MinY, envelope.MaxX, envelope.MaxY],
            Center = [aoi.CenterPoint.X, aoi.CenterPoint.Y],
            AssetCount = aoi.Assets.Count,
            CreatedAt = aoi.CreatedAt
        });
    }

    /// <summary>
    /// Get assets for an Area of Interest.
    /// </summary>
    [HttpGet("{id}/assets")]
    public async Task<ActionResult<IEnumerable<AssetSummaryDto>>> GetAssets(
        string id,
        [FromQuery] int? assetType = null)
    {
        var aoi = await _context.AreasOfInterest.FindAsync(id);
        if (aoi == null)
        {
            return NotFound(new { Error = $"Area of Interest '{id}' not found" });
        }

        var query = _context.Assets.Where(a => a.AoiId == id);

        if (assetType.HasValue)
        {
            query = query.Where(a => (int)a.AssetType == assetType.Value);
        }

        var assets = await query
            .Select(a => new AssetSummaryDto
            {
                AssetId = a.AssetId,
                Name = a.Name,
                AssetTypeName = a.AssetType.ToString(),
                CriticalityName = a.Criticality.ToString(),
                GeometryType = a.Geometry.GeometryType
            })
            .ToListAsync();

        return Ok(assets);
    }

    /// <summary>
    /// Get Area of Interest with assets as GeoJSON FeatureCollection.
    /// </summary>
    [HttpGet("{id}/geojson")]
    public async Task<IActionResult> GetGeoJson(
        string id,
        [FromQuery] int? assetType = null)
    {
        var aoi = await _context.AreasOfInterest.FindAsync(id);
        if (aoi == null)
        {
            return NotFound(new { Error = $"Area of Interest '{id}' not found" });
        }

        var query = _context.Assets.Where(a => a.AoiId == id);

        if (assetType.HasValue)
        {
            query = query.Where(a => (int)a.AssetType == assetType.Value);
        }

        var assets = await query.ToListAsync();

        // Build GeoJSON FeatureCollection
        var features = assets.Select(a => new
        {
            type = "Feature",
            id = a.AssetId,
            geometry = a.Geometry,
            properties = new Dictionary<string, object?>
            {
                ["assetId"] = a.AssetId,
                ["name"] = a.Name,
                ["assetType"] = (int)a.AssetType,
                ["assetTypeName"] = a.AssetType.ToString(),
                ["criticality"] = (int)a.Criticality,
                ["criticalityName"] = a.Criticality.ToString(),
                ["sourceDataset"] = a.SourceDataset
            }
        }).ToList();

        var featureCollection = new
        {
            type = "FeatureCollection",
            name = aoi.Name,
            aoiId = aoi.AoiId,
            features
        };

        return Ok(featureCollection);
    }

    /// <summary>
    /// Create a new Area of Interest.
    /// </summary>
    [HttpPost]
    public async Task<ActionResult<AreaOfInterestDto>> Create([FromBody] CreateAreaOfInterestRequest request)
    {
        // Check if AOI already exists
        if (await _context.AreasOfInterest.AnyAsync(a => a.AoiId == request.AoiId))
        {
            return Conflict(new { Error = $"Area of Interest '{request.AoiId}' already exists" });
        }

        // Create bounding box polygon from [minLon, minLat, maxLon, maxLat]
        var bbox = request.BoundingBox;
        if (bbox.Length != 4)
        {
            return BadRequest(new { Error = "BoundingBox must be [minLon, minLat, maxLon, maxLat]" });
        }

        var boundingBox = _geometryService.CreateBoundingBox(bbox[0], bbox[1], bbox[2], bbox[3]);

        // Calculate center if not provided
        var center = request.Center ?? [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2];
        var centerPoint = _geometryService.CreatePoint(center[0], center[1]);

        var aoi = new AreaOfInterest
        {
            AoiId = request.AoiId,
            Name = request.Name,
            Description = request.Description,
            BoundingBox = boundingBox,
            CenterPoint = centerPoint
        };

        _context.AreasOfInterest.Add(aoi);
        await _context.SaveChangesAsync();

        _logger.LogInformation("Created Area of Interest: {AoiId}", aoi.AoiId);

        var envelope = aoi.BoundingBox.EnvelopeInternal;
        return CreatedAtAction(nameof(GetById), new { id = aoi.AoiId }, new AreaOfInterestDto
        {
            AoiId = aoi.AoiId,
            Name = aoi.Name,
            Description = aoi.Description,
            BoundingBox = [envelope.MinX, envelope.MinY, envelope.MaxX, envelope.MaxY],
            Center = [aoi.CenterPoint.X, aoi.CenterPoint.Y],
            AssetCount = 0,
            CreatedAt = aoi.CreatedAt
        });
    }

    /// <summary>
    /// Delete an Area of Interest and all its assets.
    /// </summary>
    [HttpDelete("{id}")]
    public async Task<IActionResult> Delete(string id)
    {
        var aoi = await _context.AreasOfInterest.FindAsync(id);
        if (aoi == null)
        {
            return NotFound(new { Error = $"Area of Interest '{id}' not found" });
        }

        _context.AreasOfInterest.Remove(aoi);
        await _context.SaveChangesAsync();

        _logger.LogInformation("Deleted Area of Interest: {AoiId}", id);

        return NoContent();
    }

    /// <summary>
    /// Update AOI scheduling configuration.
    /// </summary>
    [HttpPut("{id}/schedule")]
    public async Task<ActionResult<AreaOfInterestDto>> UpdateSchedule(
        string id,
        [FromBody] UpdateAoiScheduleRequest request)
    {
        var aoi = await _context.AreasOfInterest
            .Include(a => a.Assets)
            .FirstOrDefaultAsync(a => a.AoiId == id);

        if (aoi == null)
        {
            return NotFound(new { Error = $"Area of Interest '{id}' not found" });
        }

        // Update scheduling fields
        if (request.ProcessingSchedule != null)
        {
            aoi.ProcessingSchedule = string.IsNullOrEmpty(request.ProcessingSchedule)
                ? null
                : request.ProcessingSchedule;
        }
        if (request.ProcessingEnabled.HasValue)
        {
            aoi.ProcessingEnabled = request.ProcessingEnabled.Value;
        }
        if (request.DefaultLookbackDays.HasValue)
        {
            aoi.DefaultLookbackDays = request.DefaultLookbackDays.Value;
        }

        aoi.UpdatedAt = DateTime.UtcNow;
        await _context.SaveChangesAsync();

        _logger.LogInformation(
            "Updated scheduling for AOI {AoiId}: schedule={Schedule}, enabled={Enabled}",
            id, aoi.ProcessingSchedule, aoi.ProcessingEnabled);

        var envelope = aoi.BoundingBox.EnvelopeInternal;
        return Ok(new AreaOfInterestDto
        {
            AoiId = aoi.AoiId,
            Name = aoi.Name,
            Description = aoi.Description,
            BoundingBox = [envelope.MinX, envelope.MinY, envelope.MaxX, envelope.MaxY],
            Center = [aoi.CenterPoint.X, aoi.CenterPoint.Y],
            AssetCount = aoi.Assets.Count,
            CreatedAt = aoi.CreatedAt,
            ProcessingSchedule = aoi.ProcessingSchedule,
            ProcessingEnabled = aoi.ProcessingEnabled,
            LastProcessedAt = aoi.LastProcessedAt,
            DefaultLookbackDays = aoi.DefaultLookbackDays
        });
    }

    /// <summary>
    /// Get AOIs with scheduled processing enabled.
    /// </summary>
    [HttpGet("scheduled")]
    public async Task<ActionResult<IEnumerable<AreaOfInterestSummaryDto>>> GetScheduled()
    {
        var aois = await _context.AreasOfInterest
            .Where(a => a.ProcessingEnabled && a.ProcessingSchedule != null)
            .Select(a => new AreaOfInterestSummaryDto
            {
                AoiId = a.AoiId,
                Name = a.Name,
                AssetCount = a.Assets.Count
            })
            .ToListAsync();

        return Ok(aois);
    }
}
