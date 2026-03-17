"""Classify land cover and refine change types using EuroSAT model."""

from georisk.pipeline.context import StepContext
from georisk.pipeline.step import ErrorPolicy, PipelineStep, StepResult


class ClassifyLandcoverStep(PipelineStep):
    name = "classify_landcover"
    error_policy = ErrorPolicy.OPTIONAL

    def should_skip(self, ctx: StepContext) -> str | None:
        if ctx.skip_landcover:
            return "skip-landcover flag set"
        if not ctx.changes or not ctx.changes.polygons:
            return "no change polygons"
        return None

    def execute(self, ctx: StepContext) -> StepResult:
        try:
            from georisk.raster.change import _classify_change
            from georisk.raster.landcover import (
                classify_polygon_landcover,
                is_landcover_available,
                load_eurosat_model,
                load_scene_bands,
            )
        except ImportError as e:
            return StepResult(success=True, message=f"ML module not available ({e})")

        if not is_landcover_available():
            return StepResult(success=True, message="ML dependencies not installed")

        model = load_eurosat_model()
        ctx.scene_bands = load_scene_bands(ctx.before_scene, ctx.bbox)

        if ctx.scene_bands is None:
            return StepResult(success=True, message="Could not load scene bands")

        classified_count = 0
        for change in ctx.changes.polygons:
            result = classify_polygon_landcover(ctx.scene_bands, change.geometry, model)
            if result is not None:
                change.land_cover_class = result.dominant_class
                change.ml_confidence = result.confidence
                change.ml_model_version = result.model_version
                classified_count += 1

        # Re-classify change types with land cover context
        reclassified = 0
        for change in ctx.changes.polygons:
            if change.land_cover_class is not None:
                new_type = _classify_change(change.ndvi_drop_mean, change.land_cover_class)
                if new_type != change.change_type:
                    change.change_type = new_type
                    reclassified += 1

        total = len(ctx.changes.polygons)
        msg = f"Classified {classified_count}/{total} polygons"
        if reclassified:
            msg += f", refined {reclassified} change types"
        return StepResult(success=True, message=msg)
