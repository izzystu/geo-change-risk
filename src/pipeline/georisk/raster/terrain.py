"""Terrain analysis from DEM data."""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rioxarray as rxr
import structlog
import xarray as xr
from pyproj import CRS, Transformer
from rasterio import features as rio_features
from scipy import ndimage
from shapely.geometry import Point, Polygon, shape
from shapely.ops import transform as shapely_transform

from georisk.config import get_config

logger = structlog.get_logger()


@dataclass
class TerrainData:
    """Terrain analysis results for a location/polygon."""

    slope_degrees: float
    aspect_degrees: float
    elevation_m: float


@dataclass
class DirectionalTerrainMetrics:
    """Terrain relationship between change and asset."""

    change_elevation_m: float
    asset_elevation_m: float
    elevation_diff_m: float  # positive = change is upslope from asset
    is_upslope: bool
    slope_toward_asset_deg: float


@dataclass
class DEMData:
    """Container for DEM data with derived products."""

    elevation: xr.DataArray
    slope: xr.DataArray | None = None
    aspect: xr.DataArray | None = None
    crs: Any = None
    transform: Any = None
    resolution_m: float = 10.0

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Get bounds in native CRS."""
        return self.elevation.rio.bounds()


def load_dem_for_bbox(
    bbox: tuple[float, float, float, float],
    dem_source: str = "3dep",
    cache_dir: Path | None = None,
) -> DEMData | None:
    """Load DEM data for the given bounding box.

    Args:
        bbox: Bounding box as (min_lon, min_lat, max_lon, max_lat) in WGS84.
        dem_source: DEM source ("3dep" for USGS 3DEP via Planetary Computer).
        cache_dir: Optional local cache directory for DEM files.

    Returns:
        DEMData object with elevation and optionally slope/aspect, or None if unavailable.
    """
    logger.info("Loading DEM", bbox=bbox, source=dem_source)

    if dem_source == "3dep":
        return _load_3dep_dem(bbox, cache_dir)
    elif dem_source == "local":
        config = get_config()
        if config.terrain.local_dem_path:
            return _load_local_dem(Path(config.terrain.local_dem_path), bbox)
        logger.warning("Local DEM source specified but no path configured")
        return None
    else:
        logger.warning("Unknown DEM source", source=dem_source)
        return None


def _load_3dep_dem(
    bbox: tuple[float, float, float, float],
    cache_dir: Path | None = None,
) -> DEMData | None:
    """Load USGS 3DEP DEM from Planetary Computer STAC.

    Args:
        bbox: Bounding box in WGS84.
        cache_dir: Optional cache directory.

    Returns:
        DEMData or None if not available.
    """
    try:
        import planetary_computer
        import pystac_client

        catalog = pystac_client.Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=planetary_computer.sign_inplace,
        )

        # Search for 3DEP DEM tiles
        search = catalog.search(
            collections=["3dep-seamless"],
            bbox=bbox,
            limit=10,
        )

        items = list(search.items())
        if not items:
            logger.warning("No 3DEP DEM tiles found for bbox", bbox=bbox)
            return None

        logger.info("Found 3DEP tiles", count=len(items))

        # Use the first item (typically the 10m seamless DEM)
        item = items[0]

        # Get the COG URL for elevation data
        elevation_url = item.assets.get("data", item.assets.get("elevation"))
        if not elevation_url:
            logger.warning("No elevation asset found in 3DEP item")
            return None

        signed_url = elevation_url.href

        # Load and clip to bbox
        logger.info("Loading DEM from URL", url=signed_url[:100] + "...")

        da = rxr.open_rasterio(signed_url)

        # Transform bbox to DEM CRS for clipping
        dem_crs = da.rio.crs
        if dem_crs and dem_crs.to_epsg() != 4326:
            transformer = Transformer.from_crs(4326, dem_crs, always_xy=True)
            min_x, min_y = transformer.transform(bbox[0], bbox[1])
            max_x, max_y = transformer.transform(bbox[2], bbox[3])
        else:
            min_x, min_y, max_x, max_y = bbox

        # Clip to bbox
        try:
            da = da.rio.clip_box(minx=min_x, miny=min_y, maxx=max_x, maxy=max_y)
        except Exception as e:
            logger.warning("Could not clip DEM to bbox", error=str(e))

        # Squeeze band dimension if present
        if da.ndim == 3 and da.shape[0] == 1:
            da = da.squeeze("band", drop=True)

        # Calculate resolution in meters
        res_x = abs(float(da.rio.resolution()[0]))
        res_y = abs(float(da.rio.resolution()[1]))
        resolution_m = (res_x + res_y) / 2

        logger.info(
            "DEM loaded",
            shape=da.shape,
            crs=str(dem_crs),
            resolution_m=resolution_m,
        )

        return DEMData(
            elevation=da,
            crs=dem_crs,
            transform=da.rio.transform(),
            resolution_m=resolution_m,
        )

    except ImportError as e:
        logger.warning("Missing dependency for 3DEP access", error=str(e))
        return None
    except Exception as e:
        logger.error("Failed to load 3DEP DEM", error=str(e))
        return None


def _load_local_dem(dem_path: Path, bbox: tuple[float, float, float, float]) -> DEMData | None:
    """Load DEM from a local file.

    Args:
        dem_path: Path to local DEM GeoTIFF.
        bbox: Bounding box for clipping.

    Returns:
        DEMData or None if file doesn't exist.
    """
    if not dem_path.exists():
        logger.warning("Local DEM file not found", path=str(dem_path))
        return None

    try:
        da = rxr.open_rasterio(dem_path)

        # Transform bbox to DEM CRS for clipping
        dem_crs = da.rio.crs
        if dem_crs and dem_crs.to_epsg() != 4326:
            transformer = Transformer.from_crs(4326, dem_crs, always_xy=True)
            min_x, min_y = transformer.transform(bbox[0], bbox[1])
            max_x, max_y = transformer.transform(bbox[2], bbox[3])
        else:
            min_x, min_y, max_x, max_y = bbox

        # Clip to bbox
        da = da.rio.clip_box(minx=min_x, miny=min_y, maxx=max_x, maxy=max_y)

        if da.ndim == 3 and da.shape[0] == 1:
            da = da.squeeze("band", drop=True)

        res_x = abs(float(da.rio.resolution()[0]))
        res_y = abs(float(da.rio.resolution()[1]))
        resolution_m = (res_x + res_y) / 2

        return DEMData(
            elevation=da,
            crs=dem_crs,
            transform=da.rio.transform(),
            resolution_m=resolution_m,
        )

    except Exception as e:
        logger.error("Failed to load local DEM", path=str(dem_path), error=str(e))
        return None


def calculate_slope_aspect(dem: DEMData) -> DEMData:
    """Calculate slope and aspect rasters from DEM elevation.

    Uses the Horn (1981) algorithm for slope and aspect calculation.

    Args:
        dem: DEMData with elevation raster.

    Returns:
        DEMData with slope and aspect rasters added.
    """
    logger.info("Calculating slope and aspect")

    elev = dem.elevation.values.astype(np.float64)

    # Handle NaN values
    nodata_mask = np.isnan(elev)
    if nodata_mask.any():
        elev = np.where(nodata_mask, 0, elev)

    # Cell size in meters (assumes projected CRS or approximately equal resolution)
    cell_size = dem.resolution_m

    # Calculate gradients using Sobel-like filters (Horn algorithm)
    # dz/dx kernel: [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]] / (8 * cell_size)
    # dz/dy kernel: [[1, 2, 1], [0, 0, 0], [-1, -2, -1]] / (8 * cell_size)

    kernel_x = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]) / (8 * cell_size)
    kernel_y = np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]]) / (8 * cell_size)

    dz_dx = ndimage.convolve(elev, kernel_x, mode="nearest")
    dz_dy = ndimage.convolve(elev, kernel_y, mode="nearest")

    # Calculate slope in degrees
    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    slope_deg = np.degrees(slope_rad)

    # Calculate aspect in degrees (0=N, 90=E, 180=S, 270=W)
    aspect_rad = np.arctan2(-dz_dx, dz_dy)  # Note the negation for proper orientation
    aspect_deg = np.degrees(aspect_rad)
    aspect_deg = np.where(aspect_deg < 0, aspect_deg + 360, aspect_deg)

    # Restore NaN values
    if nodata_mask.any():
        slope_deg = np.where(nodata_mask, np.nan, slope_deg)
        aspect_deg = np.where(nodata_mask, np.nan, aspect_deg)

    # Create DataArrays with same coordinates as elevation
    slope_da = dem.elevation.copy(data=slope_deg.astype(np.float32))
    aspect_da = dem.elevation.copy(data=aspect_deg.astype(np.float32))

    logger.info(
        "Slope/aspect calculated",
        slope_min=float(np.nanmin(slope_deg)),
        slope_max=float(np.nanmax(slope_deg)),
        slope_mean=float(np.nanmean(slope_deg)),
    )

    return DEMData(
        elevation=dem.elevation,
        slope=slope_da,
        aspect=aspect_da,
        crs=dem.crs,
        transform=dem.transform,
        resolution_m=dem.resolution_m,
    )


def sample_terrain_at_point(dem: DEMData, point: Point) -> TerrainData | None:
    """Sample terrain data at a specific point.

    Args:
        dem: DEMData with elevation (and optionally slope/aspect).
        point: Point geometry in WGS84.

    Returns:
        TerrainData or None if point is outside DEM bounds.
    """
    # Transform point to DEM CRS if needed
    if dem.crs and CRS.from_user_input(dem.crs).to_epsg() != 4326:
        transformer = Transformer.from_crs(4326, dem.crs, always_xy=True)
        x, y = transformer.transform(point.x, point.y)
    else:
        x, y = point.x, point.y

    try:
        # Sample elevation
        elev = float(dem.elevation.sel(x=x, y=y, method="nearest").values)

        # Sample slope if available
        if dem.slope is not None:
            slope = float(dem.slope.sel(x=x, y=y, method="nearest").values)
        else:
            slope = 0.0

        # Sample aspect if available
        if dem.aspect is not None:
            aspect = float(dem.aspect.sel(x=x, y=y, method="nearest").values)
        else:
            aspect = 0.0

        if np.isnan(elev):
            return None

        return TerrainData(
            slope_degrees=slope if not np.isnan(slope) else 0.0,
            aspect_degrees=aspect if not np.isnan(aspect) else 0.0,
            elevation_m=elev,
        )

    except (KeyError, IndexError):
        logger.debug("Point outside DEM bounds", x=x, y=y)
        return None


def extract_terrain_stats_for_polygon(
    dem: DEMData,
    polygon: Polygon,
    polygon_crs: Any = None,
) -> dict[str, float]:
    """Extract terrain statistics within a polygon.

    Args:
        dem: DEMData with elevation, slope, aspect.
        polygon: Polygon geometry.
        polygon_crs: CRS of the polygon (default: WGS84).

    Returns:
        Dictionary with terrain statistics.
    """
    # Transform polygon to DEM CRS if needed
    if polygon_crs is None:
        polygon_crs = CRS.from_epsg(4326)
    else:
        polygon_crs = CRS.from_user_input(polygon_crs)

    dem_crs = CRS.from_user_input(dem.crs) if dem.crs else CRS.from_epsg(4326)

    if polygon_crs != dem_crs:
        transformer = Transformer.from_crs(polygon_crs, dem_crs, always_xy=True)
        polygon = shapely_transform(transformer.transform, polygon)

    # Create mask for the polygon
    elev_array = dem.elevation.values
    if elev_array.ndim == 3:
        elev_array = elev_array[0]

    try:
        mask = rio_features.geometry_mask(
            [polygon],
            out_shape=elev_array.shape,
            transform=dem.transform,
            invert=True,
        )
    except Exception as e:
        logger.warning("Could not create polygon mask", error=str(e))
        return {
            "elevation_m": 0.0,
            "slope_degree_mean": 0.0,
            "slope_degree_max": 0.0,
            "aspect_degrees": 0.0,
        }

    # Extract statistics
    elev_values = elev_array[mask]
    elev_values = elev_values[~np.isnan(elev_values)]

    stats = {
        "elevation_m": float(np.mean(elev_values)) if len(elev_values) > 0 else 0.0,
    }

    if dem.slope is not None:
        slope_array = dem.slope.values
        if slope_array.ndim == 3:
            slope_array = slope_array[0]
        slope_values = slope_array[mask]
        slope_values = slope_values[~np.isnan(slope_values)]

        stats["slope_degree_mean"] = float(np.mean(slope_values)) if len(slope_values) > 0 else 0.0
        stats["slope_degree_max"] = float(np.max(slope_values)) if len(slope_values) > 0 else 0.0

    if dem.aspect is not None:
        aspect_array = dem.aspect.values
        if aspect_array.ndim == 3:
            aspect_array = aspect_array[0]
        aspect_values = aspect_array[mask]
        aspect_values = aspect_values[~np.isnan(aspect_values)]

        # Calculate mean aspect using circular mean
        if len(aspect_values) > 0:
            aspect_rad = np.radians(aspect_values)
            mean_sin = np.mean(np.sin(aspect_rad))
            mean_cos = np.mean(np.cos(aspect_rad))
            mean_aspect = np.degrees(np.arctan2(mean_sin, mean_cos))
            stats["aspect_degrees"] = float(mean_aspect % 360)
        else:
            stats["aspect_degrees"] = 0.0

    return stats


def calculate_directional_metrics(
    dem: DEMData,
    change_centroid: Point,
    asset_location: Point,
) -> DirectionalTerrainMetrics | None:
    """Calculate directional terrain relationship between change and asset.

    Args:
        dem: DEMData with elevation.
        change_centroid: Centroid of change polygon (WGS84).
        asset_location: Asset location point (WGS84).

    Returns:
        DirectionalTerrainMetrics or None if elevations can't be sampled.
    """
    # Sample elevations at both points
    change_terrain = sample_terrain_at_point(dem, change_centroid)
    asset_terrain = sample_terrain_at_point(dem, asset_location)

    if change_terrain is None or asset_terrain is None:
        return None

    change_elev = change_terrain.elevation_m
    asset_elev = asset_terrain.elevation_m

    elevation_diff = change_elev - asset_elev

    # Consider "upslope" if change is >5m higher than asset
    is_upslope = elevation_diff > 5.0

    # Calculate slope angle toward asset
    slope_toward = _calculate_slope_toward_point(
        dem, change_centroid, asset_location, change_elev, asset_elev
    )

    return DirectionalTerrainMetrics(
        change_elevation_m=change_elev,
        asset_elevation_m=asset_elev,
        elevation_diff_m=elevation_diff,
        is_upslope=is_upslope,
        slope_toward_asset_deg=slope_toward,
    )


def _calculate_slope_toward_point(
    dem: DEMData,
    from_point: Point,
    to_point: Point,
    from_elev: float,
    to_elev: float,
) -> float:
    """Calculate slope angle from one point toward another.

    Args:
        dem: DEMData (used for CRS info).
        from_point: Starting point (WGS84).
        to_point: Target point (WGS84).
        from_elev: Elevation at from_point.
        to_elev: Elevation at to_point.

    Returns:
        Slope angle in degrees. Positive = downhill toward target.
    """
    # Transform to projected CRS for accurate distance
    centroid = Point((from_point.x + to_point.x) / 2, (from_point.y + to_point.y) / 2)

    from georisk.geo_utils import get_utm_transformer

    transformer = get_utm_transformer(centroid.x, centroid.y)

    from_x, from_y = transformer.transform(from_point.x, from_point.y)
    to_x, to_y = transformer.transform(to_point.x, to_point.y)

    # Horizontal distance
    dist_m = math.sqrt((to_x - from_x) ** 2 + (to_y - from_y) ** 2)

    if dist_m < 1.0:  # Avoid division by zero
        return 0.0

    # Elevation difference (positive = from is higher = downhill toward to)
    elev_diff = from_elev - to_elev

    # Slope angle
    slope_rad = math.atan2(elev_diff, dist_m)
    return math.degrees(slope_rad)


def is_change_upslope_from_asset(
    dem: DEMData,
    change_centroid: Point,
    asset_location: Point,
    threshold_m: float = 5.0,
) -> tuple[bool, float]:
    """Determine if change polygon is upslope from asset.

    Args:
        dem: DEMData with elevation.
        change_centroid: Centroid of change polygon (WGS84).
        asset_location: Asset location (WGS84).
        threshold_m: Minimum elevation difference to consider "upslope".

    Returns:
        Tuple of (is_upslope, elevation_difference_meters).
    """
    metrics = calculate_directional_metrics(dem, change_centroid, asset_location)

    if metrics is None:
        return False, 0.0

    return metrics.is_upslope, metrics.elevation_diff_m
