namespace GeoChangeRisk.Contracts;

/// <summary>
/// Interface for LLM services that translate natural language queries into structured query plans.
/// </summary>
public interface ILlmService
{
    /// <summary>
    /// Translate a natural language query into a structured query plan.
    /// </summary>
    /// <param name="query">The natural language query from the user.</param>
    /// <param name="context">Optional context about the current AOI and available entities.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>A result containing the parsed query plan and interpretation.</returns>
    Task<LlmQueryResult> TranslateQueryAsync(
        string query,
        QueryContext? context = null,
        CancellationToken ct = default);

    /// <summary>
    /// Check whether the LLM service is available and responding.
    /// </summary>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>True if the service is reachable and ready.</returns>
    Task<bool> IsAvailableAsync(CancellationToken ct = default);
}

/// <summary>
/// LLM provider configuration.
/// </summary>
public class LlmOptions
{
    public const string SectionName = "Llm";

    /// <summary>
    /// Active provider: "ollama" or "bedrock".
    /// </summary>
    public string Provider { get; set; } = "ollama";

    /// <summary>
    /// Ollama (local) settings.
    /// </summary>
    public OllamaOptions Ollama { get; set; } = new();

    /// <summary>
    /// AWS Bedrock settings.
    /// </summary>
    public BedrockOptions Bedrock { get; set; } = new();
}

/// <summary>
/// Ollama local LLM configuration.
/// </summary>
public class OllamaOptions
{
    /// <summary>
    /// Base URL for the Ollama HTTP API.
    /// </summary>
    public string BaseUrl { get; set; } = "http://localhost:11434";

    /// <summary>
    /// Model name to use for queries.
    /// </summary>
    public string Model { get; set; } = "llama3.1:8b";
}

/// <summary>
/// AWS Bedrock LLM configuration.
/// </summary>
public class BedrockOptions
{
    /// <summary>
    /// AWS region for Bedrock API calls.
    /// </summary>
    public string Region { get; set; } = "us-east-1";

    /// <summary>
    /// Bedrock foundation model ID.
    /// </summary>
    public string ModelId { get; set; } = "anthropic.claude-3-haiku-20240307-v1:0";

    /// <summary>
    /// Maximum tokens in the LLM response.
    /// </summary>
    public int MaxTokens { get; set; } = 1024;
}
