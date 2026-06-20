"""Tests for tile_metadata module — metadata computation without JPEG loading."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from cartoload.exporters.garmin_img_model import TileMetadata
from cartoload.processor.tile_metadata import compute_tile_metadata


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


class TestTileMetadata:
    """Tests for TileMetadata dataclass."""

    def test_fields(self):
        tm = TileMetadata(
            x=17000,
            y=11300,
            zoom=15,
            lat_min=46.5,
            lon_min=7.0,
            lat_max=46.6,
            lon_max=7.1,
            jpeg_size=12345,
            source_path=Path("/tmp/test.jpeg"),
        )
        assert tm.x == 17000
        assert tm.y == 11300
        assert tm.zoom == 15
        assert tm.lat_min == 46.5
        assert tm.jpeg_size == 12345
        assert tm.source_path == Path("/tmp/test.jpeg")

    def test_source_path_optional(self):
        tm = TileMetadata(
            x=0,
            y=0,
            zoom=0,
            lat_min=-85.0,
            lon_min=-180.0,
            lat_max=85.0,
            lon_max=180.0,
            jpeg_size=5000,
        )
        assert tm.source_path is None


class TestComputeTileMetadata:
    """Tests for compute_tile_metadata function."""

    def test_single_tile_zoom8(self):
        """Single tile at zoom 8 produces correct bounds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create mock downloader
            cache_path = Path(tmpdir) / "source" / "8" / "130" / "85.jpeg"
            jpeg_data = _create_test_jpeg(cache_path)

            downloader = MagicMock()
            downloader._cache_path.return_value = cache_path

            results = compute_tile_metadata(
                tile_coords=[(130, 85)],
                zoom=8,
                source_crs="EPSG:3857",
                downloader=downloader,
            )

            assert len(results) == 1
            tm = results[0]
            assert tm.x == 130
            assert tm.y == 85
            assert tm.zoom == 8
            assert tm.jpeg_size == len(jpeg_data)
            assert tm.source_path == cache_path
            # Verify bounds are reasonable for zoom 8
            assert -180 <= tm.lon_min < tm.lon_max <= 180
            assert -90 <= tm.lat_min < tm.lat_max <= 90

    def test_multiple_tiles(self):
        """Multiple tiles at same zoom produce individual metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = MagicMock()

            coords = [(130, 85), (131, 85), (130, 86)]
            for x, y in coords:
                path = Path(tmpdir) / f"source/{8}/{x}/{y}.jpeg"
                _create_test_jpeg(path)
                downloader._cache_path.side_effect = None
                # Use a simple side_effect map

            def cache_path(x, y, z):
                return Path(tmpdir) / f"source/{z}/{x}/{y}.jpeg"

            downloader._cache_path.side_effect = cache_path

            results = compute_tile_metadata(
                tile_coords=coords,
                zoom=8,
                source_crs="EPSG:3857",
                downloader=downloader,
            )

            assert len(results) == 3
            # Tiles should be at different geographic positions
            assert results[0].lon_max == pytest.approx(results[1].lon_min, abs=0.001)
            assert results[0].lat_min == pytest.approx(results[2].lat_max, abs=0.001)

    def test_missing_source_file(self):
        """Missing source file results in jpeg_size=0."""
        downloader = MagicMock()
        downloader._cache_path.return_value = Path("/nonexistent/tile.jpeg")

        results = compute_tile_metadata(
            tile_coords=[(0, 0)],
            zoom=0,
            source_crs="EPSG:3857",
            downloader=downloader,
        )

        assert len(results) == 1
        assert results[0].jpeg_size == 0

    def test_bounds_match_compute_bounds_4326(self):
        """Bounds should match compute_bounds_4326 exactly."""
        from cartoload.processor.warp import compute_bounds_4326

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "source/15/17000/11300.jpeg"
            _create_test_jpeg(path)

            downloader = MagicMock()
            downloader._cache_path.return_value = path

            results = compute_tile_metadata(
                tile_coords=[(17000, 11300)],
                zoom=15,
                source_crs="EPSG:3857",
                downloader=downloader,
            )

            expected = compute_bounds_4326(17000, 11300, 15)
            tm = results[0]
            assert tm.lat_min == pytest.approx(expected[0], abs=1e-10)
            assert tm.lon_min == pytest.approx(expected[1], abs=1e-10)
            assert tm.lat_max == pytest.approx(expected[2], abs=1e-10)
            assert tm.lon_max == pytest.approx(expected[3], abs=1e-10)

    def test_zoom0_edge_tiles(self):
        """Edge tiles at zoom 0 have correct bounds near ±180 longitude."""
        downloader = MagicMock()
        downloader._cache_path.return_value = Path("/nonexistent.jpeg")

        # Only tile at zoom 0
        results = compute_tile_metadata(
            tile_coords=[(0, 0)],
            zoom=0,
            source_crs="EPSG:3857",
            downloader=downloader,
        )

        tm = results[0]
        assert tm.lon_min == pytest.approx(-180.0)
        assert tm.lon_max == pytest.approx(180.0)
        assert tm.lat_max > 85.0  # Near +85.05°
        assert tm.lat_min < -85.0  # Near -85.05°
