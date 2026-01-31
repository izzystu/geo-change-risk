"""Unit tests for the NDVI calculation module."""

import numpy as np
import pytest
import rioxarray  # noqa: F401 - needed for .rio accessor on DataArrays
import xarray as xr

from georisk.raster.ndvi import NdviResult, calculate_ndvi


def make_band(values: np.ndarray) -> xr.DataArray:
    """Create a test band DataArray with CRS and transform metadata.

    Args:
        values: 2D numpy array of band values.

    Returns:
        xr.DataArray with spatial dims, CRS (EPSG:4326), and affine transform.
    """
    rows, cols = values.shape
    da = xr.DataArray(
        values,
        dims=["y", "x"],
        coords={
            "y": np.arange(rows, dtype=float),
            "x": np.arange(cols, dtype=float),
        },
    )
    da = da.rio.write_crs("EPSG:4326")
    da = da.rio.write_transform()
    return da


# ---------------------------------------------------------------------------
# 1. Basic NDVI calculation - healthy vegetation
# ---------------------------------------------------------------------------

class TestBasicNdviCalculation:
    """Verify correct NDVI for uniform healthy-vegetation pixels."""

    def test_healthy_vegetation_constant_bands(self):
        """Red=100, NIR=400 should yield NDVI=0.6 everywhere."""
        red = make_band(np.full((3, 3), 100, dtype=np.float32))
        nir = make_band(np.full((3, 3), 400, dtype=np.float32))

        result = calculate_ndvi(red, nir)

        expected_ndvi = (400 - 100) / (400 + 100)  # 0.6
        np.testing.assert_allclose(result.data.values, expected_ndvi, atol=1e-6)

    def test_returns_ndvi_result_dataclass(self):
        """calculate_ndvi must return an NdviResult instance."""
        red = make_band(np.full((3, 3), 100, dtype=np.float32))
        nir = make_band(np.full((3, 3), 400, dtype=np.float32))

        result = calculate_ndvi(red, nir)

        assert isinstance(result, NdviResult)

    def test_output_shape_matches_input(self):
        """Output NDVI array shape must match the input band shape."""
        red = make_band(np.full((5, 7), 100, dtype=np.float32))
        nir = make_band(np.full((5, 7), 400, dtype=np.float32))

        result = calculate_ndvi(red, nir)

        assert result.data.shape == (5, 7)


# ---------------------------------------------------------------------------
# 2. Bare soil / low vegetation
# ---------------------------------------------------------------------------

class TestBareSoilLowVegetation:
    """Verify low positive NDVI for bare soil or sparse vegetation."""

    def test_bare_soil_ndvi(self):
        """Red=300, NIR=350 should yield NDVI~0.077."""
        red = make_band(np.full((3, 3), 300, dtype=np.float32))
        nir = make_band(np.full((3, 3), 350, dtype=np.float32))

        result = calculate_ndvi(red, nir)

        expected = (350 - 300) / (350 + 300)  # ~0.07692
        np.testing.assert_allclose(result.data.values, expected, atol=1e-5)

    def test_bare_soil_ndvi_is_low_positive(self):
        """Bare soil NDVI should be small and positive."""
        red = make_band(np.full((3, 3), 300, dtype=np.float32))
        nir = make_band(np.full((3, 3), 350, dtype=np.float32))

        result = calculate_ndvi(red, nir)

        assert (result.data.values > 0).all()
        assert (result.data.values < 0.2).all()


# ---------------------------------------------------------------------------
# 3. Water body (negative NDVI)
# ---------------------------------------------------------------------------

