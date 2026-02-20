# Automated Scheduling

The platform supports fully automated monitoring of each AOI for new satellite imagery. When configured, a recurring job checks for new Sentinel-2 scenes on a cron schedule and automatically triggers processing runs when acceptable data is available.

Scheduling is provider-agnostic — the `ISchedulerService` interface allows swapping between backends depending on the deployment target.

## Scheduler Providers

| Deployment | Provider | Job Execution | Status |
|------------|----------|---------------|--------|
| **Local** | Hangfire (`HangfireSchedulerService`) | In-process within the API | Complete |
| **AWS** | EventBridge Scheduler (`EventBridgeSchedulerService`) | ECS Fargate container | Complete |
| **Azure** | Azure Logic Apps (planned `AzureSchedulerService`) | Azure Container Instances | Documented |
| **GCP** | Cloud Scheduler (planned `CloudSchedulerService`) | Cloud Run Jobs | Documented |

**Local (Hangfire):** Jobs run inside the API process using Hangfire's `IRecurringJobManager`, backed by PostgreSQL storage. Dashboard available at `/hangfire`.

**AWS (EventBridge):** Schedules are created via the AWS EventBridge Scheduler API. Each tick triggers an ECS Fargate task that runs `georisk check` independently of the API — no in-process job execution. Converts standard 5-field cron to EventBridge's 6-field format automatically. Requires IAM role configuration for scheduler-to-ECS invocation.

Provider selection is config-driven (`Scheduler:Provider` = `hangfire` or `eventbridge`) and resolved via DI at startup.

## How It Works

1. **Schedule configuration** — Each AOI can be assigned a cron schedule (e.g., daily, weekly) and a maximum cloud cover threshold via the Scheduling panel in the Web UI or the REST API
2. **Imagery check** — On each scheduled tick, the `georisk check` CLI command queries the STAC API for new Sentinel-2 scenes since the last completed run, filtered by the cloud cover threshold
3. **Automatic run creation** — If a new scene is found that hasn't been processed yet, a processing run is created with:
   - **After date** = the date of the new scene
   - **Before date** = the after date from the last completed run (creating a continuous monitoring chain), or `defaultLookbackDays` back from the new scene if no previous run exists
4. **Guard logic** — If a processing run is already in progress for the AOI, the check skips to avoid duplicate runs
5. **Persistence** — Schedules are stored on the AOI record in the database and re-synced with the active scheduler provider on API startup

## CLI Usage

```bash
# Check for new imagery (used by scheduler, also available manually)
python -m georisk check --aoi-id paradise-ca --json

# With custom cloud cover threshold
python -m georisk check --aoi-id paradise-ca --max-cloud 15 --json
```

## API Usage

```bash
# Configure a daily schedule at 6 AM UTC with 25% max cloud cover
curl -X PUT http://localhost:5074/api/areas-of-interest/paradise-ca/schedule \
  -H "Content-Type: application/json" \
  -d '{"processingSchedule": "0 6 * * *", "processingEnabled": true, "maxCloudCover": 25}'
```

## Common Cron Schedules

| Schedule | Cron Expression |
|----------|----------------|
| Every 6 hours | `0 */6 * * *` |
| Daily at 6 AM UTC | `0 6 * * *` |
| Twice weekly (Mon/Thu) | `0 6 * * 1,4` |
| Weekly (Monday) | `0 6 * * 1` |
