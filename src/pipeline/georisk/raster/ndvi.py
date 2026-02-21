"""NDVI calculation from satellite imagery."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import structlog
import xarray as xr

from georisk.raster.download import load_band, load_band_from_url
from georisk.stac.search import SceneInfo

logger = structlog.get_logger()


@dataclass
class NdviResult:
    """Result of NDVI calculation."""

    data: xr.DataArray
    scene_id: str
    datetime: str
    crs: Any
    transform: Any
    min_value: float
    max_value: float
    mean_value: float

    def save(self, output_path: Path) -> Path:
        """Save NDVI raster to a GeoTIFF file.

        Args:
            output_path: Output file path.

        Returns:
            Path to the saved file.
        """
        self.data.rio.to_raster(output_path)
        logger.info(
            "Saved NDVI raster",
            path=str(output_path),
            mean=f"{self.mean_value:.3f}",
        )
        return output_path


def calculate_ndvi(
    red_band: xr.DataArray | Path | str,
    nir_band: xr.DataArray | Path | str,
    scene_id: str = "unknown",
    datetime_str: str = "",
    nodata_value: float = 0,
) -> NdviResult:
    """Calculate NDVI from red and NIR bands.

    NDVI = (NIR - Red) / (NIR + Red)

    Args:
        red_band: Red band data (B04 for Sentinel-2) as DataArray, file path, or URL.
        nir_band: NIR band data (B08 for Sentinel-2) as DataArray, file path, or URL.
        scene_id: Scene identifier for tracking.
        datetime_str: Scene datetime string.
        nodata_value: Value to use for nodata/invalid pixels.

    Returns:
        NdviResult with calculated NDVI values.
    """
    logger.info("Calculating NDVI", scene_id=scene_id)

    # Load bands if paths/URLs provided
    if isinstance(red_band, (str, Path)):
        red = (
            load_band(Path(red_band))
            if Path(red_band).exists()
            else load_band_from_url(str(red_band))
        )
    else:
        red = red_band

    if isinstance(nir_band, (str, Path)):
        nir = (
            load_band(Path(nir_band))
            if Path(nir_band).exists()
            else load_band_from_url(str(nir_band))
        )
    else:
        nir = nir_band

    # Convert to float for calculation
    red_f = red.astype(np.float32)
    nir_f = nir.astype(np.float32)

    # Calculate NDVI with division-by-zero handling
    denominator = nir_f + red_f
    ndvi = xr.where(
        denominator != 0,
        (nir_f - red_f) / denominator,
        nodata_value,
    )

    # Clip to valid NDVI range [-1, 1]
    ndvi = ndvi.clip(-1, 1)

    # Copy CRS and transform from input
    ndvi = ndvi.rio.write_crs(red.rio.crs)
    if hasattr(red.rio, "transform"):
        ndvi = ndvi.rio.write_transform(red.rio.transform())

    # Calculate statistics (excluding nodata)
    valid_mask = ndvi != nodata_value
    valid_data = ndvi.where(valid_mask)

    result = NdviResult(
        data=ndvi,
        scene_id=scene_id,
        datetime=datetime_str,
        crs=red.rio.crs,
        transform=red.rio.transform() if hasattr(red.rio, "transform") else None,
        min_value=float(valid_data.min().values) if valid_mask.any() else -1,
        max_value=float(valid_data.max().values) if valid_mask.any() else 1,
        mean_value=float(valid_data.mean().values) if valid_mask.any() else 0,
    )

    logger.info(
        "NDVI calculated",
        scene_id=scene_id,
        min=f"{result.min_value:.3f}",
        max=f"{result.max_value:.3f}",
        mean=f"{result.mean_value:.3f}",
    )

    return result


def calculate_ndvi_from_scene(
    scene: SceneInfo,
    bbox: tuple[float, float, float, float] | None = None,
) -> NdviResult:
    """Calculate NDVI directly from a scene's band URLs.

    Args:
        scene: SceneInfo with band URLs.
        bbox: Optional bounding box to clip to.

    Returns:
        NdviResult with calculated NDVI values.
    """
    red_url = scene.get_band_url("B04")
    nir_url = scene.get_band_url("B08")

    if not red_url or not nir_url:
        raise ValueError(f"Scene {scene.scene_id} missing required bands (B04, B08)")

    logger.info(
        "Loading bands from URLs",
        scene_id=scene.scene_id,
        bbox=bbox,
    )

    # Load bands directly from URLs with optional bbox clipping
    red = load_band_from_url(red_url, bbox)
    nir = load_band_from_url(nir_url, bbox)

    return calculate_ndvi(
        red_band=red,
        nir_band=nir,
        scene_id=scene.scene_id,
        datetime_str=scene.datetime.isoformat(),
    )
