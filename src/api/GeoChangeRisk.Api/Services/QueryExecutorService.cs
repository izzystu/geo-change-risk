using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Services;

/// <summary>
/// Translates a structured QueryPlan into EF Core LINQ queries with PostGIS spatial functions.
/// No raw SQL is ever generated.
/// </summary>
public class QueryExecutorService
{
    private readonly GeoChangeDbContext _context;
    private readonly ILogger<QueryExecutorService> _logger;

    private const int MaxResults = 200;

    // Property whitelists per entity type — unknown properties are silently ignored
    private static readonly HashSet<string> RiskEventProperties = new(StringComparer.OrdinalIgnoreCase)
    {
        "RiskScore", "RiskLevel", "DistanceMeters", "CreatedAt"
    };

    private static readonly HashSet<string> ChangePolygonProperties = new(StringComparer.OrdinalIgnoreCase)
    {
        "AreaSqMeters", "NdviDropMean", "NdviDropMax", "ChangeType",
        "SlopeDegreeMean", "DetectedAt", "MlConfidence"
    };

    private static readonly HashSet<string> AssetProperties = new(StringComparer.OrdinalIgnoreCase)
    {
        "AssetType", "Criticality", "Name", "SourceDataset", "CreatedAt"
    };

    private static readonly HashSet<string> ProcessingRunProperties = new(StringComparer.OrdinalIgnoreCase)
    {
        "Status", "BeforeDate", "AfterDate", "CreatedAt"
    };

    public QueryExecutorService(GeoChangeDbContext context, ILogger<QueryExecutorService> logger)
    {
        _context = context;
        _logger = logger;
    }

    public async Task<QueryExecutionResult> ExecuteAsync(QueryPlan plan, CancellationToken ct = default)
    {
        return plan.TargetEntity switch
        {
            TargetEntityType.RiskEvent => await ExecuteRiskEventQueryAsync(plan, ct),
            TargetEntityType.ChangePolygon => await ExecuteChangePolygonQueryAsync(plan, ct),
            TargetEntityType.Asset => await ExecuteAssetQueryAsync(plan, ct),
            TargetEntityType.ProcessingRun => await ExecuteProcessingRunQueryAsync(plan, ct),
            _ => new QueryExecutionResult()
        };
    }

    private async Task<QueryExecutionResult> ExecuteRiskEventQueryAsync(QueryPlan plan, CancellationToken ct)
    {
        var query = _context.RiskEvents
            .Include(e => e.ChangePolygon)
                .ThenInclude(c => c!.ProcessingRun)
            .Include(e => e.Asset)
            .AsQueryable();

        // AOI scoping
        if (!string.IsNullOrEmpty(plan.AoiId))
            query = query.Where(e => e.ChangePolygon!.ProcessingRun!.AoiId == plan.AoiId);

        // Attribute filters
        foreach (var filter in plan.Filters)
        {
            if (!RiskEventProperties.Contains(filter.Property) &&
                !filter.Property.Equals("AssetType", StringComparison.OrdinalIgnoreCase))
                continue;

            query = ApplyRiskEventFilter(query, filter);
        }

        // Spatial filter
        if (plan.SpatialFilter != null)
            query = ApplyRiskEventSpatialFilter(query, plan.SpatialFilter);

        // Date range
        if (plan.DateRange != null)
            query = ApplyDateRange(query, plan.DateRange,
                (q, from) => q.Where(e => e.CreatedAt >= from),
                (q, to) => q.Where(e => e.CreatedAt <= to));

        // Count before paging
        var totalCount = await query.CountAsync(ct);

        // Ordering
        query = ApplyRiskEventOrdering(query, plan.OrderBy, plan.OrderDescending);

        // Limit
        var limit = Math.Min(plan.Limit ?? 50, MaxResults);
        var results = await query.Take(limit).ToListAsync(ct);

        // Map to DTOs
        var items = results.Select(e => (object)new RiskEventDto
        {
            RiskEventId = e.RiskEventId,
            ChangePolygonId = e.ChangePolygonId,
            AssetId = e.AssetId,
            AssetName = e.Asset?.Name ?? "Unknown",
            AssetTypeName = e.Asset?.AssetType.ToString() ?? "Unknown",
            DistanceMeters = e.DistanceMeters,
            RiskScore = e.RiskScore,
            RiskLevel = (int)e.RiskLevel,
            RiskLevelName = e.RiskLevel.ToString(),
            ScoringFactors = e.ScoringFactors,
            CreatedAt = e.CreatedAt,
            AoiId = e.ChangePolygon?.ProcessingRun?.AoiId
        }).ToList();

        // GeoJSON
        var geoJson = BuildRiskEventGeoJson(results);

        return new QueryExecutionResult
        {
            TotalCount = totalCount,
            Items = items,
            GeoJson = geoJson
        };
    }

