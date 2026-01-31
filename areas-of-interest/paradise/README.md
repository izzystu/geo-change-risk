# Paradise, California - Area of Interest

This AOI covers the area affected by the 2018 Camp Fire, the deadliest and most destructive wildfire in California history.

## Location

- **Center**: -121.62, 39.76 (lon, lat)
- **Bounding Box**: [-121.70, 39.70, -121.55, 39.85]
- **Area**: Approximately 15km x 17km

## Data Sources

### OpenStreetMap (via Overpass API)
- Buildings
- Roads
- Power lines (local distribution)

### California Energy Commission (CEC)
- Transmission lines (high voltage)
- Substations

### HIFLD (Homeland Infrastructure Foundation-Level Data)
- Fire stations
- Hospitals
- Schools

### CAL FIRE
- Camp Fire perimeter (for context/reference)

## Usage

### Prerequisites

1. Python 3.11+ with pip
2. API running at http://localhost:5074
3. Virtual environment recommended

### Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Activate (Linux/Mac)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Download Assets

Downloads infrastructure data from external sources and saves to `data/` folder:

```bash
python download-assets.py
```

Options:
- `--skip-osm`: Skip OpenStreetMap data
- `--skip-cec`: Skip California Energy Commission data
- `--skip-hifld`: Skip HIFLD data
- `--skip-calfire`: Skip CAL FIRE perimeter

### Initialize Database

Loads downloaded data into the database via the API:

```bash
python initialize.py
```

Options:
- `--api-url`: API base URL (default: http://localhost:5074)
- `--clear`: Clear existing data before loading

## Data Directory Structure

After running `download-assets.py`:

```
data/
├── osm/
│   ├── buildings.geojson
│   ├── roads.geojson
│   └── power_lines.geojson
├── cec/
│   ├── transmission_lines.geojson
│   └── substations.geojson
├── hifld/
│   ├── fire_stations.geojson
│   ├── hospitals.geojson
│   └── schools.geojson
└── calfire/
    └── camp_fire_perimeter.geojson
```

## Notes

- OSM data is queried in real-time and reflects current state
- CEC/HIFLD data may be periodically updated at source
- Camp Fire perimeter is historical (November 2018)
