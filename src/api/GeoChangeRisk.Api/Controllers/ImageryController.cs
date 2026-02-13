using System.Text.Json;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Controllers;

/// <summary>
/// Endpoints for satellite imagery management.
/// </summary>
[ApiController]
[Route("api/imagery")]
public class ImageryController : ControllerBase
{
    private readonly GeoChangeDbContext _context;
    private readonly IObjectStorageService _storageService;
    private readonly IConfiguration _configuration;
    private readonly ILogger<ImageryController> _logger;

    public ImageryController(
        GeoChangeDbContext context,
        IObjectStorageService storageService,
        IConfiguration configuration,
        ILogger<ImageryController> logger)
    {
        _context = context;
        _storageService = storageService;
        _configuration = configuration;
        _logger = logger;
    }

    /// <summary>
    /// List available imagery scenes for an AOI.
    /// </summary>
    [HttpGet("{aoiId}")]
    public async Task<ActionResult<IEnumerable<ImagerySceneDto>>> ListScenes(string aoiId)
    {
        // Verify AOI exists
        var aoi = await _context.AreasOfInterest.FindAsync(aoiId);
        if (aoi == null)
        {
            return NotFound(new { Error = $"Area of Interest '{aoiId}' not found" });
        }

        var bucket = _configuration["Storage:BucketImagery"]
            ?? _configuration["MinIO:BucketImagery"] ?? "georisk-imagery";
        var prefix = $"{aoiId}/";

        try
        {
            var objects = await _storageService.ListObjectsAsync(bucket, prefix);

            // Group by scene ID (parent folder)
            var scenes = objects
                .Where(o => o.ObjectPath.EndsWith(".tif", StringComparison.OrdinalIgnoreCase))
                .GroupBy(o =>
                {
                    // Extract scene ID from path: {aoiId}/{sceneId}/{file}.tif
                    var parts = o.ObjectPath.Split('/');
                    return parts.Length >= 2 ? parts[1] : "unknown";
                })
                .Select(g => new ImagerySceneDto
                {
                    SceneId = g.Key,
                    AoiId = aoiId,
                    Files = g.Select(o => new ImageryFileDto
                    {
                        FileName = Path.GetFileName(o.ObjectPath),
                        ObjectPath = o.ObjectPath,
                        Size = o.Size,
                        LastModified = o.LastModified
                    }).ToList(),
                    LastModified = g.Max(o => o.LastModified)
                })
                .OrderByDescending(s => s.LastModified)
                .ToList();

            return Ok(scenes);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to list imagery for AOI {AoiId}", aoiId);
            return StatusCode(500, new { Error = "Failed to list imagery from storage" });
        }
    }

