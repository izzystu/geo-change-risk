"""Asset proximity analysis for risk assessment."""

from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import structlog
from pyproj import CRS, Transformer
from shapely.geometry import Polygon, shape
from shapely.ops import transform

logger = structlog.get_logger()

# Overhead lines: ground changes don't threaten suspended cables.
# Risk is captured by ground-level support structures (poles/towers = Point geometries).
OVERHEAD_LINE_TYPES = {'TransmissionLine'}


@dataclass
class ProximityResult:
    """Result of proximity analysis between change polygon and asset."""

    asset_id: str
    asset_name: str
    asset_type: int
    asset_type_name: str
    criticality: int
    criticality_name: str
    distance_meters: float
    asset_geometry: Any
    # Terrain/directional fields
    asset_elevation_m: float | None = None
    elevation_diff_m: float | None = None  # positive = change is upslope from asset
    is_upslope: bool | None = None
    slope_toward_asset_deg: float | None = None


def find_nearby_assets(
    change_polygon: Polygon,
    assets: list[dict[str, Any]],
    max_distance_m: float = 2500.0,
    dem_data: Any = None,
    change_elevation_m: float | None = None,
) -> list[ProximityResult]:
    """Find assets within a specified distance of a change polygon.

    Args:
        change_polygon: The change polygon geometry (must be in WGS84/EPSG:4326).
        assets: List of asset dictionaries from the API.
        max_distance_m: Maximum distance in meters to search.
        dem_data: Optional DEMData object for terrain analysis.
        change_elevation_m: Optional pre-calculated elevation at change centroid.

    Returns:
        List of ProximityResult objects for nearby assets.
    """
    if not assets:
        return []

    results = []

    # Get UTM zone for accurate distance calculation
    # Polygon should be in WGS84 (longitude/latitude)
    centroid = change_polygon.centroid

    # Validate coordinates are in WGS84 range
    if not (-180 <= centroid.x <= 180 and -90 <= centroid.y <= 90):
        logger.warning(
            "Change polygon appears to be in projected CRS, not WGS84",
            centroid_x=centroid.x,
            centroid_y=centroid.y,
        )
        # Assume it's already in a projected CRS with meters
        # This is a fallback - ideally polygons should be transformed to WGS84 before this
        change_projected = change_polygon
        to_projected = None
    else:
        from georisk.geo_utils import get_utm_crs

        # Calculate UTM zone from WGS84 coordinates
        utm_crs = get_utm_crs(centroid.x, centroid.y)
        wgs84_crs = CRS.from_epsg(4326)

        # Create transformer from WGS84 to UTM
        to_projected = Transformer.from_crs(wgs84_crs, utm_crs, always_xy=True)

        # Transform change polygon to UTM for accurate distance calculation
        change_projected = transform(to_projected.transform, change_polygon)

    # Import terrain module if DEM data is provided
    terrain_module = None
    if dem_data is not None:
        try:
            from georisk.raster.terrain import sample_terrain_at_point, calculate_directional_metrics
            terrain_module = True
        except ImportError:
            logger.warning("Terrain module not available for directional analysis")
            terrain_module = None

    for asset in assets:
        try:
            # Parse asset geometry
            asset_geom = asset.get("geometry")
            if not asset_geom:
                continue

            if isinstance(asset_geom, dict):
                asset_geom = shape(asset_geom)

            # Skip overhead line geometries — ground changes don't affect suspended cables
            if (asset_geom.geom_type in ('LineString', 'MultiLineString') and
                    asset.get('assetTypeName') in OVERHEAD_LINE_TYPES):
                logger.debug(
                    "Skipping overhead line geometry",
                    asset_name=asset.get("name"),
                    asset_type=asset.get("assetTypeName"),
                )
                continue

            # Validate asset coordinates are in WGS84 range
            asset_bounds = asset_geom.bounds  # (minx, miny, maxx, maxy)
            if (asset_bounds[0] < -180 or asset_bounds[2] > 180 or
                    asset_bounds[1] < -90 or asset_bounds[3] > 90):
                logger.warning(
                    "Skipping asset with non-WGS84 coordinates",
                    asset_id=asset.get("assetId"),
                    asset_name=asset.get("name"),
                    bounds=asset_bounds,
                )
                continue

            # Transform to projected CRS if we have a transformer
            if to_projected:
                asset_projected = transform(to_projected.transform, asset_geom)
            else:
                asset_projected = asset_geom

            # Calculate distance in meters
            distance_m = change_projected.distance(asset_projected)

            if distance_m <= max_distance_m:
                # Calculate terrain metrics if DEM is available
                asset_elevation_m = None
                elevation_diff_m = None
                is_upslope = None
                slope_toward_asset_deg = None

                if terrain_module and dem_data is not None:
                    from georisk.raster.terrain import sample_terrain_at_point, calculate_directional_metrics
                    from shapely.geometry import Point

                    # Get asset centroid for point-based terrain sampling
                    asset_point = asset_geom.centroid if hasattr(asset_geom, 'centroid') else Point(asset_geom.coords[0])
                    change_point = centroid

                    # Calculate directional metrics
                    metrics = calculate_directional_metrics(dem_data, change_point, asset_point)
                    if metrics is not None:
                        asset_elevation_m = metrics.asset_elevation_m
                        elevation_diff_m = metrics.elevation_diff_m
                        is_upslope = metrics.is_upslope
                        slope_toward_asset_deg = metrics.slope_toward_asset_deg

                results.append(ProximityResult(
                    asset_id=asset.get("assetId", "unknown"),
                    asset_name=asset.get("name", "Unknown"),
                    asset_type=asset.get("assetType", 0),
                    asset_type_name=asset.get("assetTypeName", "Unknown"),
                    criticality=asset.get("criticality", 1),
                    criticality_name=asset.get("criticalityName", "Medium"),
                    distance_meters=distance_m,
                    asset_geometry=asset_geom,
                    asset_elevation_m=asset_elevation_m,
                    elevation_diff_m=elevation_diff_m,
                    is_upslope=is_upslope,
                    slope_toward_asset_deg=slope_toward_asset_deg,
                ))

        except Exception as e:
            logger.warning("Failed to process asset", asset_id=asset.get("assetId"), error=str(e))
            continue

    # Sort by distance
    results.sort(key=lambda r: r.distance_meters)

    logger.info(
        "Proximity analysis complete",
        num_nearby_assets=len(results),
        max_distance_m=max_distance_m,
    )

    return results


def batch_proximity_analysis(
    change_polygons: list[Polygon],
    assets: list[dict[str, Any]],
    max_distance_m: float = 2500.0,
    dem_data: Any = None,
    change_elevations: list[float | None] | None = None,
) -> dict[int, list[ProximityResult]]:
    """Perform proximity analysis for multiple change polygons.

    Args:
        change_polygons: List of change polygon geometries.
        assets: List of asset dictionaries from the API.
        max_distance_m: Maximum distance in meters to search.
        dem_data: Optional DEMData object for terrain analysis.
        change_elevations: Optional list of pre-calculated elevations for each change polygon.

    Returns:
        Dictionary mapping polygon index to list of ProximityResults.
    """
    results = {}

    for idx, polygon in enumerate(change_polygons):
        change_elev = change_elevations[idx] if change_elevations and idx < len(change_elevations) else None
        nearby = find_nearby_assets(polygon, assets, max_distance_m, dem_data, change_elev)
        if nearby:
            results[idx] = nearby

    return results
