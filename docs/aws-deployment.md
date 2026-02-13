# AWS Deployment Guide

Deploy the Geo Change Risk platform to AWS using Terraform infrastructure-as-code and a single deployment script.

## Architecture

```
Internet
   ├── CloudFront ── S3 (static SvelteKit build)
   └── App Runner (.NET API, scale-to-zero)
              │
         RDS PostgreSQL 16 + PostGIS 3.4 (db.t4g.micro)
              │
   EventBridge Scheduler ──→ ECS Fargate Task (pipeline, on-demand)
```

### Components

| Service | Role | Spec |
|---------|------|------|
| **App Runner** | REST API | 0.25 vCPU / 0.5 GB, scale-to-zero (~$2/month idle) |
| **ECS Fargate Spot** | Pipeline tasks | 2 vCPU / 8 GB, on-demand only (~$0.60/month for ~4 hrs) |
| **RDS PostgreSQL** | Database | db.t4g.micro, 20 GB gp3, PostGIS 3.4, single-AZ |
| **S3** | Object storage | 5 data buckets + 1 web UI bucket |
| **CloudFront** | Web UI CDN | OAC to S3, SPA fallback |
| **EventBridge Scheduler** | Cron scheduling | Replaces Hangfire recurring jobs |
| **Secrets Manager** | Credentials | RDS connection string |
| **ECR** | Container registry | API and pipeline images |

### Estimated Monthly Cost (us-east-1)

| Service | ~Cost |
|---------|-------|
| RDS PostgreSQL (db.t4g.micro, 20 GB) | $24 |
| App Runner (scale-to-zero) | ~$2 |
| ECS Fargate Spot (~4 hrs/month) | $0.60 |
| S3 + CloudFront + ECR | $5 |
| VPC Interface Endpoints (2, single AZ) | ~$15 |
| EventBridge Scheduler | $0 (free tier) |
| Secrets Manager (2 secrets) | $0.80 |
| **Total** | **~$47/month** |

## Prerequisites

- **AWS CLI** configured with standard credentials in `~/.aws/credentials` (see note below)
- **Terraform** >= 1.5
- **Docker Desktop** running
- **.NET 8 SDK**
- **Node.js 18+**
- **Python 3.11+** (for local testing)

> **Important:** Terraform requires credentials in `~/.aws/credentials` (the standard credentials file). If you use `aws configure login` or AWS IAM Identity Center (SSO), those credentials are stored in `~/.aws/login/` or `~/.aws/sso/`, which Terraform cannot read. Run `aws configure set aws_access_key_id <KEY>` and `aws configure set aws_secret_access_key <SECRET>` to create the standard credentials file.

## Deployment

### 1. Configure Variables

Copy the example tfvars:

```powershell
cp deployments\aws\terraform.tfvars.example deployments\aws\environments\dev.tfvars
```

Edit `dev.tfvars` and set your API key:

```hcl
region   = "us-east-1"
env_name = "dev"
```

Set the API key via environment variable (avoid committing it):

```powershell
$env:TF_VAR_api_key = "your-secure-demo-key"
```

### 2. First-Time Setup — Create ECR Repositories

ECR repos must exist before Docker images can be pushed, so create them first:

```powershell
cd deployments\aws
terraform init
terraform apply -var-file="environments\dev.tfvars" '-target=module.ecr'
```

> **Note:** The single quotes around `-target=module.ecr` are required on Terraform >= 1.14.

### 3. Deploy

```powershell
.\deployments\aws\scripts\deploy.ps1
```

The script will:
1. Validate `TF_VAR_api_key` is set
2. Build API and Pipeline Docker images and push to ECR
3. Run `terraform apply` (single phase — pipeline reads API URL from SSM at runtime)
4. Build the web UI as a static export with the AWS API URL baked in
5. Upload the web UI to S3 and invalidate CloudFront cache
6. Print the deployment URLs

Database migrations are applied automatically by the API on startup — no manual migration step needed.

### 4. Load Sample Data (Optional)

```powershell
$env:GEORISK_API_KEY = $env:TF_VAR_api_key
python areas-of-interest\paradise\initialize.py --api-url https://<app-runner-url>
```

The script reads the `GEORISK_API_KEY` environment variable for authentication. You can also pass `--api-key <key>` directly.

### 5. Verify

```powershell
# Health check
curl https://<app-runner-url>/health

# API auth test (should return 401)
curl https://<app-runner-url>/api/areas-of-interest

# API auth test (should return data)
curl -H "X-Api-Key: your-key" https://<app-runner-url>/api/areas-of-interest

# Web UI
# Browse to https://<cloudfront-url> — should show login gate
```

## Configuration Reference

### App Runner Environment Variables

