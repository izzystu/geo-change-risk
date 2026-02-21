"""Tests for change detection module, focusing on change classification."""

import pytest

from georisk.raster.change import ChangePolygon, _classify_change

# ---------------------------------------------------------------------------
# _classify_change without land cover context
# ---------------------------------------------------------------------------

class TestClassifyChangeWithoutLandCover:
    """Tests for _classify_change when no land cover class is provided."""

    def test_severe_loss_is_vegetation_loss(self):
        assert _classify_change(-0.5) == "VegetationLoss"

    def test_moderate_loss_is_vegetation_loss(self):
        assert _classify_change(-0.3) == "VegetationLoss"

    def test_gain_is_vegetation_gain(self):
        assert _classify_change(0.3) == "VegetationGain"

    def test_minor_change_is_unknown(self):
        assert _classify_change(-0.1) == "Unknown"

    def test_zero_change_is_unknown(self):
        assert _classify_change(0.0) == "Unknown"

    @pytest.mark.parametrize(
        "ndvi_drop, expected",
        [
            (-0.60, "VegetationLoss"),
            (-0.50, "VegetationLoss"),
            (-0.40, "VegetationLoss"),  # boundary: exactly -0.4 is in -0.4 to -0.2 range
            (-0.35, "VegetationLoss"),
            (-0.20, "Unknown"),          # boundary: exactly -0.2 is NOT < -0.2, falls to Unknown
            (-0.15, "Unknown"),
            (0.0, "Unknown"),
            (0.15, "Unknown"),
            (0.20, "Unknown"),          # boundary: exactly 0.2 is not > 0.2
            (0.25, "VegetationGain"),
        ],
        ids=[
            "severe_-0.60",
            "severe_boundary_-0.50",
            "strong_boundary_-0.40",
            "moderate_-0.35",
            "moderate_boundary_-0.20",
            "mild_-0.15",
            "no_change",
            "mild_gain_0.15",
            "boundary_0.20",
            "gain_0.25",
        ],
    )
    def test_thresholds(self, ndvi_drop, expected):
        assert _classify_change(ndvi_drop) == expected


# ---------------------------------------------------------------------------
# _classify_change with land cover context
# ---------------------------------------------------------------------------

class TestClassifyChangeWithLandCover:
    """Tests for _classify_change when EuroSAT land cover class is provided."""

    # Severe loss (< -0.4)

    def test_severe_forest_is_fire_burn_scar(self):
        assert _classify_change(-0.5, "Forest") == "FireBurnScar"

    def test_severe_annual_crop_is_agricultural(self):
        assert _classify_change(-0.5, "AnnualCrop") == "AgriculturalChange"

    def test_severe_permanent_crop_is_agricultural(self):
        assert _classify_change(-0.5, "PermanentCrop") == "AgriculturalChange"

    def test_severe_residential_is_vegetation_loss(self):
        """Non-forest, non-crop severe loss defaults to VegetationLoss."""
        assert _classify_change(-0.5, "Residential") == "VegetationLoss"

    def test_severe_highway_is_vegetation_loss(self):
        assert _classify_change(-0.5, "Highway") == "VegetationLoss"

    # Moderate loss (-0.2 to -0.4)

    def test_moderate_annual_crop_is_agricultural(self):
        assert _classify_change(-0.3, "AnnualCrop") == "AgriculturalChange"

    def test_moderate_permanent_crop_is_agricultural(self):
        assert _classify_change(-0.3, "PermanentCrop") == "AgriculturalChange"

    def test_moderate_herbaceous_is_drought(self):
        assert _classify_change(-0.3, "HerbaceousVegetation") == "DroughtStress"

    def test_moderate_pasture_is_drought(self):
        assert _classify_change(-0.3, "Pasture") == "DroughtStress"

    def test_moderate_forest_is_vegetation_loss(self):
        """Forest with moderate (not severe) loss is still VegetationLoss."""
        assert _classify_change(-0.3, "Forest") == "VegetationLoss"

    def test_moderate_residential_is_vegetation_loss(self):
        assert _classify_change(-0.3, "Residential") == "VegetationLoss"

    # Gain and minor change are unaffected by land cover

    def test_gain_with_forest_is_still_vegetation_gain(self):
        assert _classify_change(0.3, "Forest") == "VegetationGain"

    def test_minor_with_forest_is_still_unknown(self):
        assert _classify_change(-0.1, "Forest") == "Unknown"

    def test_minor_with_crop_is_still_unknown(self):
        assert _classify_change(-0.1, "AnnualCrop") == "Unknown"


