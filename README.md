# Geo Change Risk Platform

Geospatial risk intelligence for critical infrastructure. Detects land-surface changes from satellite imagery, scores threat severity using terrain and proximity analysis, and delivers actionable risk events to asset operators.

*Designed and built by a senior geospatial software architect with 25+ years spanning GIS, cloud platforms, and applied AI — from cartography and petroleum mapping through real-time medical systems to satellite remote sensing.*

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
- **Interactive Map UI** — ArcGIS Maps SDK with before/after imagery comparison, layer controls, and risk event exploration
- **Dismiss/Act Workflow** — Risk events support operational triage with dismiss and action tracking

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Database** | PostgreSQL + PostGIS | Spatial data storage and queries |
| **Object Storage** | MinIO (S3-compatible) | Raster imagery and processing artifacts |
| **API** | ASP.NET Core 8 | REST API with EF Core + NetTopologySuite |
| **Raster Pipeline** | Python 3.11+ | Geospatial processing (rasterio, geopandas, pystac) |
| **Web UI** | SvelteKit + ArcGIS Maps SDK + D3.js | Interactive mapping, visualization, and data graphics |
| **Background Jobs** | Hangfire | Scheduled processing and notifications |
| **ML Classification** | PyTorch + TorchGeo | Land cover classification (EuroSAT) |
| **ML Segmentation** | PyTorch + segmentation-models-pytorch | Landslide detection (custom-trained U-Net) |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Web UI (SvelteKit)                         │
│                     ArcGIS Maps SDK + Interactive Panels                │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           REST API (.NET 8)                             │
│              Areas of Interest │ Assets │ Processing │ Risk Events      │
└───────────┬─────────────────────────────────────────────┬───────────────┘
            │                                             │
            ▼                                             ▼
┌───────────────────────┐                   ┌─────────────────────────────┐
│  PostgreSQL/PostGIS   │                   │    Python Raster Pipeline   │
│  - AOIs & Assets      │                   │    - STAC Search            │
│  - Processing Runs    │◄──────────────────│    - NDVI Calculation       │
│  - Change Polygons    │                   │    - Change Detection       │
│  - Risk Events        │                   │    - Terrain Analysis       │
└───────────────────────┘                   │    - ML Land Cover          │
                                            │    - ML Landslide Detection │
                                            │    - Risk Scoring           │
                                            └──────────────┬──────────────┘
                                                           │
                                                           ▼
                                            ┌─────────────────────────────┐
                                            │     MinIO Object Storage    │
                                            │     - Satellite Imagery     │
                                            │     - NDVI Rasters          │
                                            │     - DEM Tiles             │
                                            └─────────────────────────────┘
```

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
│   ├── aws/                       # AWS deployment (planned)
│   └── azure/                     # Azure deployment (planned)
├── machine-learning/           # ML model training
│   └── landslide/                 # U-Net landslide segmentation (training pipeline)
└── docs/                       # Documentation
```

## Getting Started

### Prerequisites

- Docker Desktop
- .NET 8 SDK
- Python 3.11+
- Node.js 18+

### Quick Start

**Windows (PowerShell):**
```powershell
.\deployments\local\setup.ps1
```

**Linux/Mac:**
```bash
chmod +x deployments/local/setup.sh
./deployments/local/setup.sh
```

This will:
1. Generate random credentials for local development
2. Start PostgreSQL/PostGIS and MinIO containers
3. Initialize MinIO buckets
4. Display your credentials at the end

Credentials are stored in `infra/local/.env` (gitignored).

### Initialize Sample Data (Paradise, CA)

```bash
cd areas-of-interest/paradise
pip install -r requirements.txt
python download-assets.py
python initialize.py
```

### Start the Application

```bash
# Terminal 1: Start API
cd src/api/GeoChangeRisk.Api
dotnet run

# Terminal 2: Start Web UI
cd src/web-ui
npm install
npm run dev
```

Open http://localhost:5173 to view the application.

### Run Change Detection

```bash
cd src/pipeline
pip install -e ".[ml]"   # includes ML land cover classification
# Or: pip install -e .   # base pipeline without ML

# Search for available imagery
python -m georisk search --aoi-id paradise-ca --date-range 2018-01-01/2018-12-31

# Run change detection (before/after Camp Fire)
python -m georisk process --aoi-id paradise-ca --before 2018-10-01 --after 2018-12-01
```

## Sample Area of Interest: Paradise, CA

The included Paradise AOI covers the 2018 Camp Fire area with ~3,900 infrastructure assets:

- **Buildings:** 1,420 structures from OpenStreetMap
- **Roads:** 2,354 road segments
- **Power Infrastructure:** 117 power features + 6 CEC transmission lines
- **Emergency Services:** 6 fire stations, 11 schools

## Current Status

| Component | Status | Description |
|-----------|--------|-------------|
| Infrastructure | Complete | Docker Compose, PostgreSQL/PostGIS, MinIO |
| REST API | Complete | Full CRUD for AOIs, assets, processing runs, risk events |
| Web UI | Complete | Interactive map, before/after imagery, risk event triage |
| Raster Pipeline | Complete | STAC search, NDVI change detection, vectorization |
| Terrain Analysis | Complete | USGS 3DEP slope/aspect/elevation, directional scoring |
| Risk Scoring | Complete | Multi-factor additive scoring with land cover and criticality multipliers |
| ML Land Cover | Complete | EuroSAT classification via TorchGeo (optional `[ml]` dependency) |
| ML Landslide Detection | Complete | Custom U-Net trained on Landslide4Sense, integrated into pipeline and risk scoring |
| Testing | Complete | xUnit (.NET API controllers, services, models) + pytest (Python pipeline raster processing, risk scoring) |

## Roadmap

### Automated Scheduling & Data Quality Checks

Automatically monitor each AOI for new Sentinel-2 imagery on a configurable schedule. When acceptable data is available (cloud cover below threshold), trigger a processing run without manual intervention.

- Per-AOI cloud cover thresholds and scheduling via cron expressions
- New `georisk check` CLI command to query for new imagery availability
- Hangfire recurring jobs to orchestrate the check-and-process cycle
- Guard logic to prevent duplicate runs when processing is already in progress

### AWS Cloud Deployment

Deploy the full platform to AWS using Terraform. Replaces local Docker infrastructure with managed cloud services while preserving the local development workflow.

- **Compute:** API on ECS Fargate (always-on), pipeline as on-demand ECS Fargate tasks
- **Storage:** S3 replaces MinIO (boto3 already used — minimal code changes)
- **Database:** RDS PostgreSQL 16 with PostGIS
- **Web UI:** Static SvelteKit build served via CloudFront + S3
- **IaC:** Modular Terraform with VPC, ALB, security groups, IAM roles

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

## License

This project is licensed under the [MIT License](LICENSE).