    private async Task<QueryExecutionResult> ExecuteChangePolygonQueryAsync(QueryPlan plan, CancellationToken ct)
    {
        var query = _context.ChangePolygons
            .Include(c => c.ProcessingRun)
            .Include(c => c.RiskEvents)
            .AsQueryable();

        // AOI scoping
        if (!string.IsNullOrEmpty(plan.AoiId))
            query = query.Where(c => c.ProcessingRun!.AoiId == plan.AoiId);

        // Attribute filters
        foreach (var filter in plan.Filters)
        {
            if (!ChangePolygonProperties.Contains(filter.Property))
                continue;

            query = ApplyChangePolygonFilter(query, filter);
        }

        // Date range
        if (plan.DateRange != null)
            query = ApplyDateRange(query, plan.DateRange,
                (q, from) => q.Where(c => c.DetectedAt >= from),
                (q, to) => q.Where(c => c.DetectedAt <= to));

        var totalCount = await query.CountAsync(ct);

        // Ordering
        query = plan.OrderBy?.ToLowerInvariant() switch
        {
            "areasqmeters" => plan.OrderDescending
                ? query.OrderByDescending(c => c.AreaSqMeters)
                : query.OrderBy(c => c.AreaSqMeters),
            "ndvidropmean" => plan.OrderDescending
                ? query.OrderByDescending(c => c.NdviDropMean)
                : query.OrderBy(c => c.NdviDropMean),
            "detectedat" => plan.OrderDescending
                ? query.OrderByDescending(c => c.DetectedAt)
                : query.OrderBy(c => c.DetectedAt),
            _ => query.OrderByDescending(c => c.AreaSqMeters)
        };

        var limit = Math.Min(plan.Limit ?? 50, MaxResults);
        var results = await query.Take(limit).ToListAsync(ct);

        var items = results.Select(c => (object)new ChangePolygonDto
        {
            ChangePolygonId = c.ChangePolygonId,
            RunId = c.RunId,
            Geometry = c.Geometry,
            AreaSqMeters = c.AreaSqMeters,
            NdviDropMean = c.NdviDropMean,
            NdviDropMax = c.NdviDropMax,
            ChangeType = (int)c.ChangeType,
            ChangeTypeName = c.ChangeType.ToString(),
            SlopeDegreeMean = c.SlopeDegreeMean,
            DetectedAt = c.DetectedAt,
            MlConfidence = c.MlConfidence,
            MlModelVersion = c.MlModelVersion,
            RiskEventCount = c.RiskEvents?.Count ?? 0
        }).ToList();

        var geoJson = BuildChangePolygonGeoJson(results);

        return new QueryExecutionResult
        {
            TotalCount = totalCount,
            Items = items,
            GeoJson = geoJson
        };
    }

    private async Task<QueryExecutionResult> ExecuteAssetQueryAsync(QueryPlan plan, CancellationToken ct)
    {
        var query = _context.Assets.AsQueryable();

        // AOI scoping
        if (!string.IsNullOrEmpty(plan.AoiId))
            query = query.Where(a => a.AoiId == plan.AoiId);

        // Attribute filters
        foreach (var filter in plan.Filters)
        {
            if (!AssetProperties.Contains(filter.Property))
                continue;

            query = ApplyAssetFilter(query, filter);
        }

        // Date range
        if (plan.DateRange != null)
            query = ApplyDateRange(query, plan.DateRange,
                (q, from) => q.Where(a => a.CreatedAt >= from),
                (q, to) => q.Where(a => a.CreatedAt <= to));

        var totalCount = await query.CountAsync(ct);

        // Ordering
        query = plan.OrderBy?.ToLowerInvariant() switch
        {
            "criticality" => plan.OrderDescending
                ? query.OrderByDescending(a => a.Criticality)
                : query.OrderBy(a => a.Criticality),
            "name" => plan.OrderDescending
                ? query.OrderByDescending(a => a.Name)
                : query.OrderBy(a => a.Name),
            "createdat" => plan.OrderDescending
                ? query.OrderByDescending(a => a.CreatedAt)
                : query.OrderBy(a => a.CreatedAt),
            _ => query.OrderByDescending(a => a.Criticality)
        };

        var limit = Math.Min(plan.Limit ?? 50, MaxResults);
        var results = await query.Take(limit).ToListAsync(ct);

        var items = results.Select(a => (object)new AssetDto
        {
            AssetId = a.AssetId,
            AoiId = a.AoiId,
            Name = a.Name,
            AssetType = (int)a.AssetType,
            AssetTypeName = a.AssetType.ToString(),
            Criticality = (int)a.Criticality,
            CriticalityName = a.Criticality.ToString(),
            Geometry = a.Geometry,
            Properties = a.Properties,
            SourceDataset = a.SourceDataset,
            CreatedAt = a.CreatedAt
        }).ToList();

        var geoJson = BuildAssetGeoJson(results);

        return new QueryExecutionResult
        {
            TotalCount = totalCount,
            Items = items,
            GeoJson = geoJson
        };
    }

