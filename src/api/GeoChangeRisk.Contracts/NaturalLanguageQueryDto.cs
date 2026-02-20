using System.ComponentModel.DataAnnotations;

namespace GeoChangeRisk.Contracts;

/// <summary>
/// Request to translate and execute a natural language spatial query.
/// </summary>
public class NaturalLanguageQueryRequest
{
    /// <summary>
    /// The natural language query (e.g., "Show me critical risk events near hospitals").
    /// </summary>
    [Required]
    public required string Query { get; set; }

    /// <summary>
    /// Optional AOI ID to scope the query.
    /// </summary>
    public string? AoiId { get; set; }
}

/// <summary>
/// Response from a natural language query execution.
/// </summary>
public class NaturalLanguageQueryResponse
{
    /// <summary>
    /// Human-readable interpretation of how the LLM understood the query.
    /// </summary>
    public string Interpretation { get; set; } = "";

    /// <summary>
    /// The structured query plan produced by the LLM.
    /// </summary>
    public QueryPlan? QueryPlan { get; set; }

    /// <summary>
    /// Total number of matching results.
    /// </summary>
    public int TotalCount { get; set; }

    /// <summary>
    /// The query results (typed per target entity).
    /// </summary>
    public List<object> Results { get; set; } = new();

    /// <summary>
    /// GeoJSON FeatureCollection for map display.
    /// </summary>
    public object? GeoJson { get; set; }

    /// <summary>
    /// Whether the query was successful.
    /// </summary>
    public bool Success { get; set; }

    /// <summary>
    /// Error message if the query failed.
    /// </summary>
    public string? ErrorMessage { get; set; }
}
