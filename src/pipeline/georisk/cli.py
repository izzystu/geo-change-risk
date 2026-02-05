"""Command-line interface for the GeoRisk pipeline."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import structlog

from georisk.config import get_config, reload_config
from georisk.db.client import ApiClient, ProcessingStatus
from georisk.raster.change import detect_changes
from georisk.raster.ndvi import calculate_ndvi_from_scene
from georisk.risk.proximity import find_nearby_assets
from georisk.risk.scoring import RiskScorer
from georisk.stac.search import search_scenes, find_scene_pair
from georisk.storage.minio import MinioStorage

# Configure structlog for CLI output
import logging

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
@click.option("--config-dir", type=click.Path(exists=True, path_type=Path), help="Configuration directory")
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
            click.echo(f"  {scene.scene_id} | {scene.datetime.strftime('%Y-%m-%d')} | {scene.cloud_cover:.1f}% cloud")

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
@click.option("--before", required=True, help="Before date (YYYY-MM-DD)")
@click.option("--after", required=True, help="After date (YYYY-MM-DD)")
@click.option("--run-id", help="Existing processing run ID (if not provided, creates new run)")
@click.option("--window", type=int, default=30, help="Search window in days")
@click.option("--threshold", type=float, help="NDVI change threshold (e.g., -0.2)")
@click.option("--min-area", type=float, help="Minimum change area in m\u00b2")
@click.option("--max-distance", type=float, help="Max proximity distance in meters (default: 1000)")
@click.option("--dem-source", type=click.Choice(["3dep", "local", "none"]), default="3dep",
              help="DEM source for terrain analysis (3dep=USGS 3DEP, local=local file, none=disable)")
@click.option("--skip-terrain", is_flag=True, help="Skip terrain analysis")
@click.option("--skip-landcover", is_flag=True, help="Skip ML land cover classification")
@click.option("--skip-landslide", is_flag=True, help="Skip ML landslide detection")
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
    dry_run: bool,
) -> None:
    """Process imagery and detect changes for an AOI."""
    verbose = ctx.obj.get("verbose", False)

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

            # Find imagery scenes
            click.echo("\n1. Searching for imagery...")
            if run_id:
                api.update_processing_run(run_id, status=ProcessingStatus.FETCHING_IMAGERY)

            before_scene, after_scene = find_scene_pair(bbox, before, after, window)

            if not before_scene or not after_scene:
                error_msg = "Could not find suitable imagery scenes"
                if run_id:
                    api.update_processing_run(run_id, status=ProcessingStatus.FAILED, error_message=error_msg)
                click.echo(f"Error: {error_msg}", err=True)
                sys.exit(1)

            click.echo(f"  Before: {before_scene.scene_id} ({before_scene.datetime.strftime('%Y-%m-%d')})")
            click.echo(f"  After:  {after_scene.scene_id} ({after_scene.datetime.strftime('%Y-%m-%d')})")

            if run_id:
                api.update_processing_run(
                    run_id,
                    before_scene_id=before_scene.scene_id,
                    after_scene_id=after_scene.scene_id,
                )

            # Create and upload RGB composites for visualization
            if not dry_run:
                click.echo("\n1b. Creating RGB imagery for visualization...")
                from georisk.raster.download import create_rgb_composite
                import tempfile

                with tempfile.TemporaryDirectory(prefix="georisk_rgb_") as temp_dir:
                    temp_path = Path(temp_dir)
                    storage = MinioStorage()

                    # Before scene RGB
                    before_rgb_path = temp_path / f"{before_scene.scene_id}_rgb.tif"
                    before_tif, before_png, before_bounds = create_rgb_composite(before_scene, bbox, before_rgb_path)
                    storage.upload_imagery(before_tif, aoi_id, before_scene.scene_id, "rgb.tif")
                    if before_png:
                        storage.upload_imagery(before_png, aoi_id, before_scene.scene_id, "rgb.png")
                        # Upload bounds sidecar file for proper georeferencing
                        bounds_file = before_rgb_path.with_suffix('.bounds.json')
                        if bounds_file.exists():
                            storage.upload_imagery(bounds_file, aoi_id, before_scene.scene_id, "rgb.bounds.json")
                    click.echo(f"  Uploaded before imagery: {before_scene.scene_id}")

                    # After scene RGB
                    after_rgb_path = temp_path / f"{after_scene.scene_id}_rgb.tif"
                    after_tif, after_png, after_bounds = create_rgb_composite(after_scene, bbox, after_rgb_path)
                    storage.upload_imagery(after_tif, aoi_id, after_scene.scene_id, "rgb.tif")
                    if after_png:
                        storage.upload_imagery(after_png, aoi_id, after_scene.scene_id, "rgb.png")
                        # Upload bounds sidecar file for proper georeferencing
                        bounds_file = after_rgb_path.with_suffix('.bounds.json')
                        if bounds_file.exists():
                            storage.upload_imagery(bounds_file, aoi_id, after_scene.scene_id, "rgb.bounds.json")
                    click.echo(f"  Uploaded after imagery: {after_scene.scene_id}")

            # Calculate NDVI
            click.echo("\n2. Calculating NDVI...")
            if run_id:
                api.update_processing_run(run_id, status=ProcessingStatus.CALCULATING_NDVI)

            before_ndvi = calculate_ndvi_from_scene(before_scene, bbox)
            after_ndvi = calculate_ndvi_from_scene(after_scene, bbox)

            click.echo(f"  Before NDVI: mean={before_ndvi.mean_value:.3f}")
            click.echo(f"  After NDVI:  mean={after_ndvi.mean_value:.3f}")

            # Detect changes
            click.echo("\n3. Detecting changes...")
            if run_id:
                api.update_processing_run(run_id, status=ProcessingStatus.DETECTING_CHANGES)

            changes = detect_changes(
                before_ndvi,
                after_ndvi,
                threshold=threshold,
                min_area_m2=min_area,
            )

            click.echo(f"  Found {len(changes.polygons)} change polygons")
            click.echo(f"  Changed area: {changes.stats['change_percent']:.2f}%")

            # Load DEM and analyze terrain (if enabled)
            dem_data = None
            if not skip_terrain and dem_source != "none" and changes.polygons:
                click.echo("\n3b. Analyzing terrain...")
                try:
                    from georisk.raster.terrain import (
                        load_dem_for_bbox,
                        calculate_slope_aspect,
                        extract_terrain_stats_for_polygon,
                    )

                    dem_data = load_dem_for_bbox(bbox, dem_source=dem_source)

                    if dem_data is not None:
                        # Calculate slope and aspect
                        dem_data = calculate_slope_aspect(dem_data)

                        # Enrich change polygons with terrain data
                        for change in changes.polygons:
                            terrain_stats = extract_terrain_stats_for_polygon(
                                dem_data, change.geometry
                            )
                            change.slope_degree_mean = terrain_stats.get("slope_degree_mean")
                            change.slope_degree_max = terrain_stats.get("slope_degree_max")
                            change.aspect_degrees = terrain_stats.get("aspect_degrees")
                            change.elevation_m = terrain_stats.get("elevation_m")

                        click.echo(f"  Enriched {len(changes.polygons)} polygons with terrain data")
                    else:
                        click.echo("  Warning: Could not load DEM, skipping terrain analysis")
                except ImportError as e:
                    click.echo(f"  Warning: Terrain module not available ({e}), skipping terrain analysis")
                except Exception as e:
                    click.echo(f"  Warning: Terrain analysis failed ({e}), continuing without terrain data")
            elif skip_terrain:
                click.echo("\n3b. Terrain analysis skipped (--skip-terrain)")

            # Initialize scene_bands so it can be reused by both land cover and landslide blocks
            scene_bands = None

            # Land cover classification (if enabled and ML deps available)
            if not skip_landcover and changes.polygons:
                click.echo("\n3c. Classifying land cover...")
                try:
                    from georisk.raster.landcover import (
                        is_landcover_available,
                        load_eurosat_model,
                        load_scene_bands,
                        classify_polygon_landcover,
                    )
                    from georisk.raster.change import _classify_change

                    if is_landcover_available():
                        model = load_eurosat_model()
                        scene_bands = load_scene_bands(before_scene, bbox)

                        if scene_bands is not None:
                            classified_count = 0
                            for change in changes.polygons:
                                result = classify_polygon_landcover(
                                    scene_bands, change.geometry, model
                                )
                                if result is not None:
                                    change.land_cover_class = result.dominant_class
                                    change.ml_confidence = result.confidence
                                    change.ml_model_version = result.model_version
                                    classified_count += 1

                            click.echo(f"  Classified {classified_count}/{len(changes.polygons)} polygons")

                            # Re-classify change types with land cover context
                            reclassified = 0
                            for change in changes.polygons:
                                if change.land_cover_class is not None:
                                    new_type = _classify_change(
                                        change.ndvi_drop_mean, change.land_cover_class
                                    )
                                    if new_type != change.change_type:
                                        change.change_type = new_type
                                        reclassified += 1
                            if reclassified:
                                click.echo(f"  Refined {reclassified} change types with land cover context")
                        else:
                            click.echo("  Warning: Could not load scene bands, skipping classification")
                    else:
                        click.echo("  ML dependencies not installed (pip install -e '.[ml]'), skipping")
                except ImportError as e:
                    click.echo(f"  Warning: Land cover module not available ({e}), skipping")
                except Exception as e:
                    click.echo(f"  Warning: Land cover classification failed ({e}), continuing without")
            elif skip_landcover:
                click.echo("\n3c. Land cover classification skipped (--skip-landcover)")

            # Landslide detection (if enabled, ML deps available, and terrain data exists)
            if not skip_landslide and dem_data is not None and changes.polygons:
                click.echo("\n3d. Running landslide detection...")
                try:
                    from georisk.raster.landslide import (
                        is_landslide_available,
                        load_landslide_model,
                        classify_polygon_landslide,
                        LANDSLIDE_SENTINEL_BANDS,
                    )

                    if is_landslide_available():
                        ls_model = load_landslide_model()

                        # Load 12-band scene for landslide model (excludes B8A,
                        # different from landcover's 13 bands)
                        from georisk.raster.landcover import load_scene_bands
                        ls_scene_bands = load_scene_bands(
                            before_scene, bbox, bands=LANDSLIDE_SENTINEL_BANDS,
                        )

                        if ls_scene_bands is not None:
                            candidates = 0
                            landslide_count = 0
                            for change in changes.polygons:
                                if (change.slope_degree_mean or 0) >= 10.0:
                                    candidates += 1
                                    result = classify_polygon_landslide(
                                        ls_scene_bands, dem_data, change.geometry, ls_model,
                                    )
                                    if result is not None and result.is_landslide:
                                        change.change_type = "LandslideDebris"
                                        change.ml_confidence = result.landslide_probability
                                        change.ml_model_version = result.model_version
                                        landslide_count += 1
                            click.echo(
                                f"  Analyzed {candidates} steep-terrain polygons, "
                                f"classified {landslide_count} as landslides"
                            )
                        else:
                            click.echo("  Warning: Could not load scene bands, skipping")
                    else:
                        click.echo("  ML dependencies not installed (pip install -e '.[ml]'), skipping")
                except FileNotFoundError as e:
                    click.echo(f"  Warning: {e}")
                except ImportError as e:
                    click.echo(f"  Warning: Landslide module not available ({e}), skipping")
                except Exception as e:
                    click.echo(f"  Warning: Landslide detection failed ({e}), continuing without")
            elif skip_landslide:
                click.echo("\n3d. Landslide detection skipped (--skip-landslide)")
            elif dem_data is None and not skip_landslide:
                click.echo("\n3d. Landslide detection skipped (no terrain data)")

            # Track created polygon IDs for risk event mapping
            created_polygon_ids: list[str] = []

            if not dry_run and changes.polygons:
                # Save change polygons to API
                result = api.create_change_polygons(run_id, changes.polygons)
                click.echo(f"  Saved {result.get('successCount', 0)} polygons to database")
                created_polygon_ids = result.get("createdIds", [])

            # Score risk events
            click.echo("\n4. Scoring risk events...")
            if run_id:
                api.update_processing_run(run_id, status=ProcessingStatus.SCORING_RISK)

            # Get assets for proximity analysis (need geometry for distance calculation)
            assets_geojson = api.get_assets_geojson(aoi_id)
            assets = []
            for feature in assets_geojson.get("features", []):
                props = feature.get("properties", {})
                assets.append({
                    "assetId": feature.get("id"),
                    "name": props.get("name"),
                    "assetType": props.get("assetType"),
                    "assetTypeName": props.get("assetTypeName"),
                    "criticality": props.get("criticality"),
                    "criticalityName": props.get("criticalityName"),
                    "geometry": feature.get("geometry"),
                })
            click.echo(f"  Analyzing proximity to {len(assets)} assets...")

            # Get max distance from CLI, config, or default
            config = get_config()
            proximity_distance = max_distance or config.processing.max_proximity_m
            click.echo(f"  Using max proximity distance: {proximity_distance}m")

            scorer = RiskScorer()
            risk_events = []

            for polygon_index, change in enumerate(changes.polygons):
                # Map polygon to its created ID (by index)
                polygon_id = created_polygon_ids[polygon_index] if polygon_index < len(created_polygon_ids) else None
                # Pass DEM data for directional terrain analysis
                nearby = find_nearby_assets(
                    change.geometry,
                    assets,
                    max_distance_m=proximity_distance,
                    dem_data=dem_data,
                    change_elevation_m=change.elevation_m,
                )
                for prox in nearby:
                    score = scorer.calculate_risk_score(change, prox)
                    risk_events.append({
                        "changePolygonId": polygon_id,
                        "assetId": prox.asset_id,
                        "distanceMeters": prox.distance_meters,
                        "riskScore": score.score,
                        "riskLevel": {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}.get(score.level, 0),
                        "scoringFactors": score.scoring_factors_dict,
                    })

            click.echo(f"  Generated {len(risk_events)} risk events")

            # Save risk events to database
            if not dry_run and risk_events:
                risk_result = api.create_risk_events(risk_events)
                click.echo(f"  Saved {risk_result.get('successCount', 0)} risk events to database")

            # Report high-risk events
            critical = [e for e in risk_events if e["riskLevel"] >= 2]
            if critical:
                click.echo(f"\n  High/Critical risk events: {len(critical)}")
                for event in critical[:5]:
                    click.echo(f"    - Asset {event['assetId']}: score={event['riskScore']}")

            # Complete processing
            if run_id:
                api.update_processing_run(
                    run_id,
                    status=ProcessingStatus.COMPLETED,
                    metadata={
                        "change_polygons": len(changes.polygons),
                        "risk_events": len(risk_events),
                        "stats": changes.stats,
                        "terrain_analysis": dem_data is not None,
                        "dem_source": dem_source if dem_data is not None else None,
                        "land_cover_classification": any(
                            c.land_cover_class is not None for c in changes.polygons
                        ),
                        "ml_model_version": next(
                            (c.ml_model_version for c in changes.polygons if c.ml_model_version),
                            None,
                        ),
                    },
                )

            click.echo("\n" + "=" * 50)
            click.echo("Processing complete!")
            click.echo(f"  Run ID: {run_id or 'dry-run'}")
            click.echo(f"  Changes: {len(changes.polygons)}")
            click.echo(f"  Risk events: {len(risk_events)}")

    except Exception as e:
        logger.exception("Processing failed")
        click.echo(f"Error: {e}", err=True)
        if run_id:
            try:
                with ApiClient() as api:
                    api.update_processing_run(run_id, status=ProcessingStatus.FAILED, error_message=str(e))
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


if __name__ == "__main__":
    cli()