    private async Task<QueryExecutionResult> ExecuteProcessingRunQueryAsync(QueryPlan plan, CancellationToken ct)
    {
        var query = _context.ProcessingRuns.AsQueryable();

        // AOI scoping
        if (!string.IsNullOrEmpty(plan.AoiId))
            query = query.Where(r => r.AoiId == plan.AoiId);

        // Attribute filters
        foreach (var filter in plan.Filters)
        {
            if (!ProcessingRunProperties.Contains(filter.Property))
                continue;

            query = ApplyProcessingRunFilter(query, filter);
        }

        // Date range
        if (plan.DateRange != null)
            query = ApplyDateRange(query, plan.DateRange,
                (q, from) => q.Where(r => r.CreatedAt >= from),
                (q, to) => q.Where(r => r.CreatedAt <= to));

        var totalCount = await query.CountAsync(ct);

        query = plan.OrderBy?.ToLowerInvariant() switch
        {
            "beforedate" => plan.OrderDescending
                ? query.OrderByDescending(r => r.BeforeDate)
                : query.OrderBy(r => r.BeforeDate),
            "afterdate" => plan.OrderDescending
                ? query.OrderByDescending(r => r.AfterDate)
                : query.OrderBy(r => r.AfterDate),
            _ => query.OrderByDescending(r => r.CreatedAt)
        };

        var limit = Math.Min(plan.Limit ?? 50, MaxResults);
        var results = await query.Take(limit).ToListAsync(ct);

        var items = results.Select(r => (object)new ProcessingRunDto
        {
            RunId = r.RunId,
            AoiId = r.AoiId,
            Status = (int)r.Status,
            StatusName = r.Status.ToString(),
            BeforeDate = r.BeforeDate,
            AfterDate = r.AfterDate,
            BeforeSceneId = r.BeforeSceneId,
            AfterSceneId = r.AfterSceneId,
            StartedAt = r.StartedAt,
            CompletedAt = r.CompletedAt,
            ErrorMessage = r.ErrorMessage,
            Metadata = r.Metadata,
            CreatedAt = r.CreatedAt,
            ChangePolygonCount = 0,
            RiskEventCount = 0
        }).ToList();

        return new QueryExecutionResult
        {
            TotalCount = totalCount,
            Items = items,
            GeoJson = null // Processing runs don't have geometry
        };
    }

    // ========================
    // Attribute filter helpers
    // ========================

    private static IQueryable<RiskEvent> ApplyRiskEventFilter(IQueryable<RiskEvent> query, AttributeFilter filter)
    {
        switch (filter.Property.ToLowerInvariant())
        {
            case "riskscore":
                if (int.TryParse(filter.Value, out var score))
                    query = ApplyNumericFilter(query, e => e.RiskScore, filter.Operator, score);
                break;

            case "risklevel":
                if (Enum.TryParse<RiskLevel>(filter.Value, true, out var level))
                    query = filter.Operator == FilterOperator.eq
                        ? query.Where(e => e.RiskLevel == level)
                        : filter.Operator == FilterOperator.gte
                            ? query.Where(e => e.RiskLevel >= level)
                            : query;
                break;

            case "distancemeters":
                if (double.TryParse(filter.Value, out var dist))
                    query = ApplyNumericFilter(query, e => e.DistanceMeters, filter.Operator, dist);
                break;

            case "assettype":
                if (Enum.TryParse<AssetType>(filter.Value, true, out var at))
                    query = query.Where(e => e.Asset!.AssetType == at);
                break;
        }
        return query;
    }