class TestWaterBody:
    """Verify negative NDVI when red reflectance exceeds NIR."""

    def test_water_negative_ndvi(self):
        """Red=500, NIR=200 should yield NDVI ~ -0.4286."""
        red = make_band(np.full((3, 3), 500, dtype=np.float32))
        nir = make_band(np.full((3, 3), 200, dtype=np.float32))

        result = calculate_ndvi(red, nir)

        expected = (200 - 500) / (200 + 500)  # ~-0.42857
        np.testing.assert_allclose(result.data.values, expected, atol=1e-5)

    def test_water_ndvi_is_negative(self):
        """All water pixels should have strictly negative NDVI."""
        red = make_band(np.full((3, 3), 500, dtype=np.float32))
        nir = make_band(np.full((3, 3), 200, dtype=np.float32))

        result = calculate_ndvi(red, nir)

        assert (result.data.values < 0).all()


# ---------------------------------------------------------------------------
# 4. Division by zero handling
# ---------------------------------------------------------------------------

class TestDivisionByZero:
    """Both bands zero means denominator=0; should produce nodata_value."""

    def test_both_bands_zero_default_nodata(self):
        """When red=0 and NIR=0, result should be nodata_value (default 0)."""
        red = make_band(np.zeros((3, 3), dtype=np.float32))
        nir = make_band(np.zeros((3, 3), dtype=np.float32))

        result = calculate_ndvi(red, nir)

        np.testing.assert_array_equal(result.data.values, 0.0)

    def test_both_bands_zero_custom_nodata(self):
        """When red=0 and NIR=0 with custom nodata=-9999, result should be -1.

        Note: The function clips to [-1, 1] after assigning nodata_value.
        A nodata_value of -9999 gets clipped to -1.
        """
        red = make_band(np.zeros((3, 3), dtype=np.float32))
        nir = make_band(np.zeros((3, 3), dtype=np.float32))

        result = calculate_ndvi(red, nir, nodata_value=-9999)

        # -9999 is clipped to -1 by the clip operation
        np.testing.assert_array_equal(result.data.values, -1.0)


# ---------------------------------------------------------------------------
# 5. Mixed pixel values
# ---------------------------------------------------------------------------

class TestMixedPixelValues:
    """Array mixing vegetation, water, and bare soil pixels."""

    def test_mixed_pixels_correct_ranges(self):
        """Verify each pixel type falls within its expected NDVI range."""
        # Row 0: vegetation (high NIR, low Red)
        # Row 1: water (high Red, low NIR)
        # Row 2: bare soil (similar Red & NIR)
        red_vals = np.array(
            [[100, 100, 100],
             [500, 500, 500],
             [300, 300, 300]],
            dtype=np.float32,
        )
        nir_vals = np.array(
            [[400, 400, 400],
             [200, 200, 200],
             [350, 350, 350]],
            dtype=np.float32,
        )
        red = make_band(red_vals)
        nir = make_band(nir_vals)

        result = calculate_ndvi(red, nir)
        data = result.data.values

        # Vegetation row: NDVI should be > 0.3
        assert (data[0, :] > 0.3).all(), f"Vegetation NDVI too low: {data[0, :]}"

        # Water row: NDVI should be < 0
        assert (data[1, :] < 0).all(), f"Water NDVI should be negative: {data[1, :]}"

        # Bare soil row: NDVI should be small positive (0 < NDVI < 0.2)
        assert (data[2, :] > 0).all(), f"Bare soil NDVI should be positive: {data[2, :]}"
        assert (data[2, :] < 0.2).all(), f"Bare soil NDVI too high: {data[2, :]}"

    def test_mixed_pixels_exact_values(self):
        """Verify exact NDVI values for each pixel in a mixed scene."""
        red_vals = np.array(
            [[100, 500],
             [300, 0]],
            dtype=np.float32,
        )
        nir_vals = np.array(
            [[400, 200],
             [350, 0]],
            dtype=np.float32,
        )
        red = make_band(red_vals)
        nir = make_band(nir_vals)

        result = calculate_ndvi(red, nir)
        data = result.data.values

        expected_veg = (400 - 100) / (400 + 100)      # 0.6
        expected_water = (200 - 500) / (200 + 500)     # ~-0.4286
        expected_bare = (350 - 300) / (350 + 300)      # ~0.0769
        expected_nodata = 0.0                           # both zero -> nodata

        np.testing.assert_allclose(data[0, 0], expected_veg, atol=1e-5)
        np.testing.assert_allclose(data[0, 1], expected_water, atol=1e-5)
        np.testing.assert_allclose(data[1, 0], expected_bare, atol=1e-5)
        np.testing.assert_allclose(data[1, 1], expected_nodata, atol=1e-5)


