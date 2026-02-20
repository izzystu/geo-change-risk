using System.Text.Json;
using System.Text.Json.Serialization;

namespace GeoChangeRisk.Contracts;

/// <summary>
/// Structured query plan produced by the LLM and consumed by the query executor.
/// </summary>
public class QueryPlan
{
    /// <summary>
    /// The primary entity type to query.
    /// </summary>
    [JsonConverter(typeof(JsonStringEnumConverter))]
    public TargetEntityType TargetEntity { get; set; }

    /// <summary>
    /// Attribute-based filters (e.g., RiskLevel = Critical).
    /// </summary>
    public List<AttributeFilter> Filters { get; set; } = new();

    /// <summary>
    /// Optional spatial filter (e.g., within 500m of hospitals).
    /// </summary>
    public SpatialFilter? SpatialFilter { get; set; }

    /// <summary>
    /// Optional date range filter.
    /// </summary>
    public DateRangeFilter? DateRange { get; set; }

    /// <summary>
    /// Optional AOI ID to scope the query.
    /// </summary>
    public string? AoiId { get; set; }

    /// <summary>
    /// Property to order results by (e.g., "RiskScore", "CreatedAt").
    /// </summary>
    public string? OrderBy { get; set; }

    /// <summary>
    /// Whether to order descending. Default true.
    /// </summary>
    public bool OrderDescending { get; set; } = true;

    /// <summary>
    /// Maximum number of results to return.
    /// </summary>
    public int? Limit { get; set; }
}

/// <summary>
/// Entities that can be queried.
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum TargetEntityType
{
    RiskEvent,
    ChangePolygon,
    Asset,
    ProcessingRun
}

/// <summary>
/// A single attribute filter condition.
/// </summary>
public class AttributeFilter
{
    /// <summary>
    /// Property name on the target entity (e.g., "RiskLevel", "AssetType").
    /// </summary>
    public string Property { get; set; } = "";

    /// <summary>
    /// Comparison operator.
    /// </summary>
    [JsonConverter(typeof(JsonStringEnumConverter))]
    public FilterOperator Operator { get; set; }

    /// <summary>
    /// The value to compare against. For "in" operator, use comma-separated values.
    /// Accepts strings, numbers, booleans, and arrays from LLM output.
    /// </summary>
    [JsonConverter(typeof(LenientStringConverter))]
    public string Value { get; set; } = "";
}

/// <summary>
/// Supported filter operators.
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum FilterOperator
{
    eq,
    neq,
    gt,
    gte,
    lt,
    lte,
    @in
}

/// <summary>
/// Spatial filter for proximity or intersection queries.
/// </summary>
public class SpatialFilter
{
    /// <summary>
    /// The spatial operation to perform.
    /// </summary>
    [JsonConverter(typeof(JsonStringEnumConverter))]
    public SpatialOperation Operation { get; set; }

    /// <summary>
    /// Entity type to use as the spatial reference (e.g., Asset).
    /// </summary>
    [JsonConverter(typeof(JsonStringEnumConverter))]
    public TargetEntityType ReferenceEntityType { get; set; }

    /// <summary>
    /// Filters on the reference entity (e.g., AssetType = Hospital).
    /// </summary>
    public List<AttributeFilter> ReferenceFilters { get; set; } = new();

    /// <summary>
    /// Distance in meters for within_distance operations.
    /// </summary>
    public double? DistanceMeters { get; set; }
}

/// <summary>
/// Supported spatial operations.
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum SpatialOperation
{
    within_distance,
    intersects
}

/// <summary>
/// Date range filter.
/// </summary>
public class DateRangeFilter
{
    /// <summary>
    /// Date property to filter on (e.g., "CreatedAt", "DetectedAt").
    /// </summary>
    public string Property { get; set; } = "CreatedAt";

    /// <summary>
    /// Start of date range (inclusive).
    /// </summary>
    public DateTime? From { get; set; }

    /// <summary>
    /// End of date range (inclusive).
    /// </summary>
    public DateTime? To { get; set; }
}

/// <summary>
/// Context provided to the LLM to improve query interpretation.
/// </summary>
public class QueryContext
{
    /// <summary>
    /// Currently selected AOI ID.
    /// </summary>
    public string? CurrentAoiId { get; set; }

    /// <summary>
    /// Currently selected AOI name.
    /// </summary>
    public string? CurrentAoiName { get; set; }

    /// <summary>
    /// Names of all available AOIs for disambiguation.
    /// </summary>
    public List<string> AvailableAoiNames { get; set; } = new();
}

/// <summary>
/// Result from the LLM translation.
/// </summary>
public class LlmQueryResult
{
    /// <summary>
    /// The structured query plan (null if parsing failed).
    /// </summary>
    public QueryPlan? Plan { get; set; }

    /// <summary>
    /// Human-readable interpretation of the query.
    /// </summary>
    public string Interpretation { get; set; } = "";

    /// <summary>
    /// Whether the translation was successful.
    /// </summary>
    public bool Success { get; set; }

    /// <summary>
    /// Error message if translation failed.
    /// </summary>
    public string? ErrorMessage { get; set; }
}

/// <summary>
/// Converts any JSON value (string, number, boolean, array) to a string.
/// Arrays are joined with commas. Handles inconsistent LLM JSON output.
/// </summary>
public class LenientStringConverter : JsonConverter<string>
{
    public override string Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        switch (reader.TokenType)
        {
            case JsonTokenType.String:
                return reader.GetString() ?? "";
            case JsonTokenType.Number:
                return reader.GetDouble().ToString(System.Globalization.CultureInfo.InvariantCulture);
            case JsonTokenType.True:
                return "true";
            case JsonTokenType.False:
                return "false";
            case JsonTokenType.StartArray:
                var items = new List<string>();
                while (reader.Read() && reader.TokenType != JsonTokenType.EndArray)
                {
                    items.Add(reader.TokenType switch
                    {
                        JsonTokenType.String => reader.GetString() ?? "",
                        JsonTokenType.Number => reader.GetDouble().ToString(System.Globalization.CultureInfo.InvariantCulture),
                        _ => ""
                    });
                }
                return string.Join(",", items);
            default:
                reader.Skip();
                return "";
        }
    }

    public override void Write(Utf8JsonWriter writer, string value, JsonSerializerOptions options)
    {
        writer.WriteStringValue(value);
    }
}
