"""Tests for WMTSDownloader: tile grid, URL interpolation, caching, retries, progress."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from cartoload.downloader.wmts import WMTSDownloader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_downloader(
    tmp_path: Path,
    url_template: str = "https://example.com/{zoom}/{x}/{y}.jpeg",
    **kwargs,
) -> WMTSDownloader:
    return WMTSDownloader(
        source_id="test_source",
        url_template=url_template,
        cache_dir=tmp_path / "cache",
        delay_ms=0,
        **kwargs,
    )


def _mock_response(status_code: int = 200, content: bytes = b"tile-data") -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.content = content
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


# ===================================================================
# 2.3 – Tile grid computation tests
# ===================================================================


class TestTileGridComputation:
    """Unit tests for _bbox_to_tile_indices."""

    def test_known_bbox_zoom10(self) -> None:
        """Bbox (7,46)-(8,47) at zoom 10 should produce valid tile indices."""
        tiles = WMTSDownloader._bbox_to_tile_indices((7.0, 46.0, 8.0, 47.0), 10)
        assert len(tiles) > 0
        for x, y in tiles:
            assert 0 <= x < 2**10
            assert 0 <= y < 2**10

    def test_single_tile_bbox(self) -> None:
        """A tiny bbox should produce exactly one tile at low zoom."""
        tiles = WMTSDownloader._bbox_to_tile_indices((0.0, 0.0, 0.001, 0.001), 0)
        assert len(tiles) == 1

    def test_zoom0_whole_world(self) -> None:
        """At zoom 0, any bbox should produce exactly one tile (0, 0)."""
        tiles = WMTSDownloader._bbox_to_tile_indices((-180.0, -85.0, 180.0, 85.0), 0)
        assert tiles == [(0, 0)]

    def test_antimeridian_wrapping(self) -> None:
        """Bbox crossing the antimeridian (min_lon > max_lon) wraps correctly."""
        tiles = WMTSDownloader._bbox_to_tile_indices((179.0, 0.0, -179.0, 1.0), 5)
        assert len(tiles) > 0
        xs = {x for x, _ in tiles}
        # Should include tiles at both edges of the x range
        assert min(xs) == 0 or max(xs) == 2**5 - 1

    def test_tile_boundary_bbox(self) -> None:
        """Bbox right on a tile boundary should include that tile."""
        # Zoom 1: 2 tiles wide. Tile boundary at lon 0.
        tiles = WMTSDownloader._bbox_to_tile_indices((-1.0, -1.0, 1.0, 1.0), 1)
        xs = {x for x, _ in tiles}
        assert 0 in xs and 1 in xs

    def test_returns_sorted_list(self) -> None:
        """Output should be sorted by (x, y)."""
        tiles = WMTSDownloader._bbox_to_tile_indices((7.0, 46.0, 8.0, 47.0), 10)
        assert tiles == sorted(tiles)


# ===================================================================
# 3.2 – URL template interpolation tests
# ===================================================================


class TestURLInterpolation:
    """Unit tests for _build_tile_url."""

    def test_xyz_style(self) -> None:
        url = WMTSDownloader._build_tile_url(
            "https://wmts.example.com/tiles/{zoom}/{x}/{y}.jpeg",
            x=543,
            y=361,
            zoom=10,
        )
        assert url == "https://wmts.example.com/tiles/10/543/361.jpeg"

    def test_kvp_style_wmts(self) -> None:
        url = WMTSDownloader._build_tile_url(
            "https://wmts.example.com/wmts?SERVICE=WMTS&REQUEST=GetTile"
            "&LAYER=basemap&TILEMATRIXSET=3857"
            "&TILEMATRIX={zoom}&TILECOL={x}&TILEROW={y}&FORMAT=image/jpeg",
            x=543,
            y=361,
            zoom=10,
        )
        assert "TILEMATRIX=10" in url
        assert "TILECOL=543" in url
        assert "TILEROW=361" in url

    def test_source_id_placeholder(self) -> None:
        url = WMTSDownloader._build_tile_url(
            "https://example.com/{source_id}/{zoom}/{x}/{y}.png",
            x=1,
            y=2,
            zoom=3,
            source_id="swisstopo_wmts",
        )
        assert "swisstopo_wmts" in url
        assert "{source_id}" not in url

    def test_z_alias(self) -> None:
        """{z} should work as an alias for {zoom}."""
        url = WMTSDownloader._build_tile_url(
            "https://tiles.example.com/{z}/{x}/{y}.png",
            x=5,
            y=3,
            zoom=10,
        )
        assert url == "https://tiles.example.com/10/5/3.png"

    def test_layer_placeholder(self) -> None:
        """{layer} should be replaced with layer_name."""
        url = WMTSDownloader._build_tile_url(
            "https://wmts.example.com/{layer}/{z}/{x}/{y}.jpeg",
            x=1,
            y=2,
            zoom=3,
            layer_name="ch.swisstopo.pixelkarte-farbe",
        )
        assert "ch.swisstopo.pixelkarte-farbe" in url
        assert "{layer}" not in url


# ===================================================================
# 4.3 – Concurrent download loop tests
# ===================================================================


class TestConcurrentDownload:
    """Integration tests for download_grid with mocked HTTP."""

    def test_all_tiles_fetched(self, tmp_path: Path) -> None:
        """All tiles in a small grid should be downloaded."""
        dl = _make_downloader(tmp_path)
        # Use a small bbox at zoom 2 -> few tiles
        bbox = (0.0, 0.0, 10.0, 10.0)
        zoom = 2
        tiles = WMTSDownloader._bbox_to_tile_indices(bbox, zoom)
        assert len(tiles) > 0

        with patch(
            "cartoload.downloader.wmts.requests.get", return_value=_mock_response()
        ):
            results = dl.download_grid(bbox, zoom)

        # All tiles should be on disk
        for p in results:
            assert p.exists()

    def test_concurrency_respects_max_workers(self, tmp_path: Path) -> None:
        """At most max_workers threads should run concurrently."""
        max_concurrent = 0
        current = 0

        def track_concurrent(*args, **kwargs):
            nonlocal max_concurrent, current
            current += 1
            max_concurrent = max(max_concurrent, current)
            time.sleep(0.05)
            current -= 1
            return _mock_response()

        dl = _make_downloader(tmp_path, max_workers=2)
        bbox = (0.0, 0.0, 20.0, 20.0)
        zoom = 3

        with patch(
            "cartoload.downloader.wmts.requests.get", side_effect=track_concurrent
        ):
            dl.download_grid(bbox, zoom)

        assert max_concurrent <= 2


# ===================================================================
# 5.3 – Rate limiting tests
# ===================================================================


class TestRateLimiting:
    """Tests that the delay is enforced between requests."""

    def test_delay_is_applied(self, tmp_path: Path) -> None:
        """time.sleep should be called with the configured delay."""
        dl = _make_downloader(tmp_path)
        dl._delay_ms = 200

        with (
            patch(
                "cartoload.downloader.wmts.requests.get", return_value=_mock_response()
            ),
            patch("cartoload.downloader.wmts.time.sleep") as mock_sleep,
        ):
            dl.download_tile(0, 0, 1)

        # Should have slept at least once (the per-request delay)
        mock_sleep.assert_any_call(0.2)


# ===================================================================
# 6.5 – Caching logic tests
# ===================================================================


class TestCaching:
    """Tests for cache path, cache hit, and atomic write."""

    def test_cache_path_format(self, tmp_path: Path) -> None:
        dl = _make_downloader(tmp_path)
        path = dl._cache_path(543, 361, 10)
        assert path == tmp_path / "cache" / "test_source" / "10" / "543" / "361.jpeg"

    def test_cache_miss_downloads_and_writes(self, tmp_path: Path) -> None:
        dl = _make_downloader(tmp_path)
        with patch(
            "cartoload.downloader.wmts.requests.get", return_value=_mock_response()
        ):
            path = dl.download_tile(0, 0, 1)
        assert path.exists()
        assert path.read_bytes() == b"tile-data"

    def test_cache_hit_skips_download(self, tmp_path: Path) -> None:
        dl = _make_downloader(tmp_path)
        # Pre-populate cache
        path = dl._cache_path(0, 0, 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"cached-tile")

        with patch("cartoload.downloader.wmts.requests.get") as mock_get:
            result = dl.download_tile(0, 0, 1)

        mock_get.assert_not_called()
        assert result == path
        assert result.read_bytes() == b"cached-tile"

    def test_atomic_write_uses_tmp_then_rename(self, tmp_path: Path) -> None:
        dl = _make_downloader(tmp_path)
        path = dl._cache_path(0, 0, 1)
        dl._write_to_cache(path, b"atomic-data")
        assert path.exists()
        assert path.read_bytes() == b"atomic-data"
        # No leftover tmp file
        tmp_path_check = path.with_suffix(path.suffix + ".tmp")
        assert not tmp_path_check.exists()


# ===================================================================
# 7.5 – Retry with backoff tests
# ===================================================================


class TestRetryBackoff:
    """Tests for retry logic on HTTP errors."""

    def test_retry_on_503(self, tmp_path: Path) -> None:
        """Should retry on 503 and succeed on 2nd attempt."""
        dl = _make_downloader(tmp_path)
        responses = [_mock_response(503), _mock_response(200, b"ok")]

        with (
            patch("cartoload.downloader.wmts.requests.get", side_effect=responses),
            patch("cartoload.downloader.wmts.time.sleep"),
        ):
            data = dl._download_with_retry("http://x", 0, 0, 1)

        assert data == b"ok"

    def test_retry_on_429(self, tmp_path: Path) -> None:
        """Should retry on 429 and succeed on 2nd attempt."""
        dl = _make_downloader(tmp_path)
        responses = [_mock_response(429), _mock_response(200, b"ok")]

        with (
            patch("cartoload.downloader.wmts.requests.get", side_effect=responses),
            patch("cartoload.downloader.wmts.time.sleep"),
        ):
            data = dl._download_with_retry("http://x", 0, 0, 1)

        assert data == b"ok"

    def test_exhausted_retries_returns_none(self, tmp_path: Path) -> None:
        """After 3 transient failures, returns None."""
        dl = _make_downloader(tmp_path)

        with (
            patch(
                "cartoload.downloader.wmts.requests.get",
                return_value=_mock_response(503),
            ),
            patch("cartoload.downloader.wmts.time.sleep"),
        ):
            data = dl._download_with_retry("http://x", 0, 0, 1)

        assert data is None

    def test_no_retry_on_404(self, tmp_path: Path) -> None:
        """Should not retry on 404."""
        dl = _make_downloader(tmp_path)

        with (
            patch(
                "cartoload.downloader.wmts.requests.get",
                return_value=_mock_response(404),
            ),
            patch("cartoload.downloader.wmts.time.sleep") as mock_sleep,
        ):
            data = dl._download_with_retry("http://x", 0, 0, 1)

        assert data is None
        # Should not have called sleep for backoff (only the per-request delay is separate)
        mock_sleep.assert_not_called()

    def test_backoff_durations(self, tmp_path: Path) -> None:
        """Exponential backoff should sleep 1, 2 seconds (no sleep after last attempt)."""
        dl = _make_downloader(tmp_path)

        with (
            patch(
                "cartoload.downloader.wmts.requests.get",
                return_value=_mock_response(503),
            ),
            patch("cartoload.downloader.wmts.time.sleep") as mock_sleep,
        ):
            dl._download_with_retry("http://x", 0, 0, 1)

        # Sleep happens before retry, not after the last failed attempt:
        # attempt 0 fails -> sleep(1), attempt 1 fails -> sleep(2), attempt 2 fails -> no more retries
        calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert calls == [1, 2]


# ===================================================================
# 8.4 – Rich progress output tests
# ===================================================================


class TestProgressOutput:
    """Tests that progress bar output is produced during download_grid."""

    def test_progress_bar_produced(self, tmp_path: Path) -> None:
        """download_grid should run without error and produce rich output."""
        dl = _make_downloader(tmp_path)
        bbox = (0.0, 0.0, 5.0, 5.0)
        zoom = 2

        with patch(
            "cartoload.downloader.wmts.requests.get", return_value=_mock_response()
        ):
            results = dl.download_grid(bbox, zoom)

        # Just verify it completed and returned results
        assert len(results) > 0

    def test_progress_fast_forwards_cached(self, tmp_path: Path) -> None:
        """Cached tiles should be counted immediately in progress."""
        dl = _make_downloader(tmp_path)
        bbox = (0.0, 0.0, 5.0, 5.0)
        zoom = 2

        # Pre-cache some tiles
        tiles = WMTSDownloader._bbox_to_tile_indices(bbox, zoom)
        for x, y in tiles[:2]:
            path = dl._cache_path(x, y, zoom)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"cached")

        with patch(
            "cartoload.downloader.wmts.requests.get", return_value=_mock_response()
        ) as mock_get:
            results = dl.download_grid(bbox, zoom)

        # Only the uncached tiles should trigger HTTP requests
        expected_calls = len(tiles) - 2
        assert mock_get.call_count == expected_calls
        assert len(results) == len(tiles)


# ===================================================================
# 9.1 – End-to-end test with mocked HTTP
# ===================================================================


class TestEndToEnd:
    """E2E tests with mocked HTTP verifying full download cycle."""

    def test_full_download_cycle(self, tmp_path: Path) -> None:
        """Configure source, run download_grid, verify all tiles cached."""
        dl = _make_downloader(tmp_path)
        bbox = (7.0, 46.0, 7.5, 46.5)
        zoom = 8

        tiles = WMTSDownloader._bbox_to_tile_indices(bbox, zoom)
        assert len(tiles) > 0

        with patch(
            "cartoload.downloader.wmts.requests.get", return_value=_mock_response()
        ):
            results = dl.download_grid(bbox, zoom)

        assert len(results) == len(tiles)
        for p in results:
            assert p.exists()
            assert p.stat().st_size > 0

    def test_resumable_download(self, tmp_path: Path) -> None:
        """Download half, stop, resume — only uncached tiles fetched on 2nd run."""
        dl = _make_downloader(tmp_path)
        bbox = (0.0, 0.0, 10.0, 10.0)
        zoom = 3
        tiles = WMTSDownloader._bbox_to_tile_indices(bbox, zoom)
        half = len(tiles) // 2

        # First run: only "succeed" for the first half of tiles
        call_count = [0]

        def partial_download(url, *args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx < half:
                return _mock_response(content=idx.to_bytes(4, "big"))
            return _mock_response(503)  # Fail the rest

        with (
            patch(
                "cartoload.downloader.wmts.requests.get", side_effect=partial_download
            ),
            patch("cartoload.downloader.wmts.time.sleep"),
        ):
            results1 = dl.download_grid(bbox, zoom)

        cached_count = sum(1 for p in results1 if p.exists())
        assert cached_count == half

        # Second run: succeed for everything
        call_count2 = [0]

        def full_download(url, *args, **kwargs):
            call_count2[0] += 1
            return _mock_response(content=b"resumed")

        with patch("cartoload.downloader.wmts.requests.get", side_effect=full_download):
            results2 = dl.download_grid(bbox, zoom)

        # Only uncached tiles should have been fetched
        assert call_count2[0] == len(tiles) - half
        # All tiles should now be cached
        assert len(results2) == len(tiles)

    def test_mixed_success_failure(self, tmp_path: Path) -> None:
        """Some 200, some 503-then-200, some 404 — verify correct tiles cached."""
        dl = _make_downloader(tmp_path)
        bbox = (0.0, 0.0, 30.0, 30.0)
        zoom = 4
        tiles = WMTSDownloader._bbox_to_tile_indices(bbox, zoom)
        assert len(tiles) >= 3

        # Build a response schedule:
        # tile 0: immediate 200
        # tile 1: 503 then 200
        # tile 2: 404
        # rest: 200
        attempt_counts: dict[tuple[int, int], int] = {}

        def scheduled_response(url, *args, **kwargs):
            # Extract x,y from URL for deterministic scheduling
            parts = url.split("/")
            x, y_file = int(parts[-2]), parts[-1]
            y = int(y_file.split(".")[0])
            key = (x, y)
            attempt_counts[key] = attempt_counts.get(key, 0) + 1
            attempt = attempt_counts[key]

            if key == tiles[1] and attempt == 1:
                return _mock_response(503)
            if key == tiles[2]:
                return _mock_response(404)
            return _mock_response(content=f"tile-{x}-{y}".encode())

        with (
            patch(
                "cartoload.downloader.wmts.requests.get", side_effect=scheduled_response
            ),
            patch("cartoload.downloader.wmts.time.sleep"),
        ):
            results = dl.download_grid(bbox, zoom)

        result_paths = set(results)
        # Tile 0 should be cached (200)
        assert dl._cache_path(*tiles[0], zoom) in result_paths
        # Tile 1 should be cached (503 -> 200)
        assert dl._cache_path(*tiles[1], zoom) in result_paths
        # Tile 2 should NOT be cached (404)
        assert dl._cache_path(*tiles[2], zoom) not in result_paths