| Variable | Value | Description |
|----------|-------|-------------|
| `Storage__Provider` | `s3` | Use S3 instead of MinIO |
| `Scheduler__Provider` | `eventbridge` | Use EventBridge instead of Hangfire |
| `Pipeline__ExecutionMode` | `ecs` | Launch ECS tasks instead of local subprocess |
| `Auth__ApiKey` | (from Secrets Manager) | API key for demo access |
| `Storage__BucketRasters` | `georisk-dev-rasters` | S3 bucket names |
| `Aws__EcsClusterArn` | (from Terraform) | ECS cluster ARN |
| `Aws__PipelineTaskDefinitionArn` | (from Terraform) | Pipeline task definition |
| `Aws__PipelineSubnetIds` | (from Terraform) | Public subnet IDs for ECS tasks |
| `Aws__PipelineSecurityGroupId` | (from Terraform) | Security group for ECS tasks |
| `Aws__SchedulerRoleArn` | (from Terraform) | EventBridge scheduler IAM role |

### Pipeline ECS Task Environment Variables

| Variable | Value | Description |
|----------|-------|-------------|
| `GEORISK_API_URL` | (from SSM at task launch) | API endpoint for pipeline callbacks |
| `GEORISK_API_KEY` | (from SSM at task launch) | API key for authenticated callbacks |
| `AWS_REGION` | `us-east-1` | AWS region for boto3 S3 client |
| `ML_ENABLED` | `false` | ML disabled in initial deployment |
| `MINIO_ENDPOINT` | (unset) | Empty = S3 mode via IAM role |
| `MINIO_BUCKET_IMAGERY` | `georisk-dev-imagery` | S3 bucket for satellite imagery |
| `MINIO_BUCKET_CHANGES` | `georisk-dev-changes` | S3 bucket for change detection outputs |
| `MINIO_BUCKET_MODELS` | `georisk-dev-models` | S3 bucket for ML model files |

## Abstraction Interfaces

Three DI-swappable interfaces isolate all cloud-specific code:

### IObjectStorageService

- **Local:** `ObjectStorageService` (MinIO SDK)
- **AWS:** `S3ObjectStorageService` (AWS SDK for .NET)
- **Pipeline:** `MinioStorage` in `minio.py` auto-detects S3 vs MinIO based on whether `MINIO_ENDPOINT` is set

### ISchedulerService

- **Local:** `HangfireSchedulerService` (Hangfire `IRecurringJobManager`)
- **AWS:** `EventBridgeSchedulerService` (AWS Scheduler SDK)

### IPipelineExecutor

- **Local:** `LocalPipelineExecutor` (Python subprocess)
- **AWS:** `EcsPipelineExecutor` (ECS `RunTask` + polling)

## Security

### VPC Interface Endpoints

App Runner with `egress_type = "VPC"` routes all outbound traffic through the VPC connector. Since connector ENIs don't receive public IPs, AWS API calls (ECS RunTask, EventBridge Scheduler) require VPC interface endpoints to stay within the AWS network:

| Endpoint | Service | Purpose |
|----------|---------|---------|
| `ecs-endpoint` | `com.amazonaws.<region>.ecs` | ECS RunTask API calls from App Runner |
| `scheduler-endpoint` | `com.amazonaws.<region>.scheduler` | EventBridge Scheduler API calls from App Runner |
| `s3-endpoint` | `com.amazonaws.<region>.s3` | S3 access (Gateway endpoint, free) |

The ECS and Scheduler endpoints are placed in a single AZ (data subnet) to minimize cost (~$7.20/month each). The S3 gateway endpoint is free. All interface endpoints are protected by a security group allowing HTTPS (443) ingress from the VPC CIDR.

### Security Groups

| SG | Inbound | Outbound |
|----|---------|----------|
| `apprunner-connector-sg` | none (Terraform-managed) | 5432 to `rds-sg`, 443 to 0.0.0.0/0 |
| `pipeline-sg` | none | 5432 to `rds-sg`, 443 to 0.0.0.0/0 |
| `rds-sg` | 5432 from `apprunner-connector-sg` + `pipeline-sg` | none |
| `endpoints-sg` | 443 from VPC CIDR | none |

### IAM Roles

- **App Runner Instance Role:** S3, ECS RunTask, Secrets Manager, EventBridge Scheduler
- **Pipeline Task Role:** S3, Secrets Manager
- **Pipeline Execution Role:** ECR pull, CloudWatch Logs
- **EventBridge Scheduler Role:** ECS RunTask, IAM PassRole

### API Key Authentication

When `Auth:ApiKey` is set, all API endpoints (except `/health` and `/swagger`) require the `X-Api-Key` header. The web UI stores the key in `localStorage` and shows a login gate on 401 responses.

## Teardown

```powershell
cd deployments\aws
terraform destroy -var-file=environments\dev.tfvars
```

## Troubleshooting

### AWS Credentials / Terraform Auth

**Symptom:** `terraform apply` fails with "No valid credential sources found."

Terraform reads `~/.aws/credentials` (INI-format key/secret). AWS CLI login via SSO/Identity Center stores tokens in `~/.aws/login/` or `~/.aws/sso/`, which Terraform cannot use.

**Fix:** Create standard credentials:
```powershell
aws configure set aws_access_key_id <YOUR_KEY>
aws configure set aws_secret_access_key <YOUR_SECRET>
```

