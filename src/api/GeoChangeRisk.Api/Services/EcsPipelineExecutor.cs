using Amazon.ECS;
using Amazon.ECS.Model;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data.Models;

namespace GeoChangeRisk.Api.Services;

/// <summary>
/// AWS ECS Fargate pipeline executor for cloud deployment.
/// Launches ECS tasks for georisk CLI commands.
/// </summary>
public class EcsPipelineExecutor : IPipelineExecutor
{
    private readonly AmazonECSClient _ecs;
    private readonly IConfiguration _configuration;
    private readonly ILogger<EcsPipelineExecutor> _logger;

    private string ClusterArn => _configuration["Aws:EcsClusterArn"] ?? "";
    private string TaskDefinitionArn => _configuration["Aws:PipelineTaskDefinitionArn"] ?? "";
    private string SubnetIds => _configuration["Aws:PipelineSubnetIds"] ?? "";
    private string SecurityGroupId => _configuration["Aws:PipelineSecurityGroupId"] ?? "";

    public EcsPipelineExecutor(
        AmazonECSClient ecs,
        IConfiguration configuration,
        ILogger<EcsPipelineExecutor> logger)
    {
        _ecs = ecs;
        _configuration = configuration;
        _logger = logger;
    }

    public async Task<int> RunProcessAsync(ProcessingRun run, CancellationToken ct = default)
    {
        var command = new List<string>
        {
            "process",
            $"--aoi-id={run.AoiId}",
            $"--before={run.BeforeDate:yyyy-MM-dd}",
            $"--after={run.AfterDate:yyyy-MM-dd}",
            $"--run-id={run.RunId}"
        };

        _logger.LogInformation("Launching ECS task for processing run {RunId}", run.RunId);

        var taskArn = await LaunchEcsTaskAsync(command, ct);
        return await WaitForTaskCompletionAsync(taskArn, ct);
    }

    public async Task<CheckCommandResult> RunCheckAsync(string aoiId, double maxCloudCover, CancellationToken ct = default)
    {
        var command = new List<string>
        {
            "check",
            $"--aoi-id={aoiId}",
            $"--max-cloud={maxCloudCover}",
            "--json"
        };

        _logger.LogInformation("Launching ECS task for check on AOI {AoiId}", aoiId);

        var taskArn = await LaunchEcsTaskAsync(command, ct);
        var exitCode = await WaitForTaskCompletionAsync(taskArn, ct);

        if (exitCode == 0)
        {
            // In ECS mode, the check command's stdout goes to CloudWatch Logs.
            // The pipeline writes results to the API directly, so we return a
            // placeholder result. The ScheduledCheckJob handles this scenario.
            _logger.LogInformation("ECS check task completed successfully for AOI {AoiId}", aoiId);
            return new CheckCommandResult { NewData = true };
        }

        if (exitCode == 1)
        {
            return new CheckCommandResult(); // No new data
        }

        throw new InvalidOperationException(
            $"ECS georisk check task failed with exit code {exitCode}");
    }

    private async Task<string> LaunchEcsTaskAsync(List<string> command, CancellationToken ct)
    {
        var subnets = SubnetIds.Split(',', StringSplitOptions.RemoveEmptyEntries).ToList();

        var request = new RunTaskRequest
        {
            Cluster = ClusterArn,
            TaskDefinition = TaskDefinitionArn,
            Count = 1,
            NetworkConfiguration = new NetworkConfiguration
            {
                AwsvpcConfiguration = new AwsVpcConfiguration
                {
                    Subnets = subnets,
                    SecurityGroups = new List<string> { SecurityGroupId },
                    AssignPublicIp = AssignPublicIp.ENABLED
                }
            },
            CapacityProviderStrategy = new List<CapacityProviderStrategyItem>
            {
                new() { CapacityProvider = "FARGATE_SPOT", Weight = 1 }
            },
            Overrides = new TaskOverride
            {
                ContainerOverrides = new List<ContainerOverride>
                {
                    new()
                    {
                        Name = "georisk-pipeline",
                        Command = command
                    }
                }
            }
        };

        var response = await _ecs.RunTaskAsync(request, ct);

        if (response.Failures.Count > 0)
        {
            var failure = response.Failures[0];
            throw new InvalidOperationException(
                $"Failed to launch ECS task: {failure.Reason} ({failure.Detail})");
        }

        var taskArn = response.Tasks[0].TaskArn;
        _logger.LogInformation("Launched ECS task {TaskArn}", taskArn);
        return taskArn;
    }

    private async System.Threading.Tasks.Task<int> WaitForTaskCompletionAsync(string taskArn, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            await System.Threading.Tasks.Task.Delay(TimeSpan.FromSeconds(30), ct);

            var describeResponse = await _ecs.DescribeTasksAsync(new DescribeTasksRequest
            {
                Cluster = ClusterArn,
                Tasks = new List<string> { taskArn }
            }, ct);

            var ecsTask = describeResponse.Tasks.FirstOrDefault();
            if (ecsTask == null)
            {
                throw new InvalidOperationException($"ECS task {taskArn} not found");
            }

            _logger.LogDebug("ECS task {TaskArn} status: {Status}", taskArn, ecsTask.LastStatus);

            if (ecsTask.LastStatus == "STOPPED")
            {
                var container = ecsTask.Containers.FirstOrDefault();
                var exitCode = container?.ExitCode ?? -1;

                _logger.LogInformation("ECS task {TaskArn} stopped with exit code {ExitCode}",
                    taskArn, exitCode);

                return exitCode;
            }
        }

        throw new OperationCanceledException("ECS task wait was cancelled");
    }
}
