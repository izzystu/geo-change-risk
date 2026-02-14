# Geo Change Risk Platform

Geospatial risk intelligence for critical infrastructure. Detects land-surface changes from satellite imagery, scores threat severity using terrain and proximity analysis, and delivers actionable risk events to asset operators.

*End-to-end geospatial engineering — satellite data pipelines, spatial analysis, pretrained and custom-trained ML models, and full-stack cloud architecture.*

## Screenshots

### Asset Map
![Interactive map showing assets](docs/screenshots/asset-map.png)

*Interactive map displaying assets to be monitored within a specified area of interest.*

### Processing Run Dashboard
![Processing run dashboard](docs/screenshots/processing-dashboard.png)

*Processing run management showing pipeline status, change polygon counts, and risk event summaries.*

### Before/After Imagery Comparison
![Before satellite imagery](docs/screenshots/before.png)

*Sentinel-2 imagery showing vegetation state before detected change event.*

![After satellite imagery](docs/screenshots/after.png)

*Sentinel-2 imagery showing vegetation state after detected change event (in this case, the 2018 Camp fire) with detected change polygons.*

### Risk Event Detail Panel
![Risk event displayed on map](docs/screenshots/risk-event-with-map.png)

*Detailed risk event displayed on map with explainable score breakdown showing individual factor contributions, in this case including a possible landslide event detected using the custom trained ML model.*

![Risk event displayed on map](docs/screenshots/risk-event-with-alert.png)

*Risk event alert with actionable instructions (can be integrated into a site inspection scheduling system).*

### Automated Scheduling
![Scheduling panel](docs/screenshots/scheduling-panel.png)

*Scheduling panel with configurable frequency, cloud cover threshold, and job history showing automated processing runs.*

## What This Demonstrates

This project combines three engineering disciplines into a single integrated platform:

### Geospatial Engineering
- Sentinel-2 satellite imagery acquisition via STAC API (Microsoft Planetary Computer)
- NDVI change detection with rasterio/numpy raster math and vectorization
- PostGIS spatial indexing and proximity queries (NetTopologySuite)
- USGS 3DEP terrain analysis — slope, aspect, and directional risk modeling

### Cloud Architecture & Infrastructure
- Multi-cloud portable design via three DI-swappable provider interfaces
- Terraform IaC deploying to AWS (App Runner, ECS Fargate Spot, RDS, S3, CloudFront, EventBridge)
- Scale-to-zero API (~$2/month idle) with on-demand pipeline compute
- Automated per-AOI scheduling with continuous temporal coverage chaining

### Machine Learning
- EuroSAT land cover classification (pretrained via TorchGeo) for risk context weighting
- Custom U-Net landslide segmentation trained on Landslide4Sense (14-channel input)
- Recall-optimized for safety-critical detection (0.78 recall vs 0.66 competition baseline)
- Graceful degradation — ML enhances but never blocks the core pipeline

## Why This Exists

Wildfires, landslides, and other land-surface changes threaten critical infrastructure — power lines, substations, hospitals, schools, and transportation corridors. The organizations responsible for these assets (electric utilities, pipeline operators, transportation agencies, emergency managers) typically learn about threats reactively, after damage has occurred or during costly manual inspections.

This platform turns freely available satellite data into **continuous, automated risk monitoring**:

1. **Sentinel-2 imagery** (ESA, 5-day revisit) provides regular snapshots of vegetation health across any area of interest
2. **NDVI change detection** identifies where and how severely vegetation has been lost or altered
3. **Terrain modeling** (USGS 3DEP elevation data) determines whether changes are upslope of assets — a critical factor for debris flow and fire spread risk
4. **ML land cover classification** (EuroSAT via TorchGeo) distinguishes high-risk events like forest fires from routine changes like crop harvests, reducing false positives
5. **ML landslide detection** (custom U-Net trained on Landslide4Sense) identifies debris flows on steep terrain — a critical correlated hazard after wildfire
6. **Multi-factor risk scoring** produces a 0-100 score with full explainability — operators can see exactly why an event was flagged and what factors contributed

The result is a prioritized feed of risk events that tells an asset operator: *"This specific vegetation loss, 200 meters upslope of your substation on a 30-degree slope, has a risk score of 82 (Critical) — here's the before/after imagery."*

## Key Features

