# Geo Change Risk Platform

A geospatial risk intelligence platform that combines satellite imagery analysis, terrain modeling, and proximity-based risk scoring to monitor land-surface changes and assess threats to critical infrastructure.

## The Problem

Wildfires, landslides, and other land-surface changes pose significant risks to critical infrastructure like power lines, substations, hospitals, and schools. Traditional monitoring approaches are reactive - damage is discovered after the fact. This platform enables **proactive risk detection** by:

- Automatically detecting vegetation loss from satellite imagery
- Calculating risk scores based on proximity to critical assets
- Incorporating terrain analysis (slope, aspect, upslope/downslope relationships)
- Generating actionable risk events with explainable scores

## Key Features

- **Satellite Imagery Analysis** - Automated NDVI change detection using Sentinel-2 imagery via Microsoft Planetary Computer
- **Terrain-Aware Risk Scoring** - Incorporates USGS 3DEP elevation data for slope/aspect analysis and directional risk weighting
- **Asset Proximity Analysis** - Spatial queries against infrastructure datasets (power lines, substations, hospitals, schools)
- **Interactive Map UI** - ArcGIS Maps SDK visualization with before/after imagery comparison
- **Extensible Architecture** - Designed for ML integration (change classification, burn severity prediction)

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Database** | PostgreSQL + PostGIS | Spatial data storage and queries |
| **Object Storage** | MinIO (S3-compatible) | Raster imagery and processing artifacts |
| **API** | ASP.NET Core 8 | REST API with EF Core + NetTopologySuite |
| **Raster Pipeline** | Python 3.11+ | Geospatial processing (rasterio, geopandas, pystac) |
| **Web UI** | SvelteKit + ArcGIS Maps SDK | Interactive mapping and visualization |
| **Background Jobs** | Hangfire | Scheduled processing and notifications |
| **ML Framework** | PyTorch + TorchGeo | Change classification (planned) |

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
└───────────────────────┘                   │    - Risk Scoring           │
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
| **Slope + Direction** | 17 pts | Terrain steepness with upslope/downslope modifier |
| **Aspect** | 5 pts | South-facing slopes = higher fire risk |
| **Asset Criticality** | multiplier | Critical assets (hospitals, substations) get 2x weight |

**Risk Levels:** Critical (75-100), High (50-74), Medium (25-49), Low (0-24)

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
├── machine-learning/           # ML training and models (planned)
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
pip install -r requirements.txt

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

## Cloud Deployment

The platform is designed for cloud deployment while maintaining local development capability:

- **Object Storage:** MinIO locally, AWS S3 or Azure Blob Storage in cloud
- **Database:** Standard PostgreSQL/PostGIS on any cloud provider
- **API:** Containerized .NET application
- **Pipeline:** Can run as scheduled jobs (Hangfire) or serverless functions

Cloud deployment configurations for AWS and Azure are planned.

## Current Status

| Component | Status | Description |
|-----------|--------|-------------|
| Infrastructure | Complete | Docker Compose setup, PostgreSQL/PostGIS, MinIO |
| REST API | Complete | Full CRUD for AOIs, assets, processing runs, risk events |
| Web UI | Complete | Interactive map, layer controls, processing management |
| Raster Pipeline | Complete | STAC search, NDVI calculation, change detection |
| Risk Scoring | Complete | Multi-factor scoring with terrain analysis |
| Automation | In Progress | Scheduled jobs and notifications |
| ML Classification | Planned | Change type classification using TorchGeo |

## License

[License information to be added]

## Contributing

[Contribution guidelines to be added]
