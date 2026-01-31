"""Raster processing modules for NDVI, change detection, and terrain analysis."""

from georisk.raster.ndvi import calculate_ndvi, NdviResult
from georisk.raster.change import detect_changes, ChangePolygon
from georisk.raster.download import download_scene, clip_to_aoi
from georisk.raster.terrain import (
    load_dem_for_bbox,
    calculate_slope_aspect,
    extract_terrain_stats_for_polygon,
    DEMData,
    TerrainData,
    DirectionalTerrainMetrics,
)

__all__ = [
    "calculate_ndvi",
    "NdviResult",
    "detect_changes",
    "ChangePolygon",
    "download_scene",
    "clip_to_aoi",
    # Terrain analysis
    "load_dem_for_bbox",
    "calculate_slope_aspect",
    "extract_terrain_stats_for_polygon",
    "DEMData",
    "TerrainData",
    "DirectionalTerrainMetrics",
]
