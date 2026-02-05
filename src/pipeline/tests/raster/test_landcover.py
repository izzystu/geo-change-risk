"""Tests for land cover classification module constants and utilities.

These tests verify the landcover module's constants and normalization logic
without requiring PyTorch or TorchGeo to be installed.
"""

import numpy as np
import pytest

from georisk.raster.landcover import (
    EUROSAT_BANDS,
    EUROSAT_CLASSES,
    EUROSAT_MODEL_INPUT_SIZE,
    EUROSAT_NORMALIZE_DIVISOR,
    EUROSAT_PATCH_SIZE,
    LANDCOVER_RISK_MULTIPLIERS,
    _normalize_patch,
    is_landcover_available,
)


# ---------------------------------------------------------------------------
# Constants validation
# ---------------------------------------------------------------------------

class TestEurosatConstants:
    """Verify EuroSAT constants are consistent and well-formed."""

    def test_ten_land_cover_classes(self):
        assert len(EUROSAT_CLASSES) == 10

    def test_classes_alphabetically_sorted(self):
        """EuroSAT classes should be in alphabetical order (TorchGeo convention)."""
        assert EUROSAT_CLASSES == sorted(EUROSAT_CLASSES)

    def test_thirteen_sentinel2_bands(self):
        assert len(EUROSAT_BANDS) == 13

    def test_bands_include_key_bands(self):
        """Must include the four 10m Sentinel-2 bands used by NDVI pipeline."""
        for band in ["B02", "B03", "B04", "B08"]:
            assert band in EUROSAT_BANDS

    def test_b8a_is_last_band(self):
        """B8A must be the last band to match TorchGeo EuroSAT ordering."""
        assert EUROSAT_BANDS[-1] == "B8A"

    def test_patch_size_is_64(self):
        assert EUROSAT_PATCH_SIZE == 64

    def test_model_input_size_is_224(self):
        assert EUROSAT_MODEL_INPUT_SIZE == 224

    def test_normalize_divisor_is_10000(self):
        assert EUROSAT_NORMALIZE_DIVISOR == 10_000.0


# ---------------------------------------------------------------------------
# Risk multipliers validation
# ---------------------------------------------------------------------------

class TestLandcoverRiskMultipliers:
    """Verify risk multiplier values are consistent and within bounds."""

    def test_all_classes_have_multipliers(self):
        """Every EuroSAT class should have a risk multiplier."""
        for cls in EUROSAT_CLASSES:
            assert cls in LANDCOVER_RISK_MULTIPLIERS, f"Missing multiplier for {cls}"

    def test_no_extra_multipliers(self):
        """No multiplier keys outside the known EuroSAT classes."""
        for cls in LANDCOVER_RISK_MULTIPLIERS:
            assert cls in EUROSAT_CLASSES, f"Unknown class in multipliers: {cls}"

    def test_multipliers_in_valid_range(self):
        """All multipliers should be between 0 and 1 (inclusive)."""
        for cls, mult in LANDCOVER_RISK_MULTIPLIERS.items():
            assert 0 < mult <= 1.0, f"{cls} multiplier {mult} out of range (0, 1.0]"

    def test_forest_is_baseline(self):
        assert LANDCOVER_RISK_MULTIPLIERS["Forest"] == 1.0

    def test_highway_is_lowest(self):
        min_cls = min(LANDCOVER_RISK_MULTIPLIERS, key=LANDCOVER_RISK_MULTIPLIERS.get)
        assert min_cls == "Highway"
        assert LANDCOVER_RISK_MULTIPLIERS["Highway"] == 0.25


# ---------------------------------------------------------------------------
# Patch normalization (divide-by-10,000)
# ---------------------------------------------------------------------------

class TestNormalizePatch:
    """Tests for _normalize_patch which divides by 10,000."""

    def test_output_shape_matches_input(self):
        patch = np.ones((13, 64, 64), dtype=np.float32) * 1000
        result = _normalize_patch(patch)
        assert result.shape == patch.shape

    def test_output_is_float32(self):
        patch = np.ones((13, 64, 64), dtype=np.uint16) * 1000
        result = _normalize_patch(patch)
        assert result.dtype == np.float32

    def test_typical_reflectance_maps_to_expected_range(self):
        """Typical Sentinel-2 reflectance (500-3000) should map to 0.05-0.30."""
        patch = np.ones((13, 64, 64), dtype=np.float32) * 2000
        result = _normalize_patch(patch)
        np.testing.assert_allclose(result, 0.2, atol=1e-6)

    def test_zero_input_maps_to_zero(self):
        patch = np.zeros((13, 64, 64), dtype=np.float32)
        result = _normalize_patch(patch)
        np.testing.assert_allclose(result, 0.0, atol=1e-6)

    def test_ten_thousand_maps_to_one(self):
        patch = np.ones((13, 64, 64), dtype=np.float32) * 10_000
        result = _normalize_patch(patch)
        np.testing.assert_allclose(result, 1.0, atol=1e-6)

    def test_fewer_bands_still_works(self):
        """Normalization should work with any number of bands."""
        patch = np.ones((4, 64, 64), dtype=np.float32) * 5000
        result = _normalize_patch(patch)
        assert result.shape == (4, 64, 64)
        np.testing.assert_allclose(result, 0.5, atol=1e-6)


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

class TestIsLandcoverAvailable:
    """Test the ML availability check function."""

    def test_returns_bool(self):
        """is_landcover_available should always return a boolean."""
        result = is_landcover_available()
        assert isinstance(result, bool)
