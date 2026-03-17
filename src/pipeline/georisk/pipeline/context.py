from dataclasses import dataclass, field
from typing import Any
from georisk.config import Config, get_config
from georisk.db.client import ApiClient
from georisk.stac.search import SceneInfo
from georisk.storage.minio import MinioStorage
from georisk.raster.ndvi import NdviResult
from georisk.raster.change import ChangeDetectionResult
from georisk.raster.terrain import DEMData

@dataclass
class StepContext:
    # --- Inputs ---
    aoi_id: str
    aoi: dict[str, Any]
    bbox: tuple[float, float, float, float]
    before_date: str
    after_date: str
    run_id: str | None
    dry_run: bool
    window: int
    threshold: float | None 
    min_area: float | None
    max_distance: float | None
    dem_source: str
    skip_terrain: bool
    skip_landcover: bool
    skip_landslide: bool
    skip_lidar: bool

    # --- Services ---
    api: ApiClient
    storage: MinioStorage | None = None
    config: Config = field(default_factory=get_config)
    
    # --- Intermediate results ---
    before_scene: SceneInfo | None = None
    after_scene: SceneInfo | None = None
    before_ndvi: NdviResult | None = None
    after_ndvi: NdviResult | None = None
    changes: ChangeDetectionResult | None = None
    dem_data: DEMData | None = None
    scene_bands: Any | None = None  #xarray DataArray, but use Any to avoid heavy import
    created_polygon_ids: list[str] = field(default_factory=list)
    risk_events: list[dict[str, Any]] = field(default_factory=list)
    lidar_polygons_processed: int = 0
    lidar_polygon_count: int = 0