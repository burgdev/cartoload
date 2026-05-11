"""Tests for rasterio_warp module — in-process tile reprojection."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from cartoload.processor.rasterio_warp import (
    compute_bounds_4326,
    compute_transform_3857,
    warp_tile_to_jpeg,
    warp_tile_to_rgba,
)


def _create_test_jpeg(
    path: Path, width: int = 256, height: int = 256, color: tuple = (100, 150, 200)
) -> bytes:
    """Create a test JPEG file and return its bytes."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    data = buf.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _create_test_png(
    path: Path,
    width: int = 256,
    height: int = 256,
    color: tuple = (100, 150, 200, 255),
) -> bytes:
    """Create a test PNG file and return its bytes. Supports RGBA."""
    img = Image.new("RGBA", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


class TestComputeBounds4326:
    """Tests for compute_bounds_4326."""

    def test_origin_tile_zoom0(self):
        """Zoom 0 single tile covers the whole world."""
        lat_min, lon_min, lat_max, lon_max = compute_bounds_4326(0, 0, 0)
        assert lon_min == pytest.approx(-180.0, abs=0.01)
        assert lon_max == pytest.approx(180.0, abs=0.01)
        assert lat_max > 85.0
        assert lat_min < -85.0

    def test_known_tile_zoom15(self):
        """Known tile at zoom 15 gives correct bounds."""
        x, y, z = 17000, 11300, 15
        lat_min, lon_min, lat_max, lon_max = compute_bounds_4326(x, y, z)

        # Verify using inverse formula
        n = 2**z
        expected_lon_min = x / n * 360.0 - 180.0
        expected_lon_max = (x + 1) / n * 360.0 - 180.0
        assert lon_min == pytest.approx(expected_lon_min, abs=1e-10)
        assert lon_max == pytest.approx(expected_lon_max, abs=1e-10)

    def test_bounds_are_ordered(self):
        """Bounds should have lat_min < lat_max and lon_min < lon_max."""
        for z in [5, 10, 15, 18]:
            n = 2**z
            lat_min, lon_min, lat_max, lon_max = compute_bounds_4326(n // 2, n // 2, z)
            assert lat_min < lat_max
            assert lon_min < lon_max

    def test_adjacent_tiles_abut(self):
        """Adjacent tiles should share boundaries."""
        z = 10
        n = 2**z
        for x in range(n // 2 - 1, n // 2 + 1):
            b1 = compute_bounds_4326(x, n // 2, z)
            b2 = compute_bounds_4326(x + 1, n // 2, z)
            # Right edge of b1 == left edge of b2 (lon_max == lon_min)
            assert b1[3] == pytest.approx(b2[1], abs=1e-10)


class TestComputeTransform3857:
    """Tests for compute_transform_3857."""

    def test_origin_tile(self):
        """Zoom 0 tile covers the full Web Mercator extent."""
        transform, width, height = compute_transform_3857(0, 0, 0)
        assert width == 256
        assert height == 256
        # Top-left should be at (-20037508.34, 20037508.34)
        assert transform.c == pytest.approx(-20037508.34, rel=1e-4)
        assert transform.f == pytest.approx(20037508.34, rel=1e-4)

    def test_pixel_size_decreases_with_zoom(self):
        """Pixel size should halve with each zoom level."""
        t1, _, _ = compute_transform_3857(0, 0, 10)
        t2, _, _ = compute_transform_3857(0, 0, 11)
        assert abs(t2.a) == pytest.approx(abs(t1.a) / 2, rel=1e-6)

    def test_transform_matches_wmts_downloader(self):
        """Transform should match the WMTSDownloader._compute_tile_bounds values."""
        x, y, z = 17000, 11300, 15
        transform, _, _ = compute_transform_3857(x, y, z)

        origin = -20037508.342789244
        tile_size = 40075016.68557849 / 2**z
        expected_left = origin + x * tile_size
        expected_top = -origin - y * tile_size

        assert transform.c == pytest.approx(expected_left, rel=1e-6)
        assert transform.f == pytest.approx(expected_top, rel=1e-6)

    def test_custom_tile_size(self):
        """Custom tile size should be reflected in dimensions and pixel size."""
        transform, width, height = compute_transform_3857(0, 0, 10, tile_pixels=512)
        assert width == 512
        assert height == 512
        t256, _, _ = compute_transform_3857(0, 0, 10, tile_pixels=256)
        # Pixel size for 512px should be half of 256px
        assert abs(transform.a) == pytest.approx(abs(t256.a) / 2, rel=1e-6)


class TestWarpTileToJpeg:
    """Tests for warp_tile_to_jpeg."""

    def test_passthrough_same_crs(self):
        """When source CRS matches target, return raw JPEG bytes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tile.jpeg"
            original_bytes = _create_test_jpeg(path)

            result = warp_tile_to_jpeg(path, 17000, 11300, 15, "EPSG:4326")
            assert result is not None
            jpeg_bytes, bounds = result
            # Should be exact passthrough
            assert jpeg_bytes == original_bytes
            # Bounds should be computed from tile coords
            assert len(bounds) == 4
            lat_min, lon_min, lat_max, lon_max = bounds
            assert lat_min < lat_max
            assert lon_min < lon_max

    def test_warp_3857_to_4326(self):
        """Warp from EPSG:3857 to EPSG:4326 produces valid JPEG."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tile.jpeg"
            _create_test_jpeg(path)

            result = warp_tile_to_jpeg(path, 17000, 11300, 15, "EPSG:3857")
            assert result is not None
            jpeg_bytes, bounds = result

            # Output should be valid JPEG
            assert jpeg_bytes[:2] == b"\xff\xd8"
            img = Image.open(io.BytesIO(jpeg_bytes))
            assert img.format == "JPEG"
            assert img.mode == "RGB"

            # Bounds should be valid WGS84
            lat_min, lon_min, lat_max, lon_max = bounds
            assert -90 <= lat_min <= 90
            assert -90 <= lat_max <= 90
            assert -180 <= lon_min <= 180
            assert -180 <= lon_max <= 180

    def test_missing_file_returns_none(self):
        """Non-existent file returns None."""
        result = warp_tile_to_jpeg(Path("/nonexistent/tile.jpeg"), 0, 0, 0, "EPSG:3857")
        assert result is None

    def test_bounds_consistency_with_warp(self):
        """Bounds from warp should match compute_bounds_4326 for same tile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tile.jpeg"
            _create_test_jpeg(path)

            x, y, z = 17000, 11300, 15
            result = warp_tile_to_jpeg(path, x, y, z, "EPSG:3857")
            assert result is not None
            _, warp_bounds = result

            expected_bounds = compute_bounds_4326(x, y, z)
            assert warp_bounds[0] == pytest.approx(expected_bounds[0], abs=1e-6)
            assert warp_bounds[1] == pytest.approx(expected_bounds[1], abs=1e-6)
            assert warp_bounds[2] == pytest.approx(expected_bounds[2], abs=1e-6)
            assert warp_bounds[3] == pytest.approx(expected_bounds[3], abs=1e-6)

    def test_quality_affects_output_size(self):
        """Lower quality should produce smaller JPEG output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tile.jpeg"
            # Use a non-uniform image to make quality differences visible
            img = Image.new("RGB", (256, 256))
            pixels = img.load()
            for i in range(256):
                for j in range(256):
                    pixels[i, j] = (i, j, (i + j) % 256)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=95)
            path.write_bytes(buf.getvalue())

            result_high = warp_tile_to_jpeg(
                path, 17000, 11300, 15, "EPSG:3857", quality=95
            )
            result_low = warp_tile_to_jpeg(
                path, 17000, 11300, 15, "EPSG:3857", quality=30
            )

            assert result_high is not None
            assert result_low is not None
            # Higher quality should produce larger (or equal) output
            assert len(result_high[0]) >= len(result_low[0])

    def test_warp_preserves_approximate_dimensions(self):
        """Warped tile dimensions should be close to source (256x256)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tile.jpeg"
            _create_test_jpeg(path)

            result = warp_tile_to_jpeg(path, 17000, 11300, 15, "EPSG:3857")
            assert result is not None
            jpeg_bytes, _ = result

            img = Image.open(io.BytesIO(jpeg_bytes))
            # At zoom 15, 3857→4326 warp changes tile dimensions based on latitude
            assert 150 <= img.width <= 400
            assert 150 <= img.height <= 400


class TestWarpTileToRgba:
    """Tests for warp_tile_to_rgba (PNG/RGBA-aware tile reprojection)."""

    def test_png_passthrough_same_crs(self):
        """PNG with same CRS: returns RGBA image directly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tile.png"
            _create_test_png(path, color=(100, 150, 200, 255))

            result = warp_tile_to_rgba(path, 17000, 11300, 15, "EPSG:4326")
            assert result is not None
            img, bounds = result
            assert img.mode == "RGBA"
            px = img.getpixel((0, 0))
            assert px[:3] == (100, 150, 200)
            assert px[3] == 255  # fully opaque

    def test_png_with_alpha_passthrough(self):
        """PNG with alpha channel preserved in passthrough."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tile.png"
            _create_test_png(path, color=(100, 150, 200, 128))

            result = warp_tile_to_rgba(path, 17000, 11300, 15, "EPSG:4326")
            assert result is not None
            img, _ = result
            assert img.mode == "RGBA"
            px = img.getpixel((0, 0))
            assert px[3] == 128  # alpha preserved

    def test_png_warp_3857_to_4326(self):
        """PNG warp from EPSG:3857 to EPSG:4326 produces RGBA image."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tile.png"
            _create_test_png(path, color=(200, 100, 50, 200))

            result = warp_tile_to_rgba(path, 17000, 11300, 15, "EPSG:3857")
            assert result is not None
            img, bounds = result
            assert img.mode == "RGBA"
            # Should have 4 channels
            assert len(img.getpixel((0, 0))) == 4
            # Alpha should be preserved (approximately, due to bilinear resampling)
            px = img.getpixel((img.width // 2, img.height // 2))
            assert abs(px[3] - 200) <= 10

    def test_jpeg_treated_as_opaque_rgba(self):
        """JPEG input produces RGBA with fully opaque alpha."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tile.jpeg"
            _create_test_jpeg(path, color=(100, 150, 200))

            result = warp_tile_to_rgba(path, 17000, 11300, 15, "EPSG:4326")
            assert result is not None
            img, _ = result
            assert img.mode == "RGBA"
            px = img.getpixel((0, 0))
            assert px[3] == 255  # fully opaque

    def test_missing_file_returns_none(self):
        """Non-existent file returns None."""
        result = warp_tile_to_rgba(Path("/nonexistent/tile.png"), 0, 0, 0, "EPSG:3857")
        assert result is None

    def test_rgb_png_treated_as_opaque(self):
        """PNG without alpha (RGB mode) treated as fully opaque."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tile.png"
            img = Image.new("RGB", (256, 256), (128, 64, 32))
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path, format="PNG")

            result = warp_tile_to_rgba(path, 17000, 11300, 15, "EPSG:4326")
            assert result is not None
            rgba_img, _ = result
            assert rgba_img.mode == "RGBA"
            px = rgba_img.getpixel((0, 0))
            assert px[:3] == (128, 64, 32)
            assert px[3] == 255
