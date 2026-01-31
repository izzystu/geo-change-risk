"""Change detection from NDVI time series."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
import structlog
import xarray as xr
from rasterio import features
from shapely.geometry import shape, Polygon

from georisk.config import get_config
from georisk.raster.ndvi import NdviResult

logger = structlog.get_logger()


@dataclass
class ChangePolygon:
    """A detected change polygon."""

    geometry: Polygon
    area_sq_meters: float
    ndvi_drop_mean: float
    ndvi_drop_max: float
    change_type: str = "VegetationLoss"
    slope_degree_mean: float | None = None
    slope_degree_max: float | None = None
    aspect_degrees: float | None = None
    elevation_m: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API submission (camelCase for C# API)."""
        # Map change type string to int value
        change_type_map = {
            "Unknown": 0,
            "VegetationLoss": 1,
            "VegetationGain": 2,
            "UrbanExpansion": 3,
            "WaterChange": 4,
            "FireBurnScar": 5,
            "LandslideDebris": 6,
            "DroughtStress": 7,
            "AgriculturalChange": 8,
        }
        change_type_int = change_type_map.get(self.change_type, 0)

        return {
            "geometry": self.geometry.__geo_interface__,
            "areaSqMeters": self.area_sq_meters,
            "ndviDropMean": self.ndvi_drop_mean,
            "ndviDropMax": self.ndvi_drop_max,
            "changeType": change_type_int,
            "slopeDegreeMean": self.slope_degree_mean,
            "slopeDegreeMax": self.slope_degree_max,
            "aspectDegrees": self.aspect_degrees,
            "elevationM": self.elevation_m,
        }


@dataclass
class ChangeDetectionResult:
    """Result of change detection analysis."""

    ndvi_diff: xr.DataArray
    change_mask: xr.DataArray
    polygons: list[ChangePolygon]
    before_scene_id: str
    after_scene_id: str
    threshold: float
    stats: dict[str, float] = field(default_factory=dict)

    def save_diff_raster(self, output_path: Path) -> Path:
        """Save NDVI difference raster to a GeoTIFF file."""
        self.ndvi_diff.rio.to_raster(output_path)
        return output_path

    def save_mask_raster(self, output_path: Path) -> Path:
        """Save change mask raster to a GeoTIFF file."""
        self.change_mask.astype(np.uint8).rio.to_raster(output_path)
        return output_path

    def to_geodataframe(self) -> gpd.GeoDataFrame:
        """Convert change polygons to a GeoDataFrame."""
        if not self.polygons:
            return gpd.GeoDataFrame(
                columns=[
                    "geometry", "area_sq_meters", "ndvi_drop_mean", "ndvi_drop_max",
                    "change_type", "slope_degree_mean", "slope_degree_max",
                    "aspect_degrees", "elevation_m",
                ],
                crs="EPSG:4326",
            )

        records = [
            {
                "geometry": p.geometry,
                "area_sq_meters": p.area_sq_meters,
                "ndvi_drop_mean": p.ndvi_drop_mean,
                "ndvi_drop_max": p.ndvi_drop_max,
                "change_type": p.change_type,
                "slope_degree_mean": p.slope_degree_mean,
                "slope_degree_max": p.slope_degree_max,
                "aspect_degrees": p.aspect_degrees,
                "elevation_m": p.elevation_m,
            }
            for p in self.polygons
        ]
        return gpd.GeoDataFrame(records, crs="EPSG:4326")


def detect_changes(
    before_ndvi: NdviResult,
    after_ndvi: NdviResult,
    threshold: float | None = None,
    min_area_m2: float | None = None,
) -> ChangeDetectionResult:
    """Detect changes between two NDVI images.

    Change is detected where NDVI drops below the threshold
    (negative change indicates vegetation loss).

    Args:
        before_ndvi: NDVI result for the "before" period.
        after_ndvi: NDVI result for the "after" period.
        threshold: NDVI drop threshold (negative value, e.g., -0.2).
        min_area_m2: Minimum polygon area in square meters.

    Returns:
        ChangeDetectionResult with difference raster, mask, and polygons.
    """
    config = get_config()
    threshold = threshold if threshold is not None else config.processing.ndvi_threshold
    min_area = min_area_m2 if min_area_m2 is not None else config.processing.min_area_m2

    logger.info(
        "Detecting changes",
        before_scene=before_ndvi.scene_id,
        after_scene=after_ndvi.scene_id,
        threshold=threshold,
        min_area_m2=min_area,
    )

    # Calculate NDVI difference (after - before)
    # Negative values indicate vegetation loss
    ndvi_diff = after_ndvi.data - before_ndvi.data

    # Create binary change mask (1 = significant vegetation loss)
    change_mask = xr.where(ndvi_diff < threshold, 1, 0)

    # Copy spatial reference
    ndvi_diff = ndvi_diff.rio.write_crs(before_ndvi.crs)
    change_mask = change_mask.rio.write_crs(before_ndvi.crs)

    # Vectorize change mask to polygons
    polygons = _vectorize_changes(
        change_mask=change_mask.values,
        ndvi_diff=ndvi_diff.values,
        transform=before_ndvi.transform,
        crs=before_ndvi.crs,
        min_area_m2=min_area,
    )

    # Calculate statistics
    valid_diff = ndvi_diff.where(ndvi_diff != 0)
    stats = {
        "mean_diff": float(valid_diff.mean().values) if valid_diff.any() else 0,
        "min_diff": float(valid_diff.min().values) if valid_diff.any() else 0,
        "max_diff": float(valid_diff.max().values) if valid_diff.any() else 0,
        "changed_pixels": int(change_mask.sum().values),
        "total_pixels": int(change_mask.size),
        "change_percent": float(change_mask.sum().values / change_mask.size * 100),
    }

    logger.info(
        "Change detection complete",
        num_polygons=len(polygons),
        changed_percent=f"{stats['change_percent']:.2f}%",
    )

    return ChangeDetectionResult(
        ndvi_diff=ndvi_diff,
        change_mask=change_mask,
        polygons=polygons,
        before_scene_id=before_ndvi.scene_id,
        after_scene_id=after_ndvi.scene_id,
        threshold=threshold,
        stats=stats,
    )


