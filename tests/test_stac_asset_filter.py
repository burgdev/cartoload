"""Tests for STAC downloader asset_filter functionality."""

from __future__ import annotations

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from cartoload.source.stac.downloader import STACDownloader, _find_geotiff_asset


# ---------------------------------------------------------------------------
# 4.1 Unit tests for _find_geotiff_asset with asset_filter
# ---------------------------------------------------------------------------

# Sample assets mimicking swisstopo STAC items
_SAMPLE_ASSETS = {
    "tile_kgrs_1.25_2056.tif": {
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "href": "https://example.com/kgrs.tif",
        "geoadmin:variant": "kgrs",
        "proj:epsg": 2056,
    },
    "tile_komb_1.25_2056.tif": {
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "href": "https://example.com/komb.tif",
        "geoadmin:variant": "komb",
        "proj:epsg": 2056,
    },
    "tile_krel_1.25_2056.tif": {
        "type": "image/tiff; application=geotiff; profile=cloud-optimized",
        "href": "https://example.com/krel.tif",
        "geoadmin:variant": "krel",
        "proj:epsg": 2056,
    },
}


class TestFindGeotiffAsset:
    """Tests for _find_geotiff_asset with and without asset_filter."""

    def test_no_filter_single_asset_returns_it(self):
        """Without asset_filter and a single GeoTIFF, returns it."""
        assets = {
            "data.tif": {
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "href": "https://example.com/data.tif",
            }
        }
        result = _find_geotiff_asset(assets)
        assert result == "https://example.com/data.tif"

    def test_no_filter_multiple_assets_raises(self):
        """Without asset_filter and multiple GeoTIFFs, raises ValueError."""
        with pytest.raises(ValueError, match="Multiple GeoTIFF assets found"):
            _find_geotiff_asset(_SAMPLE_ASSETS)

    def test_no_filter_no_geotiff_returns_none(self):
        """Without asset_filter and no GeoTIFF assets, returns None."""
        assets = {
            "thumbnail": {
                "type": "image/png",
                "href": "https://example.com/thumb.png",
            }
        }
        assert _find_geotiff_asset(assets) is None

    def test_single_key_filter(self):
        """Filter on a single asset property."""
        result = _find_geotiff_asset(
            _SAMPLE_ASSETS, asset_filter={"geoadmin:variant": "komb"}
        )
        assert result == "https://example.com/komb.tif"

    def test_single_key_filter_grayscale(self):
        """Filter for the grayscale variant."""
        result = _find_geotiff_asset(
            _SAMPLE_ASSETS, asset_filter={"geoadmin:variant": "kgrs"}
        )
        assert result == "https://example.com/kgrs.tif"

    def test_multi_key_filter(self):
        """Filter on multiple properties (AND logic)."""
        result = _find_geotiff_asset(
            _SAMPLE_ASSETS,
            asset_filter={"geoadmin:variant": "komb", "proj:epsg": 2056},
        )
        assert result == "https://example.com/komb.tif"

    def test_multi_key_filter_no_match(self):
        """Filter with conflicting properties returns None."""
        result = _find_geotiff_asset(
            _SAMPLE_ASSETS,
            asset_filter={"geoadmin:variant": "komb", "proj:epsg": 4326},
        )
        assert result is None

    def test_filter_no_match(self):
        """Filter matching no asset returns None."""
        result = _find_geotiff_asset(
            _SAMPLE_ASSETS, asset_filter={"geoadmin:variant": "nonexistent"}
        )
        assert result is None

    def test_filter_unknown_property(self):
        """Filter on a property not present in any asset returns None."""
        result = _find_geotiff_asset(
            _SAMPLE_ASSETS, asset_filter={"custom:prop": "value"}
        )
        assert result is None

    def test_empty_filter_same_as_no_filter_single_asset(self):
        """Empty dict filter behaves like no filter (single asset = ok)."""
        assets = {
            "data.tif": {
                "type": "image/tiff; application=geotiff",
                "href": "https://example.com/data.tif",
            }
        }
        result = _find_geotiff_asset(assets, asset_filter={})
        assert result is not None

    def test_none_filter_same_as_no_filter_single_asset(self):
        """None filter behaves like no filter (single asset = ok)."""
        assets = {
            "data.tif": {
                "type": "image/tiff; application=geotiff",
                "href": "https://example.com/data.tif",
            }
        }
        result = _find_geotiff_asset(assets, asset_filter=None)
        assert result is not None


