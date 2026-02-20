using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Amazon.BedrockRuntime;
using Amazon.BedrockRuntime.Model;
using GeoChangeRisk.Contracts;
using Microsoft.Extensions.Options;

namespace GeoChangeRisk.Api.Services;

/// <summary>
/// LLM service implementation using AWS Bedrock (Claude models).
/// Auth via IAM roles — no API keys needed.
/// </summary>
public class BedrockLlmService : ILlmService
{
    private readonly AmazonBedrockRuntimeClient _client;
    private readonly LlmOptions _options;
    private readonly ILogger<BedrockLlmService> _logger;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true,
        NumberHandling = System.Text.Json.Serialization.JsonNumberHandling.AllowReadingFromString,
        Converters = { new LenientBoolConverter() }
    };

    /// <summary>
    /// Handles booleans returned as strings ("true"/"false") by LLMs.
    /// </summary>
    private class LenientBoolConverter : JsonConverter<bool>
    {
        public override bool Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        {
            if (reader.TokenType == JsonTokenType.True) return true;
            if (reader.TokenType == JsonTokenType.False) return false;
            if (reader.TokenType == JsonTokenType.String)
            {
                var str = reader.GetString();
                if (bool.TryParse(str, out var result)) return result;
            }
            if (reader.TokenType == JsonTokenType.Number)
            {
                return reader.GetInt32() != 0;
            }
            return false;
        }

        public override void Write(Utf8JsonWriter writer, bool value, JsonSerializerOptions options)
        {
            writer.WriteBooleanValue(value);
        }
    }

    public BedrockLlmService(
        AmazonBedrockRuntimeClient client,
        IOptions<LlmOptions> options,
        ILogger<BedrockLlmService> logger)
    {
        _client = client;
        _options = options.Value;
        _logger = logger;
    }

    public async Task<LlmQueryResult> TranslateQueryAsync(
        string query,
        QueryContext? context = null,
        CancellationToken ct = default)
    {
        try
        {
            var systemPrompt = LlmPromptTemplate.GetSystemPrompt();
            if (context != null)
            {
                systemPrompt += $"\n\nCurrent context: AOI=\"{context.CurrentAoiName ?? "none"}\", " +
                                $"Available AOIs: {string.Join(", ", context.AvailableAoiNames)}";
            }

            // Claude Messages API format
            var requestPayload = new
            {
                anthropic_version = "bedrock-2023-05-31",
                max_tokens = _options.Bedrock.MaxTokens,
                system = systemPrompt,
                messages = new[]
                {
                    new { role = "user", content = query }
                }
            };

            var payloadJson = JsonSerializer.Serialize(requestPayload, JsonOptions);

            var request = new InvokeModelRequest
            {
                ModelId = _options.Bedrock.ModelId,
                ContentType = "application/json",
                Accept = "application/json",
                Body = new MemoryStream(Encoding.UTF8.GetBytes(payloadJson))
            };

            var response = await _client.InvokeModelAsync(request, ct);

            using var reader = new StreamReader(response.Body);
            var responseBody = await reader.ReadToEndAsync(ct);
            var responseJson = JsonSerializer.Deserialize<JsonElement>(responseBody);

            // Extract content from Claude response format
            var content = responseJson
                .GetProperty("content")[0]
                .GetProperty("text")
                .GetString();

            if (string.IsNullOrWhiteSpace(content))
            {
                return new LlmQueryResult
                {
                    Success = false,
                    ErrorMessage = "Bedrock returned empty response"
                };
            }

            // Claude may wrap JSON in markdown code blocks — strip them
            content = StripMarkdownCodeBlock(content);

            return ParseLlmResponse(content);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to translate query via Bedrock");
            return new LlmQueryResult
            {
                Success = false,
                ErrorMessage = $"LLM translation failed: {ex.Message}"
            };
        }
    }

    public async Task<bool> IsAvailableAsync(CancellationToken ct = default)
    {
        try
        {
            // Lightweight check — invoke with a minimal prompt
            var request = new InvokeModelRequest
            {
                ModelId = _options.Bedrock.ModelId,
                ContentType = "application/json",
                Accept = "application/json",
                Body = new MemoryStream(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
                {
                    anthropic_version = "bedrock-2023-05-31",
                    max_tokens = 10,
                    messages = new[] { new { role = "user", content = "ping" } }
                })))
            };

            var response = await _client.InvokeModelAsync(request, ct);
            return response.HttpStatusCode == System.Net.HttpStatusCode.OK;
        }
        catch
        {
            return false;
        }
    }

    private static string StripMarkdownCodeBlock(string content)
    {
        content = content.Trim();
        if (content.StartsWith("```json"))
            content = content[7..];
        else if (content.StartsWith("```"))
            content = content[3..];

        if (content.EndsWith("```"))
            content = content[..^3];

        return content.Trim();
    }

    private static LlmQueryResult ParseLlmResponse(string content)
    {
        try
        {
            var parsed = JsonSerializer.Deserialize<LlmResponseEnvelope>(content, JsonOptions);

            if (parsed?.Plan == null)
            {
                return new LlmQueryResult
                {
                    Success = false,
                    Interpretation = parsed?.Interpretation ?? "",
                    ErrorMessage = "LLM response did not contain a valid query plan"
                };
            }

            return new LlmQueryResult
            {
                Success = true,
                Plan = parsed.Plan,
                Interpretation = parsed.Interpretation ?? "Query interpreted successfully"
            };
        }
        catch (JsonException ex)
        {
            return new LlmQueryResult
            {
                Success = false,
                ErrorMessage = $"Failed to parse LLM response as JSON: {ex.Message}"
            };
        }
    }

    private class LlmResponseEnvelope
    {
        public string? Interpretation { get; set; }
        public QueryPlan? Plan { get; set; }
    }
}
