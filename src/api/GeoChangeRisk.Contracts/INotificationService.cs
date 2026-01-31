using GeoChangeRisk.Data.Models;

namespace GeoChangeRisk.Contracts;

/// <summary>
/// Interface for notification services.
/// </summary>
public interface INotificationService
{
    /// <summary>
    /// Send notifications for high-risk events.
    /// </summary>
    /// <param name="events">Risk events to notify about.</param>
    /// <param name="aoiName">Name of the affected AOI.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    Task NotifyRiskEventsAsync(
        IEnumerable<RiskEvent> events,
        string aoiName,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Send notification for a completed processing run.
    /// </summary>
    /// <param name="run">The completed processing run.</param>
    /// <param name="changeCount">Number of changes detected.</param>
    /// <param name="highRiskCount">Number of high/critical risk events.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    Task NotifyProcessingCompleteAsync(
        ProcessingRun run,
        int changeCount,
        int highRiskCount,
        CancellationToken cancellationToken = default);
}

/// <summary>
/// Notification configuration.
/// </summary>
public class NotificationOptions
{
    public const string SectionName = "Notifications";

    /// <summary>
    /// Email notification settings.
    /// </summary>
    public EmailNotificationOptions Email { get; set; } = new();

    /// <summary>
    /// Webhook notification settings.
    /// </summary>
    public WebhookNotificationOptions Webhook { get; set; } = new();
}

public class EmailNotificationOptions
{
    /// <summary>
    /// Whether email notifications are enabled.
    /// </summary>
    public bool Enabled { get; set; } = false;

    /// <summary>
    /// SMTP server hostname.
    /// </summary>
    public string SmtpServer { get; set; } = "";

    /// <summary>
    /// SMTP server port.
    /// </summary>
    public int SmtpPort { get; set; } = 587;

    /// <summary>
    /// Email recipients.
    /// </summary>
    public List<string> Recipients { get; set; } = new();

    /// <summary>
    /// Minimum risk level to trigger email (0=Low, 1=Medium, 2=High, 3=Critical).
    /// </summary>
    public int MinRiskLevel { get; set; } = 2; // High
}

public class WebhookNotificationOptions
{
    /// <summary>
    /// Whether webhook notifications are enabled.
    /// </summary>
    public bool Enabled { get; set; } = false;

    /// <summary>
    /// Webhook URL to POST to.
    /// </summary>
    public string Url { get; set; } = "";

    /// <summary>
    /// Minimum risk level to trigger webhook.
    /// </summary>
    public int MinRiskLevel { get; set; } = 3; // Critical
}
