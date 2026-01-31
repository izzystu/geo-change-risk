using System.Net.Http.Json;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data.Models;
using Microsoft.Extensions.Options;

namespace GeoChangeRisk.Api.Services;

/// <summary>
/// Service for sending notifications about risk events.
/// </summary>
public class NotificationService : INotificationService
{
    private readonly NotificationOptions _options;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<NotificationService> _logger;

    public NotificationService(
        IOptions<NotificationOptions> options,
        IHttpClientFactory httpClientFactory,
        ILogger<NotificationService> logger)
    {
        _options = options.Value;
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    public async Task NotifyRiskEventsAsync(
        IEnumerable<RiskEvent> events,
        string aoiName,
        CancellationToken cancellationToken = default)
    {
        var eventList = events.ToList();
        if (eventList.Count == 0) return;

        // Filter by risk level for each notification channel
        var webhookEvents = eventList
            .Where(e => (int)e.RiskLevel >= _options.Webhook.MinRiskLevel)
            .ToList();

        var emailEvents = eventList
            .Where(e => (int)e.RiskLevel >= _options.Email.MinRiskLevel)
            .ToList();

        // Send webhook notification
        if (_options.Webhook.Enabled && webhookEvents.Count > 0)
        {
            await SendWebhookNotificationAsync(webhookEvents, aoiName, cancellationToken);
        }

        // Send email notification (placeholder - needs SMTP implementation)
        if (_options.Email.Enabled && emailEvents.Count > 0)
        {
            await SendEmailNotificationAsync(emailEvents, aoiName, cancellationToken);
        }
    }

    public async Task NotifyProcessingCompleteAsync(
        ProcessingRun run,
        int changeCount,
        int highRiskCount,
        CancellationToken cancellationToken = default)
    {
        if (!_options.Webhook.Enabled) return;

        try
        {
            var client = _httpClientFactory.CreateClient();
            var payload = new
            {
                type = "processing_complete",
                runId = run.RunId,
                aoiId = run.AoiId,
                status = run.Status.ToString(),
                beforeDate = run.BeforeDate,
                afterDate = run.AfterDate,
                changeCount,
                highRiskCount,
                completedAt = run.CompletedAt
            };

            var response = await client.PostAsJsonAsync(
                _options.Webhook.Url,
                payload,
                cancellationToken);

            if (response.IsSuccessStatusCode)
            {
                _logger.LogInformation(
                    "Sent processing complete webhook for run {RunId}",
                    run.RunId);
            }
            else
            {
                _logger.LogWarning(
                    "Webhook returned {StatusCode} for run {RunId}",
                    response.StatusCode, run.RunId);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to send processing complete webhook");
        }
    }

    private async Task SendWebhookNotificationAsync(
        List<RiskEvent> events,
        string aoiName,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrEmpty(_options.Webhook.Url)) return;

        try
        {
            var client = _httpClientFactory.CreateClient();
            var payload = new
            {
                type = "risk_events",
                aoiName,
                eventCount = events.Count,
                events = events.Select(e => new
                {
                    riskEventId = e.RiskEventId,
                    assetId = e.AssetId,
                    riskScore = e.RiskScore,
                    riskLevel = e.RiskLevel.ToString(),
                    distanceMeters = e.DistanceMeters,
                    createdAt = e.CreatedAt
                })
            };

            var response = await client.PostAsJsonAsync(
                _options.Webhook.Url,
                payload,
                cancellationToken);

            if (response.IsSuccessStatusCode)
            {
                _logger.LogInformation(
                    "Sent webhook notification for {Count} risk events in {AoiName}",
                    events.Count, aoiName);
            }
            else
            {
                _logger.LogWarning(
                    "Webhook returned {StatusCode} for risk events",
                    response.StatusCode);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to send webhook notification");
        }
    }

    private Task SendEmailNotificationAsync(
        List<RiskEvent> events,
        string aoiName,
        CancellationToken cancellationToken)
    {
        // Placeholder for email implementation
        // In production, use a library like MailKit or a service like SendGrid
        _logger.LogInformation(
            "Email notification would be sent for {Count} events in {AoiName}",
            events.Count, aoiName);

        return Task.CompletedTask;
    }
}
