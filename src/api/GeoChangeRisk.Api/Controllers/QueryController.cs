using GeoChangeRisk.Api.Services;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Controllers;

/// <summary>
/// Natural language spatial query endpoint powered by LLM translation.
/// </summary>
[ApiController]
[Route("api/query")]
public class QueryController : ControllerBase
{
    private readonly ILlmService _llmService;
    private readonly QueryExecutorService _queryExecutor;
    private readonly GeoChangeDbContext _context;
    private readonly ILogger<QueryController> _logger;

    public QueryController(
        ILlmService llmService,
        QueryExecutorService queryExecutor,
        GeoChangeDbContext context,
        ILogger<QueryController> logger)
    {
        _llmService = llmService;
        _queryExecutor = queryExecutor;
        _context = context;
        _logger = logger;
    }

    /// <summary>
    /// Translate and execute a natural language spatial query.
    /// </summary>
    [HttpPost]
    public async Task<ActionResult<NaturalLanguageQueryResponse>> Query(
        [FromBody] NaturalLanguageQueryRequest request,
        CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(request.Query))
        {
            return BadRequest(new { Error = "Query text is required" });
        }

        _logger.LogInformation("Natural language query: \"{Query}\" (AOI: {AoiId})",
            request.Query, request.AoiId ?? "none");

        // Build context for the LLM
        var aois = await _context.AreasOfInterest
            .Select(a => new { a.AoiId, a.Name })
            .ToListAsync(ct);

        var queryContext = new QueryContext
        {
            CurrentAoiId = request.AoiId,
            CurrentAoiName = aois.FirstOrDefault(a => a.AoiId == request.AoiId)?.Name,
            AvailableAoiNames = aois.Select(a => a.Name).ToList()
        };

        // Step 1: LLM translation
        var llmResult = await _llmService.TranslateQueryAsync(request.Query, queryContext, ct);

        if (!llmResult.Success || llmResult.Plan == null)
        {
            _logger.LogWarning("LLM translation failed for query: \"{Query}\". Error: {Error}",
                request.Query, llmResult.ErrorMessage);

            return Ok(new NaturalLanguageQueryResponse
            {
                Success = false,
                Interpretation = llmResult.Interpretation,
                ErrorMessage = llmResult.ErrorMessage ?? "Failed to interpret query"
            });
        }

        _logger.LogInformation("LLM query plan: Entity={Entity}, Filters={FilterCount}, AoiId={AoiId}, Limit={Limit}",
            llmResult.Plan.TargetEntity, llmResult.Plan.Filters.Count,
            llmResult.Plan.AoiId ?? "(none)", llmResult.Plan.Limit);
        foreach (var f in llmResult.Plan.Filters)
            _logger.LogInformation("  Filter: {Property} {Operator} {Value}", f.Property, f.Operator, f.Value);

        // Resolve AOI: if LLM set a display name, map it back to the DB ID
        if (!string.IsNullOrEmpty(llmResult.Plan.AoiId))
        {
            var matchedAoi = aois.FirstOrDefault(a => a.AoiId == llmResult.Plan.AoiId)
                ?? aois.FirstOrDefault(a => a.Name.Equals(llmResult.Plan.AoiId, StringComparison.OrdinalIgnoreCase))
                ?? aois.FirstOrDefault(a => a.Name.Contains(llmResult.Plan.AoiId, StringComparison.OrdinalIgnoreCase));

            if (matchedAoi != null)
                llmResult.Plan.AoiId = matchedAoi.AoiId;
            else
                _logger.LogWarning("LLM specified unknown AOI: \"{AoiId}\", falling back to request AOI", llmResult.Plan.AoiId);
        }

        // Apply AOI scoping from request if not resolved above
        if (string.IsNullOrEmpty(llmResult.Plan.AoiId) && !string.IsNullOrEmpty(request.AoiId))
        {
            llmResult.Plan.AoiId = request.AoiId;
        }

        // Step 2: Execute the query plan
        try
        {
            var executionResult = await _queryExecutor.ExecuteAsync(llmResult.Plan, ct);

            _logger.LogInformation(
                "Query executed: {TotalCount} results for \"{Query}\" (entity: {Entity})",
                executionResult.TotalCount, request.Query, llmResult.Plan.TargetEntity);

            return Ok(new NaturalLanguageQueryResponse
            {
                Success = true,
                Interpretation = llmResult.Interpretation,
                QueryPlan = llmResult.Plan,
                TotalCount = executionResult.TotalCount,
                Results = executionResult.Items,
                GeoJson = executionResult.GeoJson
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Query execution failed for plan: {Entity}", llmResult.Plan.TargetEntity);

            return Ok(new NaturalLanguageQueryResponse
            {
                Success = false,
                Interpretation = llmResult.Interpretation,
                QueryPlan = llmResult.Plan,
                ErrorMessage = "Query execution failed"
            });
        }
    }

    /// <summary>
    /// Check LLM service availability.
    /// </summary>
    [HttpGet("health")]
    public async Task<IActionResult> Health(CancellationToken ct)
    {
        var available = await _llmService.IsAvailableAsync(ct);
        return Ok(new { available });
    }
}
