using System.Text.Json;
using Amazon.Scheduler;
using Amazon.Scheduler.Model;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Api.Services;

/// <summary>
/// AWS EventBridge Scheduler implementation of ISchedulerService.
/// Creates EventBridge Schedules that trigger ECS RunTask for the pipeline.
/// </summary>
public class EventBridgeSchedulerService : ISchedulerService
{
    private readonly AmazonSchedulerClient _scheduler;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly IConfiguration _configuration;
    private readonly ILogger<EventBridgeSchedulerService> _logger;

    private string ScheduleGroupName => _configuration["Aws:ScheduleGroupName"] ?? "georisk-schedules";
    private string ClusterArn => _configuration["Aws:EcsClusterArn"] ?? "";
    private string TaskDefinitionArn => _configuration["Aws:PipelineTaskDefinitionArn"] ?? "";
    private string SubnetIds => _configuration["Aws:PipelineSubnetIds"] ?? "";
    private string SecurityGroupId => _configuration["Aws:PipelineSecurityGroupId"] ?? "";
    private string SchedulerRoleArn => _configuration["Aws:SchedulerRoleArn"] ?? "";

    public EventBridgeSchedulerService(
        AmazonSchedulerClient scheduler,
        IServiceScopeFactory scopeFactory,
        IConfiguration configuration,
        ILogger<EventBridgeSchedulerService> logger)
    {
        _scheduler = scheduler;
        _scopeFactory = scopeFactory;
        _configuration = configuration;
        _logger = logger;
    }

    public async Task AddOrUpdateScheduleAsync(string aoiId, string cronExpression, CancellationToken ct = default)
    {
        // Look up maxCloudCover from the DB
        double maxCloudCover = 20.0;
        using (var scope = _scopeFactory.CreateScope())
        {
            var context = scope.ServiceProvider.GetRequiredService<GeoChangeDbContext>();
            var aoi = await context.AreasOfInterest.FindAsync([aoiId], ct);
            if (aoi != null)
                maxCloudCover = aoi.MaxCloudCover;
        }

        var scheduleName = $"georisk-check-{aoiId}";

        // Convert standard cron (5-field) to EventBridge cron (6-field with year)
        var ebCron = ConvertToEventBridgeCron(cronExpression);

        var subnets = SubnetIds.Split(',', StringSplitOptions.RemoveEmptyEntries);
        var securityGroups = new List<string> { SecurityGroupId };

        var ecsParams = new EcsParameters
        {
            TaskDefinitionArn = TaskDefinitionArn,
            TaskCount = 1,
            NetworkConfiguration = new NetworkConfiguration
            {
                AwsvpcConfiguration = new AwsVpcConfiguration
                {
                    Subnets = subnets.ToList(),
                    SecurityGroups = securityGroups,
                    AssignPublicIp = AssignPublicIp.ENABLED
                }
            },
            CapacityProviderStrategy = new List<CapacityProviderStrategyItem>
            {
                new() { CapacityProvider = "FARGATE_SPOT", Weight = 1 }
            }
        };

        // Build RunTask override JSON for container command override
        // The Scheduler SDK's EcsParameters doesn't expose Overrides, so we pass
        // the override as the Target.Input JSON which gets merged into the RunTask call
        var overrideInput = JsonSerializer.Serialize(new
        {
            containerOverrides = new[]
            {
                new
                {
                    name = "georisk-pipeline",
                    command = new[]
                    {
                        "check",
                        $"--aoi-id={aoiId}",
                        $"--max-cloud={maxCloudCover}",
                        "--json"
                    }
                }
            }
        });

        var request = new CreateScheduleRequest
        {
            Name = scheduleName,
            GroupName = ScheduleGroupName,
            ScheduleExpression = $"cron({ebCron})",
            ScheduleExpressionTimezone = "UTC",
            FlexibleTimeWindow = new FlexibleTimeWindow
            {
                Mode = FlexibleTimeWindowMode.OFF
            },
            Target = new Target
            {
                Arn = ClusterArn,
                RoleArn = SchedulerRoleArn,
                EcsParameters = ecsParams,
                Input = overrideInput
            },
            ActionAfterCompletion = ActionAfterCompletion.NONE
        };

        try
        {
            await _scheduler.CreateScheduleAsync(request, ct);
            _logger.LogInformation(
                "Created EventBridge schedule {ScheduleName} for AOI {AoiId} with cron({Cron})",
                scheduleName, aoiId, ebCron);
        }
        catch (ConflictException)
        {
            // Schedule already exists — update it
            var updateRequest = new UpdateScheduleRequest
            {
                Name = scheduleName,
                GroupName = ScheduleGroupName,
                ScheduleExpression = $"cron({ebCron})",
                ScheduleExpressionTimezone = "UTC",
                FlexibleTimeWindow = new FlexibleTimeWindow
                {
                    Mode = FlexibleTimeWindowMode.OFF
                },
                Target = new Target
                {
                    Arn = ClusterArn,
                    RoleArn = SchedulerRoleArn,
                    EcsParameters = ecsParams,
                    Input = overrideInput
                },
                ActionAfterCompletion = ActionAfterCompletion.NONE
            };

            await _scheduler.UpdateScheduleAsync(updateRequest, ct);
            _logger.LogInformation(
                "Updated EventBridge schedule {ScheduleName} for AOI {AoiId} with cron({Cron})",
                scheduleName, aoiId, ebCron);
        }
    }

    public async Task RemoveScheduleAsync(string aoiId, CancellationToken ct = default)
    {
        var scheduleName = $"georisk-check-{aoiId}";

        try
        {
            await _scheduler.DeleteScheduleAsync(new DeleteScheduleRequest
            {
                Name = scheduleName,
                GroupName = ScheduleGroupName
            }, ct);

            _logger.LogInformation("Deleted EventBridge schedule {ScheduleName}", scheduleName);
        }
        catch (ResourceNotFoundException)
        {
            _logger.LogDebug("EventBridge schedule {ScheduleName} not found (already deleted)", scheduleName);
        }
    }

    public async Task SyncAllSchedulesAsync(CancellationToken ct = default)
    {
        using var scope = _scopeFactory.CreateScope();
        var context = scope.ServiceProvider.GetRequiredService<GeoChangeDbContext>();

        var scheduledAois = await context.AreasOfInterest
            .Where(a => a.ProcessingEnabled && a.ProcessingSchedule != null)
            .ToListAsync(ct);

        var registeredCount = 0;
        foreach (var aoi in scheduledAois)
        {
            try
            {
                await AddOrUpdateScheduleAsync(aoi.AoiId, aoi.ProcessingSchedule!, ct);
                registeredCount++;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex,
                    "Failed to create EventBridge schedule for AOI {AoiId} with schedule '{Schedule}'",
                    aoi.AoiId, aoi.ProcessingSchedule);
            }
        }

        _logger.LogInformation("Synced {Count}/{Total} EventBridge schedules",
            registeredCount, scheduledAois.Count);
    }

    /// <summary>
    /// Converts a standard 5-field cron expression to EventBridge 6-field format.
    /// Standard: minute hour day-of-month month day-of-week
    /// EventBridge: minute hour day-of-month month day-of-week year
    /// </summary>
    private static string ConvertToEventBridgeCron(string cron)
    {
        var parts = cron.Trim().Split(' ', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 5)
        {
            // Add wildcard year field
            return $"{parts[0]} {parts[1]} {parts[2]} {parts[3]} {parts[4]} *";
        }
        // Already 6 fields or non-standard — pass through
        return cron;
    }
}
