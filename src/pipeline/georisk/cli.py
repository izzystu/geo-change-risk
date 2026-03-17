"""Command-line interface for the GeoRisk pipeline."""

import json

# Configure structlog for CLI output
import logging
import os
import sys

# On Windows, ensure conda and PyTorch DLL directories are registered before
# any native extensions (torch, PDAL) are imported.  Python 3.8+ no longer
# uses PATH for DLL resolution, so we must call os.add_dll_directory() AND
# prepend to PATH (some libraries use ctypes with LOAD_WITH_ALTERED_SEARCH_PATH).
# We also import torch BEFORE numpy/rasterio to avoid the libomp/libiomp5md
# OpenMP runtime conflict (torch must load its OMP first).
if sys.platform == "win32":
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    _prefix = os.environ.get("CONDA_PREFIX") or sys.prefix
    _dll_dirs = [
        os.path.join(_prefix, "Lib", "site-packages", "torch", "lib"),
        os.path.join(_prefix, "Library", "bin"),
    ]
    _path_additions = []
    _current_path = os.environ.get("PATH", "")
    for _d in _dll_dirs:
        if os.path.isdir(_d):
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(_d)
            if _d not in _current_path:
                _path_additions.append(_d)
    if _path_additions:
        os.environ["PATH"] = os.pathsep.join(_path_additions) + os.pathsep + _current_path
    # Import torch early so its OpenMP runtime (libiomp5md.dll) loads first,
    # before numpy/rasterio load conda's libomp.dll.
    try:
        import torch  # noqa: F401
    except (ImportError, OSError):
        pass  # ML dependencies not installed — graceful degradation
from datetime import datetime, timezone
from pathlib import Path

import click
import structlog

from georisk.config import reload_config
from georisk.db.client import ApiClient, ProcessingStatus
from georisk.stac.search import search_scenes
from georisk.storage.minio import MinioStorage

logging.basicConfig(format="%(message)s", level=logging.INFO)

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()


