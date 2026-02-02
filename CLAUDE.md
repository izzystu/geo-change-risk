# Geo Change Risk Platform

Geospatial risk intelligence platform that detects land-surface changes from satellite imagery and assesses threats to critical infrastructure. Monitors vegetation loss via NDVI change detection on Sentinel-2 imagery and scores risk based on proximity to assets (power lines, substations, hospitals, schools), terrain slope/aspect, and change magnitude.

## Architecture

Three main components communicate via REST API and shared PostgreSQL + MinIO storage:

- **API** (`src/api/`) — .NET 8 / ASP.NET Core REST API with EF Core + PostGIS spatial database, Hangfire background jobs, and NetTopologySuite geometry. Four projects: `GeoChangeRisk.Api`, `GeoChangeRisk.Data`, `GeoChangeRisk.Contracts`, `GeoChangeRisk.Tests`.
- **Raster Pipeline** (`src/pipeline/`) — Python 3.11+ CLI (`georisk`) for satellite imagery search (STAC/Planetary Computer), NDVI calculation, change detection/vectorization, terrain analysis (USGS 3DEP), ML land cover classification (EuroSAT via TorchGeo), and multi-factor risk scoring.
- **Web UI** (`src/web-ui/`) — SvelteKit 2.0 frontend with ArcGIS Maps SDK for JavaScript and D3.js visualization. Before/after imagery comparison and interactive risk event display.

Supporting infrastructure:
- **PostgreSQL 16 + PostGIS 3.4** — spatial data storage (Docker via `infra/local/`)
- **MinIO** — S3-compatible object storage for rasters and artifacts

## Documentation

- `README.md` — Project overview, architecture diagram, tech stack, quick start guide
- `IMPLEMENTATION-PLAN.md` — Roadmap with phase-by-phase progress tracking
- `docs/ml-integration-ideas.md` — ML model proposals (Prithvi-EO-2.0 burn scar segmentation, EuroSAT land cover)
- `areas-of-interest/paradise/README.md` — Paradise, CA sample AOI documentation and data sources

## Key Directories

```
src/api/GeoChangeRisk.Api/Controllers/   # 7 REST controllers (AOI, Assets, Changes, Imagery, Processing, RiskEvents, System)
src/api/GeoChangeRisk.Api/Services/      # Business logic (object storage, geometry, notifications)
src/api/GeoChangeRisk.Api/Jobs/          # Hangfire background job definitions
src/api/GeoChangeRisk.Data/Models/       # EF Core entity models (AreaOfInterest, Asset, ChangePolygon, RiskEvent, etc.)
src/api/GeoChangeRisk.Data/Migrations/   # Database schema migrations
src/pipeline/georisk/                    # Python pipeline modules (cli, stac, raster, risk, storage, db)
src/pipeline/georisk/raster/landcover.py # EuroSAT land cover classification (optional, requires torch+torchgeo)
src/web-ui/src/                          # SvelteKit routes and components
areas-of-interest/paradise/              # Sample AOI config, asset download/init scripts
infra/local/                             # Docker Compose, env templates
deployments/local/                       # Setup scripts (setup.ps1 for Windows, setup.sh for Linux/Mac)
```

## Development Setup

Prerequisites: Docker Desktop, .NET 8 SDK, Python 3.11+, Node.js 18+

1. Infrastructure: `.\deployments\local\setup.ps1` (generates credentials, starts PostgreSQL + MinIO containers)
2. API: `cd src/api/GeoChangeRisk.Api && dotnet run` (runs on localhost:5062, Swagger at `/swagger`, Hangfire at `/hangfire`)
3. Pipeline: `cd src/pipeline && pip install -e .` (base) or `pip install -e ".[ml]"` (with ML land cover classification), then `python -m georisk <command>`
4. Web UI: `cd src/web-ui && npm install && npm run dev` (runs on localhost:5173)

Credentials are generated into `infra/local/.env` (gitignored) and shared across components.

## Conventions

- All geometry uses WGS84 (SRID 4326) via PostGIS / NetTopologySuite
- Python pipeline uses `click` CLI, `structlog` for logging, `httpx` for API calls, `boto3` for MinIO
- .NET API uses async/await throughout, EF Core migrations for schema changes
- Risk scores are 0-100 scale: Critical (75-100), High (50-74), Medium (25-49), Low (0-24)
- Risk scoring uses additive factors (distance, NDVI drop, area, slope+direction, aspect) with two multipliers: land cover context (0.25x-1.0x via EuroSAT classification) and asset criticality (0.5x-2.0x)
- ML dependencies (torch, torchgeo) are optional — pipeline degrades gracefully without them
- Data model supports ML with MlConfidence, MlModelVersion, and ChangeType enum fields