- **Satellite Change Detection** — Automated NDVI change detection from Sentinel-2 imagery via Microsoft Planetary Computer STAC API
- **Terrain-Aware Scoring** — USGS 3DEP elevation data powers slope, aspect, and directional risk analysis (upslope threats score higher)
- **Asset Proximity Analysis** — PostGIS spatial queries calculate distances between detected changes and infrastructure assets
- **ML Land Cover Context** — EuroSAT pretrained model (via TorchGeo) classifies land cover to weight risk appropriately (forest fire vs. crop harvest)
- **ML Landslide Detection** — Custom U-Net segmentation model trained on Landslide4Sense dataset identifies debris flows in steep terrain from 14-channel satellite + elevation input
- **Explainable Risk Scores** — Every score includes a full breakdown of contributing factors and their individual weights
- **Automated Scheduling** — Per-AOI cron-based scheduling with configurable cloud cover thresholds and continuous temporal coverage. See [docs/automated-scheduling.md](docs/automated-scheduling.md)
- **Interactive Map UI** — ArcGIS Maps SDK with before/after imagery comparison, layer controls, and risk event exploration
- **Dismiss/Act Workflow** — Risk events support operational triage with dismiss and action tracking

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Database** | PostgreSQL + PostGIS | Spatial data storage and queries |
| **Object Storage** | MinIO (local) / S3 (AWS) | Raster imagery and processing artifacts |
| **API** | ASP.NET Core 8 | REST API with EF Core + NetTopologySuite |
| **Raster Pipeline** | Python 3.11+ | Geospatial processing (rasterio, geopandas, pystac-client) |
| **Web UI** | SvelteKit + ArcGIS Maps SDK | Interactive mapping and visualization |
| **Background Jobs** | Hangfire (local) / EventBridge (AWS) | Scheduled processing and notifications |
| **Cloud Deployment** | Terraform + AWS (App Runner, ECS Fargate, RDS, S3, CloudFront) | Production cloud infrastructure |
| **ML Classification** | PyTorch + TorchGeo | Land cover classification (EuroSAT) |
| **ML Segmentation** | PyTorch + segmentation-models-pytorch | Landslide detection (custom-trained U-Net) |

## Architecture

### Local Development

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Web UI (SvelteKit)                             │
│                        ArcGIS Maps SDK                                  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            API (.NET 8)                                 │
│       Areas of Interest │ Assets │ Processing │ Risk Events             │
│                      Hangfire Scheduler                                 │
└───────────┬─────────────────────────────────────────────┬───────────────┘
            │                                             │ triggers
            ▼                                             ▼
┌───────────────────────┐                   ┌─────────────────────────────┐
│  PostgreSQL + PostGIS │                   │    Raster Pipeline (Python) │
│  - AOIs & Assets      │                   │    - STAC Search            │
│  - Processing Runs    │◄──────────────────│    - NDVI Change Detection  │
│  - Change Polygons    │                   │    - Terrain Analysis       │
│  - Risk Events        │                   │    - ML Land Cover          │
│                       │                   │    - ML Landslide Detection │
└───────────────────────┘                   │    - Risk Scoring           │
                                            └──────────────┬──────────────┘
                                                           │
                                                           ▼
                                            ┌─────────────────────────────┐
                                            │    Object Storage (MinIO)   │
                                            │    - Satellite Imagery      │
                                            │    - NDVI Rasters           │
                                            │    - DEM Tiles              │
                                            │    - ML Models              │
                                            └─────────────────────────────┘
```

### AWS Deployment

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   Web UI (SvelteKit + <<CloudFront>>)                   │
│                        ArcGIS Maps SDK                                  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      API (.NET 8 + <<App Runner>>)                      │
│       Areas of Interest │ Assets │ Processing │ Risk Events             │
│                    <<EventBridge>> Scheduler                            │
└───────────┬─────────────────────────────────────────────┬───────────────┘
            │                                             │ triggers
            ▼                                             ▼
┌───────────────────────┐                   ┌─────────────────────────────┐
│  PostgreSQL + PostGIS │                   │    Raster Pipeline (Python) │
│  <<RDS>>              │                   │    <<ECS Fargate Spot>>     │
│  - AOIs & Assets      │                   │    - STAC Search            │
│  - Processing Runs    │◄──────────────────│    - NDVI Change Detection  │
│  - Change Polygons    │                   │    - Terrain Analysis       │
│  - Risk Events        │                   │    - ML Land Cover          │
│                       │                   │    - ML Landslide Detection │
└───────────────────────┘                   │    - Risk Scoring           │
                                            └──────────────┬──────────────┘
                                                           │
                                                           ▼
                                            ┌─────────────────────────────┐
                                            │    Object Storage (<<S3>>)  │
                                            │      - Satellite Imagery    │
                                            │      - NDVI Rasters         │
                                            │      - DEM Tiles            │
                                            │      - ML Models            │
                                            └─────────────────────────────┘
```

