"""Generate LIDAR terrain products for landslide polygons."""

import json
import tempfile
from pathlib import Path

from georisk.pipeline.context import StepContext
from georisk.pipeline.step import ErrorPolicy, PipelineStep, StepResult


class GenerateLidarStep(PipelineStep):
    name = "generate_lidar"
    error_policy = ErrorPolicy.OPTIONAL

    def should_skip(self, ctx: StepContext) -> str | None:
        if ctx.dry_run:
            return "dry run"
        if ctx.skip_lidar:
            return "skip-lidar flag set"
        if not ctx.changes or not ctx.changes.polygons:
            return "no change polygons"
        # Check for LandslideDebris polygons with created IDs
        landslide_polygons = [
            (change, ctx.created_polygon_ids[i])
            for i, change in enumerate(ctx.changes.polygons)
            if change.change_type == "LandslideDebris"
            and i < len(ctx.created_polygon_ids)
            and ctx.created_polygon_ids[i]
        ]
        if not landslide_polygons:
            return "no LandslideDebris polygons"
        return None

    def execute(self, ctx: StepContext) -> StepResult:
        try:
            from georisk.raster.lidar import is_lidar_available, process_polygon_lidar
        except ImportError as e:
            return StepResult(success=True, message=f"LIDAR module not available ({e})")

        if not is_lidar_available():
            return StepResult(success=True, message="PDAL not installed")

        from georisk.storage.minio import MinioStorage

        storage = ctx.storage or MinioStorage()

        landslide_polygons = [
            (change, ctx.created_polygon_ids[i])
            for i, change in enumerate(ctx.changes.polygons)
            if change.change_type == "LandslideDebris"
            and i < len(ctx.created_polygon_ids)
            and ctx.created_polygon_ids[i]
        ]
        ctx.lidar_polygon_count = len(landslide_polygons)

        with tempfile.TemporaryDirectory(
            prefix="georisk_lidar_", ignore_cleanup_errors=True
        ) as temp_dir:
            temp_path = Path(temp_dir)

            for change, pid in landslide_polygons:
                try:
                    poly_output = temp_path / pid
                    products = process_polygon_lidar(
                        polygon_wkt=change.geometry.wkt,
                        polygon_id=pid,
                        output_dir=poly_output,
                    )
                    if products is not None:
                        source_id = f"polygon-{pid}"
                        for fname in ["dtm.tif", "dsm.tif", "chm.tif"]:
                            fpath = poly_output / fname
                            if fpath.exists():
                                storage.upload_lidar(fpath, ctx.aoi_id, source_id, fname)

                        meta_path = poly_output / "metadata.json"
                        meta_path.write_text(
                            json.dumps(products.metadata.to_dict(), indent=2)
                        )
                        storage.upload_lidar(
                            meta_path, ctx.aoi_id, source_id, "metadata.json"
                        )
                        ctx.lidar_polygons_processed += 1
                except Exception:
                    pass  # Per-polygon failures are non-fatal

        return StepResult(
            success=True,
            message=f"Processed {ctx.lidar_polygons_processed}/{ctx.lidar_polygon_count} polygons",
        )