    private static IQueryable<ChangePolygon> ApplyChangePolygonFilter(IQueryable<ChangePolygon> query, AttributeFilter filter)
    {
        switch (filter.Property.ToLowerInvariant())
        {
            case "areasqmeters":
                if (double.TryParse(filter.Value, out var area))
                    query = ApplyNumericFilter(query, c => c.AreaSqMeters, filter.Operator, area);
                break;

            case "ndvidropmean":
                if (double.TryParse(filter.Value, out var ndviMean))
                    query = ApplyNumericFilter(query, c => c.NdviDropMean, filter.Operator, ndviMean);
                break;

            case "ndvidropmax":
                if (double.TryParse(filter.Value, out var ndviMax))
                    query = ApplyNumericFilter(query, c => c.NdviDropMax, filter.Operator, ndviMax);
                break;

            case "changetype":
                if (Enum.TryParse<ChangeType>(filter.Value, true, out var ct))
                    query = query.Where(c => c.ChangeType == ct);
                break;

            case "slopedegreemean":
                if (double.TryParse(filter.Value, out var slope))
                    query = ApplyNumericFilter(query, c => c.SlopeDegreeMean ?? 0, filter.Operator, slope);
                break;

            case "mlconfidence":
                if (double.TryParse(filter.Value, out var conf))
                    query = ApplyNumericFilter(query, c => c.MlConfidence ?? 0, filter.Operator, conf);
                break;
        }
        return query;
    }

    private static IQueryable<Asset> ApplyAssetFilter(IQueryable<Asset> query, AttributeFilter filter)
    {
        switch (filter.Property.ToLowerInvariant())
        {
            case "assettype":
                if (Enum.TryParse<AssetType>(filter.Value, true, out var at))
                    query = query.Where(a => a.AssetType == at);
                break;

            case "criticality":
                if (Enum.TryParse<Criticality>(filter.Value, true, out var crit))
                    query = filter.Operator == FilterOperator.eq
                        ? query.Where(a => a.Criticality == crit)
                        : filter.Operator == FilterOperator.gte
                            ? query.Where(a => a.Criticality >= crit)
                            : query;
                break;

            case "name":
                query = query.Where(a => a.Name.Contains(filter.Value));
                break;
        }
        return query;
    }

    private static IQueryable<ProcessingRun> ApplyProcessingRunFilter(IQueryable<ProcessingRun> query, AttributeFilter filter)
    {
        switch (filter.Property.ToLowerInvariant())
        {
            case "status":
                if (Enum.TryParse<ProcessingStatus>(filter.Value, true, out var status))
                    query = query.Where(r => r.Status == status);
                break;
        }
        return query;
    }

    // ========================
    // Spatial filter (RiskEvent only for now)
    // ========================

    private IQueryable<RiskEvent> ApplyRiskEventSpatialFilter(IQueryable<RiskEvent> query, SpatialFilter spatial)
    {
        if (spatial.Operation != SpatialOperation.within_distance || !spatial.DistanceMeters.HasValue)
            return query;

        if (spatial.ReferenceEntityType != TargetEntityType.Asset)
            return query;

        // Build a subquery to find matching reference assets
        var assetQuery = _context.Assets.AsQueryable();
        foreach (var refFilter in spatial.ReferenceFilters)
        {
            if (refFilter.Property.Equals("AssetType", StringComparison.OrdinalIgnoreCase) &&
                Enum.TryParse<AssetType>(refFilter.Value, true, out var refAssetType))
            {
                assetQuery = assetQuery.Where(a => a.AssetType == refAssetType);
            }
        }

        // Use the DistanceMeters field on the RiskEvent as a proxy —
        // the pipeline already computed distance when creating risk events.
        // Filter risk events whose associated asset matches the reference type
        // and whose distance is within the specified range.
        var matchingAssetIds = assetQuery.Select(a => a.AssetId);

        query = query.Where(e =>
            matchingAssetIds.Contains(e.AssetId) &&
            e.DistanceMeters <= spatial.DistanceMeters.Value);

        _logger.LogDebug("Applied spatial filter: within {Distance}m of {EntityType} assets",
            spatial.DistanceMeters, spatial.ReferenceEntityType);

        return query;
    }

    // ========================
    // Generic helpers
    // ========================