The `<<marked>>` items are the only differences between deployments — AWS managed services replace local equivalents:

| Component | Local | AWS |
|-----------|-------|-----|
| **Web Hosting** | SvelteKit dev server | CloudFront CDN |
| **API Hosting** | localhost | App Runner (scale-to-zero) |
| **Scheduler** | Hangfire (in-process) | EventBridge |
| **Database** | PostgreSQL container | RDS PostgreSQL |
| **Pipeline Execution** | Local subprocess | ECS Fargate Spot |
| **Object Storage** | MinIO | S3 |

Three DI-swappable provider interfaces (`IObjectStorageService`, `ISchedulerService`, `IPipelineExecutor`) enable the same application code to run against either environment — local services swap for AWS managed services via configuration.

## Risk Scoring Model

The platform uses a multi-factor risk scoring model (0-100 scale):

| Factor | Weight | Description |
|--------|--------|-------------|
| **Distance** | 28 pts | Proximity of change to asset (<100m = max score) |
| **NDVI Drop** | 25 pts | Severity of vegetation loss (more negative = higher risk) |
| **Area** | 15 pts | Size of change polygon |
| **Slope + Direction** | 20 pts | Terrain steepness; upslope (landslide/debris risk) 1.5-2.5x, downslope (fire risk) 0.7-0.9x |
| **Aspect** | 5 pts | South-facing slopes = higher fire risk |
| **Land Cover** | multiplier | ML-classified context: Forest=1.0x, Crop=0.3x, Highway=0.25x (requires `[ml]` deps) |
| **Landslide** | multiplier | ML-detected debris on steep terrain: 1.8x base, +0.5x if upslope, capped at 2.5x |
| **Asset Criticality** | multiplier | Critical assets (hospitals, substations) get 2x weight |

**Risk Levels:** Critical (75-100), High (50-74), Medium (25-49), Low (0-24)

## Machine Learning

The platform uses two ML models that integrate into the pipeline as optional dependencies — the pipeline degrades gracefully without them.

### Land Cover Classification (EuroSAT)

Pretrained EuroSAT model (via TorchGeo) classifies the land cover around each change polygon. This provides context for risk scoring: a vegetation loss event in forest land (1.0x) is treated very differently from one on agricultural land (0.3x) where seasonal clearing is routine.

### Landslide Detection (Custom U-Net)

