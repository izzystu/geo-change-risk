# Geo Change Risk Platform

Geospatial risk intelligence platform that detects land-surface changes from satellite imagery and assesses threats to critical infrastructure. Monitors vegetation loss via NDVI change detection on Sentinel-2 imagery and scores risk based on proximity to assets (power lines, substations, hospitals, schools), terrain slope/aspect, and change magnitude.

## Architecture

Three main components communicate via REST API and shared PostgreSQL + S3-compatible storage:

- **API** (`src/api/`) — .NET 8 / ASP.NET Core REST API with EF Core + PostGIS spatial database, background jobs (processing + automated scheduling), and NetTopologySuite geometry. Four projects: `GeoChangeRisk.Api`, `GeoChangeRisk.Data`, `GeoChangeRisk.Contracts`, `GeoChangeRisk.Tests`.
- **Raster Pipeline** (`src/pipeline/`) — Python 3.11+ CLI (`georisk`) for satellite imagery search (STAC/Planetary Computer), NDVI calculation, change detection/vectorization, terrain analysis (USGS 3DEP), ML land cover classification (EuroSAT via TorchGeo), multi-factor risk scoring, and automated new imagery checks (`georisk check`).
- **Web UI** (`src/web-ui/`) — SvelteKit 2.0 frontend with ArcGIS Maps SDK for JavaScript and D3.js visualization. Before/after imagery comparison and interactive risk event display.

Three DI-swappable provider interfaces (`GeoChangeRisk.Contracts`) enable local and cloud deployment:
- **IObjectStorageService** — `ObjectStorageService` (MinIO) / `S3ObjectStorageService` (AWS S3)
- **ISchedulerService** — `HangfireSchedulerService` (local) / `EventBridgeSchedulerService` (AWS)
- **IPipelineExecutor** — `LocalPipelineExecutor` (subprocess) / `EcsPipelineExecutor` (AWS ECS Fargate)

**Local infrastructure** (Docker via `infra/local/`):
- PostgreSQL 16 + PostGIS 3.4, MinIO for S3-compatible object storage

**AWS infrastructure** (Terraform via `deployments/aws/`; see `docs/aws-deployment.md`):
- App Runner (API), RDS PostgreSQL, S3, ECS Fargate (pipeline), EventBridge Scheduler, CloudFront CDN

## Documentation

- `README.md` — Project overview, architecture diagram, tech stack, quick start guide
- `docs/arcgis-pro-setup.md` — ArcGIS Pro connection guide and PostGIS compatibility views
- `docs/aws-deployment.md` — AWS deployment guide
- `docs/multi-cloud-strategy.md` — Multi-cloud strategy documentation
- `areas-of-interest/paradise/README.md` — Paradise, CA sample AOI documentation and data sources

## Key Directories

```
src/api/GeoChangeRisk.Api/Controllers/   # 7 REST controllers (AOI, Assets, Changes, Imagery, Processing, RiskEvents, System)
src/api/GeoChangeRisk.Api/Services/      # Business logic + provider implementations (storage, geometry, scheduling, pipeline execution)
src/api/GeoChangeRisk.Api/Jobs/          # Hangfire background jobs (RasterProcessingJob, ScheduledCheckJob)
src/api/GeoChangeRisk.Data/Models/       # EF Core entity models (AreaOfInterest, Asset, ChangePolygon, RiskEvent, etc.)
src/api/GeoChangeRisk.Data/Migrations/   # Database schema migrations
src/pipeline/georisk/                    # Python pipeline modules (cli, stac, raster, risk, storage, db)
src/pipeline/georisk/raster/landcover.py # EuroSAT land cover classification (optional, requires torch+torchgeo)
src/web-ui/src/                          # SvelteKit routes and components
areas-of-interest/paradise/              # Sample AOI config, asset download/init scripts
infra/local/                             # Docker Compose, env templates
deployments/local/                       # Local setup scripts (setup.ps1 for Windows, setup.sh for Linux/Mac)
deployments/aws/                         # Terraform modules (apprunner, pipeline, scheduler, storage) and deploy script
```

## Development Setup

Prerequisites: Docker Desktop, .NET 8 SDK, Python 3.11+, Node.js 18+

1. Infrastructure: `.\deployments\local\setup.ps1` (generates credentials, starts PostgreSQL + MinIO containers)
2. API: `cd src/api/GeoChangeRisk.Api && dotnet run` (runs on localhost:5062, Swagger at `/swagger`, Hangfire at `/hangfire`)
3. Pipeline: `cd src/pipeline && pip install -e .` (base) or `pip install -e ".[ml]"` (with ML land cover classification), then `python -m georisk <command>` (commands: `search`, `check`, `process`, `fetch`, `status`, `health`, `model upload/download/list`)
4. Web UI: `cd src/web-ui && npm install && npm run dev` (runs on localhost:5173)

Credentials are generated into `infra/local/.env` (gitignored) and shared across components.

For AWS deployment, see `docs/aws-deployment.md`. AWS uses IAM roles instead of local credential files.

## Conventions

- All geometry uses WGS84 (SRID 4326) via PostGIS / NetTopologySuite
- Python pipeline uses `click` CLI, `structlog` for logging, `httpx` for API calls, `boto3` for object storage (MinIO locally, S3 in AWS)
- .NET API uses async/await throughout, EF Core migrations for schema changes
- Risk scores are 0-100 scale: Critical (75-100), High (50-74), Medium (25-49), Low (0-24)
- Risk scoring uses additive factors (distance, NDVI drop, area, slope+direction, aspect) with three multipliers: land cover context (0.25x-1.0x via EuroSAT classification), landslide detection (1.8x-2.5x for confirmed LandslideDebris, skips land cover suppression), and asset criticality (0.5x-2.0x)
- ML dependencies (torch, torchgeo) are optional — pipeline degrades gracefully without them
- Data model supports ML with MlConfidence, MlModelVersion, and ChangeType enum fields
- Automated scheduling uses per-AOI cron expressions (ProcessingSchedule field), the active ISchedulerService provider (Hangfire or EventBridge), and the `georisk check` CLI command
- ScheduledCheckJob guards against duplicate runs by checking for in-progress ProcessingRuns before creating new ones
- Scheduled runs chain dates: each run's "before" date = previous run's "after" date, creating continuous temporal coverage
- ML models stored in `ml-models` bucket (S3/MinIO), auto-downloaded to `~/.cache/georisk/models/` on first use