# ---------------------------------------------------------------------------
# 6. NDVI clipping to [-1, 1]
# ---------------------------------------------------------------------------

class TestNdviClipping:
    """Verify NDVI values are clipped to the valid [-1, 1] range."""

    def test_max_ndvi_is_one(self):
        """Red=0, NIR=1000 yields NDVI = 1.0 exactly (maximum possible)."""
        red = make_band(np.full((3, 3), 0, dtype=np.float32))
        nir = make_band(np.full((3, 3), 1000, dtype=np.float32))

        result = calculate_ndvi(red, nir, nodata_value=-999)

        # When red=0, denom=NIR only, so: (NIR-0)/NIR = 1.0
        np.testing.assert_allclose(result.data.values, 1.0, atol=1e-6)

    def test_min_ndvi_is_negative_one(self):
        """Red=1000, NIR=0 yields NDVI = -1.0 exactly (minimum possible)."""
        red = make_band(np.full((3, 3), 1000, dtype=np.float32))
        nir = make_band(np.full((3, 3), 0, dtype=np.float32))

        result = calculate_ndvi(red, nir, nodata_value=-999)

        # (0-1000)/1000 = -1.0
        np.testing.assert_allclose(result.data.values, -1.0, atol=1e-6)

    def test_all_ndvi_within_bounds(self):
        """NDVI values must always fall within [-1, 1] for any input."""
        rng = np.random.default_rng(42)
        red_vals = rng.integers(0, 10000, size=(10, 10)).astype(np.float32)
        nir_vals = rng.integers(0, 10000, size=(10, 10)).astype(np.float32)

        red = make_band(red_vals)
        nir = make_band(nir_vals)

        result = calculate_ndvi(red, nir)

        assert (result.data.values >= -1.0).all()
        assert (result.data.values <= 1.0).all()


# ---------------------------------------------------------------------------
# 7. Result metadata
# ---------------------------------------------------------------------------

