# Multi-Cloud Portability Strategy

The Geo Change Risk platform uses three DI-swappable interfaces to isolate all cloud-specific code. Deploying to a different cloud requires implementing 2-3 new service classes and writing equivalent Terraform modules — no changes to controllers, jobs, pipeline logic, or the web UI.

## Design Philosophy

Cloud-specific code is confined to implementations of three interfaces:

| Interface | Responsibility | Local | AWS |
|-----------|---------------|-------|-----|
| `IObjectStorageService` | File storage (rasters, imagery, artifacts) | `ObjectStorageService` (MinIO) | `S3ObjectStorageService` (AWS SDK) |
| `ISchedulerService` | Cron-based recurring job scheduling | `HangfireSchedulerService` | `EventBridgeSchedulerService` |
| `IPipelineExecutor` | Run georisk CLI commands | `LocalPipelineExecutor` (subprocess) | `EcsPipelineExecutor` (ECS RunTask) |

Selection is controlled by three configuration keys:

```json
{
  "Storage": { "Provider": "minio | s3" },
  "Scheduler": { "Provider": "hangfire | eventbridge" },
  "Pipeline": { "ExecutionMode": "local | ecs" }
}
```

The Python pipeline also auto-detects S3 vs MinIO mode: when `MINIO_ENDPOINT` is unset, `MinioStorage` uses the default boto3 client with IAM role credentials.

## What Stays the Same Across All Clouds

- **Dockerfiles** — Container images are cloud-agnostic
- **Terraform module structure** — Same organizational pattern, different provider resources
- **API controllers and business logic** — All cloud interaction happens through the interfaces
- **API key authentication middleware** — Simple header check, no cloud auth dependency
- **Web UI** — Static build served from any CDN/storage; API URL is a build-time variable
- **Database schema** — PostgreSQL + PostGIS works on any managed PostgreSQL service
- **Risk scoring, NDVI processing, ML models** — All run inside the pipeline container

## Azure Deployment Path

### Service Mapping

| AWS | Azure Equivalent | Notes |
|-----|-----------------|-------|
| App Runner | **Azure Container Apps** | Scale-to-zero, consumption plan |
| ECS Fargate | **Azure Container Instances** | On-demand container tasks |
| RDS PostgreSQL | **Azure Database for PostgreSQL Flexible Server** | Burstable B1ms tier |
| S3 | **Azure Blob Storage** | Standard tier, LRS |
| CloudFront | **Azure Static Web Apps** or **Azure Front Door** | Built-in SPA support |
| EventBridge Scheduler | **Azure Logic Apps** or **Azure Functions Timer Trigger** | Consumption plan |
| Secrets Manager | **Azure Key Vault** | Standard tier |
| ECR | **Azure Container Registry** | Basic tier |

### New Service Classes Required

1. **`AzureBlobStorageService`** — Implements `IObjectStorageService` using `Azure.Storage.Blobs`
   - `BlobServiceClient` replaces `AmazonS3Client`
   - `BlobContainerClient` maps to buckets
   - `BlobSasBuilder` for presigned URLs
   - `EnsureBucketExists` → `CreateIfNotExists`

2. **`AzureSchedulerService`** — Implements `ISchedulerService` using Azure Logic Apps REST API or Azure Functions
   - Create/update Logic App with recurrence trigger that calls ACI
   - Or use Azure Functions with `TimerTrigger` and Durable Functions

3. **`AciPipelineExecutor`** — Implements `IPipelineExecutor` using `Azure.ResourceManager.ContainerInstance`
   - `ContainerGroupCollection.CreateOrUpdate` to launch tasks
   - Poll container group status until terminated
   - Read exit code from container instance

### Configuration Changes

```json
{
  "Storage": { "Provider": "azure" },
  "Scheduler": { "Provider": "azure" },
  "Pipeline": { "ExecutionMode": "aci" }
}
```

Pipeline `MinioStorage` would need a parallel `AzureBlobStorage` class or environment-variable-controlled init using `azure-storage-blob` SDK.

