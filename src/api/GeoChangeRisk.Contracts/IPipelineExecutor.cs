using System.Text.Json.Serialization;
using GeoChangeRisk.Data.Models;

namespace GeoChangeRisk.Contracts;

/// <summary>
/// Abstracts pipeline execution (local subprocess or ECS Fargate task).
/// </summary>
public interface IPipelineExecutor
{
    /// <summary>
    /// Runs the georisk process command for a processing run.
    /// </summary>
    /// <returns>Exit code from the pipeline process.</returns>
    Task<int> RunProcessAsync(ProcessingRun run, CancellationToken ct = default);

    /// <summary>
    /// Runs the georisk check command for an AOI.
    /// </summary>
    Task<CheckCommandResult> RunCheckAsync(string aoiId, double maxCloudCover, CancellationToken ct = default);
}

/// <summary>
/// Result from the georisk check CLI command.
/// </summary>
public class CheckCommandResult
{
    [JsonPropertyName("new_data")]
    public bool NewData { get; set; }

    [JsonPropertyName("scene_id")]
    public string? SceneId { get; set; }

    [JsonPropertyName("scene_date")]
    public string? SceneDate { get; set; }

    [JsonPropertyName("cloud_cover")]
    public double CloudCover { get; set; }

    [JsonPropertyName("recommended_before_date")]
    public string RecommendedBeforeDate { get; set; } = "";

    [JsonPropertyName("recommended_after_date")]
    public string RecommendedAfterDate { get; set; } = "";
}
