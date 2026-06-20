"""Tests for STAC ETag freshness checking and metadata writing."""

from __future__ import annotations

import json
import tempfile
from unittest.mock import MagicMock, patch

from cartoload.source.stac.downloader import STACDownloader


class TestCheckFreshness:
    """Tests for STACDownloader._check_freshness."""

    def setup_method(self):
        self.dl = STACDownloader(tempfile.mkdtemp())

    def test_no_metadata_returns_none(self, tmp_path):
        """No .json metadata file returns None (can't determine freshness)."""
        cache_path = tmp_path / "item1.tif"
        cache_path.write_bytes(b"fake")

        result = self.dl._check_freshness("https://example.com/item1.tif", cache_path)
        assert result is None

    def test_etag_match_returns_true(self, tmp_path):
        """ETag match returns True (fresh)."""
        cache_path = tmp_path / "item1.tif"
        cache_path.write_bytes(b"fake")
        meta_path = tmp_path / "item1.json"
        meta_path.write_text(json.dumps({"etag": '"abc123"'}))

        with patch("cartoload.source.stac.downloader.requests.head") as mock_head:
            mock_head.return_value = MagicMock(
                status_code=200, ok=True, headers={"ETag": '"abc123"'}
            )
            result = self.dl._check_freshness(
                "https://example.com/item1.tif", cache_path
            )

        assert result is True

    def test_etag_mismatch_returns_false(self, tmp_path):
        """ETag mismatch returns False (stale)."""
        cache_path = tmp_path / "item1.tif"
        cache_path.write_bytes(b"fake")
        meta_path = tmp_path / "item1.json"
        meta_path.write_text(json.dumps({"etag": '"old"'}))

        with patch("cartoload.source.stac.downloader.requests.head") as mock_head:
            mock_head.return_value = MagicMock(
                status_code=200, ok=True, headers={"ETag": '"new"'}
            )
            result = self.dl._check_freshness(
                "https://example.com/item1.tif", cache_path
            )

        assert result is False

    def test_last_modified_match_returns_true(self, tmp_path):
        """Last-Modified match returns True when no ETag."""
        cache_path = tmp_path / "item1.tif"
        cache_path.write_bytes(b"fake")
        meta_path = tmp_path / "item1.json"
        meta_path.write_text(
            json.dumps({"last_modified": "Wed, 01 Jan 2025 00:00:00 GMT"})
        )

        with patch("cartoload.source.stac.downloader.requests.head") as mock_head:
            mock_head.return_value = MagicMock(
                status_code=200,
                ok=True,
                headers={"Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT"},
            )
            result = self.dl._check_freshness(
                "https://example.com/item1.tif", cache_path
            )

        assert result is True

    def test_head_405_returns_none(self, tmp_path):
        """HTTP 405 (HEAD not supported) returns None (fall back)."""
        cache_path = tmp_path / "item1.tif"
        cache_path.write_bytes(b"fake")
        meta_path = tmp_path / "item1.json"
        meta_path.write_text(json.dumps({"etag": '"abc"'}))

        with patch("cartoload.source.stac.downloader.requests.head") as mock_head:
            mock_head.return_value = MagicMock(status_code=405, ok=False)
            result = self.dl._check_freshness(
                "https://example.com/item1.tif", cache_path
            )

        assert result is None

    def test_head_exception_returns_none(self, tmp_path):
        """Network error on HEAD returns None (fall back)."""
        import requests

        cache_path = tmp_path / "item1.tif"
        cache_path.write_bytes(b"fake")
        meta_path = tmp_path / "item1.json"
        meta_path.write_text(json.dumps({"etag": '"abc"'}))

        with patch("cartoload.source.stac.downloader.requests.head") as mock_head:
            mock_head.side_effect = requests.RequestException("timeout")
            result = self.dl._check_freshness(
                "https://example.com/item1.tif", cache_path
            )

        assert result is None

    def test_no_comparable_headers_returns_none(self, tmp_path):
        """No ETag or Last-Modified from server returns None."""
        cache_path = tmp_path / "item1.tif"
        cache_path.write_bytes(b"fake")
        meta_path = tmp_path / "item1.json"
        meta_path.write_text(json.dumps({"etag": '"abc"'}))

        with patch("cartoload.source.stac.downloader.requests.head") as mock_head:
            mock_head.return_value = MagicMock(status_code=200, ok=True, headers={})
            result = self.dl._check_freshness(
                "https://example.com/item1.tif", cache_path
            )

        assert result is None


class TestWriteMetadata:
    """Tests for STACDownloader._write_metadata."""

    def setup_method(self):
        self.dl = STACDownloader(tempfile.mkdtemp())

    def test_writes_json_with_etag(self, tmp_path):
        """Metadata JSON is written with ETag from HEAD response."""
        cache_path = tmp_path / "item1.tif"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(b"fake")

        with patch("cartoload.source.stac.downloader.requests.head") as mock_head:
            mock_head.return_value = MagicMock(
                status_code=200,
                ok=True,
                headers={
                    "ETag": '"abc123"',
                    "Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT",
                },
            )
            self.dl._write_metadata(cache_path, "https://example.com/item1.tif")

        meta_path = tmp_path / "item1.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["item_id"] == "item1"
        assert meta["url"] == "https://example.com/item1.tif"
        assert meta["etag"] == "abc123"
        assert meta["last_modified"] == "Wed, 01 Jan 2025 00:00:00 GMT"

    def test_writes_json_without_etag_on_head_failure(self, tmp_path):
        """Metadata JSON is written even if HEAD fails."""
        import requests

        cache_path = tmp_path / "item1.tif"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(b"fake")

        with patch("cartoload.source.stac.downloader.requests.head") as mock_head:
            mock_head.side_effect = requests.RequestException("fail")
            self.dl._write_metadata(cache_path, "https://example.com/item1.tif")

        meta_path = tmp_path / "item1.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["item_id"] == "item1"
        assert "etag" not in meta or meta.get("etag") == ""