def _vectorize_changes(
    change_mask: np.ndarray,
    ndvi_diff: np.ndarray,
    transform: Any,
    crs: Any,
    min_area_m2: float,
) -> list[ChangePolygon]:
    """Convert change mask raster to vector polygons.

    Args:
        change_mask: Binary change mask array.
        ndvi_diff: NDVI difference array.
        transform: Raster transform.
        crs: Coordinate reference system (of the raster).
        min_area_m2: Minimum polygon area in square meters.

    Returns:
        List of ChangePolygon objects (geometries in WGS84/EPSG:4326).
    """
    from pyproj import CRS, Transformer
    from shapely.ops import transform as shapely_transform

    polygons = []

    # Ensure arrays are 2D
    if change_mask.ndim == 3:
        change_mask = change_mask[0]
    if ndvi_diff.ndim == 3:
        ndvi_diff = ndvi_diff[0]

    # Set up CRS transformation from raster CRS to WGS84
    source_crs = CRS.from_user_input(crs) if crs else CRS.from_epsg(4326)
    wgs84_crs = CRS.from_epsg(4326)

    # Check if source is already geographic (WGS84) or projected
    is_projected = source_crs.is_projected

    # Create transformer to WGS84 if needed
    to_wgs84 = None
    if source_crs != wgs84_crs:
        to_wgs84 = Transformer.from_crs(source_crs, wgs84_crs, always_xy=True)

    # Extract shapes from the mask
    for geom, value in features.shapes(
        change_mask.astype(np.uint8),
        mask=change_mask == 1,
        transform=transform,
    ):
        if value != 1:
            continue

        # Polygon is in raster's native CRS
        polygon_native = shape(geom)

        # Calculate area in square meters
        # If source is already projected (UTM), area is in meters^2
        # If source is geographic (WGS84), we need to project to UTM
        area_m2 = _calculate_area_m2(polygon_native, source_crs, is_projected)

        if area_m2 < min_area_m2:
            continue

        # Extract NDVI statistics within this polygon (in native CRS)
        ndvi_stats = _extract_polygon_stats(polygon_native, ndvi_diff, transform)

        # Transform polygon to WGS84 for storage
        if to_wgs84:
            polygon_wgs84 = shapely_transform(to_wgs84.transform, polygon_native)
        else:
            polygon_wgs84 = polygon_native

        change_polygon = ChangePolygon(
            geometry=polygon_wgs84,
            area_sq_meters=area_m2,
            ndvi_drop_mean=ndvi_stats["mean"],
            ndvi_drop_max=ndvi_stats["max"],
            change_type=_classify_change(ndvi_stats["mean"]),
        )
        polygons.append(change_polygon)

    logger.debug(f"Vectorized {len(polygons)} change polygons")
    return polygons


def _calculate_area_m2(polygon: Polygon, crs: Any, is_projected: bool) -> float:
    """Calculate polygon area in square meters.

    Args:
        polygon: The polygon geometry (in the source CRS).
        crs: The source coordinate reference system.
        is_projected: Whether the CRS is already projected (area in meters).

    Returns:
        Area in square meters.
    """
    from pyproj import CRS, Transformer
    from shapely.ops import transform as shapely_transform

    # If source CRS is already projected (e.g., UTM), area is in the CRS units (meters^2)
    if is_projected:
        return polygon.area

    # For geographic CRS, transform to an appropriate UTM zone
    source_crs = CRS.from_user_input(crs) if crs else CRS.from_epsg(4326)

    from georisk.geo_utils import get_utm_crs

    # Get UTM zone from the polygon centroid (in WGS84)
    centroid = polygon.centroid
    utm_crs = get_utm_crs(centroid.x, centroid.y)

    # Transform to UTM and calculate area
    transformer = Transformer.from_crs(source_crs, utm_crs, always_xy=True)
    utm_polygon = shapely_transform(transformer.transform, polygon)
    return utm_polygon.area


def _extract_polygon_stats(
    polygon: Polygon,
    ndvi_diff: np.ndarray,
    transform: Any,
) -> dict[str, float]:
    """Extract NDVI statistics within a polygon."""
    from rasterio import features as rio_features

    # Create a mask for the polygon
    mask = rio_features.geometry_mask(
        [polygon],
        out_shape=ndvi_diff.shape,
        transform=transform,
        invert=True,
    )

    # Extract values within polygon
    values = ndvi_diff[mask]
    values = values[~np.isnan(values)]

    if len(values) == 0:
        return {"mean": 0, "max": 0, "min": 0}

    return {
        "mean": float(np.mean(values)),
        "max": float(np.max(values)),
        "min": float(np.min(values)),
    }


def _classify_change(mean_ndvi_drop: float) -> str:
    """Classify the type of change based on NDVI drop magnitude."""
    if mean_ndvi_drop < -0.4:
        return "VegetationLoss"  # Severe loss
    elif mean_ndvi_drop < -0.2:
        return "VegetationLoss"  # Moderate loss
    elif mean_ndvi_drop > 0.2:
        return "VegetationGain"  # Growth
    else:
        return "Unknown"
