# AWS Terraform Deployment

Infrastructure-as-code for deploying the Geo Change Risk platform to AWS.

## Architecture

```
Internet
   │
   ├── CloudFront CDN ──→ S3 (static SvelteKit build)
   │
   └── App Runner (.NET API, scale-to-zero)
           │                                          ┌─────────────────────┐
           ├──→ RDS PostgreSQL + PostGIS  ←───────────┤  VPC (10.0.0.0/16)  │
           ├──→ S3 (via Gateway Endpoint, free)       │                     │
           ├──→ ECS API (via Interface Endpoint)      │  Public subnets:    │
           └──→ Scheduler API (via Interface Endpoint)│    ECS tasks        │
                   │                                  │    (public IP)      │
                   └──→ ECS Fargate Spot task          │                     │
                          (Python pipeline, on-demand) │  Data subnets:      │
                          ├──→ STAC / USGS (internet)  │    RDS              │
                          ├──→ S3 (upload results)     │    VPC endpoints    │
                          └──→ App Runner (callbacks)  └─────────────────────┘
```

## Module Structure

```
deployments/aws/
├── main.tf                 Root module — wires all child modules together
├── variables.tf            Input variables (region, env_name, api_key)
├── outputs.tf              Exported values (API URL, CloudFront URL, bucket names)
├── backend.tf              Terraform backend configuration
├── environments/
│   └── dev.tfvars          Per-environment variable values
├── scripts/
│   └── deploy.ps1          One-command deployment script (build, push, apply, deploy UI)
└── modules/
    ├── networking/         VPC, subnets, internet gateway, VPC endpoints, security groups
    ├── database/           RDS PostgreSQL, Secrets Manager credentials
    ├── storage/            S3 buckets (5 data + 1 web UI), lifecycle rules, CORS
    ├── ecr/                Container registries for API and pipeline images
    ├── pipeline/           ECS cluster, Fargate task definition, IAM roles
    ├── apprunner/          App Runner service, VPC connector, IAM roles
    ├── scheduler/          EventBridge schedule group, IAM role
    └── cdn/                CloudFront distribution, Origin Access Control
```

## Module Dependency Graph

Arrows show data flow (outputs → inputs). Terraform uses these to determine creation order.

```
networking ──→ database        (data_subnet_ids, rds_security_group_id)
networking ──→ pipeline        (public_subnet_ids, pipeline_security_group_id)
networking ──→ apprunner       (vpc_id, public_subnet_ids, rds_security_group_id)
networking ──→ scheduler       (public_subnet_ids, pipeline_security_group_id)

database ────→ pipeline        (credentials_secret_arn)
database ────→ apprunner       (credentials_secret_arn, endpoint, db_name)

storage ─────→ pipeline        (bucket_arns, bucket_names)
storage ─────→ apprunner       (bucket_arns, bucket_names)
storage ─────→ cdn             (webui_bucket_name, webui_bucket_arn)

ecr ─────────→ pipeline        (pipeline_repo_url)
ecr ─────────→ apprunner       (api_repo_url, api_repo_arn)

pipeline ────→ apprunner       (cluster_arn, task_definition_arn, task/execution role ARNs)
pipeline ────→ scheduler       (cluster_arn, task_definition_arn, task/execution role ARNs)

scheduler ───→ apprunner       (scheduler_role_arn)
```

**No circular dependency:** The pipeline task definition references the API URL
and API key via SSM Parameter Store ARN strings (constructed from region,
account ID, and env_name — not Terraform resource references). The apprunner
module writes these SSM parameters after creating the App Runner service. ECS
resolves the SSM values at task launch time, so the pipeline module has no
Terraform dependency on the apprunner module.

## What Each Module Creates

### networking/ — VPC and Network Plumbing

| Resource | Purpose |
|----------|---------|
| VPC (`10.0.0.0/16`) | Isolated network for all resources |
| 2 public subnets | ECS tasks run here (get public IPs for internet access) |
| 2 data subnets | RDS lives here (no internet route, private) |
| Internet Gateway | Gives public subnets a route to the internet |
| S3 Gateway Endpoint | Free path from VPC to S3 (no internet needed) |
| ECS Interface Endpoint | Private path to ECS API (~$7.20/month) |
| Scheduler Interface Endpoint | Private path to EventBridge Scheduler API (~$7.20/month) |
| Security groups | Firewall rules: pipeline-sg, rds-sg, endpoints-sg |

**Why VPC endpoints?** App Runner with `egress_type = "VPC"` routes ALL traffic
through the VPC connector. Connector ENIs don't get public IPs, so AWS API
calls (like `ecs:RunTask`) have no route to the public AWS endpoints. Interface
endpoints create private DNS entries that redirect these calls to private IPs
inside the VPC. The S3 gateway endpoint is a simpler (and free) variant that
adds routes to the route table.

