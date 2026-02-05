"""Tests for the landslide detection module."""

import numpy as np
import pytest

from georisk.raster.landslide import (
    LANDSLIDE_SENTINEL_BANDS,
    LANDSLIDE_PATCH_SIZE,
    LandslideResult,
    _normalize_landslide_patch,
    is_landslide_available,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestLandslideConstants:
    """Tests for landslide module constants."""

    def test_sentinel_bands_count(self):
        """Landslide4Sense uses 12 Sentinel-2 bands."""
        assert len(LANDSLIDE_SENTINEL_BANDS) == 12

    def test_b8a_excluded(self):
        """B8A is excluded from Landslide4Sense bands."""
        assert "B8A" not in LANDSLIDE_SENTINEL_BANDS

    def test_b08_included(self):
        """B08 (10m NIR) is included."""
        assert "B08" in LANDSLIDE_SENTINEL_BANDS

    def test_patch_size(self):
        """Landslide4Sense uses 128x128 patches."""
        assert LANDSLIDE_PATCH_SIZE == 128

    def test_bands_are_ordered(self):
        """Bands should be in standard Sentinel-2 order."""
        expected = [
            "B01", "B02", "B03", "B04", "B05", "B06",
            "B07", "B08", "B09", "B10", "B11", "B12",
        ]
        assert LANDSLIDE_SENTINEL_BANDS == expected


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

class TestIsLandslideAvailable:
    """Tests for is_landslide_available()."""

    def test_returns_bool(self):
        """Should always return a boolean."""
        result = is_landslide_available()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

class TestNormalizeLandslidePatch:
    """Tests for _normalize_landslide_patch()."""

    def test_output_shape_matches_input(self):
        """Normalized patch should have the same shape as input."""
        patch = np.random.rand(14, 128, 128).astype(np.float32)
        means = [0.0] * 14
        stds = [1.0] * 14
        result = _normalize_landslide_patch(patch, means, stds)
        assert result.shape == (14, 128, 128)

    def test_normalization_with_known_values(self):
        """(x - mean) / std should produce expected output."""
        patch = np.full((14, 128, 128), 10.0, dtype=np.float32)
        means = [5.0] * 14
        stds = [2.5] * 14
        result = _normalize_landslide_patch(patch, means, stds)
        # (10.0 - 5.0) / 2.5 = 2.0
        np.testing.assert_allclose(result, 2.0, atol=1e-6)

    def test_zero_std_preserves_values(self):
        """Channels with zero std should preserve original values."""
        patch = np.full((14, 128, 128), 7.0, dtype=np.float32)
        means = [0.0] * 14
        stds = [0.0] * 14  # All zero stds
        result = _normalize_landslide_patch(patch, means, stds)
        np.testing.assert_allclose(result, 7.0, atol=1e-6)

    def test_per_channel_normalization(self):
        """Each channel should be normalized independently."""
        patch = np.zeros((14, 128, 128), dtype=np.float32)
        patch[0] = 10.0
        patch[1] = 20.0
        means = [0.0] * 14
        stds = [1.0] * 14
        stds[0] = 5.0
        stds[1] = 10.0
        result = _normalize_landslide_patch(patch, means, stds)
        np.testing.assert_allclose(result[0], 2.0, atol=1e-6)  # 10/5
        np.testing.assert_allclose(result[1], 2.0, atol=1e-6)  # 20/10

    def test_fewer_stats_than_channels(self):
        """If stats have fewer entries than channels, extra channels get zeros."""
        patch = np.ones((14, 128, 128), dtype=np.float32)
        means = [0.0] * 10  # Only 10 values
        stds = [1.0] * 10
        result = _normalize_landslide_patch(patch, means, stds)
        # First 10 channels normalized, rest are zeros
        np.testing.assert_allclose(result[:10], 1.0, atol=1e-6)
        np.testing.assert_allclose(result[10:], 0.0, atol=1e-6)


# ---------------------------------------------------------------------------
# LandslideResult dataclass
# ---------------------------------------------------------------------------

class TestLandslideResult:
    """Tests for LandslideResult dataclass."""

    def test_fields_accessible(self):
        """All expected fields should be accessible."""
        result = LandslideResult(
            is_landslide=True,
            landslide_probability=0.75,
            max_probability=0.92,
            landslide_pixel_fraction=0.35,
            model_version="test-v1",
            confidence_threshold=0.5,
        )
        assert result.is_landslide is True
        assert result.landslide_probability == 0.75
        assert result.max_probability == 0.92
        assert result.landslide_pixel_fraction == 0.35
        assert result.model_version == "test-v1"
        assert result.confidence_threshold == 0.5

    def test_negative_result(self):
        """Non-landslide result should have is_landslide=False."""
        result = LandslideResult(
            is_landslide=False,
            landslide_probability=0.15,
            max_probability=0.3,
            landslide_pixel_fraction=0.05,
            model_version="test-v1",
            confidence_threshold=0.5,
        )
        assert result.is_landslide is False
        assert result.landslide_probability < result.confidence_threshold
