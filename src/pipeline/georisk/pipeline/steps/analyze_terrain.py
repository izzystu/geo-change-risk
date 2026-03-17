"""Analyze terrain characteristics (slope, aspect, elevation) for change polygons."""

from georisk.pipeline.context import StepContext
from georisk.pipeline.step import ErrorPolicy, PipelineStep, StepResult

class AnalyzeTerrainStep(PipelineStep):
    name = "analyze_terrain"
    error_policy = ErrorPolicy.OPTIONAL

    def should_skip(self, ctx: StepContext) -> str | None:
        if ctx.skip_terrain:
            return "skip_terrain flag set"
        if ctx.dem_source == "none":
            return "no DEM source"
        if not ctx.changes or not ctx.changes.polygons:
            return "no change polygons"
        return None

    def execute(self, ctx: StepContext) -> StepResult:
        try:
            from georisk.raster.terrain import (
                    calculate_slope_aspect,
                    extract_terrain_stats_for_polygon,
                    load_dem_for_bbox,
                )
        except ImportError as e:
            return StepResult(success=True, message=f"ML module not available ({e})")

        dem_data = load_dem_for_bbox(ctx.bbox, dem_source=ctx.dem_source)
        if dem_data is None:
            return StepResult(success=True, message="Could not load DEM data")

        dem_data = calculate_slope_aspect(dem_data)

        for change in ctx.changes.polygons:
            terrain_stats = extract_terrain_stats_for_polygon(dem_data, change.geometry)
            if terrain_stats:
                change.slope_degree_mean = terrain_stats.get("slope_degree_mean")
                change.slope_degree_max = terrain_stats.get("slope_degree_max")
                change.aspect_degrees = terrain_stats.get("aspect_degrees")
                change.elevation_m = terrain_stats.get("elevation_m")

        ctx.dem_data = dem_data

        return StepResult(
            success=True,
            message="Analyzed terrain for change polygons",
        )
