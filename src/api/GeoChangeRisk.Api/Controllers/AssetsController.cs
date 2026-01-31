using GeoChangeRisk.Api.Services;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using NetTopologySuite.Geometries;

namespace GeoChangeRisk.Api.Controllers;

/// <summary>
/// Endpoints for managing Assets.
/// </summary>
[ApiController]
[Route("api/[controller]")]
public class AssetsController : ControllerBase
{
    private readonly GeoChangeDbContext _context;
    private readonly ILogger<AssetsController> _logger;
    private readonly IGeometryParsingService _geometryService;

    public AssetsController(
        GeoChangeDbContext context,
        ILogger<AssetsController> logger,
        IGeometryParsingService geometryService)
    {
        _context = context;
        _logger = logger;
        _geometryService = geometryService;
    }

    /// <summary>
    /// List assets with optional filtering.
    /// </summary>
    [HttpGet]
    public async Task<ActionResult<IEnumerable<AssetSummaryDto>>> GetAll(
        [FromQuery] string? aoiId = null,
        [FromQuery] int? assetType = null,
        [FromQuery] int? criticality = null,
        [FromQuery] int skip = 0,
        [FromQuery] int take = 100)
    {
        var query = _context.Assets.AsQueryable();

        if (!string.IsNullOrEmpty(aoiId))
        {
            query = query.Where(a => a.AoiId == aoiId);
        }

        if (assetType.HasValue)
        {
            query = query.Where(a => (int)a.AssetType == assetType.Value);
        }

        if (criticality.HasValue)
        {
            query = query.Where(a => (int)a.Criticality == criticality.Value);
        }

        var assets = await query
            .OrderBy(a => a.AssetId)
            .Skip(skip)
            .Take(Math.Min(take, 1000)) // Cap at 1000
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
    /// Get a single asset by ID.
    /// </summary>
    [HttpGet("{id}")]
    public async Task<ActionResult<AssetDto>> GetById(string id)
    {
        var asset = await _context.Assets.FindAsync(id);

        if (asset == null)
        {
            return NotFound(new { Error = $"Asset '{id}' not found" });
        }

        return Ok(MapToDto(asset));
    }

    /// <summary>
    /// Create a new asset.
    /// </summary>
    [HttpPost]
    public async Task<ActionResult<AssetDto>> Create([FromBody] CreateAssetRequest request)
    {
        // Validate AOI exists
        var aoi = await _context.AreasOfInterest.FindAsync(request.AoiId);
        if (aoi == null)
        {
            return BadRequest(new { Error = $"Area of Interest '{request.AoiId}' not found" });
        }

        // Generate ID if not provided
        var assetId = request.AssetId ?? $"{request.AoiId}-{Guid.NewGuid():N}"[..36];

        // Check if asset already exists
        if (await _context.Assets.AnyAsync(a => a.AssetId == assetId))
        {
            return Conflict(new { Error = $"Asset '{assetId}' already exists" });
        }

        // Parse geometry from GeoJSON
        Geometry geometry;
        try
        {
            geometry = _geometryService.ParseGeoJson(request.Geometry);
        }
        catch (Exception ex)
        {
            return BadRequest(new { Error = $"Invalid geometry: {ex.Message}" });
        }

        var asset = new Asset
        {
            AssetId = assetId,
            AoiId = request.AoiId,
            Name = request.Name,
            AssetType = (AssetType)request.AssetType,
            Criticality = (Criticality)request.Criticality,
            Geometry = geometry,
            Properties = request.Properties,
            SourceDataset = request.SourceDataset,
            SourceFeatureId = request.SourceFeatureId
        };

        _context.Assets.Add(asset);
        await _context.SaveChangesAsync();

        _logger.LogInformation("Created asset: {AssetId} in AOI: {AoiId}", asset.AssetId, asset.AoiId);

        return CreatedAtAction(nameof(GetById), new { id = asset.AssetId }, MapToDto(asset));
    }

    /// <summary>
    /// Bulk create assets.
    /// </summary>
    [HttpPost("bulk")]
    public async Task<ActionResult<BulkOperationResult>> BulkCreate([FromBody] BulkCreateAssetsRequest request)
    {
        // Validate AOI exists
        var aoi = await _context.AreasOfInterest.FindAsync(request.AoiId);
        if (aoi == null)
        {
            return BadRequest(new { Error = $"Area of Interest '{request.AoiId}' not found" });
        }

        var result = new BulkOperationResult
        {
            SuccessCount = 0,
            FailureCount = 0,
            Errors = new List<string>()
        };

        var assetsToAdd = new List<Asset>();
        var existingIds = (await _context.Assets
            .Where(a => a.AoiId == request.AoiId)
            .Select(a => a.AssetId)
            .ToListAsync())
            .ToHashSet();

        foreach (var assetRequest in request.Assets)
        {
            try
            {
                var assetId = assetRequest.AssetId ?? $"{request.AoiId}-{Guid.NewGuid():N}"[..36];

                if (existingIds.Contains(assetId))
                {
                    result.FailureCount++;
                    result.Errors.Add($"Asset '{assetId}' already exists");
                    continue;
                }

                // Parse geometry
                var geometry = _geometryService.ParseGeoJson(assetRequest.Geometry);

                var asset = new Asset
                {
                    AssetId = assetId,
                    AoiId = request.AoiId,
                    Name = assetRequest.Name,
                    AssetType = (AssetType)assetRequest.AssetType,
                    Criticality = (Criticality)assetRequest.Criticality,
                    Geometry = geometry,
                    Properties = assetRequest.Properties,
                    SourceDataset = assetRequest.SourceDataset ?? request.SourceDataset,
                    SourceFeatureId = assetRequest.SourceFeatureId
                };

                assetsToAdd.Add(asset);
                existingIds.Add(assetId);
                result.SuccessCount++;
            }
            catch (Exception ex)
            {
                result.FailureCount++;
                result.Errors.Add($"Failed to create asset '{assetRequest.AssetId ?? "unnamed"}': {ex.Message}");
            }
        }

        if (assetsToAdd.Count > 0)
        {
            _context.Assets.AddRange(assetsToAdd);
            await _context.SaveChangesAsync();
        }

        _logger.LogInformation(
            "Bulk created {SuccessCount} assets in AOI: {AoiId} ({FailureCount} failures)",
            result.SuccessCount, request.AoiId, result.FailureCount);

        // Clear errors if empty
        if (result.Errors.Count == 0)
        {
            result.Errors = null;
        }

        return Ok(result);
    }

    /// <summary>
    /// Get assets as GeoJSON FeatureCollection.
    /// </summary>
    [HttpGet("geojson")]
    public async Task<ActionResult> GetGeoJson(
        [FromQuery] string aoiId,
        [FromQuery] string? assetTypes = null)
    {
        var query = _context.Assets.Where(a => a.AoiId == aoiId);

        // Filter by asset types if provided
        if (!string.IsNullOrEmpty(assetTypes))
        {
            var typeIds = assetTypes.Split(',')
                .Select(t => int.TryParse(t.Trim(), out var id) ? id : -1)
                .Where(id => id >= 0)
                .ToList();

            if (typeIds.Count > 0)
            {
                query = query.Where(a => typeIds.Contains((int)a.AssetType));
            }
        }

        var assets = await query
            .Take(10000) // Limit for performance
            .ToListAsync();

        // Build GeoJSON FeatureCollection
        var features = assets.Select(a => new
        {
            type = "Feature",
            id = a.AssetId,
            geometry = a.Geometry,
            properties = new
            {
                name = a.Name,
                assetType = (int)a.AssetType,
                assetTypeName = a.AssetType.ToString(),
                criticality = (int)a.Criticality,
                criticalityName = a.Criticality.ToString(),
                sourceDataset = a.SourceDataset
            }
        });

        var featureCollection = new
        {
            type = "FeatureCollection",
            features = features
        };

        return Ok(featureCollection);
    }

    /// <summary>
    /// Delete an asset.
    /// </summary>
    [HttpDelete("{id}")]
    public async Task<IActionResult> Delete(string id)
    {
        var asset = await _context.Assets.FindAsync(id);
        if (asset == null)
        {
            return NotFound(new { Error = $"Asset '{id}' not found" });
        }

        _context.Assets.Remove(asset);
        await _context.SaveChangesAsync();

        _logger.LogInformation("Deleted asset: {AssetId}", id);

        return NoContent();
    }

    /// <summary>
    /// Delete all assets for an AOI (optionally filtered by type).
    /// </summary>
    [HttpDelete]
    public async Task<ActionResult<BulkOperationResult>> DeleteByAoi(
        [FromQuery] string aoiId,
        [FromQuery] int? assetType = null)
    {
        var query = _context.Assets.Where(a => a.AoiId == aoiId);

        if (assetType.HasValue)
        {
            query = query.Where(a => (int)a.AssetType == assetType.Value);
        }

        var count = await query.ExecuteDeleteAsync();

        _logger.LogInformation(
            "Deleted {Count} assets from AOI: {AoiId} (type filter: {AssetType})",
            count, aoiId, assetType?.ToString() ?? "none");

        return Ok(new BulkOperationResult
        {
            SuccessCount = count,
            FailureCount = 0
        });
    }

    private static AssetDto MapToDto(Asset asset)
    {
        return new AssetDto
        {
            AssetId = asset.AssetId,
            AoiId = asset.AoiId,
            Name = asset.Name,
            AssetType = (int)asset.AssetType,
            AssetTypeName = asset.AssetType.ToString(),
            Criticality = (int)asset.Criticality,
            CriticalityName = asset.Criticality.ToString(),
            Geometry = asset.Geometry,
            Properties = asset.Properties,
            SourceDataset = asset.SourceDataset,
            CreatedAt = asset.CreatedAt
        };
    }
}
