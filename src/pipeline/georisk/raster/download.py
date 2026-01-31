"""Raster download and clipping utilities."""

import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import rioxarray as rxr
import structlog
import xarray as xr
from pyproj import Transformer
from rasterio.mask import mask
from rasterio.enums import Resampling
from shapely.geometry import box, mapping

from georisk.stac.search import SceneInfo

logger = structlog.get_logger()


def _get_wgs84_bounds(da: xr.DataArray) -> tuple[float, float, float, float]:
    """Get WGS84 bounding box from a DataArray in any CRS.

    Args:
        da: DataArray with CRS information.

    Returns:
        Tuple of (min_lon, min_lat, max_lon, max_lat) in WGS84.
    """
    bounds = da.rio.bounds()  # (minx, miny, maxx, maxy) in native CRS
    crs = da.rio.crs

    if crs and crs.to_epsg() != 4326:
        transformer = Transformer.from_crs(crs, 4326, always_xy=True)
        # Transform all four corners to handle non-rectangular projections
        corners = [
            (bounds[0], bounds[1]),  # min_x, min_y
            (bounds[0], bounds[3]),  # min_x, max_y
            (bounds[2], bounds[1]),  # max_x, min_y
            (bounds[2], bounds[3]),  # max_x, max_y
        ]
        transformed = [transformer.transform(x, y) for x, y in corners]
        lons = [c[0] for c in transformed]
        lats = [c[1] for c in transformed]
        return (min(lons), min(lats), max(lons), max(lats))

    return bounds


def create_rgb_composite(
    scene: SceneInfo,
    bbox: tuple[float, float, float, float],
    output_path: Path,
    scale_factor: float = 0.0001,
    brightness: float = 3.0,
    create_png: bool = True,
) -> tuple[Path, Path | None, tuple[float, float, float, float] | None]:
    """Create an RGB composite from Sentinel-2 bands.

    Args:
        scene: SceneInfo with band URLs.
        bbox: Bounding box to clip to (WGS84).
        output_path: Output file path for the RGB GeoTIFF.
        scale_factor: Scale factor for Sentinel-2 reflectance values.
        brightness: Brightness multiplier for visualization.
        create_png: Also create a PNG for web display.

    Returns:
        Tuple of (GeoTIFF path, PNG path or None, WGS84 bounds or None).
    """
    logger.info("Creating RGB composite", scene_id=scene.scene_id)

    # Load RGB bands (B04=Red, B03=Green, B02=Blue for Sentinel-2)
    red = load_band_from_url(scene.get_band_url("B04"), bbox)
    green = load_band_from_url(scene.get_band_url("B03"), bbox)
    blue = load_band_from_url(scene.get_band_url("B02"), bbox)

    # Calculate actual WGS84 bounds from the clipped raster (may differ from input bbox due to UTM projection)
    wgs84_bounds = _get_wgs84_bounds(red)
    logger.info(
        "Calculated actual WGS84 bounds",
        bounds=wgs84_bounds,
        original_bbox=bbox,
    )

    # Stack into RGB array and convert to float
    rgb = np.stack([
        red.values.astype(np.float32),
        green.values.astype(np.float32),
        blue.values.astype(np.float32),
    ])

    # Scale and apply brightness for visualization
    rgb = rgb * scale_factor * brightness

    # Clip to 0-1 range and convert to uint8 (0-255)
    rgb = np.clip(rgb, 0, 1) * 255
    rgb = rgb.astype(np.uint8)

    # Get CRS and transform from the source data
    crs = red.rio.crs
    transform = red.rio.transform()

    # Write the RGB GeoTIFF
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=rgb.shape[1],
        width=rgb.shape[2],
        count=3,
        dtype=np.uint8,
        crs=crs,
        transform=transform,
        compress="deflate",
    ) as dst:
        dst.write(rgb)

    logger.info(
        "RGB composite created",
        scene_id=scene.scene_id,
        path=str(output_path),
        size_mb=output_path.stat().st_size / (1024 * 1024),
    )

    # Also create PNG for web display
    png_path = None
    if create_png:
        from PIL import Image

        # Transpose from (bands, height, width) to (height, width, bands)
        rgb_hwc = np.transpose(rgb, (1, 2, 0))
        img = Image.fromarray(rgb_hwc, mode='RGB')

        png_path = output_path.with_suffix('.png')
        img.save(png_path, 'PNG', optimize=True)

        logger.info(
            "PNG created for web display",
            path=str(png_path),
            size_mb=png_path.stat().st_size / (1024 * 1024),
        )

        # Save bounds.json sidecar file alongside PNG for proper georeferencing
        bounds_path = output_path.with_suffix('.bounds.json')
        bounds_data = {
            "bounds": list(wgs84_bounds),
            "crs": "EPSG:4326",
            "scene_id": scene.scene_id,
        }
        with open(bounds_path, 'w') as f:
            json.dump(bounds_data, f, indent=2)

        logger.info(
            "Bounds sidecar file created",
            path=str(bounds_path),
            bounds=wgs84_bounds,
        )

    return output_path, png_path, wgs84_bounds


