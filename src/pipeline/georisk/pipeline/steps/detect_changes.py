"""Detect changes by computing NDVI difference and vectorizing."""

from georisk.pipeline.context import StepContext
from georisk.pipeline.step import ErrorPolicy, PipelineStep, StepResult


class DetectChangesStep(PipelineStep):
    name = "detect_changes"
    error_policy = ErrorPolicy.REQUIRED

    def execute(self, ctx: StepContext) -> StepResult:
        from georisk.raster.change import detect_changes

        ctx.changes = detect_changes(
            ctx.before_ndvi,
            ctx.after_ndvi,
            threshold=ctx.threshold,
            min_area_m2=ctx.min_area,
        )

        return StepResult(
            success=True,
            message=f"{len(ctx.changes.polygons)} change polygons, "
                    f"{ctx.changes.stats['change_percent']:.2f}% changed",
        )