# ---------------------------------------------------------------------------
# 4.2 Test for query() with asset_filter
# ---------------------------------------------------------------------------


class TestQueryWithAssetFilter:
    """Tests for STACDownloader.query with asset_filter."""

    def _make_stac_response(self, items):
        """Build a STAC /items response dict."""
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "id": item["id"],
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0, 0]},
                    "properties": {},
                    "assets": item["assets"],
                }
                for item in items
            ],
        }

    @patch("cartoload.source.stac.downloader.requests.get")
    def test_query_with_filter_skips_non_matching_items(self, mock_get):
        """Items whose assets don't match the filter are skipped."""
        response_data = self._make_stac_response(
            [
                {
                    "id": "item1",
                    "assets": {
                        "data_kgrs.tif": {
                            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                            "href": "https://example.com/kgrs.tif",
                            "geoadmin:variant": "kgrs",
                        },
                        "data_komb.tif": {
                            "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                            "href": "https://example.com/komb.tif",
                            "geoadmin:variant": "komb",
                        },
                    },
                }
            ]
        )
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_data
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        dl = STACDownloader(tempfile.mkdtemp())
        results = dl.query(
            "https://example.com/collections/test",
            "test",
            [0, 0, 1, 1],
            asset_filter={"geoadmin:variant": "komb"},
        )

        assert len(results) == 1
        assert results[0][0] == "item1"
        assert results[0][1] == "https://example.com/komb.tif"

    @patch("cartoload.source.stac.downloader.requests.get")
    def test_query_with_filter_all_skipped(self, mock_get):
        """When no items match, returns empty list and logs warnings."""
        response_data = self._make_stac_response(
            [
                {
                    "id": "item1",
                    "assets": {
                        "data.tif": {
                            "type": "image/tiff; application=geotiff",
                            "href": "https://example.com/data.tif",
                            "geoadmin:variant": "kgrs",
                        }
                    },
                }
            ]
        )
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_data
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        dl = STACDownloader(tempfile.mkdtemp())
        results = dl.query(
            "https://example.com/collections/test",
            "test",
            [0, 0, 1, 1],
            asset_filter={"geoadmin:variant": "nonexistent"},
        )

        assert results == []

    @patch("cartoload.source.stac.downloader.requests.get")
    def test_query_without_filter_single_asset(self, mock_get):
        """Without filter and a single asset, returns that asset."""
        response_data = self._make_stac_response(
            [
                {
                    "id": "item1",
                    "assets": {
                        "data_kgrs.tif": {
                            "type": "image/tiff; application=geotiff",
                            "href": "https://example.com/kgrs.tif",
                            "geoadmin:variant": "kgrs",
                        },
                    },
                }
            ]
        )
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_data
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        dl = STACDownloader(tempfile.mkdtemp())
        results = dl.query(
            "https://example.com/collections/test",
            "test",
            [0, 0, 1, 1],
        )

        assert len(results) == 1
        assert results[0][1] == "https://example.com/kgrs.tif"

    @patch("cartoload.source.stac.downloader.requests.get")
    def test_query_without_filter_multiple_assets_raises(self, mock_get):
        """Without filter and multiple assets, raises ValueError."""
        response_data = self._make_stac_response(
            [
                {
                    "id": "item1",
                    "assets": {
                        "data_kgrs.tif": {
                            "type": "image/tiff; application=geotiff",
                            "href": "https://example.com/kgrs.tif",
                            "geoadmin:variant": "kgrs",
                        },
                        "data_komb.tif": {
                            "type": "image/tiff; application=geotiff",
                            "href": "https://example.com/komb.tif",
                            "geoadmin:variant": "komb",
                        },
                    },
                }
            ]
        )
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_data
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        dl = STACDownloader(tempfile.mkdtemp())
        with pytest.raises(ValueError, match="Multiple GeoTIFF assets found"):
            dl.query(
                "https://example.com/collections/test",
                "test",
                [0, 0, 1, 1],
            )
