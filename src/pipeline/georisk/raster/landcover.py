"""Land cover classification using EuroSAT pretrained model via TorchGeo.

Classifies the "before" scene into 10 land cover classes (Forest, AnnualCrop, etc.)
to provide context for risk scoring. A forest-to-bare transition means something
different from a crop-to-bare transition.

Requires optional ML dependencies: pip install -e ".[ml]"
The pipeline degrades gracefully when these are not installed.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import structlog
import xarray as xr

from georisk.raster.download import load_band_from_url

logger = structlog.get_logger()


# EuroSAT class names in TorchGeo's order (alphabetical)
EUROSAT_CLASSES: list[str] = [
    "AnnualCrop",
    "Forest",
    "HerbaceousVegetation",
    "Highway",
    "Industrial",
    "Pasture",
    "PermanentCrop",
    "Residential",
    "River",
    "SeaLake",
]

# All 13 Sentinel-2 bands in TorchGeo EuroSAT order (B8A is last)
EUROSAT_BANDS: list[str] = [
    "B01", "B02", "B03", "B04", "B05", "B06", "B07",
    "B08", "B09", "B10", "B11", "B12", "B8A",
]

# Land cover risk multipliers: how much a change on this land cover type
# should be weighted relative to Forest (baseline = 1.0).
LANDCOVER_RISK_MULTIPLIERS: dict[str, float] = {
    "Forest": 1.0,
    "Residential": 0.9,
    "HerbaceousVegetation": 0.85,
    "River": 0.8,
    "PermanentCrop": 0.75,
    "Pasture": 0.7,
    "Industrial": 0.5,
    "SeaLake": 0.4,
    "AnnualCrop": 0.3,
    "Highway": 0.25,
}

# The pretrained SENTINEL2_ALL_MOCO weights expect raw Sentinel-2 reflectance
# divided by 10,000 (mapping typical values to the 0-1 range).
EUROSAT_NORMALIZE_DIVISOR = 10_000.0

# EuroSAT spatial patch size (matches EuroSAT dataset native 64x64 pixel patches)
EUROSAT_PATCH_SIZE = 64

# Model input size expected by the pretrained weights (Resize(256) → CenterCrop(224))
EUROSAT_MODEL_INPUT_SIZE = 224

# Module-level model cache
_cached_model: "LandCoverModel | None" = None


def is_landcover_available() -> bool:
    """Check if ML dependencies (torch, torchgeo) are installed."""
    try:
        import torch  # noqa: F401
        import torchgeo  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass
class LandCoverModel:
    """Wrapper around TorchGeo's pretrained EuroSAT model."""

    model: Any  # torch.nn.Module
    model_version: str
    device: str


@dataclass
class LandCoverResult:
    """Classification result for a single polygon or patch."""

    dominant_class: str
    class_index: int
    confidence: float
    class_probabilities: dict[str, float]
    risk_multiplier: float
    model_version: str


def load_eurosat_model(
    backbone: str = "resnet18",
    device: str | None = None,
) -> LandCoverModel:
    """Load TorchGeo's pretrained EuroSAT ResNet model.

    The model is cached at module level to avoid reloading across calls.

    Args:
        backbone: Model backbone ("resnet18" or "resnet50").
        device: Torch device ("cpu", "cuda", or None for auto-detect).

    Returns:
        LandCoverModel wrapper with loaded model.
    """
    global _cached_model
    if _cached_model is not None:
        return _cached_model

    import torch
    from torchgeo.models import ResNet18_Weights, ResNet50_Weights, resnet18, resnet50

    if device is None or device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    logger.info("Loading EuroSAT model", backbone=backbone, device=device)

    num_classes = len(EUROSAT_CLASSES)
    in_chans = len(EUROSAT_BANDS)

    if backbone == "resnet50":
        weights = ResNet50_Weights.SENTINEL2_ALL_MOCO
        model = resnet50(weights=weights, num_classes=num_classes, in_chans=in_chans)
        version = "eurosat-resnet50-sentinel2-all-moco"
    else:
        weights = ResNet18_Weights.SENTINEL2_ALL_MOCO
        model = resnet18(weights=weights, num_classes=num_classes, in_chans=in_chans)
        version = "eurosat-resnet18-sentinel2-all-moco"

    model = model.to(device)
    model.eval()

    _cached_model = LandCoverModel(model=model, model_version=version, device=device)
    logger.info("EuroSAT model loaded", version=version)
    return _cached_model


