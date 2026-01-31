using GeoChangeRisk.Data;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Controllers;

/// <summary>
/// System endpoints for health checks and diagnostics.
/// </summary>
[ApiController]
[Route("api/[controller]")]
public class SystemController : ControllerBase
{
    private readonly GeoChangeDbContext _context;
    private readonly ILogger<SystemController> _logger;

    public SystemController(GeoChangeDbContext context, ILogger<SystemController> logger)
    {
        _context = context;
        _logger = logger;
    }

    /// <summary>
    /// Basic health check endpoint.
    /// </summary>
    [HttpGet("health")]
    public async Task<IActionResult> GetHealth()
    {
        var result = new
        {
            Status = "Healthy",
            Timestamp = DateTime.UtcNow,
            Version = "1.0.0"
        };

        try
        {
            // Test database connectivity
            await _context.Database.CanConnectAsync();
            return Ok(new
            {
                result.Status,
                result.Timestamp,
                result.Version,
                Database = "Connected"
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Health check failed - database connection error");
            return StatusCode(503, new
            {
                Status = "Unhealthy",
                result.Timestamp,
                result.Version,
                Database = "Disconnected",
                Error = ex.Message
            });
        }
    }

    /// <summary>
    /// Get database statistics.
    /// </summary>
    [HttpGet("stats")]
    public async Task<IActionResult> GetStats()
    {
        try
        {
            var aoiCount = await _context.AreasOfInterest.CountAsync();
            var assetCount = await _context.Assets.CountAsync();

            return Ok(new
            {
                AreasOfInterest = aoiCount,
                Assets = assetCount,
                Timestamp = DateTime.UtcNow
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get stats");
            return StatusCode(500, new { Error = ex.Message });
        }
    }
}
