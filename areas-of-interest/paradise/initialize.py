#!/usr/bin/env python3
"""
Initialize Paradise AOI in the database.

Loads downloaded GeoJSON data into the database via the API.
"""

import argparse
import json
import sys
from pathlib import Path

import requests

# Load configuration
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
DATA_DIR = SCRIPT_DIR / "data"

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

# Asset type mapping (matches AssetType enum in C# code)
ASSET_TYPES = {
    "TransmissionLine": 0,
    "Substation": 1,
    "GasPipeline": 2,
    "Building": 3,
    "Road": 4,
    "FireStation": 5,
    "Hospital": 6,
    "School": 7,
    "WaterInfrastructure": 8,
    "Other": 99
}

# Criticality mapping (matches Criticality enum in C# code)
CRITICALITY = {
    "Low": 0,
    "Medium": 1,
    "High": 2,
    "Critical": 3
}


def create_aoi(api_url: str) -> bool:
    """Create the Area of Interest."""
    print(f"Creating AOI: {CONFIG['aoi_id']}...")

    bbox = CONFIG["bbox"]
    payload = {
        "aoiId": CONFIG["aoi_id"],
        "name": CONFIG["name"],
        "description": CONFIG["description"],
        "boundingBox": [bbox["min_lon"], bbox["min_lat"], bbox["max_lon"], bbox["max_lat"]],
        "center": CONFIG["center"]
    }

    response = requests.post(f"{api_url}/api/areas-of-interest", json=payload, timeout=30)

    if response.status_code == 201:
        print(f"  Created AOI: {CONFIG['aoi_id']}")
        return True
    elif response.status_code == 409:
        print(f"  AOI already exists: {CONFIG['aoi_id']}")
        return True
    else:
        print(f"  Error creating AOI: {response.status_code} - {response.text}")
        return False


def delete_existing_assets(api_url: str) -> int:
    """Delete existing assets for this AOI."""
    print(f"Deleting existing assets for AOI: {CONFIG['aoi_id']}...")

    response = requests.delete(
        f"{api_url}/api/assets",
        params={"aoiId": CONFIG["aoi_id"]},
        timeout=60
    )

    if response.status_code == 200:
        result = response.json()
        count = result.get("successCount", 0)
        print(f"  Deleted {count} existing assets")
        return count
    else:
        print(f"  Warning: Could not delete existing assets: {response.status_code}")
        return 0


def load_geojson(filepath: Path) -> dict:
    """Load a GeoJSON file."""
    if not filepath.exists():
        return {"type": "FeatureCollection", "features": []}

    with open(filepath) as f:
        return json.load(f)