Verify with `aws configure list` — the "Type" column should show `shared-credentials-file`, not `login`.

### ECR Docker Login Fails (400 Bad Request)

**Symptom:** `docker login` returns `400 Bad Request` when piping the password.

On Windows PowerShell 5.x, piping with `--password-stdin` fails silently. The deploy script uses `--password` directly instead:

```powershell
$EcrPassword = aws ecr get-login-password --region us-east-1
docker login --username AWS --password $EcrPassword <registry>
```

### App Runner CREATE_FAILED

Common causes:
1. **No image in ECR** — ECR login failed silently, images never pushed. Verify with `aws ecr describe-images --repository-name georisk-dev-api`.
2. **Missing connection string** — The `ConnectionStrings__DefaultConnection` must be injected via `runtime_environment_secrets` from Secrets Manager, not as a plain env var.

### Docker Build Cache / Code Changes Not Deploying

**Symptom:** You changed source code but the deployed API behaves the same way.

Docker layer caching means `docker build` may skip copying updated source files. Force a clean build:

```powershell
docker build --no-cache -t georisk-api -f src\api\Dockerfile src\api
```

After pushing the new image, App Runner auto-deploys if `auto_deployments_enabled = true`. You can also trigger manually:

```powershell
aws apprunner start-deployment --service-arn <service-arn>
```

### CORS Errors in Browser

**Symptom:** Browser shows "CORS policy: No 'Access-Control-Allow-Origin' header" when the web UI calls the API.

The API detects AWS deployment via `Storage:Provider == "s3"` and automatically uses `AllowAnyOrigin()`. If CORS headers are missing:
1. Verify the API image was rebuilt and pushed after the CORS fix
2. Verify App Runner deployed the new image (check deployment status in console)
3. Test directly: `curl.exe -v -H "Origin: https://example.com" https://<api-url>/health` — response should include `access-control-allow-origin: *`

> **Note:** ASP.NET Core's `WithOrigins("*")` does literal string matching — it does NOT act as a wildcard. You must use `AllowAnyOrigin()` instead.

### Web UI Shows "localhost" API URL

**Symptom:** Web UI loads but shows "Failed to connect to API at localhost:5074."

SvelteKit's `$env/static/public` reads `PUBLIC_API_URL` from the `.env` file **at build time**, not from process environment variables. The deploy script handles this by temporarily overwriting `.env` with the AWS API URL during the build. If you build manually:

```powershell
# In src\web-ui:
Set-Content .env "PUBLIC_API_URL=https://<app-runner-url>"
$env:ADAPTER = "static"
npm run build
```

After uploading to S3, invalidate CloudFront cache for changes to take effect.

### App Runner VPC Connector

If the API can't reach RDS, verify:
- VPC connector is attached to subnets with routes to RDS
- `apprunner-connector-sg` allows egress to port 5432
- `rds-sg` allows ingress from `apprunner-connector-sg`

If the API can't reach AWS APIs (ECS RunTask hangs, EventBridge calls timeout):
- Verify VPC interface endpoints exist for `ecs` and `scheduler`
- Verify `endpoints-sg` allows HTTPS (443) ingress from VPC CIDR
- `apprunner-connector-sg` needs egress on port 443

### ECS Task Failures

Check CloudWatch Logs at `/ecs/georisk-dev-pipeline` for task output. Common issues:
- Missing environment variables (check task definition)
- S3 permissions (check task role policy)
- Network connectivity (tasks need public IP or NAT for STAC API access)

### RDS Connectivity

- Verify RDS is in the data subnets
- Check security group rules allow ingress from both App Runner connector and pipeline SGs
- PostGIS extension is created automatically by the EF Core migrations

### CloudFront Cache

After web UI updates, invalidate the cache:
```powershell
aws cloudfront create-invalidation --distribution-id <dist-id> --paths "/*"
```

Invalidations take 1-2 minutes. You can also test with an incognito/private browser window to bypass local cache.

### Pipeline Missing API URL / Key

The pipeline ECS task reads `GEORISK_API_URL` and `GEORISK_API_KEY` from SSM Parameter Store at launch time (via the ECS `secrets` block). If the pipeline can't reach the API:

1. Verify SSM parameters exist:
   ```powershell
   aws ssm get-parameter --name /georisk/dev/pipeline/api-url --query Parameter.Value
   aws ssm get-parameter --name /georisk/dev/pipeline/api-key --with-decryption --query Parameter.Value
   ```
2. Verify the pipeline execution role has `ssm:GetParameters` permission
3. Check CloudWatch logs at `/ecs/georisk-dev-pipeline` for injection errors

## Windows PowerShell Notes

The deploy script is designed for Windows PowerShell 5.x (the default). Key differences from PowerShell 7+ / bash:
- No `&&` operator for chaining commands (use `;` or separate statements)
- `--password-stdin` piping doesn't work with `docker login` (use `--password`)
- `curl` is aliased to `Invoke-WebRequest`; use `curl.exe` for the real curl
- Terraform `-target` flag must be quoted: `'-target=module.ecr'`
