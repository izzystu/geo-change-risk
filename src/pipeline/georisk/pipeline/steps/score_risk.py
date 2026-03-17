"""Score risk events based on proximity to assets."""

from georisk.pipeline.context import StepContext
from georisk.pipeline.step import ErrorPolicy, PipelineStep, StepResult


class ScoreRiskStep(PipelineStep):
    name = "score_risk"
    error_policy = ErrorPolicy.REQUIRED

    def should_skip(self, ctx: StepContext) -> str | None:
        if not ctx.changes or not ctx.changes.polygons:
            return "no change polygons"
        return None

    def execute(self, ctx: StepContext) -> StepResult:
        from georisk.risk.proximity import find_nearby_assets
        from georisk.risk.scoring import RiskScorer

        # Get assets for proximity analysis
        assets_geojson = ctx.api.get_assets_geojson(ctx.aoi_id)
        assets = []
        for feature in assets_geojson.get("features", []):
            props = feature.get("properties", {})
            assets.append({
                "assetId": feature.get("id"),
                "name": props.get("name"),
                "assetType": props.get("assetType"),
                "assetTypeName": props.get("assetTypeName"),
                "criticality": props.get("criticality"),
                "criticalityName": props.get("criticalityName"),
                "geometry": feature.get("geometry"),
            })

        proximity_distance = ctx.max_distance or ctx.config.processing.max_proximity_m
        scorer = RiskScorer()

        for polygon_index, change in enumerate(ctx.changes.polygons):
            polygon_id = (
                ctx.created_polygon_ids[polygon_index]
                if polygon_index < len(ctx.created_polygon_ids)
                else None
            )
            nearby = find_nearby_assets(
                change.geometry,
                assets,
                max_distance_m=proximity_distance,
                dem_data=ctx.dem_data,
                change_elevation_m=change.elevation_m,
            )
            for prox in nearby:
                score = scorer.calculate_risk_score(change, prox)
                ctx.risk_events.append({
                    "changePolygonId": polygon_id,
                    "assetId": prox.asset_id,
                    "distanceMeters": prox.distance_meters,
                    "riskScore": score.score,
                    "riskLevel": {
                        "Low": 0, "Medium": 1,
                        "High": 2, "Critical": 3,
                    }.get(score.level, 0),
                    "scoringFactors": score.scoring_factors_dict,
                })

        # Save to database
        if not ctx.dry_run and ctx.risk_events:
            ctx.api.create_risk_events(ctx.risk_events)

        return StepResult(
            success=True,
            message=f"Generated {len(ctx.risk_events)} risk events",
        )
