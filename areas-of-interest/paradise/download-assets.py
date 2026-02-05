#!/usr/bin/env python3
"""
Download infrastructure assets for Paradise, CA AOI from various data sources.

Data sources:
- OpenStreetMap (buildings, roads, power lines) via Overpass API
- California Energy Commission (transmission lines, substations)
- EIA (natural gas pipelines)
- HIFLD/USGS (fire stations, hospitals, schools)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from tqdm import tqdm

# Load configuration
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
DATA_DIR = SCRIPT_DIR / "data"

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

BBOX = CONFIG["bbox"]
# Overpass uses south,west,north,east format
OVERPASS_BBOX = f"{BBOX['min_lat']},{BBOX['min_lon']},{BBOX['max_lat']},{BBOX['max_lon']}"

# ArcGIS geometry envelope format (must be compact JSON string)
ARCGIS_GEOMETRY = json.dumps({
    "xmin": BBOX["min_lon"],
    "ymin": BBOX["min_lat"],
    "xmax": BBOX["max_lon"],
    "ymax": BBOX["max_lat"],
    "spatialReference": {"wkid": 4326}
}, separators=(',', ':'))

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]


def overpass_query(query: str, max_retries: int = 3) -> dict:
    """Execute Overpass query with retries and fallback endpoints."""
    last_error = None

    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(max_retries):
            try:
                print(f"    Trying {endpoint.split('/')[2]}... (attempt {attempt + 1})")
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    timeout=300  # 5 minutes
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.Timeout:
                print(f"    Timeout, retrying...")
                last_error = "Timeout"
            except requests.exceptions.HTTPError as e:
                if e.response.status_code in [429, 503, 504]:
                    print(f"    Server busy ({e.response.status_code}), retrying...")
                    last_error = str(e)
                    time.sleep(5 * (attempt + 1))  # Exponential backoff
                else:
                    raise
            except Exception as e:
                last_error = str(e)
                break  # Try next endpoint

    raise Exception(f"All Overpass endpoints failed. Last error: {last_error}")


def ensure_dirs():
    """Create data directory structure."""
    for subdir in ["osm", "cec", "eia", "hifld"]:
        (DATA_DIR / subdir).mkdir(parents=True, exist_ok=True)


def download_osm_buildings():
    """Download buildings from OpenStreetMap."""
    print("Downloading OSM buildings...")

    query = f"""
    [out:json][timeout:180];
    (
      way["building"]({OVERPASS_BBOX});
      node["building"]({OVERPASS_BBOX});
      relation["building"]({OVERPASS_BBOX});
    );
    out body;
    >;
    out skel qt;
    """

    osm_data = overpass_query(query)
    geojson = osm_to_geojson(osm_data, "building")

    output_path = DATA_DIR / "osm" / "buildings.geojson"
    with open(output_path, "w") as f:
        json.dump(geojson, f, indent=2)

    print(f"  Saved {len(geojson['features'])} buildings to {output_path}")
    return len(geojson['features'])


def download_osm_roads():
    """Download roads from OpenStreetMap."""
    print("Downloading OSM roads...")

    query = f"""
    [out:json][timeout:180];
    (
      way["highway"]({OVERPASS_BBOX});
    );
    out body;
    >;
    out skel qt;
    """

    osm_data = overpass_query(query)
    geojson = osm_to_geojson(osm_data, "highway")

    output_path = DATA_DIR / "osm" / "roads.geojson"
    with open(output_path, "w") as f:
        json.dump(geojson, f, indent=2)

    print(f"  Saved {len(geojson['features'])} roads to {output_path}")
    return len(geojson['features'])


def download_osm_power_lines():
    """Download power lines from OpenStreetMap."""
    print("Downloading OSM power lines...")

    query = f"""
    [out:json][timeout:180];
    (
      way["power"="line"]({OVERPASS_BBOX});
      way["power"="minor_line"]({OVERPASS_BBOX});
      node["power"="tower"]({OVERPASS_BBOX});
      node["power"="pole"]({OVERPASS_BBOX});
    );
    out body;
    >;
    out skel qt;
    """

    osm_data = overpass_query(query)
    geojson = osm_to_geojson(osm_data, "power")

    output_path = DATA_DIR / "osm" / "power_lines.geojson"
    with open(output_path, "w") as f:
        json.dump(geojson, f, indent=2)

    print(f"  Saved {len(geojson['features'])} power features to {output_path}")
    return len(geojson['features'])


def osm_to_geojson(osm_data, primary_tag):
    """Convert OSM JSON to GeoJSON."""
    features = []

    # Build node lookup for way geometry
    nodes = {}
    for element in osm_data.get("elements", []):
        if element["type"] == "node":
            nodes[element["id"]] = (element["lon"], element["lat"])

    for element in osm_data.get("elements", []):
        if element["type"] == "node" and "tags" in element:
            # Point feature
            features.append({
                "type": "Feature",
                "id": f"node/{element['id']}",
                "geometry": {
                    "type": "Point",
                    "coordinates": [element["lon"], element["lat"]]
                },
                "properties": {
                    "osm_id": element["id"],
                    "osm_type": "node",
                    **element.get("tags", {})
                }
            })
        elif element["type"] == "way" and "nodes" in element:
            # Line or polygon
            coords = [nodes[n] for n in element["nodes"] if n in nodes]
            if len(coords) < 2:
                continue

            tags = element.get("tags", {})

            # Determine if polygon (closed way with area-like tags)
            is_polygon = (
                coords[0] == coords[-1] and
                len(coords) >= 4 and
                primary_tag in ["building", "landuse", "natural", "leisure"]
            )

            if is_polygon:
                geometry = {
                    "type": "Polygon",
                    "coordinates": [coords]
                }
            else:
                geometry = {
                    "type": "LineString",
                    "coordinates": coords
                }

            features.append({
                "type": "Feature",
                "id": f"way/{element['id']}",
                "geometry": geometry,
                "properties": {
                    "osm_id": element["id"],
                    "osm_type": "way",
                    **tags
                }
            })

    return {
        "type": "FeatureCollection",
        "features": features
    }


def download_cec_transmission_lines():
    """Download transmission lines from California Energy Commission."""
    print("Downloading CEC transmission lines...")

    # Try GeoJSON download first (full state, then filter)
    geojson_url = "https://cecgis-caenergy.opendata.arcgis.com/api/download/v1/items/260b4513acdb4a3a8e4d64e69fc84fee/geojson?layers=2"

    try:
        print("  Downloading full state dataset...")
        response = requests.get(geojson_url, timeout=300)
        response.raise_for_status()
        data = response.json()

        total_features = len(data.get("features", []))
        print(f"  Downloaded {total_features} features from full state")

        # Filter to bbox
        filtered = filter_geojson_to_bbox(data)
        print(f"  Filtered to bbox: {len(filtered['features'])} features")

        output_path = DATA_DIR / "cec" / "transmission_lines.geojson"
        with open(output_path, "w") as f:
            json.dump(filtered, f, indent=2)

        print(f"  Saved {len(filtered['features'])} transmission lines to {output_path}")
        return len(filtered['features'])
    except Exception as e:
        print(f"  Warning: Could not download CEC transmission lines: {e}")
        print("  Trying alternative source...")
        return download_cec_transmission_lines_alt()


def download_cec_transmission_lines_alt():
    """Alternative: Query CEC ArcGIS Feature Service directly."""
    # CEC Feature Service - correct service name and layer ID
    base_url = "https://services3.arcgis.com/bWPjFyq029ChCGur/arcgis/rest/services"
    layer_url = f"{base_url}/Transmission_Line/FeatureServer/2/query"

    # Try multiple approaches
    approaches = [
        # Approach 1: Simple envelope
        {
            "where": "1=1",
            "geometry": f"{BBOX['min_lon']},{BBOX['min_lat']},{BBOX['max_lon']},{BBOX['max_lat']}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "f": "geojson"
        },
        # Approach 2: JSON envelope
        {
            "where": "1=1",
            "geometry": ARCGIS_GEOMETRY,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "f": "geojson"
        },
        # Approach 3: County filter (Butte County) + local bbox filter
        {
            "where": "COUNTY = 'Butte' OR COUNTY = 'BUTTE'",
            "outFields": "*",
            "f": "geojson"
        }
    ]

    for i, params in enumerate(approaches):
        try:
            print(f"    Trying approach {i+1}...")
            response = requests.get(layer_url, params=params, timeout=120)

            if response.status_code == 400:
                try:
                    error_detail = response.json()
                    print(f"    Approach {i+1} failed: {error_detail.get('error', {}).get('message', 'Unknown')}")
                except:
                    pass
                continue

            response.raise_for_status()
            data = response.json()

            # Filter to bbox if we got county-level data
            if i == 2:
                data = filter_geojson_to_bbox(data)

            output_path = DATA_DIR / "cec" / "transmission_lines.geojson"
            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)

            count = len(data.get("features", []))
            print(f"  Saved {count} transmission lines to {output_path}")
            return count

        except Exception as e:
            print(f"    Approach {i+1} error: {e}")
            continue

    print("  All approaches failed for transmission lines")
    empty = {"type": "FeatureCollection", "features": []}
    output_path = DATA_DIR / "cec" / "transmission_lines.geojson"
    with open(output_path, "w") as f:
        json.dump(empty, f, indent=2)
    return 0


def download_cec_substations():
    """Download substations from California Energy Commission or HIFLD."""
    print("Downloading substations...")

    # Try multiple sources
    sources = [
        # Source 1: CEC GeoJSON download
        {
            "name": "CEC GeoJSON",
            "url": "https://cecgis-caenergy.opendata.arcgis.com/api/download/v1/items/c2d4e65fe7b84c67a94e98ff9555c3ac/geojson",
            "full_state": True
        },
        # Source 2: HIFLD Electric Substations (national)
        {
            "name": "HIFLD",
            "url": "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Electric_Substations_1/FeatureServer/0/query",
            "params": {
                "where": "STATE = 'CA'",
                "outFields": "*",
                "f": "geojson"
            },
            "full_state": True
        }
    ]

    for source in sources:
        try:
            print(f"  Trying {source['name']}...")

            if "params" in source:
                response = requests.get(source["url"], params=source["params"], timeout=120)
            else:
                response = requests.get(source["url"], timeout=120)

            if response.status_code != 200:
                print(f"    Failed: HTTP {response.status_code}")
                continue

            data = response.json()

            # Check for errors in response
            if "error" in data:
                print(f"    Failed: {data['error'].get('message', 'Unknown error')}")
                continue

            # Filter to bbox
            if source.get("full_state"):
                data = filter_geojson_to_bbox(data)

            output_path = DATA_DIR / "cec" / "substations.geojson"
            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)

            count = len(data.get("features", []))
            print(f"  Saved {count} substations to {output_path}")
            return count

        except Exception as e:
            print(f"    Error: {e}")
            continue

    print("  All sources failed for substations")
    empty = {"type": "FeatureCollection", "features": []}
    output_path = DATA_DIR / "cec" / "substations.geojson"
    with open(output_path, "w") as f:
        json.dump(empty, f, indent=2)
    return 0


def download_eia_gas_pipelines():
    """Download natural gas pipelines from EIA via Bureau of Transportation Statistics."""
    print("Downloading EIA natural gas pipelines...")

    # EIA Natural Gas Pipelines REST API (hosted by Bureau of Transportation Statistics)
    # Documentation: https://geo.dot.gov/server/rest/services/Hosted/Natural_Gas_Pipelines_US_EIA/FeatureServer/0
    base_url = "https://geo.dot.gov/server/rest/services/Hosted/Natural_Gas_Pipelines_US_EIA/FeatureServer/0/query"

    # Use an expanded bbox to catch pipelines that pass through the area
    # Pipelines are linear and may originate outside but pass through
    expanded_bbox = {
        "min_lon": BBOX["min_lon"] - 0.5,
        "min_lat": BBOX["min_lat"] - 0.5,
        "max_lon": BBOX["max_lon"] + 0.5,
        "max_lat": BBOX["max_lat"] + 0.5
    }

    params = {
        "where": "1=1",
        "geometry": f"{expanded_bbox['min_lon']},{expanded_bbox['min_lat']},{expanded_bbox['max_lon']},{expanded_bbox['max_lat']}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "f": "geojson"
    }

    try:
        print(f"  Querying EIA pipeline service...")
        response = requests.get(base_url, params=params, timeout=120)
        response.raise_for_status()
        data = response.json()

        # Check for errors
        if "error" in data:
            raise Exception(data["error"].get("message", "Unknown error"))

        count = len(data.get("features", []))
        print(f"  Found {count} pipeline segments in expanded bbox")

        # Filter to actual bbox (may still want the expanded results for context)
        # For pipelines, we keep the expanded area since they're linear infrastructure
        output_path = DATA_DIR / "eia" / "gas_pipelines.geojson"
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"  Saved {count} pipeline segments to {output_path}")
        return count

    except Exception as e:
        print(f"  Error downloading EIA pipelines: {e}")
        print("  Trying HIFLD alternative source...")
        return download_hifld_gas_pipelines()


def download_hifld_gas_pipelines():
    """Alternative: Download natural gas pipelines from HIFLD."""
    print("  Trying HIFLD Natural Gas Pipelines...")

    # HIFLD Natural Gas Pipelines
    base_url = "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Natural_Gas_Pipelines/FeatureServer/0/query"

    # Expanded bbox for linear features
    expanded_bbox = {
        "min_lon": BBOX["min_lon"] - 0.5,
        "min_lat": BBOX["min_lat"] - 0.5,
        "max_lon": BBOX["max_lon"] + 0.5,
        "max_lat": BBOX["max_lat"] + 0.5
    }

    params = {
        "where": "1=1",
        "geometry": f"{expanded_bbox['min_lon']},{expanded_bbox['min_lat']},{expanded_bbox['max_lon']},{expanded_bbox['max_lat']}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "f": "geojson"
    }

    try:
        response = requests.get(base_url, params=params, timeout=120)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise Exception(data["error"].get("message", "Unknown error"))

        count = len(data.get("features", []))
        output_path = DATA_DIR / "eia" / "gas_pipelines.geojson"
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"  Saved {count} pipeline segments to {output_path}")
        return count

    except Exception as e:
        print(f"  HIFLD also failed: {e}")
        empty = {"type": "FeatureCollection", "features": []}
        output_path = DATA_DIR / "eia" / "gas_pipelines.geojson"
        with open(output_path, "w") as f:
            json.dump(empty, f, indent=2)
        return 0


def download_hifld_fire_stations():
    """Download fire stations from USGS National Map."""
    print("Downloading fire stations (USGS National Map)...")
    return download_usgs_structures_layer(16, "fire_stations.geojson")


def download_hifld_hospitals():
    """Download hospitals from USGS National Map."""
    print("Downloading hospitals (USGS National Map)...")
    return download_usgs_structures_layer(14, "hospitals.geojson")


def download_hifld_schools():
    """Download schools from USGS National Map."""
    print("Downloading schools (USGS National Map)...")
    return download_usgs_structures_layer(23, "schools.geojson")


def download_usgs_structures_layer(layer_id: int, filename: str):
    """Download a layer from USGS National Map Structures service."""
    # USGS National Map Structures MapServer
    base_url = "https://carto.nationalmap.gov/arcgis/rest/services/structures/MapServer"
    layer_url = f"{base_url}/{layer_id}/query"

    params = {
        "where": "1=1",
        "geometry": f"{BBOX['min_lon']},{BBOX['min_lat']},{BBOX['max_lon']},{BBOX['max_lat']}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "f": "geojson"
    }

    try:
        response = requests.get(layer_url, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()

        output_path = DATA_DIR / "hifld" / filename
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        count = len(data.get("features", []))
        print(f"  Saved {count} features to {output_path}")
        return count
    except Exception as e:
        print(f"  Error: {e}")
        empty = {"type": "FeatureCollection", "features": []}
        output_path = DATA_DIR / "hifld" / filename
        with open(output_path, "w") as f:
            json.dump(empty, f, indent=2)
        return 0


def download_hifld_layer(url, filename):
    """Generic HIFLD layer download."""
    # Try multiple geometry formats
    geometry_formats = [
        # Format 1: Simple envelope string (xmin,ymin,xmax,ymax)
        {
            "geometry": f"{BBOX['min_lon']},{BBOX['min_lat']},{BBOX['max_lon']},{BBOX['max_lat']}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
        },
        # Format 2: JSON envelope
        {
            "geometry": ARCGIS_GEOMETRY,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
        },
        # Format 3: No geometry, filter by state/county instead (download all CA, filter locally)
        None
    ]

    for i, geom_params in enumerate(geometry_formats):
        params = {
            "where": "1=1",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "f": "geojson"
        }

        if geom_params:
            params.update(geom_params)
        else:
            # No spatial filter - try state filter for HIFLD
            params["where"] = "STATE = 'CA'"
            params["resultRecordCount"] = "2000"

        try:
            response = requests.get(url, params=params, timeout=120)

            if response.status_code == 400:
                # Try to get error details
                try:
                    error_detail = response.json()
                    print(f"    Format {i+1} failed: {error_detail.get('error', {}).get('message', 'Unknown error')}")
                except:
                    print(f"    Format {i+1} failed: 400 Bad Request")
                continue

            response.raise_for_status()
            data = response.json()

            # If we got all of CA, filter to bbox
            if not geom_params:
                data = filter_geojson_to_bbox(data)

            output_path = DATA_DIR / "hifld" / filename
            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)

            count = len(data.get("features", []))
            print(f"  Saved {count} features to {output_path}")
            return count

        except requests.exceptions.HTTPError as e:
            print(f"    Format {i+1} failed: {e}")
            continue
        except Exception as e:
            print(f"    Format {i+1} error: {e}")
            continue

    print(f"  All formats failed for {filename}")
    empty = {"type": "FeatureCollection", "features": []}
    output_path = DATA_DIR / "hifld" / filename
    with open(output_path, "w") as f:
        json.dump(empty, f, indent=2)
    return 0


def filter_geojson_to_bbox(geojson):
    """Filter GeoJSON features to bounding box. Auto-detects coordinate system."""
    from shapely.geometry import shape, box, mapping
    from shapely.ops import transform as shapely_transform
    from pyproj import Transformer

    features = geojson.get("features", [])
    if not features:
        return {"type": "FeatureCollection", "features": []}

    # Check if data is in Web Mercator (EPSG:3857) by looking at coordinate magnitude
    try:
        first_geom = shape(features[0]["geometry"])
        bounds = first_geom.bounds
        is_web_mercator = abs(bounds[0]) > 180 or abs(bounds[1]) > 90
    except Exception:
        is_web_mercator = False

    # Create bbox polygon in appropriate CRS
    reverse_transformer = None
    if is_web_mercator:
        # Transform bbox from WGS84 to Web Mercator for filtering
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        min_x, min_y = transformer.transform(BBOX['min_lon'], BBOX['min_lat'])
        max_x, max_y = transformer.transform(BBOX['max_lon'], BBOX['max_lat'])
        bbox_polygon = box(min_x, min_y, max_x, max_y)
        # Prepare reverse transformer to reproject features to WGS84
        reverse_transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
        print(f"  Detected Web Mercator coordinates, will reproject to WGS84")
    else:
        bbox_polygon = box(BBOX['min_lon'], BBOX['min_lat'], BBOX['max_lon'], BBOX['max_lat'])

    filtered_features = []
    for feature in features:
        try:
            geom = shape(feature["geometry"])
            if geom.intersects(bbox_polygon):
                if reverse_transformer:
                    geom_wgs84 = shapely_transform(reverse_transformer.transform, geom)
                    feature = dict(feature)  # shallow copy
                    feature["geometry"] = mapping(geom_wgs84)
                filtered_features.append(feature)
        except Exception:
            continue

    return {
        "type": "FeatureCollection",
        "features": filtered_features
    }


def main():
    parser = argparse.ArgumentParser(description="Download Paradise AOI infrastructure data")
    parser.add_argument("--skip-osm", action="store_true", help="Skip OpenStreetMap data")
    parser.add_argument("--skip-cec", action="store_true", help="Skip CEC data")
    parser.add_argument("--skip-eia", action="store_true", help="Skip EIA pipeline data")
    parser.add_argument("--skip-hifld", action="store_true", help="Skip HIFLD data")
    args = parser.parse_args()

    print(f"Downloading assets for: {CONFIG['name']}")
    print(f"Bounding box: {BBOX}")
    print()

    ensure_dirs()

    stats = {}

    # OpenStreetMap
    if not args.skip_osm:
        print("=== OpenStreetMap ===")
        stats["osm_buildings"] = download_osm_buildings()
        stats["osm_roads"] = download_osm_roads()
        stats["osm_power_lines"] = download_osm_power_lines()
        print()

    # California Energy Commission
    if not args.skip_cec:
        print("=== California Energy Commission ===")
        stats["cec_transmission_lines"] = download_cec_transmission_lines()
        stats["cec_substations"] = download_cec_substations()
        print()

    # EIA (Energy Information Administration) - Natural Gas Pipelines
    if not args.skip_eia:
        print("=== EIA Natural Gas Pipelines ===")
        stats["eia_gas_pipelines"] = download_eia_gas_pipelines()
        print()

    # HIFLD
    if not args.skip_hifld:
        print("=== HIFLD / USGS ===")
        stats["hifld_fire_stations"] = download_hifld_fire_stations()
        stats["hifld_hospitals"] = download_hifld_hospitals()
        stats["hifld_schools"] = download_hifld_schools()
        print()

    # Summary
    print("=== Download Summary ===")
    total = 0
    for source, count in stats.items():
        print(f"  {source}: {count}")
        total += count
    print(f"  Total: {total} features")
    print()
    print(f"Data saved to: {DATA_DIR}")


if __name__ == "__main__":
    main()
