"""Landslide detection using a U-Net segmentation model.

Classifies change polygons on steep terrain as landslides by running inference
on 14-channel input (12 Sentinel-2 bands + slope + DEM elevation). Follows
the same graceful-degradation pattern as landcover.py.

Requires optional ML dependencies: pip install -e ".[ml]"
The pipeline degrades gracefully when these are not installed.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import structlog
import xarray as xr

logger = structlog.get_logger()


# 12 Sentinel-2 bands used in Landslide4Sense (B8A excluded)
LANDSLIDE_SENTINEL_BANDS: list[str] = [
    "B01", "B02", "B03", "B04", "B05", "B06",
    "B07", "B08", "B09", "B10", "B11", "B12",
]

LANDSLIDE_PATCH_SIZE = 128

DEFAULT_MODEL_PATH = Path.home() / ".cache" / "georisk" / "models" / "landslide_model.pth"

# Module-level model cache
_cached_model: "LandslideModel | None" = None


def is_landslide_available() -> bool:
    """Check if ML dependencies (torch, segmentation-models-pytorch) are installed."""
    try:
        import torch  # noqa: F401
        import segmentation_models_pytorch  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass
class LandslideModel:
    """Wrapper around a trained landslide U-Net model."""

    model: Any  # smp.Unet
    model_version: str
    device: str
    normalization_means: list[float]  # 14 values from checkpoint
    normalization_stds: list[float]   # 14 values from checkpoint
    patch_size: int
    confidence_threshold: float = 0.5


@dataclass
class LandslideResult:
    """Classification result for a single polygon."""

    is_landslide: bool
    landslide_probability: float       # Mean probability within polygon
    max_probability: float             # Peak pixel probability
    landslide_pixel_fraction: float    # Fraction of pixels above threshold
    model_version: str
    confidence_threshold: float


def _ensure_model_cached(target_path: Path) -> Path | None:
    """Try to download the landslide model from object storage to local cache.

    Returns the path if successfully downloaded, or None if the model is not
    available in storage or storage is unreachable. Designed for graceful
    degradation — storage errors are logged but never raised.

    Args:
        target_path: Local path to download the model to.

    Returns:
        Path to the cached model file, or None if not available.
    """
    if target_path.exists():
        return target_path

    try:
        from georisk.storage.minio import MinioStorage

        storage = MinioStorage()
        if storage.model_exists():
            logger.info("Downloading landslide model from object storage")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            storage.download_model(target_path)
            logger.info("Landslide model cached", path=str(target_path))
            return target_path
        else:
            logger.debug("Landslide model not found in object storage")
            return None
    except Exception as e:
        logger.debug(f"Could not retrieve model from object storage: {e}")
        return None


def load_landslide_model(
    model_path: str | Path | None = None,
    device: str | None = None,
    confidence_threshold: float = 0.5,
) -> LandslideModel:
    """Load a trained landslide U-Net model from a checkpoint.

    The model is cached at module level to avoid reloading across calls.

    Args:
        model_path: Path to .pth checkpoint. Defaults to standard locations.
        device: Torch device ("cpu", "cuda", or None for auto-detect).
        confidence_threshold: Probability threshold for landslide classification.

    Returns:
        LandslideModel wrapper with loaded model.

    Raises:
        FileNotFoundError: If no model checkpoint is found.
    """
    global _cached_model
    if _cached_model is not None:
        return _cached_model

    import torch
    import segmentation_models_pytorch as smp

    if device is None or device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    # Resolve model path
    if model_path is None:
        model_path = DEFAULT_MODEL_PATH

    model_path = Path(model_path)

    # Also check src/pipeline/models/ as alternative
    if not model_path.exists():
        alt_path = Path(__file__).parent.parent.parent / "models" / "landslide_model.pth"
        if alt_path.exists():
            model_path = alt_path
        else:
            # Try downloading from object storage (S3/MinIO)
            cached = _ensure_model_cached(DEFAULT_MODEL_PATH)
            if cached is not None:
                model_path = cached
            else:
                raise FileNotFoundError(
                    f"Landslide model not found at {model_path} or {alt_path}. "
                    f"Upload with 'georisk model upload', train a model "
                    f"(see machine-learning/landslide/), or set LANDSLIDE_MODEL_PATH."
                )

    logger.info("Loading landslide model", path=str(model_path), device=device)

    checkpoint = torch.load(model_path, map_location=device, weights_only=False)

    encoder_name = checkpoint.get("encoder_name", "resnet34")
    in_channels = checkpoint.get("in_channels", 14)
    patch_size = checkpoint.get("patch_size", LANDSLIDE_PATCH_SIZE)
    model_version = checkpoint.get("model_version", "landslide-unet-unknown")

    normalization = checkpoint.get("normalization", {})
    means = normalization.get("means", [0.0] * 14)
    stds = normalization.get("stds", [1.0] * 14)

    model = smp.Unet(
        encoder_name=encoder_name,
        encoder_weights=None,
        in_channels=in_channels,
        classes=1,
        activation=None,
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(device)
    model.eval()

    _cached_model = LandslideModel(
        model=model,
        model_version=model_version,
        device=device,
        normalization_means=means,
        normalization_stds=stds,
        patch_size=patch_size,
        confidence_threshold=confidence_threshold,
    )

    metrics = checkpoint.get("metrics", {})
    logger.info(
        "Landslide model loaded",
        version=model_version,
        val_iou=metrics.get("val_iou"),
    )
    return _cached_model


def assemble_landslide_input(
    scene_bands: xr.DataArray,
    dem_data: Any,
    polygon: Any,
) -> np.ndarray | None:
    """Build a 14-channel (14, 128, 128) input patch for landslide inference.

    Channels 0-11: 12 Sentinel-2 bands (from scene_bands)
    Channel 12: Slope in degrees (from dem_data)
    Channel 13: DEM elevation in meters (from dem_data)

    Args:
        scene_bands: Pre-loaded multi-band DataArray from load_scene_bands().
            Must have 12 bands (LANDSLIDE_SENTINEL_BANDS order).
        dem_data: DEM data object with slope and elevation arrays (xarray).
        polygon: Shapely Polygon geometry.

    Returns:
        Numpy array of shape (14, 128, 128) or None on failure.
    """
    try:
        centroid = polygon.centroid
        bounds = polygon.bounds

        # Extract 12-band spectral patch
        spectral_patch = _extract_patch(scene_bands, bounds, centroid)
        if spectral_patch is None:
            logger.debug("Failed to extract spectral patch for landslide input")
            return None

        # Get slope and elevation from DEM data
        slope_array = _get_dem_channel(dem_data, "slope", scene_bands)
        elev_array = _get_dem_channel(dem_data, "elevation", scene_bands)

        if slope_array is None or elev_array is None:
            logger.debug("Failed to get DEM channels for landslide input")
            return None

        # Extract patches from slope and elevation
        slope_patch = _extract_single_band_patch(slope_array, bounds, centroid)
        elev_patch = _extract_single_band_patch(elev_array, bounds, centroid)

        if slope_patch is None or elev_patch is None:
            logger.debug("Failed to extract DEM patches for landslide input")
            return None

        # Stack: (12, 128, 128) + (1, 128, 128) + (1, 128, 128) = (14, 128, 128)
        combined = np.concatenate([
            spectral_patch,       # (12, 128, 128)
            slope_patch[np.newaxis, ...],   # (1, 128, 128)
            elev_patch[np.newaxis, ...],    # (1, 128, 128)
        ], axis=0)

        return combined.astype(np.float32)

    except Exception as e:
        logger.debug(f"Landslide input assembly failed: {e}")
        return None


def classify_polygon_landslide(
    scene_bands: xr.DataArray,
    dem_data: Any,
    polygon: Any,
    model: LandslideModel | None = None,
    slope_threshold_deg: float = 10.0,
) -> LandslideResult | None:
    """Classify whether a polygon represents a landslide.

    Args:
        scene_bands: Pre-loaded 12-band DataArray (LANDSLIDE_SENTINEL_BANDS).
        dem_data: DEM data with slope and elevation.
        polygon: Shapely Polygon geometry.
        model: Pre-loaded landslide model. If None, loads automatically.
        slope_threshold_deg: Minimum slope to consider for classification.

    Returns:
        LandslideResult with classification outcome, or None on failure.
    """
    try:
        import torch

        if model is None:
            model = load_landslide_model()

        # Assemble 14-channel input
        input_patch = assemble_landslide_input(scene_bands, dem_data, polygon)
        if input_patch is None:
            return None

        # Normalize using checkpoint statistics
        normalized = _normalize_landslide_patch(
            input_patch, model.normalization_means, model.normalization_stds,
        )

        # Run inference
        tensor = torch.tensor(normalized, dtype=torch.float32).unsqueeze(0)  # (1, 14, 128, 128)
        tensor = tensor.to(model.device)

        with torch.no_grad():
            logits = model.model(tensor)       # (1, 1, 128, 128)
            probs = torch.sigmoid(logits)      # (1, 1, 128, 128)

        probs_np = probs.cpu().numpy()[0, 0]  # (128, 128)

        # Compute statistics
        mean_prob = float(np.mean(probs_np))
        max_prob = float(np.max(probs_np))
        pixel_fraction = float(
            np.sum(probs_np > model.confidence_threshold) / probs_np.size
        )

        # Dual classification criteria to reduce false positives:
        # - Mean probability exceeds 70% of threshold
        # - At least 15% of pixels exceed the full threshold
        is_landslide = (
            mean_prob > model.confidence_threshold * 0.7
            and pixel_fraction > 0.15
        )

        return LandslideResult(
            is_landslide=is_landslide,
            landslide_probability=mean_prob,
            max_probability=max_prob,
            landslide_pixel_fraction=pixel_fraction,
            model_version=model.model_version,
            confidence_threshold=model.confidence_threshold,
        )

    except Exception as e:
        logger.warning("Landslide classification failed for polygon", error=str(e))
        return None


def _extract_patch(
    scene_bands: xr.DataArray,
    bounds: tuple[float, float, float, float],
    centroid: Any,
) -> np.ndarray | None:
    """Extract a 128x128 patch from scene bands centered on a polygon.

    Adapted from landcover.py _extract_patch for 128x128 patch size.

    Args:
        scene_bands: Multi-band DataArray (num_bands, H, W).
        bounds: Polygon bounds (minx, miny, maxx, maxy).
        centroid: Polygon centroid point.

    Returns:
        Numpy array of shape (num_bands, 128, 128) or None if extraction fails.
    """
    try:
        y_coords = scene_bands.coords[scene_bands.dims[-2]].values
        x_coords = scene_bands.coords[scene_bands.dims[-1]].values

        cx = float(centroid.x)
        cy = float(centroid.y)

        scene_crs = getattr(scene_bands, 'rio', None) and scene_bands.rio.crs
        if scene_crs and scene_crs.to_epsg() != 4326:
            from pyproj import Transformer
            transformer = Transformer.from_crs(4326, scene_crs, always_xy=True)
            cx, cy = transformer.transform(cx, cy)

        y_idx = int(np.argmin(np.abs(y_coords - cy)))
        x_idx = int(np.argmin(np.abs(x_coords - cx)))

        half = LANDSLIDE_PATCH_SIZE // 2
        h, w = scene_bands.shape[-2], scene_bands.shape[-1]

        y_start = max(0, y_idx - half)
        y_end = min(h, y_idx + half)
        x_start = max(0, x_idx - half)
        x_end = min(w, x_idx + half)

        patch = scene_bands.values[:, y_start:y_end, x_start:x_end]

        # Pad to 128x128 if needed
        if patch.shape[1] < LANDSLIDE_PATCH_SIZE or patch.shape[2] < LANDSLIDE_PATCH_SIZE:
            padded = np.zeros(
                (patch.shape[0], LANDSLIDE_PATCH_SIZE, LANDSLIDE_PATCH_SIZE),
                dtype=patch.dtype,
            )
            ph, pw = patch.shape[1], patch.shape[2]
            y_off = (LANDSLIDE_PATCH_SIZE - ph) // 2
            x_off = (LANDSLIDE_PATCH_SIZE - pw) // 2
            padded[:, y_off:y_off + ph, x_off:x_off + pw] = patch
            patch = padded

        # Center crop to 128x128 if larger
        if patch.shape[1] > LANDSLIDE_PATCH_SIZE or patch.shape[2] > LANDSLIDE_PATCH_SIZE:
            ch = (patch.shape[1] - LANDSLIDE_PATCH_SIZE) // 2
            cw = (patch.shape[2] - LANDSLIDE_PATCH_SIZE) // 2
            patch = patch[:, ch:ch + LANDSLIDE_PATCH_SIZE, cw:cw + LANDSLIDE_PATCH_SIZE]

        return patch.astype(np.float32)

    except Exception as e:
        logger.debug(f"Patch extraction failed: {e}")
        return None


def _extract_single_band_patch(
    data: xr.DataArray,
    bounds: tuple[float, float, float, float],
    centroid: Any,
) -> np.ndarray | None:
    """Extract a 128x128 patch from a single-band DataArray.

    Args:
        data: Single-band DataArray (H, W).
        bounds: Polygon bounds.
        centroid: Polygon centroid point.

    Returns:
        Numpy array of shape (128, 128) or None if extraction fails.
    """
    try:
        y_coords = data.coords[data.dims[-2]].values
        x_coords = data.coords[data.dims[-1]].values

        cx = float(centroid.x)
        cy = float(centroid.y)

        scene_crs = getattr(data, 'rio', None) and data.rio.crs
        if scene_crs and scene_crs.to_epsg() != 4326:
            from pyproj import Transformer
            transformer = Transformer.from_crs(4326, scene_crs, always_xy=True)
            cx, cy = transformer.transform(cx, cy)

        y_idx = int(np.argmin(np.abs(y_coords - cy)))
        x_idx = int(np.argmin(np.abs(x_coords - cx)))

        half = LANDSLIDE_PATCH_SIZE // 2
        h, w = data.shape[-2], data.shape[-1]

        y_start = max(0, y_idx - half)
        y_end = min(h, y_idx + half)
        x_start = max(0, x_idx - half)
        x_end = min(w, x_idx + half)

        # Handle both 2D and 3D arrays
        values = data.values
        if values.ndim == 3:
            values = values[0]

        patch = values[y_start:y_end, x_start:x_end]

        # Pad to 128x128 if needed
        if patch.shape[0] < LANDSLIDE_PATCH_SIZE or patch.shape[1] < LANDSLIDE_PATCH_SIZE:
            padded = np.zeros(
                (LANDSLIDE_PATCH_SIZE, LANDSLIDE_PATCH_SIZE),
                dtype=patch.dtype,
            )
            ph, pw = patch.shape[0], patch.shape[1]
            y_off = (LANDSLIDE_PATCH_SIZE - ph) // 2
            x_off = (LANDSLIDE_PATCH_SIZE - pw) // 2
            padded[y_off:y_off + ph, x_off:x_off + pw] = patch
            patch = padded

        # Center crop if larger
        if patch.shape[0] > LANDSLIDE_PATCH_SIZE or patch.shape[1] > LANDSLIDE_PATCH_SIZE:
            ch = (patch.shape[0] - LANDSLIDE_PATCH_SIZE) // 2
            cw = (patch.shape[1] - LANDSLIDE_PATCH_SIZE) // 2
            patch = patch[ch:ch + LANDSLIDE_PATCH_SIZE, cw:cw + LANDSLIDE_PATCH_SIZE]

        return patch.astype(np.float32)

    except Exception as e:
        logger.debug(f"Single band patch extraction failed: {e}")
        return None


def _get_dem_channel(
    dem_data: Any,
    channel: str,
    reference: xr.DataArray,
) -> xr.DataArray | None:
    """Extract a DEM-derived channel (slope or elevation), reprojected to match the reference grid.

    Args:
        dem_data: DEM data object. Expected to have 'slope' and 'elevation' attributes
            as xarray DataArrays.
        channel: "slope" or "elevation".
        reference: Reference DataArray to reproject to (for grid alignment).

    Returns:
        DataArray reprojected to match reference, or None on failure.
    """
    try:
        if hasattr(dem_data, channel):
            arr = getattr(dem_data, channel)
        elif isinstance(dem_data, dict) and channel in dem_data:
            arr = dem_data[channel]
        else:
            logger.debug(f"DEM data has no '{channel}' attribute/key")
            return None

        if not isinstance(arr, xr.DataArray):
            return None

        # Reproject to match the Sentinel-2 grid
        ref_band = reference.isel(band=0) if 'band' in reference.dims else reference
        reprojected = arr.rio.reproject_match(ref_band)
        return reprojected

    except Exception as e:
        logger.debug(f"Failed to get DEM channel '{channel}': {e}")
        return None


def _normalize_landslide_patch(
    patch: np.ndarray,
    means: list[float],
    stds: list[float],
) -> np.ndarray:
    """Normalize a patch using per-channel statistics from the training set.

    Args:
        patch: Array of shape (14, 128, 128).
        means: Per-channel means (14 values).
        stds: Per-channel stds (14 values).

    Returns:
        Normalized array of the same shape.
    """
    normalized = np.zeros_like(patch, dtype=np.float32)
    for i in range(min(patch.shape[0], len(means))):
        if stds[i] > 0:
            with np.errstate(over="ignore", invalid="ignore"):
                normalized[i] = (patch[i].astype(np.float32) - means[i]) / stds[i]
        else:
            normalized[i] = patch[i]
    np.nan_to_num(normalized, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    return normalized
