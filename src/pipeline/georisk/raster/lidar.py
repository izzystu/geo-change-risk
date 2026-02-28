"""LIDAR point cloud processing for high-resolution DEM generation.

Processes USGS 3DEP LIDAR COPC (Cloud Optimized Point Cloud) data from
Planetary Computer STAC into 1m DTM/DSM/CHM raster products using PDAL.

Requires optional LIDAR dependencies: pip install -e ".[lidar]"
On Windows, PDAL typically needs conda: conda install -c conda-forge pdal python-pdal
The pipeline degrades gracefully when PDAL is not installed.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import rioxarray as rxr
import structlog
import xarray as xr
from pyproj import CRS

from georisk.config import get_config

logger = structlog.get_logger()


def is_lidar_available() -> bool:
    """Check if PDAL Python bindings are installed."""
    try:
        import pdal  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass
class LidarMetadata:
    """Metadata from LIDAR point cloud processing."""

    source_id: str
    point_count: int
    point_density_per_m2: float
    crs_epsg: int
    resolution_m: float
    bounds: tuple[float, float, float, float]  # minx, miny, maxx, maxy
    classification_counts: dict[int, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "source_id": self.source_id,
            "point_count": self.point_count,
            "point_density_per_m2": self.point_density_per_m2,
            "crs_epsg": self.crs_epsg,
            "resolution_m": self.resolution_m,
            "bounds": list(self.bounds),
            "classification_counts": {
                str(k): v for k, v in self.classification_counts.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LidarMetadata":
        """Deserialize from dictionary."""
        return cls(
            source_id=data["source_id"],
            point_count=data["point_count"],
            point_density_per_m2=data["point_density_per_m2"],
            crs_epsg=data["crs_epsg"],
            resolution_m=data["resolution_m"],
            bounds=tuple(data["bounds"]),
            classification_counts={
                int(k): v for k, v in data.get("classification_counts", {}).items()
            },
        )


@dataclass
class LidarProducts:
    """Products generated from LIDAR point cloud processing."""

    dtm: xr.DataArray
    dsm: xr.DataArray
    chm: xr.DataArray | None
    metadata: LidarMetadata
    crs: Any
    transform: Any


def _get_utm_epsg(lon: float, lat: float) -> int:
    """Get UTM EPSG code for a given lon/lat coordinate."""
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        return 32600 + zone  # Northern hemisphere
    return 32700 + zone  # Southern hemisphere


def _detect_copc_crs(copc_url: str) -> int:
    """Detect the CRS EPSG code of a COPC file by reading its header.

    Reads just 1 point to access the SRS metadata without downloading the full file.
    Falls back to EPSG:26910 (NAD83/UTM 10N) if detection fails.
    """
    import pdal

    try:
        pipeline_json = json.dumps([{
            "type": "readers.copc",
            "filename": copc_url,
            "count": 1,
        }])
        p = pdal.Pipeline(pipeline_json)
        p.execute()

        metadata = p.metadata
        readers = metadata.get("metadata", {}).get("readers.copc", {})
        if isinstance(readers, list):
            readers = readers[0] if readers else {}

        srs = readers.get("srs", {})
        # Try to extract EPSG from the horizontal WKT
        wkt = srs.get("horizontal", "")
        if 'AUTHORITY["EPSG",' in wkt:
            # Find the last AUTHORITY["EPSG","XXXXX"] which is the overall CRS
            import re
            matches = re.findall(r'AUTHORITY\["EPSG","(\d+)"\]', wkt)
            if matches:
                return int(matches[-1])

        logger.warning("Could not detect EPSG from COPC SRS, using proj4 fallback")
        proj4 = srs.get("proj4", "")
        if "+proj=utm" in proj4 and "+zone=10" in proj4 and "+datum=NAD83" in proj4:
            return 26910
    except Exception as e:
        logger.warning("COPC CRS detection failed", error=str(e))

    return 26910  # Safe default for CONUS 3DEP data


def search_lidar_copc(
    bbox: tuple[float, float, float, float],
    collection: str | None = None,
    max_items: int = 500,
) -> list[dict[str, Any]]:
    """Search Planetary Computer STAC for 3DEP LIDAR COPC items.

    Args:
        bbox: Bounding box as (min_lon, min_lat, max_lon, max_lat) in WGS84.
        collection: STAC collection ID (default from config).

    Returns:
        List of COPC item dictionaries with id, href, bounds, and properties.
    """
    import planetary_computer
    import pystac_client

    config = get_config()
    collection = collection or config.terrain.lidar_collection

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    search = catalog.search(
        collections=[collection],
        bbox=bbox,
        max_items=max_items,
    )

    items = list(search.items())
    logger.info("LIDAR COPC search", collection=collection, bbox=bbox, items_found=len(items))

    results = []
    for item in items:
        # Get the COPC asset URL
        copc_asset = item.assets.get("data") or item.assets.get("ept.json")
        if copc_asset is None:
            continue

        results.append({
            "id": item.id,
            "href": copc_asset.href,
            "bbox": list(item.bbox) if item.bbox else None,
            "datetime": item.datetime.isoformat() if item.datetime else None,
            "proj_epsg": item.properties.get("proj:epsg"),
            "properties": {
                "pc:count": item.properties.get("pc:count"),
                "pc:type": item.properties.get("pc:type"),
                "pc:encoding": item.properties.get("pc:encoding"),
            },
        })

    return results


def process_copc_to_dem(
    copc_urls: list[str],
    bbox: tuple[float, float, float, float],
    output_dir: Path,
    resolution_m: float = 1.0,
    target_crs_epsg: int | None = None,
    source_crs_epsg: int | None = None,
) -> LidarProducts:
    """Process COPC point cloud(s) into DTM, DSM, and CHM rasters.

    Uses PDAL pipelines for:
    - DTM: Ground classification (SMRF) → ground-only points → IDW interpolation
    - DSM: First/only returns → max per cell
    - CHM: DSM - DTM, negatives clamped to 0

    Args:
        copc_urls: List of signed COPC file URLs.
        bbox: Bounding box in WGS84 for spatial filtering.
        output_dir: Directory for output raster files.
        resolution_m: Output raster resolution in meters.
        target_crs_epsg: Target CRS EPSG code (auto-detects UTM if None).
        source_crs_epsg: Native CRS of COPC files (from STAC proj:epsg).

    Returns:
        LidarProducts with DTM, DSM, CHM arrays and metadata.
    """
    import pdal

    output_dir.mkdir(parents=True, exist_ok=True)

    # Auto-detect UTM zone from bbox center
    center_lon = (bbox[0] + bbox[2]) / 2
    center_lat = (bbox[1] + bbox[3]) / 2
    if target_crs_epsg is None:
        target_crs_epsg = _get_utm_epsg(center_lon, center_lat)

    target_crs = f"EPSG:{target_crs_epsg}"
    logger.info(
        "Processing COPC to DEM",
        num_files=len(copc_urls),
        resolution_m=resolution_m,
        target_crs=target_crs,
        source_crs_epsg=source_crs_epsg,
    )

    # Convert WGS84 bbox to the COPC files' native CRS for reader-level bounds filtering.
    # This is critical for performance — without it, PDAL downloads entire tiles over HTTP.
    from pyproj import Transformer

    # Auto-detect source CRS from the first COPC file if not provided.
    # STAC metadata often lacks proj:epsg, but PDAL can read the CRS from the file header.
    if source_crs_epsg is None:
        source_crs_epsg = _detect_copc_crs(copc_urls[0])
        logger.info("Auto-detected COPC CRS", source_crs_epsg=source_crs_epsg)

    reader_bounds_crs = source_crs_epsg
    transformer_bounds = Transformer.from_crs(4326, reader_bounds_crs, always_xy=True)
    b_min_x, b_min_y = transformer_bounds.transform(bbox[0], bbox[1])
    b_max_x, b_max_y = transformer_bounds.transform(bbox[2], bbox[3])
    bounds_str = f"([{b_min_x}, {b_max_x}], [{b_min_y}, {b_max_y}])"
    logger.info("Reader bounds", crs=f"EPSG:{reader_bounds_crs}", bounds=bounds_str)

    # Also compute UTM bounds for metadata
    transformer_utm = Transformer.from_crs(4326, target_crs_epsg, always_xy=True)
    utm_min_x, utm_min_y = transformer_utm.transform(bbox[0], bbox[1])
    utm_max_x, utm_max_y = transformer_utm.transform(bbox[2], bbox[3])

    def _build_reader_stages(urls: list[str]) -> list[dict[str, Any]]:
        """Build COPC reader (with native-CRS bounds) + merge + reproject stages."""
        stages: list[dict[str, Any]] = []
        for url in urls:
            stages.append({
                "type": "readers.copc",
                "filename": url,
                "bounds": bounds_str,
            })
        if len(urls) > 1:
            stages.append({"type": "filters.merge"})
        stages.append({
            "type": "filters.reprojection",
            "out_srs": target_crs,
        })
        return stages

    # --- DTM Pipeline: ground-only points → IDW interpolation ---
    dtm_path = output_dir / "dtm.tif"

    dtm_stages = _build_reader_stages(copc_urls)

    # 3DEP COPC data is pre-classified by USGS — use existing ground classification.
    dtm_stages.append({
        "type": "filters.range",
        "limits": "Classification[2:2]",
    })

    # Rasterize to DTM using IDW interpolation
    dtm_stages.append({
        "type": "writers.gdal",
        "filename": str(dtm_path),
        "gdaldriver": "GTiff",
        "output_type": "idw",
        "resolution": resolution_m,
        "nodata": -9999,
        "gdalopts": "TILED=YES,COMPRESS=DEFLATE",
    })

    logger.info("Running DTM pipeline (pre-classified ground points + IDW interpolation)")
    try:
        dtm_pipeline = pdal.Pipeline(json.dumps(dtm_stages))
        dtm_count = dtm_pipeline.execute()
    except RuntimeError as e:
        if "no points" in str(e).lower():
            # No pre-classified ground points — retry with SMRF classification
            logger.warning("No pre-classified ground points, running SMRF classification")
            dtm_stages_smrf = _build_reader_stages(copc_urls)
            dtm_stages_smrf.append({
                "type": "filters.smrf",
                "slope": 0.2,
                "window": 16,
                "threshold": 0.45,
                "scalar": 1.25,
            })
            dtm_stages_smrf.append({
                "type": "filters.range",
                "limits": "Classification[2:2]",
            })
            dtm_stages_smrf.append({
                "type": "writers.gdal",
                "filename": str(dtm_path),
                "gdaldriver": "GTiff",
                "output_type": "idw",
                "resolution": resolution_m,
                "nodata": -9999,
                "gdalopts": "TILED=YES,COMPRESS=DEFLATE",
            })
            dtm_pipeline = pdal.Pipeline(json.dumps(dtm_stages_smrf))
            dtm_count = dtm_pipeline.execute()
        else:
            raise

    logger.info("DTM pipeline complete", ground_points=dtm_count)

    # --- DSM Pipeline: first/only returns → max per cell ---
    dsm_path = output_dir / "dsm.tif"

    dsm_stages = _build_reader_stages(copc_urls)

    # Keep first and only returns for DSM
    dsm_stages.append({
        "type": "filters.returns",
        "groups": "first,only",
    })

    # Rasterize to DSM using max per cell
    dsm_stages.append({
        "type": "writers.gdal",
        "filename": str(dsm_path),
        "gdaldriver": "GTiff",
        "output_type": "max",
        "resolution": resolution_m,
        "nodata": -9999,
        "gdalopts": "TILED=YES,COMPRESS=DEFLATE",
    })

    dsm_pipeline_json = json.dumps(dsm_stages)
    dsm_pipeline = pdal.Pipeline(dsm_pipeline_json)

    logger.info("Running DSM pipeline (first/only returns → max per cell)")
    dsm_count = dsm_pipeline.execute()
    logger.info("DSM pipeline complete", points_processed=dsm_count)

    # Load rasters
    dtm_da = rxr.open_rasterio(dtm_path)
    dsm_da = rxr.open_rasterio(dsm_path)

    # Squeeze band dimension
    if dtm_da.ndim == 3 and dtm_da.shape[0] == 1:
        dtm_da = dtm_da.squeeze("band", drop=True)
    if dsm_da.ndim == 3 and dsm_da.shape[0] == 1:
        dsm_da = dsm_da.squeeze("band", drop=True)

    # Replace nodata with NaN
    dtm_da = dtm_da.where(dtm_da != -9999, np.nan)
    dsm_da = dsm_da.where(dsm_da != -9999, np.nan)

    # --- CHM: DSM - DTM, clamp negatives to 0 ---
    chm_da = None
    chm_path = output_dir / "chm.tif"
    try:
        # Align grids (they should match since same bbox/resolution, but be safe)
        dsm_aligned = dsm_da.rio.reproject_match(dtm_da)
        chm_values = dsm_aligned.values - dtm_da.values
        chm_values = np.where(chm_values < 0, 0, chm_values)
        chm_values = np.where(np.isnan(chm_values), np.nan, chm_values)

        chm_da = dtm_da.copy(data=chm_values.astype(np.float32))
        chm_da.rio.to_raster(str(chm_path), driver="GTiff", tiled=True, compress="DEFLATE")
        logger.info("CHM generated", path=str(chm_path))
    except Exception as e:
        logger.warning("CHM generation failed, continuing without", error=str(e))

    # Collect metadata from the DTM pipeline
    total_points = dtm_count + dsm_count
    # Estimate area from bbox in projected coordinates
    area_m2 = abs(utm_max_x - utm_min_x) * abs(utm_max_y - utm_min_y)
    density = total_points / area_m2 if area_m2 > 0 else 0

    metadata = LidarMetadata(
        source_id="-".join(Path(u).stem for u in copc_urls[:3]),
        point_count=total_points,
        point_density_per_m2=round(density, 2),
        crs_epsg=target_crs_epsg,
        resolution_m=resolution_m,
        bounds=(bbox[0], bbox[1], bbox[2], bbox[3]),
    )

    crs = CRS.from_epsg(target_crs_epsg)

    return LidarProducts(
        dtm=dtm_da,
        dsm=dsm_da,
        chm=chm_da,
        metadata=metadata,
        crs=crs,
        transform=dtm_da.rio.transform(),
    )


def process_polygon_lidar(
    polygon_wkt: str,
    polygon_id: str,
    output_dir: Path,
    buffer_m: float = 100.0,
    resolution_m: float = 1.0,
) -> LidarProducts | None:
    """Generate LIDAR terrain products for a single change polygon.

    Searches for COPC tiles covering the polygon's bounding box (with buffer)
    and processes them into DTM/DSM/CHM rasters.

    Args:
        polygon_wkt: WKT geometry of the change polygon.
        polygon_id: Unique identifier for the polygon (used for logging).
        output_dir: Directory for output raster files.
        buffer_m: Buffer in meters around the polygon bbox for terrain context.
        resolution_m: Output raster resolution in meters.

    Returns:
        LidarProducts if successful, None if no COPC tiles found.
    """
    from shapely import wkt

    polygon = wkt.loads(polygon_wkt)
    minx, miny, maxx, maxy = polygon.bounds

    # Buffer the bbox (rough degree conversion: ~111km per degree at equator)
    # At mid-latitudes (~40°), 100m ≈ 0.0009° lon, 0.0009° lat
    buffer_deg = buffer_m / 111_000.0
    buffered_bbox = (
        minx - buffer_deg,
        miny - buffer_deg,
        maxx + buffer_deg,
        maxy + buffer_deg,
    )

    logger.info(
        "Processing polygon LIDAR",
        polygon_id=polygon_id,
        bbox=buffered_bbox,
        buffer_m=buffer_m,
    )

    # Search for COPC tiles covering this area
    tiles = search_lidar_copc(buffered_bbox, max_items=10)
    if not tiles:
        logger.info("No COPC tiles found for polygon", polygon_id=polygon_id)
        return None

    copc_urls = [t["href"] for t in tiles]
    source_crs = tiles[0].get("proj_epsg")

    logger.info(
        "Found COPC tiles for polygon",
        polygon_id=polygon_id,
        tile_count=len(tiles),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    return process_copc_to_dem(
        copc_urls=copc_urls,
        bbox=buffered_bbox,
        output_dir=output_dir,
        resolution_m=resolution_m,
        source_crs_epsg=source_crs,
    )


def process_polygons_batch(
    polygons: list[dict],
    output_base_dir: Path,
    buffer_m: float = 100.0,
    resolution_m: float = 1.0,
) -> dict[str, LidarProducts]:
    """Process LIDAR terrain for a batch of change polygons.

    Args:
        polygons: List of dicts with "polygon_id" and "geometry_wkt" keys.
        output_base_dir: Base directory; each polygon gets a subdirectory.
        buffer_m: Buffer in meters around each polygon bbox.
        resolution_m: Output raster resolution in meters.

    Returns:
        Dict of polygon_id → LidarProducts (only successful ones).
    """
    results: dict[str, LidarProducts] = {}
    total = len(polygons)

    for i, poly in enumerate(polygons, 1):
        polygon_id = poly["polygon_id"]
        geometry_wkt = poly["geometry_wkt"]
        poly_output_dir = output_base_dir / polygon_id

        logger.info(
            "Processing polygon LIDAR batch",
            progress=f"{i}/{total}",
            polygon_id=polygon_id,
        )

        try:
            products = process_polygon_lidar(
                polygon_wkt=geometry_wkt,
                polygon_id=polygon_id,
                output_dir=poly_output_dir,
                buffer_m=buffer_m,
                resolution_m=resolution_m,
            )
            if products is not None:
                results[polygon_id] = products
                logger.info(
                    "Polygon LIDAR complete",
                    polygon_id=polygon_id,
                    point_count=products.metadata.point_count,
                )
            else:
                logger.info(
                    "No LIDAR data available for polygon",
                    polygon_id=polygon_id,
                )
        except Exception as e:
            logger.warning(
                "Polygon LIDAR processing failed",
                polygon_id=polygon_id,
                error=str(e),
            )

    return results
