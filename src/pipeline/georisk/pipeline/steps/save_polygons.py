"""Save enriched change polygons to the API."""

from georisk.pipeline.context import StepContext
from georisk.pipeline.step import ErrorPolicy, PipelineStep, StepResult


class SavePolygonsStep(PipelineStep):
    name = "save_polygons"
    error_policy = ErrorPolicy.REQUIRED

    def should_skip(self, ctx: StepContext) -> str | None:
        if ctx.dry_run:
            return "dry run"
        if not ctx.changes or not ctx.changes.polygons:
            return "no change polygons"
        return None

    def execute(self, ctx: StepContext) -> StepResult:
        result = ctx.api.create_change_polygons(ctx.run_id, ctx.changes.polygons)
        ctx.created_polygon_ids = result.get("createdIds", [])
        count = result.get("successCount", 0)
        return StepResult(success=True, message=f"Saved {count} polygons")
