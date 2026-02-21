"""Raster processing modules for NDVI, change detection, and terrain analysis."""

from georisk.raster.change import ChangePolygon, detect_changes
from georisk.raster.download import clip_to_aoi, download_scene
from georisk.raster.ndvi import NdviResult, calculate_ndvi
from georisk.raster.terrain import (
    DEMData,
    DirectionalTerrainMetrics,
    TerrainData,
    calculate_slope_aspect,
    extract_terrain_stats_for_polygon,
    load_dem_for_bbox,
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