class TestResultMetadata:
    """Verify that scene_id, datetime, stats, and CRS propagate correctly."""

    def test_scene_id_passed_through(self):
        """scene_id in result should match what was passed to calculate_ndvi."""
        red = make_band(np.full((3, 3), 100, dtype=np.float32))
        nir = make_band(np.full((3, 3), 400, dtype=np.float32))

        result = calculate_ndvi(red, nir, scene_id="S2A_20240101")

        assert result.scene_id == "S2A_20240101"

    def test_datetime_passed_through(self):
        """datetime in result should match datetime_str argument."""
        red = make_band(np.full((3, 3), 100, dtype=np.float32))
        nir = make_band(np.full((3, 3), 400, dtype=np.float32))

        result = calculate_ndvi(
            red, nir, datetime_str="2024-01-15T10:30:00Z",
        )

        assert result.datetime == "2024-01-15T10:30:00Z"

    def test_default_scene_id_and_datetime(self):
        """Default scene_id should be 'unknown' and datetime empty string."""
        red = make_band(np.full((3, 3), 100, dtype=np.float32))
        nir = make_band(np.full((3, 3), 400, dtype=np.float32))

        result = calculate_ndvi(red, nir)

        assert result.scene_id == "unknown"
        assert result.datetime == ""

    def test_statistics_for_uniform_array(self):
        """For uniform input, min == max == mean."""
        red = make_band(np.full((3, 3), 100, dtype=np.float32))
        nir = make_band(np.full((3, 3), 400, dtype=np.float32))

        result = calculate_ndvi(red, nir)

        expected = (400 - 100) / (400 + 100)  # 0.6
        assert abs(result.min_value - expected) < 1e-5
        assert abs(result.max_value - expected) < 1e-5
        assert abs(result.mean_value - expected) < 1e-5

    def test_statistics_for_mixed_array(self):
        """min_value, max_value, mean_value should reflect valid pixel stats."""
        red_vals = np.array(
            [[100, 500],
             [300, 100]],
            dtype=np.float32,
        )
        nir_vals = np.array(
            [[400, 200],
             [350, 400]],
            dtype=np.float32,
        )
        red = make_band(red_vals)
        nir = make_band(nir_vals)

        result = calculate_ndvi(red, nir)

        veg = (400 - 100) / (400 + 100)        # 0.6
        water = (200 - 500) / (200 + 500)       # ~-0.4286
        bare = (350 - 300) / (350 + 300)         # ~0.0769

        # All four pixels are valid (nonzero denom), none equal nodata_value=0
        # Minimum should be the water pixel
        assert abs(result.min_value - water) < 1e-4
        # Maximum should be one of the vegetation pixels
        assert abs(result.max_value - veg) < 1e-4
        # Mean of four values
        expected_mean = (veg + water + bare + veg) / 4
        assert abs(result.mean_value - expected_mean) < 1e-4

    def test_crs_preserved(self):
        """CRS in the result should match the input band CRS (EPSG:4326)."""
        red = make_band(np.full((3, 3), 100, dtype=np.float32))
        nir = make_band(np.full((3, 3), 400, dtype=np.float32))

        result = calculate_ndvi(red, nir)

        assert result.crs is not None
        # rioxarray stores CRS as a pyproj.CRS or rasterio.crs.CRS
        assert "4326" in str(result.crs)

    def test_crs_preserved_in_data_array(self):
        """The output DataArray itself should carry the same CRS."""
        red = make_band(np.full((3, 3), 100, dtype=np.float32))
        nir = make_band(np.full((3, 3), 400, dtype=np.float32))

        result = calculate_ndvi(red, nir)

        assert result.data.rio.crs is not None
        assert "4326" in str(result.data.rio.crs)

    def test_transform_preserved(self):
        """The affine transform should be propagated from the input band."""
        red = make_band(np.full((3, 3), 100, dtype=np.float32))
        nir = make_band(np.full((3, 3), 400, dtype=np.float32))

        result = calculate_ndvi(red, nir)

        assert result.transform is not None


# ---------------------------------------------------------------------------
# 8. Nodata value propagation
# ---------------------------------------------------------------------------