    private static IQueryable<T> ApplyNumericFilter<T, TValue>(
        IQueryable<T> query,
        System.Linq.Expressions.Expression<Func<T, TValue>> selector,
        FilterOperator op,
        TValue value) where TValue : IComparable<TValue>
    {
        var param = selector.Parameters[0];
        var member = selector.Body;
        var constant = System.Linq.Expressions.Expression.Constant(value, typeof(TValue));

        System.Linq.Expressions.Expression comparison = op switch
        {
            FilterOperator.eq => System.Linq.Expressions.Expression.Equal(member, constant),
            FilterOperator.neq => System.Linq.Expressions.Expression.NotEqual(member, constant),
            FilterOperator.gt => System.Linq.Expressions.Expression.GreaterThan(member, constant),
            FilterOperator.gte => System.Linq.Expressions.Expression.GreaterThanOrEqual(member, constant),
            FilterOperator.lt => System.Linq.Expressions.Expression.LessThan(member, constant),
            FilterOperator.lte => System.Linq.Expressions.Expression.LessThanOrEqual(member, constant),
            _ => System.Linq.Expressions.Expression.Equal(member, constant)
        };

        var lambda = System.Linq.Expressions.Expression.Lambda<Func<T, bool>>(comparison, param);
        return query.Where(lambda);
    }

    private static IQueryable<T> ApplyDateRange<T>(
        IQueryable<T> query,
        DateRangeFilter dateRange,
        Func<IQueryable<T>, DateTime, IQueryable<T>> applyFrom,
        Func<IQueryable<T>, DateTime, IQueryable<T>> applyTo)
    {
        if (dateRange.From.HasValue)
            query = applyFrom(query, dateRange.From.Value);
        if (dateRange.To.HasValue)
            query = applyTo(query, dateRange.To.Value);
        return query;
    }

    private static IQueryable<RiskEvent> ApplyRiskEventOrdering(
        IQueryable<RiskEvent> query, string? orderBy, bool descending)
    {
        return orderBy?.ToLowerInvariant() switch
        {
            "riskscore" => descending
                ? query.OrderByDescending(e => e.RiskScore)
                : query.OrderBy(e => e.RiskScore),
            "distancemeters" => descending
                ? query.OrderByDescending(e => e.DistanceMeters)
                : query.OrderBy(e => e.DistanceMeters),
            "createdat" => descending
                ? query.OrderByDescending(e => e.CreatedAt)
                : query.OrderBy(e => e.CreatedAt),
            _ => query.OrderByDescending(e => e.RiskScore)
                      .ThenByDescending(e => e.CreatedAt)
        };
    }

    // ========================
    // GeoJSON builders
    // ========================

    private static object BuildRiskEventGeoJson(List<RiskEvent> events)
    {
        var features = events
            .Where(e => e.ChangePolygon?.Geometry != null)
            .Select(e => new
            {
                type = "Feature",
                id = e.RiskEventId.ToString(),
                geometry = e.ChangePolygon!.Geometry,
                properties = new Dictionary<string, object?>
                {
                    ["riskEventId"] = e.RiskEventId,
                    ["assetId"] = e.AssetId,
                    ["assetName"] = e.Asset?.Name,
                    ["assetTypeName"] = e.Asset?.AssetType.ToString(),
                    ["riskScore"] = e.RiskScore,
                    ["riskLevelName"] = e.RiskLevel.ToString(),
                    ["distanceMeters"] = e.DistanceMeters,
                    ["createdAt"] = e.CreatedAt
                }
            }).ToList();

        return new { type = "FeatureCollection", features };
    }

    private static object BuildChangePolygonGeoJson(List<ChangePolygon> changes)
    {
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
                ["changeTypeName"] = c.ChangeType.ToString(),
                ["detectedAt"] = c.DetectedAt
            }
        }).ToList();

        return new { type = "FeatureCollection", features };
    }

    private static object BuildAssetGeoJson(List<Asset> assets)
    {
        var features = assets.Select(a => new
        {
            type = "Feature",
            id = a.AssetId,
            geometry = a.Geometry,
            properties = new Dictionary<string, object?>
            {
                ["assetId"] = a.AssetId,
                ["name"] = a.Name,
                ["assetTypeName"] = a.AssetType.ToString(),
                ["criticalityName"] = a.Criticality.ToString()
            }
        }).ToList();

        return new { type = "FeatureCollection", features };
    }
}

/// <summary>
/// Result of executing a query plan.
/// </summary>
public class QueryExecutionResult
{
    public int TotalCount { get; set; }
    public List<object> Items { get; set; } = new();
    public object? GeoJson { get; set; }
}
