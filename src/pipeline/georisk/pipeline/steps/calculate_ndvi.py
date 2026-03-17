"""Calculate NDVI for before and after scenes."""

from georisk.pipeline.context import StepContext
from georisk.pipeline.step import ErrorPolicy, PipelineStep, StepResult


class CalculateNdviStep(PipelineStep):
    name = "calculate_ndvi"
    error_policy = ErrorPolicy.REQUIRED

    def execute(self, ctx: StepContext) -> StepResult:
        from georisk.raster.ndvi import calculate_ndvi_from_scene

        ctx.before_ndvi = calculate_ndvi_from_scene(ctx.before_scene, ctx.bbox)
        ctx.after_ndvi = calculate_ndvi_from_scene(ctx.after_scene, ctx.bbox)

        return StepResult(
            success=True,
            message=f"Before mean={ctx.before_ndvi.mean_value:.3f}, "
                    f"After mean={ctx.after_ndvi.mean_value:.3f}",
        )