class TestNodataValuePropagation:
    """Verify custom nodata_value is used for invalid pixels."""

    @pytest.mark.parametrize(
        "nodata_value, expected_clipped",
        [
            (0, 0.0),        # default: 0 is within [-1,1], no clip
            (-1, -1.0),      # -1 is the clip boundary
            (0.5, 0.5),      # arbitrary value within range
        ],
        ids=["default-zero", "negative-one", "mid-range"],
    )
    def test_nodata_within_clip_range(self, nodata_value, expected_clipped):
        """Nodata values within [-1,1] should appear unchanged in output."""
        red = make_band(np.zeros((2, 2), dtype=np.float32))
        nir = make_band(np.zeros((2, 2), dtype=np.float32))

        result = calculate_ndvi(red, nir, nodata_value=nodata_value)

        np.testing.assert_array_equal(result.data.values, expected_clipped)

    @pytest.mark.parametrize(
        "nodata_value, expected_clipped",
        [
            (-9999, -1.0),    # gets clipped to -1
            (9999, 1.0),      # gets clipped to +1
            (-5.0, -1.0),     # gets clipped to -1
        ],
        ids=["large-negative", "large-positive", "moderate-negative"],
    )
    def test_nodata_outside_clip_range(self, nodata_value, expected_clipped):
        """Nodata values outside [-1,1] are clipped by the clip operation."""
        red = make_band(np.zeros((2, 2), dtype=np.float32))
        nir = make_band(np.zeros((2, 2), dtype=np.float32))

        result = calculate_ndvi(red, nir, nodata_value=nodata_value)

        np.testing.assert_array_equal(result.data.values, expected_clipped)

    def test_nodata_only_at_zero_denominator(self):
        """Nodata should only appear where both bands are zero (denom=0)."""
        red_vals = np.array(
            [[100, 0],
             [0, 200]],
            dtype=np.float32,
        )
        nir_vals = np.array(
            [[400, 0],
             [500, 100]],
            dtype=np.float32,
        )
        red = make_band(red_vals)
        nir = make_band(nir_vals)

        result = calculate_ndvi(red, nir, nodata_value=0.0)
        data = result.data.values

        # (0,0): valid pixel
        assert data[0, 0] != 0.0 or abs(data[0, 0] - 0.6) < 1e-5
        # (0,1): both zero -> nodata=0.0
        assert data[0, 1] == 0.0
        # (1,0): NIR=500, Red=0 -> valid (1.0)
        np.testing.assert_allclose(data[1, 0], 1.0, atol=1e-5)
        # (1,1): valid pixel
        expected = (100 - 200) / (100 + 200)
        np.testing.assert_allclose(data[1, 1], expected, atol=1e-5)


# ---------------------------------------------------------------------------
# 9. Statistics exclude nodata
# ---------------------------------------------------------------------------

class TestStatisticsExcludeNodata:
    """Verify that min/max/mean statistics ignore nodata pixels."""

    def test_stats_exclude_zero_nodata_pixels(self):
        """Stats should exclude pixels where denominator was zero (nodata=0)."""
        # Build a 2x2 array: 3 valid pixels + 1 nodata pixel
        red_vals = np.array(
            [[100, 0],
             [500, 100]],
            dtype=np.float32,
        )
        nir_vals = np.array(
            [[400, 0],
             [200, 400]],
            dtype=np.float32,
        )
        red = make_band(red_vals)
        nir = make_band(nir_vals)

        result = calculate_ndvi(red, nir, nodata_value=0.0)

        # Valid pixels:
        veg1 = (400 - 100) / (400 + 100)        # 0.6
        water = (200 - 500) / (200 + 500)         # ~-0.4286
        veg2 = (400 - 100) / (400 + 100)          # 0.6
        # Nodata pixel at (0,1): excluded from stats

        assert abs(result.min_value - water) < 1e-4
        assert abs(result.max_value - veg1) < 1e-4
        expected_mean = (veg1 + water + veg2) / 3
        assert abs(result.mean_value - expected_mean) < 1e-4

    def test_all_nodata_returns_defaults(self):
        """When all pixels are nodata, use default stats: min=-1, max=1, mean=0."""
        red = make_band(np.zeros((3, 3), dtype=np.float32))
        nir = make_band(np.zeros((3, 3), dtype=np.float32))

        result = calculate_ndvi(red, nir, nodata_value=0.0)

        assert result.min_value == -1
        assert result.max_value == 1
        assert result.mean_value == 0

    def test_stats_with_custom_nodata_within_range(self):
        """When nodata_value is within [-1,1], stats should still exclude it.

        Note: The implementation excludes pixels whose value equals nodata_value.
        With nodata_value=0.5, any pixel that genuinely computes to 0.5 would
        also be excluded. This test uses inputs that avoid that ambiguity.
        """
        # Build array where one pixel has zero denominator.
        # Use nodata_value=0.5 which won't collide with other NDVI values.
        red_vals = np.array(
            [[100, 0],
             [0, 200]],
            dtype=np.float32,
        )
        nir_vals = np.array(
            [[400, 0],
             [1000, 300]],
            dtype=np.float32,
        )
        red = make_band(red_vals)
        nir = make_band(nir_vals)

        result = calculate_ndvi(red, nir, nodata_value=0.5)

        # Valid pixels:
        p00 = (400 - 100) / (400 + 100)   # 0.6
        p10 = (1000 - 0) / (1000 + 0)     # 1.0
        p11 = (300 - 200) / (300 + 200)   # 0.2

        # Nodata pixel at (0,1): both zero -> nodata_value=0.5
        # 0.5 is within [-1,1] so no clipping. Stats exclude this pixel.

        assert abs(result.min_value - 0.2) < 1e-4
        assert abs(result.max_value - 1.0) < 1e-4
        expected_mean = (p00 + p10 + p11) / 3
        assert abs(result.mean_value - expected_mean) < 1e-4

    def test_single_valid_pixel(self):
        """When only one pixel is valid, stats should reflect that pixel alone."""
        # 2x2 array: only one non-zero denominator pixel
        red_vals = np.array(
            [[0, 0],
             [0, 100]],
            dtype=np.float32,
        )
        nir_vals = np.array(
            [[0, 0],
             [0, 400]],
            dtype=np.float32,
        )
        red = make_band(red_vals)
        nir = make_band(nir_vals)

        result = calculate_ndvi(red, nir, nodata_value=0.0)

        expected = (400 - 100) / (400 + 100)  # 0.6
        assert abs(result.min_value - expected) < 1e-5
        assert abs(result.max_value - expected) < 1e-5
        assert abs(result.mean_value - expected) < 1e-5


