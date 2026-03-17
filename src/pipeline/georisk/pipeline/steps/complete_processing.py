"""Update processing run to COMPLETED with metadata summary."""

import math

from georisk.pipeline.context import StepContext
from georisk.pipeline.step import ErrorPolicy, PipelineStep, StepResult


class CompleteProcessingStep(PipelineStep):
    name = "complete_processing"
    error_policy = ErrorPolicy.OPTIONAL

    def execute(self, ctx: StepContext) -> StepResult:
        from georisk.db.client import ProcessingStatus

        if not ctx.run_id:
            return StepResult(success=True, message="No run ID (dry run)")

        # Sanitize stats: replace NaN/Inf with None for JSON compliance
        clean_stats = {}
        if ctx.changes:
            clean_stats = {
                k: (
                    None
                    if isinstance(v, float) and (math.isnan(v) or math.isinf(v))
                    else v
                )
                for k, v in ctx.changes.stats.items()
            }

        metadata = {
            "change_polygons": len(ctx.changes.polygons) if ctx.changes else 0,
            "risk_events": len(ctx.risk_events),
            "stats": clean_stats,
            "terrain_analysis": ctx.dem_data is not None,
            "dem_source": ctx.dem_source if ctx.dem_data is not None else None,
            "land_cover_classification": (
                any(c.land_cover_class is not None for c in ctx.changes.polygons)
                if ctx.changes
                else False
            ),
            "ml_model_version": (
                next(
                    (c.ml_model_version for c in ctx.changes.polygons if c.ml_model_version),
                    None,
                )
                if ctx.changes
                else None
            ),
            "lidar_polygon_count": ctx.lidar_polygon_count,
            "lidar_polygons_processed": ctx.lidar_polygons_processed,
        }

        ctx.api.update_processing_run(
            ctx.run_id,
            status=ProcessingStatus.COMPLETED,
            metadata=metadata,
        )

        return StepResult(success=True, message="Processing run completed")
