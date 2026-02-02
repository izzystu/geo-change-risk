"""Tests for land cover classification module constants and utilities.

These tests verify the landcover module's constants and normalization logic
without requiring PyTorch or TorchGeo to be installed.
"""

import numpy as np
import pytest

from georisk.raster.landcover import (
    EUROSAT_BAND_MEANS,
    EUROSAT_BAND_STDS,
    EUROSAT_BANDS,
    EUROSAT_CLASSES,
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

    def test_normalization_stats_length_matches_bands(self):
        assert len(EUROSAT_BAND_MEANS) == len(EUROSAT_BANDS)
        assert len(EUROSAT_BAND_STDS) == len(EUROSAT_BANDS)

    def test_band_stds_are_positive(self):
        """Standard deviations should be positive (used as denominators)."""
        for i, std in enumerate(EUROSAT_BAND_STDS):
            assert std > 0, f"Band {i} ({EUROSAT_BANDS[i]}) has non-positive std: {std}"

    def test_patch_size_is_64(self):
        assert EUROSAT_PATCH_SIZE == 64


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
# Patch normalization
# ---------------------------------------------------------------------------

class TestNormalizePatch:
    """Tests for _normalize_patch which applies per-band z-score normalization."""

    def test_output_shape_matches_input(self):
        patch = np.ones((13, 64, 64), dtype=np.float32) * 1000
        result = _normalize_patch(patch)
        assert result.shape == patch.shape

    def test_zero_input_normalized_to_negative(self):
        """An all-zero input should produce negative values (0 - mean) / std."""
        patch = np.zeros((13, 64, 64), dtype=np.float32)
        result = _normalize_patch(patch)

        for i in range(13):
            expected = -EUROSAT_BAND_MEANS[i] / EUROSAT_BAND_STDS[i]
            np.testing.assert_allclose(result[i], expected, atol=1e-5)

    def test_mean_input_normalized_to_zero(self):
        """When each band equals its mean, normalized value should be ~0."""
        patch = np.zeros((13, 64, 64), dtype=np.float32)
        for i in range(13):
            patch[i] = EUROSAT_BAND_MEANS[i]

        result = _normalize_patch(patch)

        for i in range(13):
            np.testing.assert_allclose(result[i], 0.0, atol=1e-5)

    def test_one_std_above_mean_is_one(self):
        """Input at mean + 1*std should normalize to ~1.0."""
        patch = np.zeros((13, 64, 64), dtype=np.float32)
        for i in range(13):
            patch[i] = EUROSAT_BAND_MEANS[i] + EUROSAT_BAND_STDS[i]

        result = _normalize_patch(patch)

        for i in range(13):
            np.testing.assert_allclose(result[i], 1.0, atol=1e-5)

    def test_fewer_bands_than_stats(self):
        """If patch has fewer bands than stats arrays, only those bands are normalized."""
        patch = np.ones((4, 64, 64), dtype=np.float32) * 1000
        result = _normalize_patch(patch)
        assert result.shape == (4, 64, 64)
        # Should still produce valid normalized values for the first 4 bands
        for i in range(4):
            expected = (1000 - EUROSAT_BAND_MEANS[i]) / EUROSAT_BAND_STDS[i]
            np.testing.assert_allclose(result[i], expected, atol=1e-5)


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

class TestIsLandcoverAvailable:
    """Test the ML availability check function."""

    def test_returns_bool(self):
        """is_landcover_available should always return a boolean."""
        result = is_landcover_available()
        assert isinstance(result, bool)
