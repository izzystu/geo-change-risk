"""Shared test fixtures for georisk pipeline tests."""

import pytest
from shapely.geometry import Polygon, Point

from georisk.raster.change import ChangePolygon
from georisk.risk.proximity import ProximityResult


@pytest.fixture
def sample_change_polygon():
    """A typical vegetation loss change polygon."""
    return ChangePolygon(
        geometry=Polygon([
            (-121.6, 39.75), (-121.59, 39.75),
            (-121.59, 39.76), (-121.6, 39.76), (-121.6, 39.75)
        ]),
        area_sq_meters=15000,
        ndvi_drop_mean=-0.35,
        ndvi_drop_max=-0.55,
        change_type="VegetationLoss",
        slope_degree_mean=22.0,
        slope_degree_max=35.0,
        aspect_degrees=180.0,
        elevation_m=850.0,
    )


@pytest.fixture
def sample_proximity_result():
    """A proximity result for a nearby critical asset."""
    return ProximityResult(
        asset_id="asset-001",
        asset_name="Test Building",
        asset_type=0,
        asset_type_name="Building",
        criticality=2,
        criticality_name="High",
        distance_meters=250.0,
        asset_geometry=Point(-121.595, 39.755),
        asset_elevation_m=800.0,
        elevation_diff_m=50.0,
        is_upslope=True,
        slope_toward_asset_deg=5.0,
    )
