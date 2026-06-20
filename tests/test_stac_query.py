"""Tests for the shared query_stac_collection() function."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cartoload.source.stac.query import query_stac_collection


def _make_asset_finder(href: str = "https://example.com/asset.tif"):
    """Create a simple asset finder that always returns the given href."""
    finder = MagicMock(return_value=href)
    return finder


def _make_stac_response(features: list[dict]) -> MagicMock:
    """Create a mock requests.Response with STAC items."""
    resp = MagicMock()
    resp.json.return_value = {"features": features}
    resp.raise_for_status = MagicMock()
    return resp


def _make_item(
    item_id: str = "item1",
    bbox: list[float] | None = None,
    asset_href: str = "https://example.com/asset.tif",
    asset_type: str = "image/tiff; application=geotiff",
) -> dict:
    """Create a minimal STAC item dict."""
    if bbox is None:
        bbox = [7.0, 46.0, 8.0, 47.0]
    return {
        "id": item_id,
        "bbox": bbox,
        "geometry": {"type": "Polygon"},
        "assets": {
            "data": {"href": asset_href, "type": asset_type},
        },
    }


BBOX = [7.0, 46.0, 8.0, 47.0]


class TestQueryStacCollection:
    """Tests for query_stac_collection."""

    @patch("cartoload.source.stac.query.requests.get")
    def test_basic_query_returns_items(self, mock_get):
        finder = _make_asset_finder()
        items = [_make_item("item1"), _make_item("item2")]
        mock_get.return_value = _make_stac_response(items)

        result = query_stac_collection(
            "https://stac.example.com/collections/test",
            BBOX,
            finder,
        )

        assert len(result) == 2
        assert result[0] == ("item1", "https://example.com/asset.tif", None)
        assert result[1] == ("item2", "https://example.com/asset.tif", None)

    @patch("cartoload.source.stac.query.requests.get")
    def test_empty_features_returns_empty(self, mock_get):
        finder = _make_asset_finder()
        mock_get.return_value = _make_stac_response([])

        result = query_stac_collection(
            "https://stac.example.com/collections/test",
            BBOX,
            finder,
        )

        assert result == []

    @patch("cartoload.source.stac.query.requests.get")
    def test_non_overlapping_items_filtered(self, mock_get):
        finder = _make_asset_finder()
        # item1 overlaps bbox, item2 is far away
        items = [
            _make_item("item1", bbox=[7.0, 46.0, 8.0, 47.0]),
            _make_item("item2", bbox=[20.0, 50.0, 21.0, 51.0]),
        ]
        mock_get.return_value = _make_stac_response(items)

        result = query_stac_collection(
            "https://stac.example.com/collections/test",
            BBOX,
            finder,
        )

        assert len(result) == 1
        assert result[0][0] == "item1"

    @patch("cartoload.source.stac.query.requests.get")
    def test_asset_finder_called_per_item(self, mock_get):
        finder = MagicMock(side_effect=["url1", None, "url3"])
        items = [_make_item("a"), _make_item("b"), _make_item("c")]
        mock_get.return_value = _make_stac_response(items)

        result = query_stac_collection(
            "https://stac.example.com/collections/test",
            BBOX,
            finder,
        )

        assert len(result) == 2
        assert result[0][0] == "a"
        assert result[1][0] == "c"

    @patch("cartoload.source.stac.query.requests.get")
    def test_request_params(self, mock_get):
        finder = _make_asset_finder()
        mock_get.return_value = _make_stac_response([])

        query_stac_collection(
            "https://stac.example.com/collections/test",
            BBOX,
            finder,
        )

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == "https://stac.example.com/collections/test/items"
        assert call_args[1]["params"]["bbox"] == "7.0,46.0,8.0,47.0"
        assert call_args[1]["params"]["limit"] == "500"

    @patch("cartoload.source.stac.query.requests.get")
    def test_request_error_raises(self, mock_get):
        import requests

        finder = _make_asset_finder()
        mock_get.side_effect = requests.RequestException("timeout")

        with pytest.raises(Exception, match="Failed to query STAC items"):
            query_stac_collection(
                "https://stac.example.com/collections/test",
                BBOX,
                finder,
            )

    @patch("cartoload.source.stac.query.requests.get")
    def test_item_without_bbox_included(self, mock_get):
        """Items without bbox are included (no spatial filter applied)."""
        finder = _make_asset_finder()
        item = _make_item("no_bbox")
        del item["bbox"]
        mock_get.return_value = _make_stac_response([item])

        result = query_stac_collection(
            "https://stac.example.com/collections/test",
            BBOX,
            finder,
        )

        assert len(result) == 1
        assert result[0][0] == "no_bbox"

    @patch("cartoload.source.stac.query.requests.get")
    def test_trailing_slash_in_url(self, mock_get):
        finder = _make_asset_finder()
        mock_get.return_value = _make_stac_response([])

        query_stac_collection(
            "https://stac.example.com/collections/test/",
            BBOX,
            finder,
        )

        call_url = mock_get.call_args[0][0]
        assert call_url == "https://stac.example.com/collections/test/items"