A U-Net segmentation model trained in-house on the [Landslide4Sense](https://github.com/iarai/Landslide4Sense-2022) dataset to detect landslide debris in satellite imagery. Post-fire terrain loses the root systems that stabilize slopes, making debris flow a critical correlated hazard for downstream infrastructure.

**Training pipeline** (`machine-learning/landslide/`):
- **Architecture:** U-Net with ResNet34 encoder (via segmentation-models-pytorch), pretrained on ImageNet and adapted to 14-channel input
- **Dataset:** Landslide4Sense — 3,799 training patches of 128x128 pixels, each with 12 Sentinel-2 spectral bands + slope + DEM elevation, with binary landslide masks
- **Training approach:** Combined Dice + BCE loss with class imbalance handling (pos_weight capping), AdamW optimizer, cosine LR scheduling, mixed-precision training, early stopping on validation IoU
- **Results:** IoU 0.47, F1 0.56, Recall 0.78 — achieves significantly higher recall than the [official competition baseline](https://github.com/iarai/Landslide4Sense-2022) (0.78 vs. 0.66) at comparable F1, prioritizing detection completeness over precision for a safety-critical application. Full training logs and hyperparameter search across 8 runs documented in [`TRAINING.md`](machine-learning/landslide/TRAINING.md)

**Inference integration** (`src/pipeline/georisk/raster/landslide.py`):
- Assembles 14-channel input patches from data the pipeline already produces (Sentinel-2 bands + USGS 3DEP terrain)
- Only evaluates polygons on steep terrain (slope > 10°) to focus on plausible landslide locations
- Dual classification criteria (mean probability + pixel fraction thresholds) to control false positive rate
- Classified landslide polygons receive a 1.8x-2.5x risk score multiplier, stacking with directional slope factors

**Model storage:** The trained model (~94 MB) is stored in the `ml-models` S3/MinIO bucket (not in git). The pipeline auto-downloads it to `~/.cache/georisk/models/` on first use. Upload with `georisk model upload <path>`, or train your own following [`TRAINING.md`](machine-learning/landslide/TRAINING.md).

## Architecture Decisions

- **Multi-process separation of concerns** — .NET handles API orchestration, auth, and job scheduling while Python handles heavy geospatial processing. Each stack uses its strongest ecosystem (EF Core + PostGIS for spatial CRUD, rasterio + numpy for raster math) rather than forcing one language to do everything.
- **Explainable scoring over black-box classification** — Every risk score includes a full factor breakdown so operators can understand *why* an event was flagged, not just that it was. This is essential for operational trust and regulatory defensibility.
- **Graceful ML degradation** — PyTorch and TorchGeo are optional dependencies. The pipeline produces useful risk scores without ML; land cover classification and landslide detection enhance accuracy when available but never block the core workflow.
- **Additive scoring with multipliers** — Base factors (distance, NDVI drop, area, slope, aspect) are additive and auditable. Context multipliers (land cover, asset criticality, landslide) scale the result. This makes the model transparent and tunable without requiring retraining.
- **PostGIS spatial indexing for proximity queries** — GIST indexes on geometries enable fast nearest-asset lookups across thousands of infrastructure features, keeping risk scoring performant as asset counts grow.

## Project Structure

```
geo-change-risk/
├── src/
│   ├── api/                    # .NET 8 REST API
│   │   ├── GeoChangeRisk.Api/      # Controllers, services, jobs
│   │   ├── GeoChangeRisk.Data/     # EF Core models, migrations
│   │   └── GeoChangeRisk.Contracts/ # DTOs and shared types
│   ├── pipeline/               # Python raster processing
│   │   └── georisk/               # CLI and processing modules
│   └── web-ui/                 # SvelteKit frontend
├── areas-of-interest/          # AOI configurations and data scripts
│   └── paradise/                  # Paradise, CA (Camp Fire area)
├── infra/                      # Infrastructure configuration
│   └── local/                     # Docker Compose, env templates
├── deployments/                # Deployment scripts
│   ├── local/                     # Local development setup
│   ├── aws/                       # AWS deployment (Terraform + deploy script)
│   └── azure/                     # Azure deployment (planned)
├── machine-learning/           # ML model training
│   └── landslide/                 # U-Net landslide segmentation (training pipeline)
└── docs/                       # Documentation
```

## Getting Started

Prerequisites: Docker Desktop, .NET 8 SDK, Python 3.11+, Node.js 18+

```powershell
# 1. Start infrastructure (generates credentials, starts PostgreSQL + MinIO)
.\deployments\local\setup.ps1

# 2. Start API
cd src/api/GeoChangeRisk.Api
dotnet run

# 3. Start Web UI (in another terminal)
cd src/web-ui
npm install && npm run dev
```

Open http://localhost:5173. See [docs/getting-started.md](docs/getting-started.md) for full instructions including sample data initialization and running change detection.

## Cloud Deployment

The platform deploys to AWS with a single script. See [docs/aws-deployment.md](docs/aws-deployment.md) for the full deployment guide.

```powershell
.\deployments\aws\scripts\deploy.ps1
```

Architecture: App Runner (scale-to-zero API, ~$2/month idle) + ECS Fargate Spot (on-demand pipeline) + RDS PostgreSQL + S3 + CloudFront + EventBridge Scheduler + VPC Endpoints. Estimated ~$47/month total.

The architecture is multi-cloud portable via three DI-swappable interfaces (`IObjectStorageService`, `ISchedulerService`, `IPipelineExecutor`). See [docs/multi-cloud-strategy.md](docs/multi-cloud-strategy.md) for Azure and GCP deployment paths.

## ArcGIS Pro Integration (Optional)

Optional read-only PostGIS views (`v_areas_of_interest`, `v_asset_*`, `v_change_polygons`, `v_risk_events`) can be installed for direct use in ArcGIS Pro. The views are not created automatically — run `infra/local/optional/arcgis-views.sql` manually after EF Core migrations. See [docs/arcgis-pro-setup.md](docs/arcgis-pro-setup.md) for setup instructions.

## Contact

Questions, feedback, or want to see a live demo? Reach out at rob@izzystu.com — I'd love to chat.

## License

This project is licensed under the [MIT License](LICENSE).