def download_scene(
    scene: SceneInfo,
    bands: list[str],
    output_dir: Path | None = None,
) -> dict[str, Path]:
    """Download scene bands to local files.

    Args:
        scene: Scene information with band URLs.
        bands: List of band names to download (e.g., ["B04", "B08"]).
        output_dir: Output directory. Uses temp dir if not specified.

    Returns:
        Dictionary mapping band names to local file paths.
    """
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="georisk_"))
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded = {}

    for band in bands:
        url = scene.get_band_url(band)
        if not url:
            logger.warning("Band not available", band=band, scene_id=scene.scene_id)
            continue

        output_path = output_dir / f"{scene.scene_id}_{band}.tif"

        try:
            logger.info("Downloading band", band=band, scene_id=scene.scene_id)

            # Use rioxarray to read from remote URL (supports COG range requests)
            da = rxr.open_rasterio(url)

            # Save to local file
            da.rio.to_raster(output_path)
            downloaded[band] = output_path

            logger.info(
                "Band downloaded",
                band=band,
                path=str(output_path),
                shape=da.shape,
            )

        except Exception as e:
            logger.error("Failed to download band", band=band, error=str(e))

    return downloaded


def clip_to_aoi(
    input_path: Path,
    bbox: tuple[float, float, float, float],
    output_path: Path | None = None,
) -> Path:
    """Clip a raster to an AOI bounding box.

    Args:
        input_path: Input raster file path.
        bbox: Bounding box as (min_lon, min_lat, max_lon, max_lat).
        output_path: Output file path. Derives from input if not specified.

    Returns:
        Path to the clipped raster.
    """
    if output_path is None:
        output_path = input_path.with_stem(f"{input_path.stem}_clipped")

    # Create shapely box from bbox
    min_lon, min_lat, max_lon, max_lat = bbox
    aoi_geom = box(min_lon, min_lat, max_lon, max_lat)

    with rasterio.open(input_path) as src:
        # Convert AOI to raster CRS if needed
        if src.crs and src.crs.to_epsg() != 4326:
            from pyproj import Transformer

            transformer = Transformer.from_crs(4326, src.crs, always_xy=True)
            min_x, min_y = transformer.transform(min_lon, min_lat)
            max_x, max_y = transformer.transform(max_lon, max_lat)
            aoi_geom = box(min_x, min_y, max_x, max_y)

        # Clip the raster
        out_image, out_transform = mask(src, [mapping(aoi_geom)], crop=True)
        out_meta = src.meta.copy()

        out_meta.update({
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
        })

        with rasterio.open(output_path, "w", **out_meta) as dest:
            dest.write(out_image)

    logger.info("Clipped raster", input=str(input_path), output=str(output_path))
    return output_path


def load_band(path: Path) -> xr.DataArray:
    """Load a raster band as an xarray DataArray.

    Args:
        path: Path to the raster file.

    Returns:
        DataArray with the raster data.
    """
    da = rxr.open_rasterio(path)
    # Squeeze single-band rasters
    if da.shape[0] == 1:
        da = da.squeeze("band", drop=True)
    return da


def load_band_from_url(url: str, bbox: tuple[float, float, float, float] | None = None) -> xr.DataArray:
    """Load a raster band directly from a URL, optionally clipping to bbox.

    Args:
        url: URL to the COG file.
        bbox: Optional bounding box to clip to (in WGS84/EPSG:4326).

    Returns:
        DataArray with the raster data.
    """
    da = rxr.open_rasterio(url)

    # Clip to bbox if provided
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox

        # Transform bbox to raster CRS if needed
        raster_crs = da.rio.crs
        if raster_crs and raster_crs.to_epsg() != 4326:
            from pyproj import Transformer
            transformer = Transformer.from_crs(4326, raster_crs, always_xy=True)
            min_x, min_y = transformer.transform(min_lon, min_lat)
            max_x, max_y = transformer.transform(max_lon, max_lat)
        else:
            min_x, min_y, max_x, max_y = min_lon, min_lat, max_lon, max_lat

        try:
            da = da.rio.clip_box(minx=min_x, miny=min_y, maxx=max_x, maxy=max_y)
        except Exception as e:
            logger.warning(f"Could not clip to bbox: {e}, using full extent")

    # Squeeze single-band rasters
    if da.shape[0] == 1:
        da = da.squeeze("band", drop=True)

    return da
