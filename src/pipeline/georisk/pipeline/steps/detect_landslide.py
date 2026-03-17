"""Detect landslides on steep-terrain polygons using ML segmentation."""

from georisk.pipeline.context import StepContext
from georisk.pipeline.step import ErrorPolicy, PipelineStep, StepResult


class DetectLandslideStep(PipelineStep):
    name = "detect_landslide"
    error_policy = ErrorPolicy.OPTIONAL

    def should_skip(self, ctx: StepContext) -> str | None:
        if ctx.skip_landslide:
            return "skip-landslide flag set"
        if ctx.dem_data is None:
            return "no terrain data"
        if not ctx.changes or not ctx.changes.polygons:
            return "no change polygons"
        return None

    def execute(self, ctx: StepContext) -> StepResult:
        try:
            from georisk.raster.landcover import load_scene_bands
            from georisk.raster.landslide import (
                LANDSLIDE_SENTINEL_BANDS,
                classify_polygon_landslide,
                is_landslide_available,
                load_landslide_model,
            )
        except ImportError as e:
            return StepResult(success=True, message=f"ML module not available ({e})")

        if not is_landslide_available():
            return StepResult(success=True, message="ML dependencies not installed")

        ls_model = load_landslide_model()

        # Load 12-band scene for landslide model (different from landcover's 13 bands)
        ls_scene_bands = load_scene_bands(
            ctx.before_scene, ctx.bbox, bands=LANDSLIDE_SENTINEL_BANDS
        )

        if ls_scene_bands is None:
            return StepResult(success=True, message="Could not load scene bands")

        candidates = 0
        landslide_count = 0
        for change in ctx.changes.polygons:
            if (change.slope_degree_mean or 0) >= 10.0:
                candidates += 1
                result = classify_polygon_landslide(
                    ls_scene_bands, ctx.dem_data, change.geometry, ls_model
                )
                if result is not None and result.is_landslide:
                    change.change_type = "LandslideDebris"
                    change.ml_confidence = result.landslide_probability
                    change.ml_model_version = result.model_version
                    landslide_count += 1

        return StepResult(
            success=True,
            message=f"Analyzed {candidates} steep polygons, "
                    f"classified {landslide_count} as landslides",
        )