def load_scene_bands(
    scene: Any,
    bbox: tuple[float, float, float, float],
    bands: list[str] | None = None,
) -> xr.DataArray | None:
    """Load and align multiple Sentinel-2 bands into a single multi-band DataArray.

    All bands are resampled to the 10m grid of B02/B03/B04/B08 using bilinear
    interpolation. Bands that are unavailable in the scene are zero-filled.

    Args:
        scene: SceneInfo with band URLs.
        bbox: WGS84 bounding box (min_lon, min_lat, max_lon, max_lat).
        bands: Band names to load. Defaults to all 13 EuroSAT bands.

    Returns:
        DataArray with shape (num_bands, H, W) in the scene's native CRS,
        or None if loading fails.
    """
    bands = bands or EUROSAT_BANDS

    logger.info("Loading scene bands for land cover classification", num_bands=len(bands))

    # Load the reference 10m band first to get the target grid
    ref_url = scene.get_band_url("B02")
    if ref_url is None:
        logger.warning("Reference band B02 not available, cannot classify land cover")
        return None

    ref_band = load_band_from_url(ref_url, bbox)

    band_arrays = []
    loaded_count = 0

    for band_name in bands:
        url = scene.get_band_url(band_name)
        if url is None:
            logger.debug(f"Band {band_name} not available, zero-filling")
            # Create zero-filled array matching reference grid
            zeros = xr.zeros_like(ref_band)
            band_arrays.append(zeros)
            continue

        try:
            band_data = load_band_from_url(url, bbox)

            # Resample to reference grid if resolution differs
            if band_data.shape != ref_band.shape:
                band_data = band_data.rio.reproject_match(ref_band)

            band_arrays.append(band_data)
            loaded_count += 1
        except Exception as e:
            logger.warning(f"Failed to load band {band_name}: {e}, zero-filling")
            zeros = xr.zeros_like(ref_band)
            band_arrays.append(zeros)

    if loaded_count < 4:
        logger.warning(
            "Too few bands loaded for reliable classification",
            loaded=loaded_count,
            required=4,
        )
        return None

    # Stack into (num_bands, H, W)
    stacked = xr.concat(band_arrays, dim="band")
    stacked = stacked.assign_coords(band=list(range(len(bands))))

    logger.info("Scene bands loaded", shape=stacked.shape, loaded_bands=loaded_count)
    return stacked


def classify_polygon_landcover(
    scene_bands: xr.DataArray,
    polygon: Any,
    model: LandCoverModel | None = None,
) -> LandCoverResult | None:
    """Classify the dominant land cover for a polygon's bounding area.

    Extracts a 64x64 patch centered on the polygon from the pre-loaded scene
    bands, normalizes it, and runs EuroSAT inference.

    Args:
        scene_bands: Pre-loaded multi-band DataArray from load_scene_bands().
        polygon: Shapely Polygon geometry (in WGS84 or the scene's native CRS).
        model: Pre-loaded EuroSAT model. If None, loads automatically.

    Returns:
        LandCoverResult with dominant class and confidence, or None on failure.
    """
    try:
        import torch

        if model is None:
            model = load_eurosat_model()

        # Get polygon centroid in the scene's CRS
        centroid = polygon.centroid
        bounds = polygon.bounds  # (minx, miny, maxx, maxy)

        # Extract patch around polygon from scene bands
        patch = _extract_patch(scene_bands, bounds, centroid)
        if patch is None:
            return None

        # Normalize (divide by 10,000 per pretrained weight convention)
        patch_normalized = _normalize_patch(patch)

        # Convert to tensor and resize to model input size (224x224)
        tensor = torch.tensor(patch_normalized, dtype=torch.float32).unsqueeze(0)
        tensor = torch.nn.functional.interpolate(
            tensor, size=(EUROSAT_MODEL_INPUT_SIZE, EUROSAT_MODEL_INPUT_SIZE),
            mode="bilinear", align_corners=False,
        )
        tensor = tensor.to(model.device)

        with torch.no_grad():
            logits = model.model(tensor)
            probs = torch.nn.functional.softmax(logits, dim=1)

        probs_np = probs.cpu().numpy()[0]
        class_idx = int(np.argmax(probs_np))
        confidence = float(probs_np[class_idx])
        dominant_class = EUROSAT_CLASSES[class_idx]

        class_probabilities = {
            cls: float(probs_np[i]) for i, cls in enumerate(EUROSAT_CLASSES)
        }

        risk_multiplier = LANDCOVER_RISK_MULTIPLIERS.get(dominant_class, 1.0)

        return LandCoverResult(
            dominant_class=dominant_class,
            class_index=class_idx,
            confidence=confidence,
            class_probabilities=class_probabilities,
            risk_multiplier=risk_multiplier,
            model_version=model.model_version,
        )

    except Exception as e:
        logger.warning("Land cover classification failed for polygon", error=str(e))
        return None


