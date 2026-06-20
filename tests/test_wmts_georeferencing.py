"""Tests for WMTS tile georeferencing: world file generation, caching, and integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from cartoload.source.wmts.download import WmtsDownloader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Full Web Mercator extent: 2 * pi * 6378137
FULL_EXTENT = 40075016.68557849
ORIGIN = -FULL_EXTENT / 2  # -20037508.342789244


def _make_downloader(
    tmp_path: Path,
    url_template: str = "https://example.com/{z}/{x}/{y}.jpeg",
    **kwargs,
) -> WmtsDownloader:
    return WmtsDownloader(
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
    return resp


# ===================================================================
# 5.1 – _compute_tile_bounds tests
# ===================================================================


class TestComputeTileBounds:
    """Unit tests for _compute_tile_bounds."""

    def test_zoom0_covers_world(self) -> None:
        """At zoom 0, tile (0,0) should cover the full Web Mercator extent."""
        left, top, right, bottom = WmtsDownloader._compute_tile_bounds(0, 0, 0)
        half_world = 20037508.342789244
        assert abs(left - (-half_world)) < 0.01
        assert abs(top - half_world) < 0.01  # top (north edge) is +half_world
        assert abs(right - half_world) < 0.01
        assert abs(bottom - (-half_world)) < 0.01  # bottom (south edge) is -half_world

    def test_zoom10_tile_541_362(self) -> None:
        """Known tile (541, 362, z=10) should have correct bounds."""
        left, top, right, bottom = WmtsDownloader._compute_tile_bounds(541, 362, 10)
        tile_size = 40075016.68557849 / 2**10
        expected_left = ORIGIN + 541 * tile_size
        expected_top = -ORIGIN - 362 * tile_size  # -ORIGIN = +half_world
        assert abs(left - expected_left) < 0.001
        assert abs(top - expected_top) < 0.001
        assert abs(right - (expected_left + tile_size)) < 0.001
        assert abs(bottom - (expected_top - tile_size)) < 0.001

    def test_adjacent_tiles_touch(self) -> None:
        """Adjacent tiles should share boundaries exactly."""
        left1, _top1, right1, _bottom1 = WmtsDownloader._compute_tile_bounds(0, 0, 5)
        left2, _top2, right2, _bottom2 = WmtsDownloader._compute_tile_bounds(1, 0, 5)
        assert abs(right1 - left2) < 1e-6

        _left3, top3, _right3, bottom3 = WmtsDownloader._compute_tile_bounds(0, 0, 5)
        _left4, top4, _right4, bottom4 = WmtsDownloader._compute_tile_bounds(0, 1, 5)
        assert abs(bottom3 - top4) < 1e-6

    def test_tile_size_halves_per_zoom(self) -> None:
        """Tile size should halve with each zoom level."""
        _, _, r0, _ = WmtsDownloader._compute_tile_bounds(0, 0, 0)
        l0, _, _, _ = WmtsDownloader._compute_tile_bounds(0, 0, 0)
        size0 = r0 - l0

        _, _, r1, _ = WmtsDownloader._compute_tile_bounds(0, 0, 1)
        l1, _, _, _ = WmtsDownloader._compute_tile_bounds(0, 0, 1)
        size1 = r1 - l1

        assert abs(size0 / 2 - size1) < 1e-6


# ===================================================================
# 5.2 – _write_world_file tests
# ===================================================================


class TestWriteWorldFile:
    """Unit tests for _write_world_file."""

    def test_jpeg_creates_jgw(self, tmp_path: Path) -> None:
        """JPEG tiles should produce .jgw world files."""
        dl = _make_downloader(tmp_path, tile_format="jpeg")
        tile_path = tmp_path / "tile.jpeg"
        tile_path.write_bytes(b"fake-jpeg")
        dl._write_world_file(tile_path, 541, 362, 10)
        world_file = tile_path.with_suffix(".jgw")
        assert world_file.exists()

    def test_png_creates_pgw(self, tmp_path: Path) -> None:
        """PNG tiles should produce .pgw world files."""
        dl = _make_downloader(tmp_path, tile_format="png")
        tile_path = tmp_path / "tile.png"
        tile_path.write_bytes(b"fake-png")
        dl._write_world_file(tile_path, 541, 362, 10)
        world_file = tile_path.with_suffix(".pgw")
        assert world_file.exists()

    def test_world_file_affine_values(self, tmp_path: Path) -> None:
        """World file should contain correct affine transform values."""
        dl = _make_downloader(tmp_path, tile_format="jpeg")
        tile_path = tmp_path / "tile.jpeg"
        tile_path.write_bytes(b"fake-jpeg")
        dl._write_world_file(tile_path, 541, 362, 10)

        world_file = tile_path.with_suffix(".jgw")
        lines = world_file.read_text().strip().split("\n")
        assert len(lines) == 6

        tile_size_m = 40075016.68557849 / 2**10
        expected_pixel_size = tile_size_m / 256

        # Line 1: pixel size X (positive)
        assert abs(float(lines[0]) - expected_pixel_size) < 1e-6
        # Line 2: rotation Y (0)
        assert float(lines[1]) == 0.0
        # Line 3: rotation X (0)
        assert float(lines[2]) == 0.0
        # Line 4: pixel size Y (negative)
        assert abs(float(lines[3]) - (-expected_pixel_size)) < 1e-6
        # Line 5: top-left X
        expected_left = ORIGIN + 541 * tile_size_m
        assert abs(float(lines[4]) - expected_left) < 1e-3
        # Line 6: top-left Y
        expected_top = -ORIGIN - 362 * tile_size_m  # -ORIGIN = +half_world
        assert abs(float(lines[5]) - expected_top) < 1e-3

    def test_world_file_256_pixel_default(self, tmp_path: Path) -> None:
        """Default tile size is 256 pixels."""
        dl = _make_downloader(tmp_path)
        tile_path = tmp_path / "tile.jpeg"
        tile_path.write_bytes(b"fake")
        dl._write_world_file(tile_path, 0, 0, 5)

        world_file = tile_path.with_suffix(".jgw")
        lines = world_file.read_text().strip().split("\n")
        tile_size_m = 40075016.68557849 / 2**5
        assert abs(float(lines[0]) - tile_size_m / 256) < 1e-6


# ===================================================================
# 5.3 – _is_cached behavior with world files
# ===================================================================


class TestIsCached:
    """Tests for _is_cached with world file awareness."""

    def test_fully_cached_returns_true(self, tmp_path: Path) -> None:
        """Tile + world file present → cached."""
        dl = _make_downloader(tmp_path)
        tile_path = dl._cache_path(0, 0, 1)
        tile_path.parent.mkdir(parents=True, exist_ok=True)
        tile_path.write_bytes(b"tile")
        dl._write_world_file(tile_path, 0, 0, 1)
        assert dl._is_cached(tile_path) is True

    def test_missing_world_file_returns_false(self, tmp_path: Path) -> None:
        """Tile present but no world file → not cached."""
        dl = _make_downloader(tmp_path)
        tile_path = dl._cache_path(0, 0, 1)
        tile_path.parent.mkdir(parents=True, exist_ok=True)
        tile_path.write_bytes(b"tile")
        # No world file created
        assert dl._is_cached(tile_path) is False

    def test_missing_tile_returns_false(self, tmp_path: Path) -> None:
        """No tile at all → not cached."""
        dl = _make_downloader(tmp_path)
        tile_path = dl._cache_path(0, 0, 1)
        assert dl._is_cached(tile_path) is False

    def test_empty_tile_returns_false(self, tmp_path: Path) -> None:
        """Empty tile file → not cached."""
        dl = _make_downloader(tmp_path)
        tile_path = dl._cache_path(0, 0, 1)
        tile_path.parent.mkdir(parents=True, exist_ok=True)
        tile_path.write_bytes(b"")
        assert dl._is_cached(tile_path) is False

    def test_download_tile_regenerates_world_file(self, tmp_path: Path) -> None:
        """Cached tile missing world file gets it regenerated without HTTP request."""
        dl = _make_downloader(tmp_path)
        tile_path = dl._cache_path(0, 0, 1)
        tile_path.parent.mkdir(parents=True, exist_ok=True)
        tile_path.write_bytes(b"cached-tile")

        # Tile exists but no world file → should regenerate without download
        with patch("cartoload.source.wmts.download.requests.get") as mock_get:
            result = dl.download_tile(0, 0, 1)

        mock_get.assert_not_called()
        assert dl._is_cached(result) is True
        assert result.with_suffix(".jgw").exists()


# ===================================================================
# 5.4 – Integration: download → VRT
# ===================================================================


class TestGeoreferencedVRT:
    """Integration tests verifying tiles are georeferenced for gdalbuildvrt."""

    def test_world_files_written_on_download(self, tmp_path: Path) -> None:
        """download_tile should create both tile and world file."""
        dl = _make_downloader(tmp_path)
        with patch(
            "cartoload.source.wmts.download.requests.get",
            return_value=_mock_response(),
        ):
            path = dl.download_tile(541, 362, 10)

        assert path.exists()
        world_file = path.with_suffix(".jgw")
        assert world_file.exists()

        # Verify world file has 6 lines
        lines = world_file.read_text().strip().split("\n")
        assert len(lines) == 6

    def test_grid_download_creates_world_files(self, tmp_path: Path) -> None:
        """download_grid should create world files for all tiles."""
        dl = _make_downloader(tmp_path)
        bbox = (0.0, 0.0, 5.0, 5.0)
        zoom = 2

        with patch(
            "cartoload.source.wmts.download.requests.get",
            return_value=_mock_response(),
        ):
            results = dl.download_grid(bbox, zoom)

        assert len(results) > 0
        for tile_path in results:
            world_file = tile_path.with_suffix(".jgw")
            assert world_file.exists(), f"Missing world file for {tile_path}"

    def test_world_file_suffix_jpeg(self) -> None:
        assert WmtsDownloader._world_file_suffix("jpeg") == ".jgw"
        assert WmtsDownloader._world_file_suffix("jpg") == ".jgw"

    def test_world_file_suffix_png(self) -> None:
        assert WmtsDownloader._world_file_suffix("png") == ".pgw"

    def test_world_file_path_method(self, tmp_path: Path) -> None:
        """_world_file_path should return the correct path."""
        dl = _make_downloader(tmp_path, tile_format="jpeg")
        tile = tmp_path / "cache" / "test" / "10" / "541" / "362.jpeg"
        assert (
            dl._world_file_path(tile)
            == tmp_path / "cache" / "test" / "10" / "541" / "362.jgw"
        )

        dl_png = _make_downloader(tmp_path, tile_format="png")
        assert (
            dl_png._world_file_path(tile.with_suffix(".png"))
            == tmp_path / "cache" / "test" / "10" / "541" / "362.pgw"
        )
