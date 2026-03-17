"""Create and upload RGB composites for visualization."""

import tempfile
from pathlib import Path

from georisk.pipeline.context import StepContext
from georisk.pipeline.step import ErrorPolicy, PipelineStep, StepResult


class CreateRgbStep(PipelineStep):
    name = "create_rgb"
    error_policy = ErrorPolicy.OPTIONAL

    def should_skip(self, ctx: StepContext) -> str | None:
        if ctx.dry_run:
            return "dry run"
        return None

    def execute(self, ctx: StepContext) -> StepResult:
        from georisk.raster.download import create_rgb_composite
        from georisk.storage.minio import MinioStorage

        storage = ctx.storage or MinioStorage()

        with tempfile.TemporaryDirectory(prefix="georisk_rgb_") as temp_dir:
            temp_path = Path(temp_dir)

            for scene, label in [
                (ctx.before_scene, "before"),
                (ctx.after_scene, "after"),
            ]:
                rgb_path = temp_path / f"{scene.scene_id}_rgb.tif"
                tif, png, bounds = create_rgb_composite(scene, ctx.bbox, rgb_path)
                storage.upload_imagery(tif, ctx.aoi_id, scene.scene_id, "rgb.tif")
                if png:
                    storage.upload_imagery(png, ctx.aoi_id, scene.scene_id, "rgb.png")
                    bounds_file = rgb_path.with_suffix(".bounds.json")
                    if bounds_file.exists():
                        storage.upload_imagery(
                            bounds_file, ctx.aoi_id, scene.scene_id, "rgb.bounds.json"
                        )

        return StepResult(success=True, message="Uploaded RGB composites")