def determine_asset_type(feature: dict, source: str) -> tuple[str, int]:
    """Determine asset type and criticality from feature properties."""
    props = feature.get("properties", {})

    # OSM Buildings
    if source == "osm_buildings":
        building_type = props.get("building", "yes")
        # Critical facilities
        if building_type in ["hospital", "fire_station"]:
            return "Building", CRITICALITY["Critical"]
        elif building_type in ["school", "university", "college"]:
            return "Building", CRITICALITY["High"]
        elif building_type in ["commercial", "industrial", "retail"]:
            return "Building", CRITICALITY["Medium"]
        else:
            return "Building", CRITICALITY["Low"]

    # OSM Roads
    elif source == "osm_roads":
        highway = props.get("highway", "")
        if highway in ["motorway", "trunk", "primary"]:
            return "Road", CRITICALITY["Critical"]
        elif highway in ["secondary", "tertiary"]:
            return "Road", CRITICALITY["High"]
        elif highway in ["residential", "service"]:
            return "Road", CRITICALITY["Medium"]
        else:
            return "Road", CRITICALITY["Low"]

    # OSM Power lines/poles
    elif source == "osm_power":
        power = props.get("power", "")
        if power in ["line"]:
            return "TransmissionLine", CRITICALITY["Critical"]
        elif power in ["minor_line"]:
            return "TransmissionLine", CRITICALITY["High"]
        elif power in ["tower", "pole"]:
            # Power poles/towers are part of transmission infrastructure
            return "TransmissionLine", CRITICALITY["Medium"]
        else:
            return "Other", CRITICALITY["Low"]

    # CEC Transmission lines
    elif source == "cec_transmission":
        voltage = props.get("VOLTAGE", 0)
        if voltage and voltage >= 230:
            return "TransmissionLine", CRITICALITY["Critical"]
        elif voltage and voltage >= 115:
            return "TransmissionLine", CRITICALITY["High"]
        else:
            return "TransmissionLine", CRITICALITY["Medium"]

    # CEC Substations
    elif source == "cec_substations":
        return "Substation", CRITICALITY["Critical"]

    # EIA Gas Pipelines
    elif source == "eia_pipelines":
        # All gas pipelines are critical infrastructure
        return "GasPipeline", CRITICALITY["Critical"]

    # HIFLD Fire stations
    elif source == "hifld_fire_stations":
        return "FireStation", CRITICALITY["Critical"]

    # HIFLD Hospitals
    elif source == "hifld_hospitals":
        return "Hospital", CRITICALITY["Critical"]

    # HIFLD Schools
    elif source == "hifld_schools":
        return "School", CRITICALITY["High"]

    # Default
    return "Other", CRITICALITY["Low"]


def get_feature_name(feature: dict, source: str, index: int) -> str:
    """Extract or generate a name for the feature."""
    props = feature.get("properties", {})

    # Try common name fields
    name = props.get("name") or props.get("NAME") or props.get("Name")
    if name:
        return str(name)

    # Source-specific name extraction
    if source == "osm_buildings":
        addr = props.get("addr:street", "")
        num = props.get("addr:housenumber", "")
        if addr:
            return f"{num} {addr}".strip() if num else addr
        return f"Building {index + 1}"

    elif source == "osm_roads":
        return props.get("name", f"Road {index + 1}")

    elif source == "cec_transmission":
        owner = props.get("OWNER", "")
        voltage = props.get("VOLTAGE", "")
        if owner and voltage:
            return f"{owner} {voltage}kV Line"
        return f"Transmission Line {index + 1}"

    elif source == "cec_substations":
        return props.get("SUBNAME", f"Substation {index + 1}")

    elif source == "eia_pipelines":
        # EIA pipeline attributes: operator, typepipe, status
        operator = props.get("operator", props.get("OPERATOR", ""))
        typepipe = props.get("typepipe", props.get("TYPEPIPE", ""))
        if operator and typepipe:
            return f"{operator} - {typepipe}"
        elif operator:
            return f"{operator} Pipeline"
        return f"Gas Pipeline {index + 1}"

    elif source == "hifld_fire_stations":
        return props.get("NAME", f"Fire Station {index + 1}")

    elif source == "hifld_hospitals":
        return props.get("NAME", f"Hospital {index + 1}")

    elif source == "hifld_schools":
        return props.get("NAME", f"School {index + 1}")

    return f"Feature {index + 1}"


def bulk_upload_assets(api_url: str, assets: list, source_dataset: str) -> tuple[int, int]:
    """Upload assets in bulk."""
    if not assets:
        return 0, 0

    # API bulk endpoint accepts max ~100 at a time for performance
    batch_size = 100
    total_success = 0
    total_failure = 0

    for i in range(0, len(assets), batch_size):
        batch = assets[i:i + batch_size]

        payload = {
            "aoiId": CONFIG["aoi_id"],
            "sourceDataset": source_dataset,
            "assets": batch
        }

        try:
            response = requests.post(
                f"{api_url}/api/assets/bulk",
                json=payload,
                timeout=120
            )

            if response.status_code == 200:
                result = response.json()
                total_success += result.get("successCount", 0)
                total_failure += result.get("failureCount", 0)
            else:
                print(f"    Batch error: {response.status_code}")
                total_failure += len(batch)
        except Exception as e:
            print(f"    Batch exception: {e}")
            total_failure += len(batch)

    return total_success, total_failure


