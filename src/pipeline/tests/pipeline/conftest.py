"""Shared test fixtures for pipeline framework tests."""

from unittest.mock import MagicMock

import pytest

from georisk.pipeline.context import StepContext


@pytest.fixture
def mock_api():
    """Mock ApiClient with common methods."""
    api = MagicMock()
    api.get_aoi.return_value = {"name": "Test AOI", "boundingBox": [-121.6, 39.7, -121.5, 39.8]}
    api.create_change_polygons.return_value = {"successCount": 0, "createdIds": []}
    api.get_assets_geojson.return_value = {"type": "FeatureCollection", "features": []}
    api.create_risk_events.return_value = {"successCount": 0}
    api.update_processing_run.return_value = {}
    return api


@pytest.fixture
def make_context(mock_api):
    """Factory that creates a StepContext with sensible defaults.

    Pass keyword arguments to override any field:
        ctx = make_context(dry_run=True, dem_source="lidar")
    """
    def _make(**overrides):
        defaults = dict(
            aoi_id="test-aoi",
            aoi={"name": "Test AOI", "boundingBox": [-121.6, 39.7, -121.5, 39.8]},
            bbox=(-121.6, 39.7, -121.5, 39.8),
            before_date="2023-01-01",
            after_date="2023-06-01",
            run_id="test-run-001",
            dry_run=False,
            window=30,
            threshold=None,
            min_area=None,
            max_distance=None,
            dem_source="3dep",
            skip_terrain=False,
            skip_landcover=False,
            skip_landslide=False,
            skip_lidar=False,
            api=mock_api,
        )
        defaults.update(overrides)
        return StepContext(**defaults)

    return _make
