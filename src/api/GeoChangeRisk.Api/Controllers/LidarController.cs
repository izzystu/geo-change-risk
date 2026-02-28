using System.Text.Json;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Controllers;

/// <summary>
/// Endpoints for LIDAR terrain data associated with change polygons.
/// </summary>
[ApiController]
[Route("api/lidar")]
public class LidarController : ControllerBase
{
    private readonly GeoChangeDbContext _context;
    private readonly IObjectStorageService _storageService;
    private readonly IConfiguration _configuration;
    private readonly ILogger<LidarController> _logger;

    public LidarController(
        GeoChangeDbContext context,
        IObjectStorageService storageService,
        IConfiguration configuration,
        ILogger<LidarController> logger)
    {
        _context = context;
        _storageService = storageService;
        _configuration = configuration;
        _logger = logger;
    }

    /// <summary>
    /// Get LIDAR terrain data for a specific change polygon.
    /// Returns presigned URLs for DTM/DSM/CHM products generated during processing.
    /// </summary>
    [HttpGet("by-polygon/{changePolygonId}")]
    public async Task<ActionResult<LidarSourceDetailDto>> GetByPolygon(string changePolygonId)
    {
        if (!Guid.TryParse(changePolygonId, out var polygonGuid))
        {
            return BadRequest(new { Error = "Invalid change polygon ID format" });
        }

        // Look up the change polygon to find its AOI
        var polygon = await _context.ChangePolygons
            .Include(cp => cp.ProcessingRun)
            .FirstOrDefaultAsync(cp => cp.ChangePolygonId == polygonGuid);

        if (polygon?.ProcessingRun == null)
        {
            return NotFound(new { Error = $"Change polygon '{changePolygonId}' not found" });
        }

        var aoiId = polygon.ProcessingRun.AoiId;
        var sourceId = $"polygon-{changePolygonId}";
        var bucket = _configuration["Storage:BucketLidar"]
            ?? _configuration["MinIO:BucketLidar"] ?? "georisk-lidar";
        var prefix = $"{aoiId}/{sourceId}/";

        try
        {
            var objects = await _storageService.ListObjectsAsync(bucket, prefix);

            if (objects.Count == 0)
            {
                return NotFound(new { Error = $"No LIDAR terrain data for polygon '{changePolygonId}'" });
            }

            // Generate presigned URLs for each file
            var files = new List<LidarFileWithUrlDto>();
            string? dtmUrl = null;
            string? dsmUrl = null;
            string? chmUrl = null;
            LidarMetadataDto? metadata = null;

            foreach (var obj in objects)
            {
                var fileName = Path.GetFileName(obj.ObjectPath);
                var url = await _storageService.GetPresignedUrlAsync(bucket, obj.ObjectPath, 3600);

                files.Add(new LidarFileWithUrlDto
                {
                    FileName = fileName,
                    ObjectPath = obj.ObjectPath,
                    Size = obj.Size,
                    LastModified = obj.LastModified,
                    PresignedUrl = url
                });

                switch (fileName.ToLowerInvariant())
                {
                    case "dtm.tif": dtmUrl = url; break;
                    case "dsm.tif": dsmUrl = url; break;
                    case "chm.tif": chmUrl = url; break;
                }

                if (fileName.Equals("metadata.json", StringComparison.OrdinalIgnoreCase))
                {
                    try
                    {
                        using var stream = await _storageService.DownloadAsync(bucket, obj.ObjectPath);
                        using var reader = new StreamReader(stream);
                        var json = await reader.ReadToEndAsync();
                        metadata = JsonSerializer.Deserialize<LidarMetadataDto>(json, new JsonSerializerOptions
                        {
                            PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
                            PropertyNameCaseInsensitive = true
                        });
                    }
                    catch (Exception ex)
                    {
                        _logger.LogWarning(ex, "Failed to parse metadata.json for polygon {PolygonId}", changePolygonId);
                    }
                }
            }

            return Ok(new LidarSourceDetailDto
            {
                SourceId = sourceId,
                AoiId = aoiId,
                Files = files,
                DtmUrl = dtmUrl,
                DsmUrl = dsmUrl,
                ChmUrl = chmUrl,
                Metadata = metadata,
                LastModified = objects.Max(o => o.LastModified)
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get LIDAR data for polygon {PolygonId}", changePolygonId);
            return StatusCode(500, new { Error = "Failed to retrieve LIDAR data from storage" });
        }
    }
}

// DTOs

public class LidarFileWithUrlDto
{
    public string FileName { get; set; } = "";
    public string ObjectPath { get; set; } = "";
    public long Size { get; set; }
    public DateTimeOffset LastModified { get; set; }
    public string PresignedUrl { get; set; } = "";
}

public class LidarSourceDetailDto
{
    public string SourceId { get; set; } = "";
    public string AoiId { get; set; } = "";
    public List<LidarFileWithUrlDto> Files { get; set; } = [];
    public string? DtmUrl { get; set; }
    public string? DsmUrl { get; set; }
    public string? ChmUrl { get; set; }
    public LidarMetadataDto? Metadata { get; set; }
    public DateTimeOffset LastModified { get; set; }
}

public class LidarMetadataDto
{
    public string SourceId { get; set; } = "";
    public int PointCount { get; set; }
    public double PointDensityPerM2 { get; set; }
    public int CrsEpsg { get; set; }
    public double ResolutionM { get; set; }
    public List<double>? Bounds { get; set; }
    public Dictionary<string, int>? ClassificationCounts { get; set; }
}