@click.group()
@click.option(
    "--config-dir",
    type=click.Path(exists=True, path_type=Path),
    help="Configuration directory",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx: click.Context, config_dir: Path | None, verbose: bool) -> None:
    """GeoRisk raster processing pipeline."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    if config_dir:
        reload_config(config_dir)

    if verbose:
        click.echo("Configuration loaded")


@cli.command()
@click.option("--aoi-id", required=True, help="Area of Interest ID")
@click.option("--date-range", required=True, help="Date range (YYYY-MM-DD/YYYY-MM-DD)")
@click.option("--max-cloud", type=float, default=20.0, help="Maximum cloud cover percentage")
@click.option("--limit", type=int, default=20, help="Maximum number of results")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output JSON file")
def search(aoi_id: str, date_range: str, max_cloud: float, limit: int, output: Path | None) -> None:
    """Search for available Sentinel-2 imagery."""
    try:
        # Get AOI bounding box from API
        with ApiClient() as api:
            bbox = api.get_aoi_bbox(aoi_id)
            click.echo(f"AOI bounding box: {bbox}")

        # Parse date range
        start_date, end_date = date_range.split("/")

        # Search for scenes
        scenes = search_scenes(
            bbox=bbox,
            start_date=start_date,
            end_date=end_date,
            max_cloud_cover=max_cloud,
            max_items=limit,
        )

        click.echo(f"\nFound {len(scenes)} scenes:")
        for scene in scenes:
            click.echo(
                f"  {scene.scene_id} | "
                f"{scene.datetime.strftime('%Y-%m-%d')} | "
                f"{scene.cloud_cover:.1f}% cloud"
            )

        # Save to file if requested
        if output:
            output_data = [
                {
                    "scene_id": s.scene_id,
                    "datetime": s.datetime.isoformat(),
                    "cloud_cover": s.cloud_cover,
                    "bbox": list(s.bbox),
                }
                for s in scenes
            ]
            with open(output, "w") as f:
                json.dump(output_data, f, indent=2)
            click.echo(f"\nResults saved to: {output}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--aoi-id", required=True, help="Area of Interest ID")
@click.option(
    "--max-cloud",
    type=float,
    default=None,
    help="Maximum cloud cover percentage (overrides AOI setting)",
)
@click.option(
    "--since",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Search for imagery after this date (YYYY-MM-DD)",
)
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON")
@click.pass_context
def check(
    ctx,
    aoi_id: str,
    max_cloud: float | None,
    since: datetime | None,
    output_json: bool,
) -> None:
    """Check for new satellite imagery availability for an AOI.

    Searches STAC for scenes newer than the last completed processing run.
    Exit codes: 0 = new data found, 1 = no new data, 2 = error.
    """
    from datetime import timedelta

    logger = structlog.get_logger()

    try:
        with ApiClient() as api:
            # 1. Get AOI details
            aoi = api.get_aoi(aoi_id)
            bbox = tuple(aoi["boundingBox"])
            cloud_threshold = max_cloud if max_cloud is not None else aoi.get("maxCloudCover", 20.0)

            # 2. Determine "since" date
            last_run = None
            if since:
                since_date = since.strftime("%Y-%m-%d")
            else:
                last_run = api.get_latest_completed_run(aoi_id)
                if last_run and last_run.get("afterDate"):
                    # Start searching the day AFTER the last run's after date
                    # to avoid re-finding the same scene on that date
                    after_str = last_run["afterDate"].replace("Z", "+00:00")
                    last_after = datetime.fromisoformat(after_str)
                    since_date = (last_after + timedelta(days=1)).strftime("%Y-%m-%d")
                else:
                    fallback = datetime.now(timezone.utc) - timedelta(days=30)
                    since_date = fallback.strftime("%Y-%m-%d")

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            if not output_json:
                click.echo(
                    f"Checking for new imagery since {since_date} "
                    f"(max cloud: {cloud_threshold}%)"
                )

            # 3. Search STAC for new scenes
            scenes = search_scenes(
                bbox=bbox,
                start_date=since_date,
                end_date=today,
                max_cloud_cover=cloud_threshold,
                max_items=10,
            )

            # 4. Filter out scenes already processed in the last run
            if last_run:
                processed_ids = set()
                if last_run.get("afterSceneId"):
                    processed_ids.add(last_run["afterSceneId"])
                if last_run.get("beforeSceneId"):
                    processed_ids.add(last_run["beforeSceneId"])
                if processed_ids:
                    scenes = [s for s in scenes if s.scene_id not in processed_ids]

            if not scenes:
                result = {
                    "new_data": False,
                    "since_date": since_date,
                    "message": "No new imagery found",
                }
                if output_json:
                    click.echo(json.dumps(result, indent=2))
                else:
                    click.echo("No new imagery found.")
                sys.exit(1)

            # 5. Pick best scene (scenes are sorted by date descending)
            best = scenes[0]

            # 6. Determine recommended "before" date
            if last_run and last_run.get("afterDate"):
                after_iso = last_run["afterDate"].replace("Z", "+00:00")
                recommended_before = datetime.fromisoformat(
                    after_iso
                ).strftime("%Y-%m-%d")
            else:
                lookback = aoi.get("defaultLookbackDays", 90)
                recommended_before = (best.datetime - timedelta(days=lookback)).strftime("%Y-%m-%d")

            recommended_after = best.datetime.strftime("%Y-%m-%d")

            result = {
                "new_data": True,
                "scene_id": best.scene_id,
                "scene_date": recommended_after,
                "cloud_cover": best.cloud_cover,
                "recommended_before_date": recommended_before,
                "recommended_after_date": recommended_after,
            }

            if output_json:
                click.echo(json.dumps(result, indent=2))
            else:
                click.echo("\nNew imagery available!")
                click.echo(f"  Scene: {best.scene_id}")
                click.echo(f"  Date:  {recommended_after}")
                click.echo(f"  Cloud: {best.cloud_cover:.1f}%")
                click.echo("\nRecommended processing dates:")
                click.echo(f"  Before: {recommended_before}")
                click.echo(f"  After:  {recommended_after}")

            sys.exit(0)

    except SystemExit:
        raise
    except Exception as e:
        if output_json:
            click.echo(json.dumps({"new_data": False, "error": str(e)}, indent=2))
        else:
            click.echo(f"Error: {e}", err=True)
        logger.exception("check_command_failed")
        sys.exit(2)


@cli.command()
@click.option("--aoi-id", required=True, help="Area of Interest ID")
@click.option("--before", required=True, help="Before date (YYYY-MM-DD)")
@click.option("--after", required=True, help="After date (YYYY-MM-DD)")
@click.option("--run-id", help="Existing processing run ID (if not provided, creates new run)")
@click.option("--window", type=int, default=30, help="Search window in days")
@click.option("--threshold", type=float, help="NDVI change threshold (e.g., -0.2)")
@click.option("--min-area", type=float, help="Minimum change area in m\u00b2")
@click.option("--max-distance", type=float, help="Max proximity distance in meters (default: 1000)")
@click.option(
    "--dem-source",
    type=click.Choice(["3dep", "lidar", "local", "none"]),
    default="3dep",
    help="DEM source for terrain analysis "
    "(3dep=10m, lidar=COPC 1m, local=file, none=disable)",
)
@click.option("--skip-terrain", is_flag=True, help="Skip terrain analysis")
@click.option("--skip-landcover", is_flag=True, help="Skip ML land cover classification")
@click.option("--skip-landslide", is_flag=True, help="Skip ML landslide detection")
@click.option(
    "--skip-lidar", is_flag=True,
    help="Skip per-polygon LIDAR terrain for landslide polygons",
)
@click.option("--dry-run", is_flag=True, help="Simulate without API updates")
@click.pass_context
def process(
    ctx: click.Context,
    aoi_id: str,
    before: str,
    after: str,
    run_id: str | None,
    window: int,
    threshold: float | None,
    min_area: float | None,
    max_distance: float | None,
    dem_source: str,
    skip_terrain: bool,
    skip_landcover: bool,
    skip_landslide: bool,
    skip_lidar: bool,
    dry_run: bool,
) -> None:
    """Process imagery and detect changes for an AOI."""
    from georisk.pipeline.context import StepContext
    from georisk.pipeline.orchestrator import PipelineError, PipelineOrchestrator
    from georisk.pipeline.progress import cli_progress
    from georisk.pipeline.steps import (
        AnalyzeTerrainStep,
        CalculateNdviStep,
        ClassifyLandcoverStep,
        CompleteProcessingStep,
        CreateRgbStep,
        DetectChangesStep,
        DetectLandslideStep,
        GenerateLidarStep,
        SavePolygonsStep,
        ScoreRiskStep,
        SearchImageryStep,
    )

    ctx.obj.get("verbose", False)

    try:
        with ApiClient() as api:
            # Get AOI details
            aoi = api.get_aoi(aoi_id)
            bbox = tuple(aoi["boundingBox"])
            click.echo(f"Processing AOI: {aoi['name']}")

            # Use existing run or create new one (unless dry run)
            if run_id:
                click.echo(f"Using existing processing run: {run_id}")
            elif not dry_run:
                run = api.create_processing_run(aoi_id, before, after)
                run_id = run["runId"]
                click.echo(f"Created processing run: {run_id}")

            pipeline_ctx = StepContext(
                aoi_id=aoi_id,
                aoi=aoi,
                bbox=bbox,
                before_date=before,
                after_date=after,
                run_id=run_id,
                dry_run=dry_run,
                window=window,
                threshold=threshold,
                min_area=min_area,
                max_distance=max_distance,
                dem_source=dem_source,
                skip_terrain=skip_terrain,
                skip_landcover=skip_landcover,
                skip_landslide=skip_landslide,
                skip_lidar=skip_lidar,
                api=api,
            )

            steps = [
                SearchImageryStep(),         # 1. Find before/after scene pair via STAC
                CreateRgbStep(),             # 2. Download RGB composites, upload to storage
                CalculateNdviStep(),         # 3. Compute NDVI for both scenes
                DetectChangesStep(),         # 4. Diff NDVI, threshold, vectorize to polygons
                AnalyzeTerrainStep(),        # 5. Load DEM, enrich polygons with slope/aspect
                ClassifyLandcoverStep(),     # 6. EuroSAT land cover, refine change types
                DetectLandslideStep(),       # 7. ML segmentation on steep-terrain polygons
                SavePolygonsStep(),          # 8. Persist enriched polygons to API
                ScoreRiskStep(),             # 9. Proximity analysis + multi-factor risk scoring
                GenerateLidarStep(),         # 10. 1m LIDAR terrain for landslide polygons
                CompleteProcessingStep(),    # 11. Update run status + metadata summary
            ]

            orchestrator = PipelineOrchestrator(steps, on_progress=cli_progress)
            orchestrator.run(pipeline_ctx)

            # Summary
            click.echo("\n" + "=" * 50)
            click.echo("Processing complete!")
            click.echo(f"  Run ID: {pipeline_ctx.run_id or 'dry-run'}")
            changes_count = len(pipeline_ctx.changes.polygons) if pipeline_ctx.changes else 0
            click.echo(f"  Changes: {changes_count}")
            click.echo(f"  Risk events: {len(pipeline_ctx.risk_events)}")

    except (PipelineError, Exception) as e:
        logger.exception("Processing failed")
        click.echo(f"Error: {e}", err=True)
        if run_id:
            try:
                with ApiClient() as api:
                    api.update_processing_run(
                        run_id,
                        status=ProcessingStatus.FAILED,
                        error_message=str(e),
                    )
            except Exception:
                pass
        sys.exit(1)


@cli.command()
@click.option("--aoi-id", required=True, help="Area of Interest ID")
@click.option("--date", required=True, help="Target date (YYYY-MM-DD)")
@click.option("--window", type=int, default=30, help="Search window in days")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), help="Output directory")
def fetch(aoi_id: str, date: str, window: int, output_dir: Path | None) -> None:
    """Fetch imagery for an AOI (download without processing)."""
    try:
        with ApiClient() as api:
            bbox = api.get_aoi_bbox(aoi_id)

        from georisk.stac.client import StacClient

        client = StacClient()
        scene = client.find_best_scene(bbox, date, window)

        if not scene:
            click.echo("No suitable scene found", err=True)
            sys.exit(1)

        click.echo(f"Found scene: {scene['id']}")
        click.echo(f"  Date: {scene['datetime']}")
        click.echo(f"  Cloud cover: {scene['cloud_cover']:.1f}%")

        # Download bands
        if output_dir:
            from georisk.raster.download import download_scene
            from georisk.stac.search import SceneInfo

            output_dir.mkdir(parents=True, exist_ok=True)
            scene_info = SceneInfo.from_dict(scene)

            downloaded = download_scene(scene_info, ["B04", "B08", "visual"], output_dir)
            click.echo(f"\nDownloaded {len(downloaded)} bands to {output_dir}")
            for band, path in downloaded.items():
                click.echo(f"  {band}: {path}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--run-id", required=True, help="Processing run ID")
def status(run_id: str) -> None:
    """Check the status of a processing run."""
    try:
        with ApiClient() as api:
            run = api.get_processing_run(run_id)

        click.echo(f"Run ID: {run['runId']}")
        click.echo(f"AOI: {run['aoiId']}")
        click.echo(f"Status: {run['statusName']}")
        click.echo(f"Before: {run['beforeDate']} ({run.get('beforeSceneId', 'N/A')})")
        click.echo(f"After: {run['afterDate']} ({run.get('afterSceneId', 'N/A')})")

        if run.get("errorMessage"):
            click.echo(f"Error: {run['errorMessage']}")

        if run.get("metadata"):
            click.echo(f"Metadata: {json.dumps(run['metadata'], indent=2)}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def health() -> None:
    """Check API and storage health."""
    try:
        # Check API
        with ApiClient() as api:
            health = api.health_check()
            click.echo(f"API: {health.get('status', 'unknown')}")

        # Check MinIO
        storage = MinioStorage()
        storage.ensure_bucket(storage.bucket_imagery)
        click.echo("MinIO: connected")

        # List AOIs
        with ApiClient() as api:
            aois = api.list_aois()
            click.echo(f"AOIs: {len(aois)} available")
            for aoi in aois:
                click.echo(f"  - {aoi['aoiId']}: {aoi['name']}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.group()
def model() -> None:
    """Manage ML models in object storage (S3/MinIO)."""
    pass


@model.command("upload")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--name", default="landslide", help="Model name (storage prefix)")
@click.option("--version", default=None, help="Optional version string (e.g. v1)")
def model_upload(path: Path, name: str, version: str | None) -> None:
    """Upload a model file to object storage."""
    try:
        storage = MinioStorage()
        result = storage.upload_model(path, model_name=name, version=version)
        click.echo(f"Uploaded {path.name} -> {result}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@model.command("download")
@click.option("--name", default="landslide", help="Model name (storage prefix)")
@click.option("--version", default=None, help="Optional version string")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Output path (default: ~/.cache/georisk/models/landslide_model.pth)")
def model_download(name: str, version: str | None, output: Path | None) -> None:
    """Download a model file from object storage."""
    from georisk.raster.landslide import DEFAULT_MODEL_PATH

    try:
        target = output or DEFAULT_MODEL_PATH
        storage = MinioStorage()
        storage.download_model(target, model_name=name, version=version)
        click.echo(f"Downloaded to {target}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@model.command("list")
@click.option("--name", default=None, help="Filter by model name")
def model_list(name: str | None) -> None:
    """List models in object storage."""
    try:
        storage = MinioStorage()
        objects = storage.list_models(model_name=name)

        if not objects:
            click.echo("No models found in storage.")
            return

        click.echo(f"Found {len(objects)} model file(s):")
        for obj in objects:
            size_mb = obj["size"] / (1024 * 1024)
            click.echo(f"  {obj['key']}  ({size_mb:.1f} MB, {obj['last_modified']})")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