# ---------------------------------------------------------------------------
# Parametrized edge case tests
# ---------------------------------------------------------------------------

class TestParametrizedCases:
    """Parametrized tests for various band combinations."""

    @pytest.mark.parametrize(
        "red_val, nir_val, expected_ndvi",
        [
            (100, 400, 0.6),                            # healthy vegetation
            (300, 350, 50.0 / 650.0),                   # bare soil
            (500, 200, -300.0 / 700.0),                 # water
            (250, 250, 0.0),                             # equal bands
            (1, 9999, (9999 - 1) / (9999 + 1)),         # extreme vegetation
            (9999, 1, (1 - 9999) / (1 + 9999)),         # extreme water
        ],
        ids=[
            "healthy-vegetation",
            "bare-soil",
            "water",
            "equal-bands",
            "extreme-high-nir",
            "extreme-high-red",
        ],
    )
    def test_ndvi_formula(self, red_val, nir_val, expected_ndvi):
        """Verify NDVI formula for various band value combinations."""
        red = make_band(np.full((2, 2), red_val, dtype=np.float32))
        nir = make_band(np.full((2, 2), nir_val, dtype=np.float32))

        # Use a nodata that won't collide with expected values
        result = calculate_ndvi(red, nir, nodata_value=-999)
        data = result.data.values

        # Clip expected to [-1, 1] to match the function behavior
        clipped_expected = np.clip(expected_ndvi, -1, 1)
        np.testing.assert_allclose(data, clipped_expected, atol=1e-4)

    @pytest.mark.parametrize(
        "scene_id, datetime_str",
        [
            ("S2A_20240101", "2024-01-01T00:00:00Z"),
            ("LC08_20230615", "2023-06-15T12:00:00Z"),
            ("", ""),
        ],
        ids=["sentinel-2", "landsat-8", "empty-strings"],
    )
    def test_metadata_passthrough(self, scene_id, datetime_str):
        """scene_id and datetime should be stored exactly as provided."""
        red = make_band(np.full((2, 2), 100, dtype=np.float32))
        nir = make_band(np.full((2, 2), 400, dtype=np.float32))

        result = calculate_ndvi(
            red, nir, scene_id=scene_id, datetime_str=datetime_str,
        )

        assert result.scene_id == scene_id
        assert result.datetime == datetime_str