def process_osm_buildings(api_url: str) -> tuple[int, int]:
    """Process OSM buildings."""
    print("Loading OSM buildings...")
    geojson = load_geojson(DATA_DIR / "osm" / "buildings.geojson")
    features = geojson.get("features", [])

    if not features:
        print("  No buildings found")
        return 0, 0

    assets = []
    for i, feature in enumerate(features):
        asset_type, criticality = determine_asset_type(feature, "osm_buildings")

        assets.append({
            "aoiId": CONFIG["aoi_id"],
            "name": get_feature_name(feature, "osm_buildings", i),
            "assetType": ASSET_TYPES[asset_type],
            "criticality": criticality,
            "geometry": feature["geometry"],
            "properties": feature.get("properties", {}),
            "sourceFeatureId": feature.get("id", str(i))
        })

    success, failure = bulk_upload_assets(api_url, assets, "osm-buildings")
    print(f"  Uploaded: {success} success, {failure} failures")
    return success, failure


def process_osm_roads(api_url: str) -> tuple[int, int]:
    """Process OSM roads."""
    print("Loading OSM roads...")
    geojson = load_geojson(DATA_DIR / "osm" / "roads.geojson")
    features = geojson.get("features", [])

    if not features:
        print("  No roads found")
        return 0, 0

    assets = []
    for i, feature in enumerate(features):
        asset_type, criticality = determine_asset_type(feature, "osm_roads")

        assets.append({
            "aoiId": CONFIG["aoi_id"],
            "name": get_feature_name(feature, "osm_roads", i),
            "assetType": ASSET_TYPES[asset_type],
            "criticality": criticality,
            "geometry": feature["geometry"],
            "properties": feature.get("properties", {}),
            "sourceFeatureId": feature.get("id", str(i))
        })

    success, failure = bulk_upload_assets(api_url, assets, "osm-roads")
    print(f"  Uploaded: {success} success, {failure} failures")
    return success, failure


def process_osm_power(api_url: str) -> tuple[int, int]:
    """Process OSM power lines."""
    print("Loading OSM power lines...")
    geojson = load_geojson(DATA_DIR / "osm" / "power_lines.geojson")
    features = geojson.get("features", [])

    if not features:
        print("  No power features found")
        return 0, 0

    assets = []
    for i, feature in enumerate(features):
        asset_type, criticality = determine_asset_type(feature, "osm_power")

        assets.append({
            "aoiId": CONFIG["aoi_id"],
            "name": get_feature_name(feature, "osm_power", i),
            "assetType": ASSET_TYPES[asset_type],
            "criticality": criticality,
            "geometry": feature["geometry"],
            "properties": feature.get("properties", {}),
            "sourceFeatureId": feature.get("id", str(i))
        })

    success, failure = bulk_upload_assets(api_url, assets, "osm-power")
    print(f"  Uploaded: {success} success, {failure} failures")
    return success, failure


def process_cec_transmission(api_url: str) -> tuple[int, int]:
    """Process CEC transmission lines."""
    print("Loading CEC transmission lines...")
    geojson = load_geojson(DATA_DIR / "cec" / "transmission_lines.geojson")
    features = geojson.get("features", [])

    if not features:
        print("  No transmission lines found")
        return 0, 0

    assets = []
    for i, feature in enumerate(features):
        asset_type, criticality = determine_asset_type(feature, "cec_transmission")

        assets.append({
            "aoiId": CONFIG["aoi_id"],
            "name": get_feature_name(feature, "cec_transmission", i),
            "assetType": ASSET_TYPES[asset_type],
            "criticality": criticality,
            "geometry": feature["geometry"],
            "properties": feature.get("properties", {}),
            "sourceFeatureId": str(feature.get("id", i))
        })

    success, failure = bulk_upload_assets(api_url, assets, "cec-transmission")
    print(f"  Uploaded: {success} success, {failure} failures")
    return success, failure