class TestIsCachedWithWarpedFallback:
    """Tests for _is_cached with warped file fallback."""

    def setup_method(self):
        self.dl = STACDownloader(tempfile.mkdtemp())

    def test_original_exists(self, tmp_path):
        """Original file with metadata sidecar returns True."""
        cache_path = tmp_path / "item1.tif"
        cache_path.write_bytes(b"real data")
        meta = tmp_path / "item1.json"
        meta.write_text('{"item_id": "item1"}')

        assert self.dl._is_cached(cache_path, None) is True

    def test_original_missing_warped_exists(self, tmp_path):
        """Original deleted but warped + metadata + warp marker exist returns True."""
        cache_path = tmp_path / "item1.tif"
        warped = tmp_path / "item1_4326.tif"
        meta = tmp_path / "item1.json"
        warp_marker = tmp_path / "item1_4326.json"
        warped.write_bytes(b"warped data")
        meta.write_text('{"item_id": "item1"}')
        warp_marker.write_text('{"warped": true}')

        assert self.dl._is_cached(cache_path, None) is True

    def test_original_missing_no_warped(self, tmp_path):
        """Neither original nor warped returns False."""
        cache_path = tmp_path / "item1.tif"

        assert self.dl._is_cached(cache_path, None) is False

    def test_empty_file_deleted(self, tmp_path):
        """Empty file is deleted and returns False."""
        cache_path = tmp_path / "item1.tif"
        cache_path.write_bytes(b"")

        assert self.dl._is_cached(cache_path, None) is False
        assert not cache_path.exists()

    def test_file_without_metadata_is_incomplete(self, tmp_path):
        """File without .json sidecar is treated as incomplete and deleted."""
        cache_path = tmp_path / "item1.tif"
        cache_path.write_bytes(b"partial download data")

        assert self.dl._is_cached(cache_path, None) is False
        assert not cache_path.exists()

    def test_file_with_metadata_is_valid(self, tmp_path):
        """File with .json sidecar is treated as valid cache."""
        cache_path = tmp_path / "item1.tif"
        cache_path.write_bytes(b"real data")
        meta = tmp_path / "item1.json"
        meta.write_text('{"item_id": "item1"}')

        assert self.dl._is_cached(cache_path, None) is True


class TestOfflineMode:
    """Tests for STACDownloader offline mode (no freshness checks)."""

    def test_offline_skips_freshness_check(self, tmp_path):
        """When offline=True, _check_freshness is not called for cached files."""
        dl = STACDownloader(tmp_path, offline=True)

        # Set up a cached file with metadata using correct cache key path
        source_config = MagicMock()
        source_config.id = "test_source"
        source_config.type = "geotiff"
        source_config.urls = ["https://example.com/api/v1/collections/${layer}"]
        source_config.asset_filter = None
        source_config.defaults = {"layer": "test"}

        layer_config = MagicMock()
        layer_config.bounds = {"west": 7, "south": 46, "east": 8, "north": 47}
        layer_config.source_args = {}
        layer_config.asset_filter = None

        resolved_url = "https://example.com/api/v1/collections/test"
        cache_path = dl._get_cache_path(source_config.id, resolved_url, "item1")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(b"cached data")
        meta_path = cache_path.parent / f"{cache_path.stem}.json"
        meta_path.write_text(json.dumps({"item_id": "item1", "etag": "old"}))

        with (
            patch.object(dl, "_check_freshness") as mock_freshness,
            patch.object(dl, "query") as mock_query,
            patch.object(dl, "_download_item"),
        ):
            mock_query.return_value = [("item1", "https://example.com/item1.tif", None)]
            result = dl.run(
                source_config,
                layer_config,
                resolved_url,
                "test",
            )

            # Freshness check should NOT have been called
            mock_freshness.assert_not_called()
            # The cached file should be returned
            assert len(result) == 1

    def test_online_calls_freshness_check(self, tmp_path):
        """When offline=False (default), _check_freshness IS called for cached files."""
        dl = STACDownloader(tmp_path, offline=False)

        source_config = MagicMock()
        source_config.id = "test_source"
        source_config.type = "geotiff"
        source_config.urls = ["https://example.com/api/v1/collections/${layer}"]
        source_config.asset_filter = None
        source_config.defaults = {"layer": "test"}

        layer_config = MagicMock()
        layer_config.bounds = {"west": 7, "south": 46, "east": 8, "north": 47}
        layer_config.source_args = {}
        layer_config.asset_filter = None

        resolved_url = "https://example.com/api/v1/collections/test"
        cache_path = dl._get_cache_path(source_config.id, resolved_url, "item1")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(b"cached data")
        meta_path = cache_path.parent / f"{cache_path.stem}.json"
        meta_path.write_text(json.dumps({"item_id": "item1", "etag": "old"}))

        with (
            patch.object(dl, "_check_freshness", return_value=True) as mock_freshness,
            patch.object(dl, "query") as mock_query,
            patch.object(dl, "_download_item"),
        ):
            mock_query.return_value = [("item1", "https://example.com/item1.tif", None)]
            result = dl.run(
                source_config,
                layer_config,
                resolved_url,
                "test",
            )

            # Freshness check SHOULD have been called
            mock_freshness.assert_called_once()
            assert len(result) == 1
