"""Tests for LIDAR point cloud processing module.

These tests verify the lidar module's dataclasses, availability checks,
and fallback behavior without requiring PDAL to be installed.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import xarray as xr

from georisk.raster.lidar import (
    LidarMetadata,
    LidarProducts,
    _get_utm_epsg,
    is_lidar_available,
)


class TestIsLidarAvailable:
    """Verify is_lidar_available works regardless of PDAL installation."""

    def test_returns_bool(self):
        result = is_lidar_available()
        assert isinstance(result, bool)


class TestGetUtmEpsg:
    """Verify UTM zone detection from lon/lat."""

    def test_northern_hemisphere_california(self):
        # Paradise, CA is roughly -121.6, 39.8 → UTM zone 10N
        epsg = _get_utm_epsg(-121.6, 39.8)
        assert epsg == 32610

    def test_northern_hemisphere_new_york(self):
        # New York is roughly -74, 40.7 → UTM zone 18N
        epsg = _get_utm_epsg(-74.0, 40.7)
        assert epsg == 32618

    def test_southern_hemisphere(self):
        # São Paulo is roughly -46.6, -23.5 → UTM zone 23S
        epsg = _get_utm_epsg(-46.6, -23.5)
        assert epsg == 32723


class TestLidarMetadata:
    """Verify LidarMetadata dataclass construction and serialization."""

    def test_construction(self):
        meta = LidarMetadata(
            source_id="test-tile",
            point_count=1_000_000,
            point_density_per_m2=8.5,
            crs_epsg=32610,
            resolution_m=1.0,
            bounds=(-121.7, 39.7, -121.5, 39.9),
            classification_counts={2: 500000, 5: 300000, 6: 200000},
        )
        assert meta.source_id == "test-tile"
        assert meta.point_count == 1_000_000
        assert meta.point_density_per_m2 == 8.5
        assert meta.crs_epsg == 32610

    def test_to_dict_and_back(self):
        meta = LidarMetadata(
            source_id="round-trip",
            point_count=5000,
            point_density_per_m2=2.1,
            crs_epsg=32618,
            resolution_m=2.0,
            bounds=(-74.1, 40.6, -73.9, 40.8),
            classification_counts={2: 3000, 5: 2000},
        )
        d = meta.to_dict()
        restored = LidarMetadata.from_dict(d)
        assert restored.source_id == meta.source_id
        assert restored.point_count == meta.point_count
        assert restored.crs_epsg == meta.crs_epsg
        assert restored.classification_counts == meta.classification_counts

    def test_to_dict_classification_keys_are_strings(self):
        meta = LidarMetadata(
            source_id="x",
            point_count=10,
            point_density_per_m2=1.0,
            crs_epsg=32610,
            resolution_m=1.0,
            bounds=(0, 0, 1, 1),
            classification_counts={2: 5, 6: 5},
        )
        d = meta.to_dict()
        # JSON requires string keys, so verify serialization produces strings
        assert all(isinstance(k, str) for k in d["classification_counts"])

    def test_default_classification_counts(self):
        meta = LidarMetadata(
            source_id="x",
            point_count=0,
            point_density_per_m2=0,
            crs_epsg=32610,
            resolution_m=1.0,
            bounds=(0, 0, 1, 1),
        )
        assert meta.classification_counts == {}


class TestLidarProducts:
    """Verify LidarProducts dataclass with mock xarray DataArrays."""

    def test_construction_with_chm(self):
        dtm = xr.DataArray(np.zeros((10, 10)), dims=["y", "x"])
        dsm = xr.DataArray(np.ones((10, 10)) * 5, dims=["y", "x"])
        chm = xr.DataArray(np.ones((10, 10)) * 5, dims=["y", "x"])
        meta = LidarMetadata(
            source_id="test",
            point_count=100,
            point_density_per_m2=1.0,
            crs_epsg=32610,
            resolution_m=1.0,
            bounds=(0, 0, 1, 1),
        )

        products = LidarProducts(
            dtm=dtm,
            dsm=dsm,
            chm=chm,
            metadata=meta,
            crs="EPSG:32610",
            transform=None,
        )
        assert products.dtm is not None
        assert products.dsm is not None
        assert products.chm is not None
        assert products.metadata.source_id == "test"

    def test_construction_without_chm(self):
        dtm = xr.DataArray(np.zeros((10, 10)), dims=["y", "x"])
        dsm = xr.DataArray(np.ones((10, 10)), dims=["y", "x"])
        meta = LidarMetadata(
            source_id="no-chm",
            point_count=50,
            point_density_per_m2=0.5,
            crs_epsg=32610,
            resolution_m=1.0,
            bounds=(0, 0, 1, 1),
        )

        products = LidarProducts(
            dtm=dtm,
            dsm=dsm,
            chm=None,
            metadata=meta,
            crs="EPSG:32610",
            transform=None,
        )
        assert products.chm is None


class TestLoadLidarDemFallback:
    """Verify _load_lidar_dem falls back to 3DEP when PDAL or data unavailable."""

    @patch("georisk.raster.terrain._load_3dep_dem")
    @patch("georisk.raster.lidar.is_lidar_available", return_value=False)
    def test_fallback_when_pdal_unavailable(self, mock_available, mock_3dep):
        mock_3dep.return_value = None
        from georisk.raster.terrain import _load_lidar_dem

        _load_lidar_dem((-121.7, 39.7, -121.5, 39.9))
        mock_3dep.assert_called_once()

    @patch("georisk.raster.terrain._load_3dep_dem")
    @patch("georisk.raster.lidar.search_lidar_copc", return_value=[])
    @patch("georisk.raster.lidar.is_lidar_available", return_value=True)
    def test_fallback_when_no_copc_data(self, mock_available, mock_search, mock_3dep):
        mock_3dep.return_value = None
        from georisk.raster.terrain import _load_lidar_dem

        _load_lidar_dem((-121.7, 39.7, -121.5, 39.9))
        mock_search.assert_called_once()
        mock_3dep.assert_called_once()


class TestSearchLidarCopc:
    """Verify search_lidar_copc formats results correctly."""

    def test_formats_results(self):
        """Mock pystac_client and planetary_computer at the import level."""
        import planetary_computer
        import pystac_client

        # Build mock STAC item
        mock_item = MagicMock()
        mock_item.id = "test-copc-tile"
        mock_item.bbox = [-121.7, 39.7, -121.5, 39.9]
        mock_item.datetime = None
        mock_item.properties = {
            "pc:count": 1000000,
            "pc:type": "lidar",
            "pc:encoding": "LASzip",
        }
        mock_asset = MagicMock()
        mock_asset.href = "https://example.com/test.copc.laz"
        mock_item.assets = {"data": mock_asset}

        mock_search = MagicMock()
        mock_search.items.return_value = [mock_item]

        mock_catalog = MagicMock()
        mock_catalog.search.return_value = mock_search

        with patch.object(pystac_client.Client, "open", return_value=mock_catalog), \
             patch.object(planetary_computer, "sign_inplace"):
            from georisk.raster.lidar import search_lidar_copc

            results = search_lidar_copc((-121.7, 39.7, -121.5, 39.9))

            assert len(results) == 1
            assert results[0]["id"] == "test-copc-tile"
            assert results[0]["href"] == "https://example.com/test.copc.laz"
            assert results[0]["properties"]["pc:count"] == 1000000
