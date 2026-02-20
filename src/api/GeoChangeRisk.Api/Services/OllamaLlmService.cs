using System.Text.Json;
using System.Text.Json.Serialization;
using GeoChangeRisk.Contracts;
using Microsoft.Extensions.Options;

namespace GeoChangeRisk.Api.Services;

/// <summary>
/// LLM service implementation using a local Ollama instance.
/// </summary>
public class OllamaLlmService : ILlmService
{
    private readonly LlmOptions _options;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<OllamaLlmService> _logger;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true,
        NumberHandling = System.Text.Json.Serialization.JsonNumberHandling.AllowReadingFromString,
        Converters = { new LenientBoolConverter() }
    };

    /// <summary>
    /// Handles booleans returned as strings ("true"/"false") by smaller LLMs.
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

    public OllamaLlmService(
        IOptions<LlmOptions> options,
        IHttpClientFactory httpClientFactory,
        ILogger<OllamaLlmService> logger)
    {
        _options = options.Value;
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    public async Task<LlmQueryResult> TranslateQueryAsync(
        string query,
        QueryContext? context = null,
        CancellationToken ct = default)
    {
        try
        {
            var client = _httpClientFactory.CreateClient();
            var baseUrl = _options.Ollama.BaseUrl.TrimEnd('/');

            var systemPrompt = LlmPromptTemplate.GetSystemPrompt();
            if (context != null)
            {
                systemPrompt += $"\n\nCurrent context: AOI=\"{context.CurrentAoiName ?? "none"}\", " +
                                $"Available AOIs: {string.Join(", ", context.AvailableAoiNames)}";
            }

            var requestBody = new
            {
                model = _options.Ollama.Model,
                messages = new[]
                {
                    new { role = "system", content = systemPrompt },
                    new { role = "user", content = query }
                },
                format = "json",
                stream = false
            };

            var response = await client.PostAsJsonAsync(
                $"{baseUrl}/api/chat",
                requestBody,
                ct);

            if (!response.IsSuccessStatusCode)
            {
                var errorBody = await response.Content.ReadAsStringAsync(ct);
                _logger.LogError("Ollama API error {StatusCode}: {Body}",
                    response.StatusCode, errorBody);
                return new LlmQueryResult
                {
                    Success = false,
                    ErrorMessage = $"LLM service returned {response.StatusCode}"
                };
            }

            var responseJson = await response.Content.ReadFromJsonAsync<JsonElement>(ct);
            var content = responseJson
                .GetProperty("message")
                .GetProperty("content")
                .GetString();

            if (string.IsNullOrWhiteSpace(content))
            {
                return new LlmQueryResult
                {
                    Success = false,
                    ErrorMessage = "LLM returned empty response"
                };
            }

            return ParseLlmResponse(content);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to translate query via Ollama");
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
            var client = _httpClientFactory.CreateClient();
            var baseUrl = _options.Ollama.BaseUrl.TrimEnd('/');

            var response = await client.GetAsync($"{baseUrl}/api/tags", ct);
            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
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

    /// <summary>
    /// Envelope matching the JSON structure returned by the LLM.
    /// </summary>
    private class LlmResponseEnvelope
    {
        public string? Interpretation { get; set; }
        public QueryPlan? Plan { get; set; }
    }
}