def process_cec_substations(api_url: str) -> tuple[int, int]:
    """Process CEC substations."""
    print("Loading CEC substations...")
    geojson = load_geojson(DATA_DIR / "cec" / "substations.geojson")
    features = geojson.get("features", [])

    if not features:
        print("  No substations found")
        return 0, 0

    assets = []
    for i, feature in enumerate(features):
        asset_type, criticality = determine_asset_type(feature, "cec_substations")

        assets.append({
            "aoiId": CONFIG["aoi_id"],
            "name": get_feature_name(feature, "cec_substations", i),
            "assetType": ASSET_TYPES[asset_type],
            "criticality": criticality,
            "geometry": feature["geometry"],
            "properties": feature.get("properties", {}),
            "sourceFeatureId": str(feature.get("id", i))
        })

    success, failure = bulk_upload_assets(api_url, assets, "cec-substations")
    print(f"  Uploaded: {success} success, {failure} failures")
    return success, failure


def process_eia_pipelines(api_url: str) -> tuple[int, int]:
    """Process EIA gas pipelines."""
    print("Loading EIA gas pipelines...")
    pipeline_path = DATA_DIR / "eia" / "gas_pipelines.geojson"

    if not pipeline_path.exists():
        print("  No pipeline data found (run download-assets.py first)")
        return 0, 0

    geojson = load_geojson(pipeline_path)
    features = geojson.get("features", [])

    if not features:
        print("  No pipelines found in data file")
        return 0, 0

    assets = []
    for i, feature in enumerate(features):
        asset_type, criticality = determine_asset_type(feature, "eia_pipelines")

        assets.append({
            "aoiId": CONFIG["aoi_id"],
            "name": get_feature_name(feature, "eia_pipelines", i),
            "assetType": ASSET_TYPES[asset_type],
            "criticality": criticality,
            "geometry": feature["geometry"],
            "properties": feature.get("properties", {}),
            "sourceFeatureId": str(feature.get("id", i))
        })

    success, failure = bulk_upload_assets(api_url, assets, "eia-gas-pipelines")
    print(f"  Uploaded: {success} success, {failure} failures")
    return success, failure


def process_hifld_fire_stations(api_url: str) -> tuple[int, int]:
    """Process HIFLD fire stations."""
    print("Loading HIFLD fire stations...")
    geojson = load_geojson(DATA_DIR / "hifld" / "fire_stations.geojson")
    features = geojson.get("features", [])

    if not features:
        print("  No fire stations found")
        return 0, 0

    assets = []
    for i, feature in enumerate(features):
        asset_type, criticality = determine_asset_type(feature, "hifld_fire_stations")

        assets.append({
            "aoiId": CONFIG["aoi_id"],
            "name": get_feature_name(feature, "hifld_fire_stations", i),
            "assetType": ASSET_TYPES[asset_type],
            "criticality": criticality,
            "geometry": feature["geometry"],
            "properties": feature.get("properties", {}),
            "sourceFeatureId": str(feature.get("id", i))
        })

    success, failure = bulk_upload_assets(api_url, assets, "hifld-fire-stations")
    print(f"  Uploaded: {success} success, {failure} failures")
    return success, failure


def process_hifld_hospitals(api_url: str) -> tuple[int, int]:
    """Process HIFLD hospitals."""
    print("Loading HIFLD hospitals...")
    geojson = load_geojson(DATA_DIR / "hifld" / "hospitals.geojson")
    features = geojson.get("features", [])

    if not features:
        print("  No hospitals found")
        return 0, 0

    assets = []
    for i, feature in enumerate(features):
        asset_type, criticality = determine_asset_type(feature, "hifld_hospitals")

        assets.append({
            "aoiId": CONFIG["aoi_id"],
            "name": get_feature_name(feature, "hifld_hospitals", i),
            "assetType": ASSET_TYPES[asset_type],
            "criticality": criticality,
            "geometry": feature["geometry"],
            "properties": feature.get("properties", {}),
            "sourceFeatureId": str(feature.get("id", i))
        })

    success, failure = bulk_upload_assets(api_url, assets, "hifld-hospitals")
    print(f"  Uploaded: {success} success, {failure} failures")
    return success, failure