### database/ — PostgreSQL + PostGIS

| Resource | Purpose |
|----------|---------|
| RDS PostgreSQL 16 (db.t4g.micro) | Spatial database with PostGIS 3.4 |
| `random_password` | Generates 32-char password at apply time |
| Secrets Manager secret | Stores connection string, read by App Runner at startup |
| DB subnet group | Places RDS in the private data subnets |

The password is generated once by Terraform and stored in state. It's never
in source code — App Runner reads it from Secrets Manager via
`runtime_environment_secrets`.

### storage/ — S3 Buckets

| Bucket | Purpose | Lifecycle |
|--------|---------|-----------|
| `georisk-{env}-rasters` | Raw NDVI raster data | Auto-delete after 90 days |
| `georisk-{env}-artifacts` | Processing artifacts | Auto-delete after 90 days |
| `georisk-{env}-imagery` | RGB satellite imagery (before/after) | Permanent |
| `georisk-{env}-changes` | Change detection GeoJSON | Permanent |
| `georisk-{env}-models` | ML model weights | Permanent |
| `georisk-{env}-webui` | Static SvelteKit build | Overwritten on deploy |

All buckets are private (public access blocked), encrypted (AES256), and
accessed via presigned URLs or IAM roles. Imagery and changes buckets have
CORS rules so browsers can load presigned URLs.

### ecr/ — Container Registries

Two private registries: `georisk-{env}-api` and `georisk-{env}-pipeline`.
Docker images are built locally, pushed here, and pulled by App Runner / ECS.

### pipeline/ — ECS Fargate Cluster and Task

| Resource | Purpose |
|----------|---------|
| ECS cluster | Logical grouping (Fargate = no servers to manage) |
| Capacity providers | FARGATE_SPOT as default (cheaper, interruptible) |
| Task definition | Container recipe: image, CPU/memory, env vars, log config |
| CloudWatch log group | Receives container stdout/stderr |
| Execution role | Used by ECS to pull images, write logs, and read SSM secrets |
| Task role | Used by the running container for S3, Secrets Manager |

**Execution role vs task role:** The execution role is ECS's identity for
*launching* the container (ECR pull, CloudWatch). The task role is the
container's identity *while running* (S3 read/write, Secrets Manager).

### apprunner/ — API Service

| Resource | Purpose |
|----------|---------|
| App Runner service | Runs the .NET API, scales to zero when idle |
| VPC connector | Bridges App Runner into the VPC (for RDS, VPC endpoints) |
| Connector security group | Allows egress: PostgreSQL (5432), HTTPS (443) |
| RDS ingress rule | Allows connector SG to reach the database |
| ECR access role | Lets App Runner pull images from ECR |
| Instance role | API's runtime identity: S3, ECS RunTask, Scheduler, Secrets |

App Runner auto-deploys when a new image is pushed to ECR
(`auto_deployments_enabled = true`).

### scheduler/ — EventBridge Cron

| Resource | Purpose |
|----------|---------|
| Schedule group (`georisk-schedules`) | Namespace for per-AOI cron schedules |
| IAM role | Allows EventBridge to call ECS RunTask |

Individual schedules are created at runtime by the .NET API when you configure
a cron expression on an AOI. Terraform only creates the group and role.

### cdn/ — CloudFront Distribution

| Resource | Purpose |
|----------|---------|
| CloudFront distribution | CDN for the static web UI |
| Origin Access Control | Lets CloudFront read from the private S3 bucket |
| S3 bucket policy | Grants CloudFront `GetObject` permission |

## Estimated Monthly Cost (us-east-1)

| Service | ~Cost |
|---------|-------|
| RDS PostgreSQL (db.t4g.micro, 20 GB) | $24 |
| App Runner (scale-to-zero) | ~$2 |
| ECS Fargate Spot (~4 hrs/month) | $0.60 |
| S3 + CloudFront + ECR | $5 |
| VPC Interface Endpoints (2, single AZ) | ~$15 |
| EventBridge Scheduler | $0 (free tier) |
| Secrets Manager | $0.80 |
| **Total** | **~$47/month** |

## Deployment

See [docs/aws-deployment.md](../../docs/aws-deployment.md) for the full
deployment guide, or use the one-command deploy script:

```powershell
$env:TF_VAR_api_key = "your-secure-key"
.\deployments\aws\scripts\deploy.ps1
```

## Teardown

```powershell
$env:TF_VAR_api_key = "your-secure-key"
terraform destroy -var-file="environments\dev.tfvars"
```