def _extract_patch(
    scene_bands: xr.DataArray,
    bounds: tuple[float, float, float, float],
    centroid: Any,
) -> np.ndarray | None:
    """Extract a 64x64 patch from scene bands centered on a polygon.

    If the polygon is smaller than 64x64 pixels, the patch is centered on
    the polygon's centroid. If larger, a center crop is taken.

    Args:
        scene_bands: Multi-band DataArray (num_bands, H, W).
        bounds: Polygon bounds (minx, miny, maxx, maxy).
        centroid: Polygon centroid point (WGS84).

    Returns:
        Numpy array of shape (num_bands, 64, 64) or None if extraction fails.
    """
    try:
        # Get pixel coordinates of centroid
        y_coords = scene_bands.coords[scene_bands.dims[-2]].values
        x_coords = scene_bands.coords[scene_bands.dims[-1]].values

        # Transform centroid from WGS84 to the scene's CRS if needed
        cx = float(centroid.x)
        cy = float(centroid.y)

        scene_crs = getattr(scene_bands, 'rio', None) and scene_bands.rio.crs
        if scene_crs and scene_crs.to_epsg() != 4326:
            from pyproj import Transformer
            transformer = Transformer.from_crs(4326, scene_crs, always_xy=True)
            cx, cy = transformer.transform(cx, cy)

        # Handle both ascending and descending coordinate orders
        y_idx = int(np.argmin(np.abs(y_coords - cy)))
        x_idx = int(np.argmin(np.abs(x_coords - cx)))

        half = EUROSAT_PATCH_SIZE // 2
        h, w = scene_bands.shape[-2], scene_bands.shape[-1]

        # Calculate slice bounds, clamping to array edges
        y_start = max(0, y_idx - half)
        y_end = min(h, y_idx + half)
        x_start = max(0, x_idx - half)
        x_end = min(w, x_idx + half)

        # Extract the region
        patch = scene_bands.values[:, y_start:y_end, x_start:x_end]

        # Pad to 64x64 if needed
        if patch.shape[1] < EUROSAT_PATCH_SIZE or patch.shape[2] < EUROSAT_PATCH_SIZE:
            padded = np.zeros(
                (patch.shape[0], EUROSAT_PATCH_SIZE, EUROSAT_PATCH_SIZE),
                dtype=patch.dtype,
            )
            ph, pw = patch.shape[1], patch.shape[2]
            # Center the extracted region in the padded array
            y_off = (EUROSAT_PATCH_SIZE - ph) // 2
            x_off = (EUROSAT_PATCH_SIZE - pw) // 2
            padded[:, y_off:y_off + ph, x_off:x_off + pw] = patch
            patch = padded

        # Center crop to 64x64 if larger
        if patch.shape[1] > EUROSAT_PATCH_SIZE or patch.shape[2] > EUROSAT_PATCH_SIZE:
            ch = (patch.shape[1] - EUROSAT_PATCH_SIZE) // 2
            cw = (patch.shape[2] - EUROSAT_PATCH_SIZE) // 2
            patch = patch[:, ch:ch + EUROSAT_PATCH_SIZE, cw:cw + EUROSAT_PATCH_SIZE]

        return patch.astype(np.float32)

    except Exception as e:
        logger.debug(f"Patch extraction failed: {e}")
        return None


def _normalize_patch(patch: np.ndarray) -> np.ndarray:
    """Normalize a patch for EuroSAT inference.

    The pretrained SENTINEL2_ALL_MOCO weights expect raw Sentinel-2 reflectance
    divided by 10,000 (mapping typical values to the 0-1 range).

    Args:
        patch: Array of shape (num_bands, H, W).

    Returns:
        Normalized array of the same shape as float32.
    """
    return patch.astype(np.float32) / EUROSAT_NORMALIZE_DIVISOR
