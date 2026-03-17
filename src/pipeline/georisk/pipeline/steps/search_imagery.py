"""Search for before/after imagery scenes via STAC."""

from georisk.pipeline.context import StepContext
from georisk.pipeline.step import ErrorPolicy, PipelineStep, StepResult


class SearchImageryStep(PipelineStep):
    name = "search_imagery"
    error_policy = ErrorPolicy.REQUIRED

    def execute(self, ctx: StepContext) -> StepResult:
        from georisk.stac.search import find_scene_pair

        before_scene, after_scene = find_scene_pair(
            ctx.bbox, ctx.before_date, ctx.after_date, ctx.window
        )

        if not before_scene or not after_scene:
            return StepResult(success=False, message="Could not find suitable imagery scenes")

        ctx.before_scene = before_scene
        ctx.after_scene = after_scene

        before_dt = before_scene.datetime.strftime("%Y-%m-%d")
        after_dt = after_scene.datetime.strftime("%Y-%m-%d")
        return StepResult(
            success=True,
            message=f"Before: {before_scene.scene_id} ({before_dt}), "
                    f"After: {after_scene.scene_id} ({after_dt})",
        )
