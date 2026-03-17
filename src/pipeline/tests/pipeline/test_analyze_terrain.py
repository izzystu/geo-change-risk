"""Tests for AnalyzeTerrainStep."""

from unittest.mock import MagicMock, patch

import pytest
from shapely.geometry import Polygon

from georisk.pipeline.steps.analyze_terrain import AnalyzeTerrainStep
from georisk.raster.change import ChangeDetectionResult, ChangePolygon


@pytest.fixture
def sample_polygon():
    return ChangePolygon(
        geometry=Polygon([
            (-121.6, 39.75), (-121.59, 39.75),
            (-121.59, 39.76), (-121.6, 39.76), (-121.6, 39.75)
        ]),
        area_sq_meters=15000,
        ndvi_drop_mean=-0.35,
        ndvi_drop_max=-0.55,
        change_type="VegetationLoss",
    )


@pytest.fixture
def changes_with_polygons(sample_polygon):
    return ChangeDetectionResult(
        ndvi_diff=MagicMock(),
        change_mask=MagicMock(),
        polygons=[sample_polygon],
        before_scene_id="scene-before",
        after_scene_id="scene-after",
        threshold=-0.2,
        stats={"change_percent": 1.5},
    )


class TestSkipConditions:

    def test_skips_when_flag_set(self, make_context):
        step = AnalyzeTerrainStep()
        ctx = make_context(skip_terrain=True)
        assert step.should_skip(ctx) is not None

    def test_skips_when_dem_source_none(self, make_context):
        step = AnalyzeTerrainStep()
        ctx = make_context(dem_source="none")
        assert step.should_skip(ctx) is not None

    def test_skips_when_no_changes(self, make_context):
        step = AnalyzeTerrainStep()
        ctx = make_context(skip_terrain=False, dem_source="3dep")
        assert step.should_skip(ctx) is not None  # changes is None by default

    def test_skips_when_empty_polygons(self, make_context):
        step = AnalyzeTerrainStep()
        empty_changes = ChangeDetectionResult(
            ndvi_diff=MagicMock(), change_mask=MagicMock(),
            polygons=[], before_scene_id="b", after_scene_id="a",
            threshold=-0.2, stats={},
        )
        ctx = make_context(skip_terrain=False, dem_source="3dep", changes=empty_changes)
        assert step.should_skip(ctx) is not None

    def test_does_not_skip_when_enabled_with_polygons(self, make_context, changes_with_polygons):
        step = AnalyzeTerrainStep()
        ctx = make_context(skip_terrain=False, dem_source="3dep", changes=changes_with_polygons)
        assert step.should_skip(ctx) is None


class TestExecute:

    @patch("georisk.raster.terrain.load_dem_for_bbox")
    @patch("georisk.raster.terrain.calculate_slope_aspect")
    @patch("georisk.raster.terrain.extract_terrain_stats_for_polygon")
    def test_enriches_polygons(
        self, mock_extract, mock_slope, mock_load,
        make_context, changes_with_polygons,
    ):
        fake_dem = MagicMock()
        mock_load.return_value = fake_dem
        mock_slope.return_value = fake_dem
        mock_extract.return_value = {
            "slope_degree_mean": 25.0,
            "slope_degree_max": 40.0,
            "aspect_degrees": 180.0,
            "elevation_m": 900.0,
        }

        ctx = make_context(
            skip_terrain=False, dem_source="3dep",
            changes=changes_with_polygons,
        )
        step = AnalyzeTerrainStep()
        result = step.execute(ctx)

        assert result.success
        assert ctx.dem_data is fake_dem
        polygon = ctx.changes.polygons[0]
        assert polygon.slope_degree_mean == 25.0
        assert polygon.slope_degree_max == 40.0
        assert polygon.aspect_degrees == 180.0
        assert polygon.elevation_m == 900.0

    @patch("georisk.raster.terrain.load_dem_for_bbox")
    def test_dem_not_found(self, mock_load, make_context, changes_with_polygons):
        mock_load.return_value = None

        ctx = make_context(
            skip_terrain=False, dem_source="3dep",
            changes=changes_with_polygons,
        )
        step = AnalyzeTerrainStep()
        result = step.execute(ctx)

        assert result.success
        assert "Could not load DEM" in result.message
        assert ctx.dem_data is None

    @patch("georisk.raster.terrain.load_dem_for_bbox")
    @patch("georisk.raster.terrain.calculate_slope_aspect")
    @patch("georisk.raster.terrain.extract_terrain_stats_for_polygon")
    def test_stores_dem_data_in_context(
        self, mock_extract, mock_slope, mock_load,
        make_context, changes_with_polygons,
    ):
        fake_dem = MagicMock()
        mock_load.return_value = fake_dem
        mock_slope.return_value = fake_dem
        mock_extract.return_value = {}

        ctx = make_context(
            skip_terrain=False, dem_source="lidar",
            changes=changes_with_polygons,
        )
        step = AnalyzeTerrainStep()
        step.execute(ctx)

        mock_load.assert_called_once_with(ctx.bbox, dem_source="lidar")
        assert ctx.dem_data is fake_dem