def process_hifld_schools(api_url: str) -> tuple[int, int]:
    """Process HIFLD schools."""
    print("Loading HIFLD schools...")
    geojson = load_geojson(DATA_DIR / "hifld" / "schools.geojson")
    features = geojson.get("features", [])

    if not features:
        print("  No schools found")
        return 0, 0

    assets = []
    for i, feature in enumerate(features):
        asset_type, criticality = determine_asset_type(feature, "hifld_schools")

        assets.append({
            "aoiId": CONFIG["aoi_id"],
            "name": get_feature_name(feature, "hifld_schools", i),
            "assetType": ASSET_TYPES[asset_type],
            "criticality": criticality,
            "geometry": feature["geometry"],
            "properties": feature.get("properties", {}),
            "sourceFeatureId": str(feature.get("id", i))
        })

    success, failure = bulk_upload_assets(api_url, assets, "hifld-schools")
    print(f"  Uploaded: {success} success, {failure} failures")
    return success, failure


def main():
    parser = argparse.ArgumentParser(description="Initialize Paradise AOI in database")
    parser.add_argument(
        "--api-url",
        default="http://localhost:5074",
        help="API base URL (default: http://localhost:5074)"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing assets before loading"
    )
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")

    print(f"Initializing: {CONFIG['name']}")
    print(f"API URL: {api_url}")
    print()

    # Check API is available
    try:
        response = requests.get(f"{api_url}/api/system/health", timeout=10)
        if response.status_code != 200:
            print(f"Error: API health check failed: {response.status_code}")
            sys.exit(1)
        print("API health check: OK")
    except Exception as e:
        print(f"Error: Could not connect to API: {e}")
        sys.exit(1)

    print()

    # Create AOI
    if not create_aoi(api_url):
        print("Error: Failed to create AOI")
        sys.exit(1)

    # Clear existing assets if requested
    if args.clear:
        delete_existing_assets(api_url)

    print()

    # Process each data source
    stats = {
        "success": 0,
        "failure": 0
    }

    print("=== Loading Assets ===")

    # OSM
    s, f = process_osm_buildings(api_url)
    stats["success"] += s
    stats["failure"] += f

    s, f = process_osm_roads(api_url)
    stats["success"] += s
    stats["failure"] += f

    s, f = process_osm_power(api_url)
    stats["success"] += s
    stats["failure"] += f

    # CEC
    s, f = process_cec_transmission(api_url)
    stats["success"] += s
    stats["failure"] += f

    s, f = process_cec_substations(api_url)
    stats["success"] += s
    stats["failure"] += f

    # EIA Pipelines
    s, f = process_eia_pipelines(api_url)
    stats["success"] += s
    stats["failure"] += f

    # HIFLD
    s, f = process_hifld_fire_stations(api_url)
    stats["success"] += s
    stats["failure"] += f

    s, f = process_hifld_hospitals(api_url)
    stats["success"] += s
    stats["failure"] += f

    s, f = process_hifld_schools(api_url)
    stats["success"] += s
    stats["failure"] += f

    print()
    print("=== Summary ===")
    print(f"  Total success: {stats['success']}")
    print(f"  Total failures: {stats['failure']}")

    # Verify
    print()
    print("Verifying...")
    response = requests.get(f"{api_url}/api/system/stats", timeout=10)
    if response.status_code == 200:
        db_stats = response.json()
        print(f"  AOIs in database: {db_stats.get('areasOfInterest', 0)}")
        print(f"  Assets in database: {db_stats.get('assets', 0)}")


if __name__ == "__main__":
    main()