### Estimated Azure Cost (comparable to ~$32/month AWS)

| Service | Spec | ~Cost |
|---------|------|-------|
| Azure Database for PostgreSQL Flexible Server | Burstable B1ms, 32 GB | $26 |
| Azure Container Apps | Scale-to-zero, consumption | ~$2 |
| Azure Container Instances | 2 vCPU / 8 GB, ~4 hrs | ~$1 |
| Azure Blob Storage + CDN | Standard LRS | $3 |
| Azure Key Vault + Logic Apps | Minimal usage | $1 |
| **Total** | | **~$33/month** |

## GCP Deployment Path

### Service Mapping

| AWS | GCP Equivalent | Notes |
|-----|---------------|-------|
| App Runner | **Cloud Run** | Scale-to-zero, fully managed |
| ECS Fargate | **Cloud Run Jobs** | On-demand container execution |
| RDS PostgreSQL | **Cloud SQL for PostgreSQL** | Shared-core tier |
| S3 | **Cloud Storage** | Standard class |
| CloudFront | **Cloud CDN + Cloud Storage** | Or Firebase Hosting |
| EventBridge Scheduler | **Cloud Scheduler** | Cron-based HTTP/Pub/Sub triggers |
| Secrets Manager | **Secret Manager** | Automatic versioning |
| ECR | **Artifact Registry** | Docker repository |

### New Service Classes Required

1. **`GcsObjectStorageService`** — Implements `IObjectStorageService` using `Google.Cloud.Storage.V1`
   - `StorageClient` replaces `AmazonS3Client`
   - `UrlSigner` for presigned URLs
   - Bucket operations map directly

2. **`CloudSchedulerService`** — Implements `ISchedulerService` using `Google.Cloud.Scheduler.V1`
   - Create/update Cloud Scheduler jobs with HTTP target
   - Target: Cloud Run Jobs API to launch pipeline tasks
   - Cron expression format is compatible (both use standard 5-field cron)

3. **`CloudRunJobsExecutor`** — Implements `IPipelineExecutor` using Cloud Run Jobs API
   - `ExecuteJob` to launch tasks
   - Poll execution status until completion
   - Read exit code from execution result

### Configuration Changes

```json
{
  "Storage": { "Provider": "gcs" },
  "Scheduler": { "Provider": "cloudscheduler" },
  "Pipeline": { "ExecutionMode": "cloudrun" }
}
```

Pipeline `MinioStorage` would use `google-cloud-storage` SDK when `STORAGE_PROVIDER=gcs` environment variable is set.

### Estimated GCP Cost (comparable to ~$32/month AWS)

| Service | Spec | ~Cost |
|---------|------|-------|
| Cloud SQL PostgreSQL | Shared-core, 10 GB | $20 |
| Cloud Run (API) | Scale-to-zero | ~$2 |
| Cloud Run Jobs (Pipeline) | 2 vCPU / 8 GB, ~4 hrs | ~$1 |
| Cloud Storage + CDN | Standard class | $4 |
| Cloud Scheduler + Secret Manager | Minimal usage | $1 |
| **Total** | | **~$28/month** |

## Implementation Summary

### To deploy on a new cloud:

1. Create 2-3 new C# service classes implementing the existing interfaces
2. Add a new config value for each (e.g., `"Storage": { "Provider": "azure" }`)
3. Add conditional DI registration in `Program.cs`
4. Write Terraform modules using the target cloud's provider
5. Update the pipeline's `MinioStorage` to support the new storage backend (or create a parallel class)

### Lines of code per cloud:

| Component | Estimate |
|-----------|----------|
| Storage service class | ~150 lines |
| Scheduler service class | ~120 lines |
| Pipeline executor class | ~130 lines |
| Program.cs DI additions | ~15 lines |
| Terraform modules | ~500 lines |
| Pipeline storage adapter | ~100 lines |
| **Total new code** | **~1,000 lines** |

The core platform (~15,000 lines across API, pipeline, and web UI) requires zero changes.