# ---------------------------------------------------------------------------
# change_type_map consistency
# ---------------------------------------------------------------------------

class TestChangeTypeMap:
    """Tests for ChangePolygon.to_dict() change_type_map values."""

    def _get_change_type_map(self):
        """Extract the change_type_map from a ChangePolygon instance."""
        from shapely.geometry import box
        ChangePolygon(
            geometry=box(0, 0, 1, 1),
            area_sq_meters=100.0,
            ndvi_drop_mean=-0.3,
            ndvi_drop_max=-0.5,
        )
        # Build the map the same way to_dict does
        return {
            "Unknown": 0,
            "VegetationLoss": 1,
            "VegetationGain": 2,
            "FireBurnScar": 3,
            "DroughtStress": 4,
            "AgriculturalChange": 5,
            "LandslideDebris": 6,
        }

    def test_values_are_sequential_0_to_6(self):
        """Map values should be sequential integers 0 through 6."""
        from shapely.geometry import box
        cp = ChangePolygon(
            geometry=box(0, 0, 1, 1),
            area_sq_meters=100.0,
            ndvi_drop_mean=-0.3,
            ndvi_drop_max=-0.5,
            change_type="Unknown",
        )
        d = cp.to_dict()
        assert d["changeType"] == 0

        # Verify each expected mapping via to_dict
        expected = {
            "Unknown": 0,
            "VegetationLoss": 1,
            "VegetationGain": 2,
            "FireBurnScar": 3,
            "DroughtStress": 4,
            "AgriculturalChange": 5,
            "LandslideDebris": 6,
        }
        for name, value in expected.items():
            cp.change_type = name
            d = cp.to_dict()
            assert d["changeType"] == value, f"{name} should map to {value}"

        assert sorted(expected.values()) == list(range(7))

    def test_classify_change_returns_exist_in_map(self):
        """Every value _classify_change can return must exist in change_type_map."""
        valid_types = {"Unknown", "VegetationLoss", "VegetationGain",
                       "FireBurnScar", "DroughtStress", "AgriculturalChange",
                       "LandslideDebris"}

        # Test a broad range of inputs and land cover classes
        test_cases = [
            (-0.6, None), (-0.5, "Forest"), (-0.5, "AnnualCrop"),
            (-0.5, "PermanentCrop"), (-0.5, "Residential"),
            (-0.3, None), (-0.3, "AnnualCrop"), (-0.3, "HerbaceousVegetation"),
            (-0.3, "Pasture"), (-0.1, None), (0.0, None), (0.3, None),
        ]
        for ndvi_drop, land_cover in test_cases:
            result = _classify_change(ndvi_drop, land_cover)
            assert result in valid_types, (
                f"_classify_change({ndvi_drop}, {land_cover!r}) returned "
                f"{result!r} which is not in the map"
            )

    def test_landslide_debris_maps_to_6(self):
        """LandslideDebris should map to integer 6."""
        from shapely.geometry import box
        cp = ChangePolygon(
            geometry=box(0, 0, 1, 1),
            area_sq_meters=100.0,
            ndvi_drop_mean=-0.3,
            ndvi_drop_max=-0.5,
            change_type="LandslideDebris",
        )
        d = cp.to_dict()
        assert d["changeType"] == 6

    def test_removed_types_absent(self):
        """UrbanExpansion, WaterChange, VegetationClearing must not be in the map."""
        from shapely.geometry import box
        cp = ChangePolygon(
            geometry=box(0, 0, 1, 1),
            area_sq_meters=100.0,
            ndvi_drop_mean=-0.3,
            ndvi_drop_max=-0.5,
        )
        for removed_type in ("UrbanExpansion", "WaterChange", "VegetationClearing"):
            cp.change_type = removed_type
            d = cp.to_dict()
            # Unknown types fall back to 0 (Unknown)
            assert d["changeType"] == 0, (
                f"Removed type {removed_type!r} should fall back to 0 (Unknown)"
            )
