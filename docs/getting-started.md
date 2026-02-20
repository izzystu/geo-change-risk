# Getting Started

## Prerequisites

- Docker Desktop
- .NET 8 SDK
- Python 3.11+
- Node.js 18+

## Quick Start

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

## Initialize Sample Data (Paradise, CA)

```bash
cd areas-of-interest/paradise
pip install -r requirements.txt
python download-assets.py
python initialize.py
```

## Start the Application

```bash
# Terminal 1: Start API
cd src/api/GeoChangeRisk.Api
dotnet run
# To run w/ log file: dotnet run 2>&1 | Tee-Object -FilePath "api-output.txt"

# Terminal 2: Start Web UI
cd src/web-ui
npm install
npm run dev
```

Open http://localhost:5173 to view the application.

## Run Change Detection

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