    /// <summary>
    /// Get scene details with presigned URLs for COG files.
    /// </summary>
    [HttpGet("{aoiId}/{sceneId}")]
    public async Task<ActionResult<ImagerySceneDetailDto>> GetScene(string aoiId, string sceneId)
    {
        // Verify AOI exists
        var aoi = await _context.AreasOfInterest.FindAsync(aoiId);
        if (aoi == null)
        {
            return NotFound(new { Error = $"Area of Interest '{aoiId}' not found" });
        }

        var bucket = _configuration["Storage:BucketImagery"]
            ?? _configuration["MinIO:BucketImagery"] ?? "georisk-imagery";
        var prefix = $"{aoiId}/{sceneId}/";

        try
        {
            var objects = await _storageService.ListObjectsAsync(bucket, prefix);
            var imageFiles = objects.Where(o =>
                o.ObjectPath.EndsWith(".tif", StringComparison.OrdinalIgnoreCase) ||
                o.ObjectPath.EndsWith(".png", StringComparison.OrdinalIgnoreCase)).ToList();

            if (imageFiles.Count == 0)
            {
                return NotFound(new { Error = $"Scene '{sceneId}' not found for AOI '{aoiId}'" });
            }

            // Try to read bounds from sidecar file for accurate georeferencing
            var boundsPath = $"{aoiId}/{sceneId}/rgb.bounds.json";
            double[]? actualBounds = null;

            try
            {
                if (await _storageService.ObjectExistsAsync(bucket, boundsPath))
                {
                    using var boundsStream = await _storageService.DownloadAsync(bucket, boundsPath);
                    using var reader = new StreamReader(boundsStream);
                    var boundsJson = await reader.ReadToEndAsync();
                    var boundsData = JsonSerializer.Deserialize<BoundsMetadata>(boundsJson);
                    actualBounds = boundsData?.Bounds;

                    if (actualBounds != null)
                    {
                        _logger.LogDebug("Using bounds from sidecar file for {SceneId}: [{MinLon}, {MinLat}, {MaxLon}, {MaxLat}]",
                            sceneId, actualBounds[0], actualBounds[1], actualBounds[2], actualBounds[3]);
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to read bounds.json for {SceneId}, falling back to AOI bounds", sceneId);
            }

            // Use actual bounds if available, otherwise fall back to AOI bounds
            var envelope = aoi.BoundingBox.EnvelopeInternal;
            var bounds = actualBounds ?? [envelope.MinX, envelope.MinY, envelope.MaxX, envelope.MaxY];

            var files = new List<ImageryFileWithUrlDto>();

            foreach (var file in imageFiles)
            {
                var url = await _storageService.GetPresignedUrlAsync(bucket, file.ObjectPath, 3600);
                files.Add(new ImageryFileWithUrlDto
                {
                    FileName = Path.GetFileName(file.ObjectPath),
                    ObjectPath = file.ObjectPath,
                    Size = file.Size,
                    LastModified = file.LastModified,
                    PresignedUrl = url
                });
            }

            // Find the PNG file for web display (prefer PNG over TIF)
            var pngFile = files.FirstOrDefault(f => f.FileName.EndsWith(".png", StringComparison.OrdinalIgnoreCase));
            var displayUrl = pngFile?.PresignedUrl ?? files.FirstOrDefault()?.PresignedUrl;

            return Ok(new ImagerySceneDetailDto
            {
                SceneId = sceneId,
                AoiId = aoiId,
                Bounds = bounds,
                Files = files,
                DisplayUrl = displayUrl,
                LastModified = imageFiles.Max(f => f.LastModified)
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get scene {SceneId} for AOI {AoiId}", sceneId, aoiId);
            return StatusCode(500, new { Error = "Failed to retrieve scene from storage" });
        }
    }

    /// <summary>
    /// Upload a COG file for manual testing/development.
    /// </summary>
    [HttpPost("{aoiId}/upload")]
    [RequestSizeLimit(500_000_000)] // 500MB limit
    public async Task<ActionResult<ImageryUploadResultDto>> UploadCog(
        string aoiId,
        [FromQuery] string sceneId,
        [FromQuery] string? fileName = null,
        IFormFile? file = null)
    {
        // Verify AOI exists
        var aoi = await _context.AreasOfInterest.FindAsync(aoiId);
        if (aoi == null)
        {
            return NotFound(new { Error = $"Area of Interest '{aoiId}' not found" });
        }

        if (string.IsNullOrWhiteSpace(sceneId))
        {
            return BadRequest(new { Error = "sceneId query parameter is required" });
        }

        if (file == null || file.Length == 0)
        {
            return BadRequest(new { Error = "No file uploaded" });
        }

        var actualFileName = fileName ?? file.FileName;
        if (!actualFileName.EndsWith(".tif", StringComparison.OrdinalIgnoreCase))
        {
            return BadRequest(new { Error = "Only .tif files are allowed" });
        }

        var bucket = _configuration["Storage:BucketImagery"]
            ?? _configuration["MinIO:BucketImagery"] ?? "georisk-imagery";
        var objectPath = $"{aoiId}/{sceneId}/{actualFileName}";

        try
        {
            using var stream = file.OpenReadStream();
            await _storageService.UploadAsync(bucket, objectPath, stream, "image/tiff");

            _logger.LogInformation("Uploaded COG {ObjectPath} ({Size} bytes)", objectPath, file.Length);

            var presignedUrl = await _storageService.GetPresignedUrlAsync(bucket, objectPath, 3600);

            return Ok(new ImageryUploadResultDto
            {
                ObjectPath = objectPath,
                Size = file.Length,
                PresignedUrl = presignedUrl,
                Message = "File uploaded successfully"
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to upload COG for AOI {AoiId}", aoiId);
            return StatusCode(500, new { Error = "Failed to upload file to storage" });
        }
    }

    /// <summary>
    /// Delete a scene and all its files.
    /// </summary>
    [HttpDelete("{aoiId}/{sceneId}")]
    public async Task<IActionResult> DeleteScene(string aoiId, string sceneId)
    {
        // Verify AOI exists
        var aoi = await _context.AreasOfInterest.FindAsync(aoiId);
        if (aoi == null)
        {
            return NotFound(new { Error = $"Area of Interest '{aoiId}' not found" });
        }

        var bucket = _configuration["Storage:BucketImagery"]
            ?? _configuration["MinIO:BucketImagery"] ?? "georisk-imagery";
        var prefix = $"{aoiId}/{sceneId}/";

        try
        {
            var objects = await _storageService.ListObjectsAsync(bucket, prefix);

            foreach (var obj in objects)
            {
                await _storageService.DeleteAsync(bucket, obj.ObjectPath);
            }

            _logger.LogInformation("Deleted scene {SceneId} for AOI {AoiId} ({Count} files)",
                sceneId, aoiId, objects.Count);

            return NoContent();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to delete scene {SceneId} for AOI {AoiId}", sceneId, aoiId);
            return StatusCode(500, new { Error = "Failed to delete scene from storage" });
        }
    }
}
