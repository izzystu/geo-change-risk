"""Configuration management for the GeoRisk pipeline."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass
class StacConfig:
    """STAC catalog configuration."""

    catalog_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    collection: str = "sentinel-2-l2a"
    max_cloud_cover: float = 20.0


@dataclass
class MinioConfig:
    """MinIO storage configuration."""

    endpoint: str = "localhost:9000"
    access_key: str = ""
    secret_key: str = ""
    secure: bool = False
    bucket_imagery: str = "georisk-imagery"
    bucket_changes: str = "georisk-changes"


@dataclass
class ApiConfig:
    """API connection configuration."""

    base_url: str = "http://localhost:5074"
    timeout: float = 30.0


@dataclass
class ProcessingConfig:
    """Raster processing configuration."""

    ndvi_threshold: float = -0.2
    min_area_m2: float = 2500.0
    temporal_window_days: int = 90
    max_proximity_m: float = 500.0  # Default proximity distance for risk events


@dataclass
class TerrainConfig:
    """Terrain analysis configuration."""

    enabled: bool = True
    dem_source: str = "3dep"  # "3dep", "copernicus", "local"
    local_dem_path: str | None = None
    cache_dem: bool = True


@dataclass
class MlConfig:
    """Machine learning model configuration."""

    enabled: bool = True
    landcover_enabled: bool = True
    landcover_backbone: str = "resnet18"  # "resnet18" or "resnet50"
    landslide_enabled: bool = True
    landslide_model_path: str | None = None
    landslide_confidence_threshold: float = 0.5
    landslide_slope_threshold_deg: float = 10.0
    device: str = "auto"  # "cpu", "cuda", "auto"


@dataclass
class Config:
    """Main configuration container."""

    stac: StacConfig = field(default_factory=StacConfig)
    minio: MinioConfig = field(default_factory=MinioConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    terrain: TerrainConfig = field(default_factory=TerrainConfig)
    ml: MlConfig = field(default_factory=MlConfig)

    @classmethod
    def load(cls, config_dir: Path | None = None) -> "Config":
        """Load configuration from files and environment variables."""
        # Load .env file if present
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)

        config = cls()

        # Load YAML config files if config_dir provided
        if config_dir and config_dir.exists():
            processing_file = config_dir / "processing.yaml"
            if processing_file.exists():
                config._load_yaml(processing_file)

            risk_file = config_dir / "risk_scoring.yaml"
            if risk_file.exists():
                config._load_yaml(risk_file)

        # Override with environment variables
        config._load_from_env()

        return config

    def _load_yaml(self, path: Path) -> None:
        """Load configuration from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
            if data:
                self._apply_yaml_config(data)

    def _apply_yaml_config(self, data: dict[str, Any]) -> None:
        """Apply YAML configuration data."""
        if "stac" in data:
            stac = data["stac"]
            if "catalog_url" in stac:
                self.stac.catalog_url = stac["catalog_url"]
            if "collection" in stac:
                self.stac.collection = stac["collection"]
            if "max_cloud_cover" in stac:
                self.stac.max_cloud_cover = float(stac["max_cloud_cover"])

        if "ml" in data:
            ml = data["ml"]
            if "enabled" in ml:
                self.ml.enabled = bool(ml["enabled"])
            if "landcover_enabled" in ml:
                self.ml.landcover_enabled = bool(ml["landcover_enabled"])
            if "landcover_backbone" in ml:
                self.ml.landcover_backbone = ml["landcover_backbone"]
            if "device" in ml:
                self.ml.device = ml["device"]
            if "landslide_enabled" in ml:
                self.ml.landslide_enabled = bool(ml["landslide_enabled"])
            if "landslide_model_path" in ml:
                self.ml.landslide_model_path = ml["landslide_model_path"]
            if "landslide_confidence_threshold" in ml:
                self.ml.landslide_confidence_threshold = float(ml["landslide_confidence_threshold"])
            if "landslide_slope_threshold_deg" in ml:
                self.ml.landslide_slope_threshold_deg = float(ml["landslide_slope_threshold_deg"])

        if "change_detection" in data:
            cd = data["change_detection"]
            if "ndvi_threshold" in cd:
                self.processing.ndvi_threshold = float(cd["ndvi_threshold"])
            if "min_area_m2" in cd:
                self.processing.min_area_m2 = float(cd["min_area_m2"])
            if "temporal_window_days" in cd:
                self.processing.temporal_window_days = int(cd["temporal_window_days"])

    def _load_from_env(self) -> None:
        """Override configuration from environment variables."""
        # API
        if url := os.getenv("GEORISK_API_URL"):
            self.api.base_url = url

        # MinIO
        if endpoint := os.getenv("MINIO_ENDPOINT"):
            self.minio.endpoint = endpoint
        if access_key := os.getenv("MINIO_ACCESS_KEY"):
            self.minio.access_key = access_key
        if secret_key := os.getenv("MINIO_SECRET_KEY"):
            self.minio.secret_key = secret_key
        if secure := os.getenv("MINIO_SECURE"):
            self.minio.secure = secure.lower() in ("true", "1", "yes")
        if bucket := os.getenv("MINIO_BUCKET_IMAGERY"):
            self.minio.bucket_imagery = bucket
        if bucket := os.getenv("MINIO_BUCKET_CHANGES"):
            self.minio.bucket_changes = bucket

        # STAC
        if url := os.getenv("STAC_CATALOG_URL"):
            self.stac.catalog_url = url
        if cloud := os.getenv("STAC_MAX_CLOUD_COVER"):
            self.stac.max_cloud_cover = float(cloud)

        # Processing
        if threshold := os.getenv("NDVI_THRESHOLD"):
            self.processing.ndvi_threshold = float(threshold)
        if area := os.getenv("MIN_CHANGE_AREA_M2"):
            self.processing.min_area_m2 = float(area)
        if proximity := os.getenv("MAX_PROXIMITY_M"):
            self.processing.max_proximity_m = float(proximity)

        # ML
        if ml_enabled := os.getenv("ML_ENABLED"):
            self.ml.enabled = ml_enabled.lower() in ("true", "1", "yes")
        if landcover_enabled := os.getenv("LANDCOVER_ENABLED"):
            self.ml.landcover_enabled = landcover_enabled.lower() in ("true", "1", "yes")
        if landcover_backbone := os.getenv("LANDCOVER_BACKBONE"):
            self.ml.landcover_backbone = landcover_backbone
        if ml_device := os.getenv("ML_DEVICE"):
            self.ml.device = ml_device
        if landslide_enabled := os.getenv("LANDSLIDE_ENABLED"):
            self.ml.landslide_enabled = landslide_enabled.lower() in ("true", "1", "yes")
        if landslide_model_path := os.getenv("LANDSLIDE_MODEL_PATH"):
            self.ml.landslide_model_path = landslide_model_path
        if landslide_threshold := os.getenv("LANDSLIDE_CONFIDENCE_THRESHOLD"):
            self.ml.landslide_confidence_threshold = float(landslide_threshold)
        if landslide_slope := os.getenv("LANDSLIDE_SLOPE_THRESHOLD_DEG"):
            self.ml.landslide_slope_threshold_deg = float(landslide_slope)

        # Terrain
        if terrain_enabled := os.getenv("TERRAIN_ENABLED"):
            self.terrain.enabled = terrain_enabled.lower() in ("true", "1", "yes")
        if dem_source := os.getenv("DEM_SOURCE"):
            self.terrain.dem_source = dem_source
        if local_dem_path := os.getenv("LOCAL_DEM_PATH"):
            self.terrain.local_dem_path = local_dem_path
        if cache_dem := os.getenv("CACHE_DEM"):
            self.terrain.cache_dem = cache_dem.lower() in ("true", "1", "yes")


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get or create the global configuration instance."""
    global _config
    if _config is None:
        config_dir = Path(__file__).parent.parent / "config"
        _config = Config.load(config_dir)
    return _config


def reload_config(config_dir: Path | None = None) -> Config:
    """Reload configuration (useful for testing)."""
    global _config
    _config = Config.load(config_dir)
    return _config
