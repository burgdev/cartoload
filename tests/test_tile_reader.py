"""Tests for direct tile reader: world file parsing, JPEG passthrough, PNG conversion, bounds."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from cartoload.processor.tile_reader import (
    TileCacheReader,
    WorldFileParams,
    compute_bounds_from_tile_coords,
    compute_bounds_from_world_file,
    parse_world_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_world_file(
    path: Path,
    pixel_size_x: float = 152.8740565,
    rotation_y: float = 0.0,
    rotation_x: float = 0.0,
    pixel_size_y: float = -152.8740565,
    top_left_x: float = 587036.384,
    top_left_y: float = 5870363.772,
) -> Path:
    """Write a world file with given parameters."""
    lines = [
        f"{pixel_size_x:.10f}",
        f"{rotation_y:.10f}",
        f"{rotation_x:.10f}",
        f"{pixel_size_y:.10f}",
        f"{top_left_x:.10f}",
        f"{top_left_y:.10f}",
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


def _make_jpeg(width: int = 256, height: int = 256) -> bytes:
    """Create a minimal JPEG image."""
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_png(width: int = 256, height: int = 256) -> bytes:
    """Create a minimal PNG image."""
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(64, 64, 64))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ===================================================================
# 5.1 – World file parser tests
# ===================================================================


class TestParseWorldFile:
    def test_parse_valid_jgw(self, tmp_path: Path) -> None:
        wf_path = tmp_path / "tile.jgw"
        _write_world_file(wf_path)

        result = parse_world_file(wf_path)
        assert isinstance(result, WorldFileParams)
        assert abs(result.pixel_size_x - 152.8740565) < 1e-4
        assert result.rotation_y == 0.0
        assert result.rotation_x == 0.0
        assert abs(result.pixel_size_y - (-152.8740565)) < 1e-4
        assert abs(result.top_left_x - 587036.384) < 1e-3
        assert abs(result.top_left_y - 5870363.772) < 1e-3

    def test_parse_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            parse_world_file(tmp_path / "missing.jgw")

    def test_parse_too_few_lines(self, tmp_path: Path) -> None:
        wf = tmp_path / "short.jgw"
        wf.write_text("1.0\n2.0\n3.0\n")
        with pytest.raises(ValueError, match="at least 6 lines"):
            parse_world_file(wf)

    def test_parse_non_numeric(self, tmp_path: Path) -> None:
        wf = tmp_path / "bad.jgw"
        wf.write_text("abc\n0\n0\n-1\n0\n0\n")
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_world_file(wf)


class TestComputeBoundsFromWorldFile:
    def test_known_bounds(self) -> None:
        wf = WorldFileParams(
            pixel_size_x=0.01,
            rotation_y=0.0,
            rotation_x=0.0,
            pixel_size_y=-0.01,
            top_left_x=7.0,
            top_left_y=47.0,
        )
        lat_min, lon_min, lat_max, lon_max = compute_bounds_from_world_file(
            wf, width=100, height=100
        )
        assert abs(lon_min - 7.0) < 1e-6
        assert abs(lat_max - 47.0) < 1e-6
        assert abs(lon_max - 8.0) < 1e-6
        assert abs(lat_min - 46.0) < 1e-6

    def test_square_tile_256(self) -> None:
        wf = WorldFileParams(
            pixel_size_x=0.005,
            rotation_y=0.0,
            rotation_x=0.0,
            pixel_size_y=-0.005,
            top_left_x=5.0,
            top_left_y=48.0,
        )
        lat_min, lon_min, lat_max, lon_max = compute_bounds_from_world_file(
            wf, width=256, height=256
        )
        assert abs(lon_min - 5.0) < 1e-6
        assert abs(lat_max - 48.0) < 1e-6
        assert abs(lon_max - (5.0 + 0.005 * 256)) < 1e-6


class TestComputeBoundsFromTileCoords:
    def test_zoom0_tile00(self) -> None:
        """Zoom 0 tile (0,0) should cover the whole world (except polar regions)."""
        lat_min, lon_min, lat_max, lon_max = compute_bounds_from_tile_coords(0, 0, 0)
        assert abs(lon_min - (-180.0)) < 1e-6
        assert abs(lon_max - 180.0) < 1e-6
        assert lat_max > 85.0
        assert lat_min < -85.0

    def test_adjacent_tiles_touch(self) -> None:
        """Adjacent tiles should share boundaries."""
        _, lon_min1, _, lon_max1 = compute_bounds_from_tile_coords(0, 0, 5)
        _, lon_min2, _, lon_max2 = compute_bounds_from_tile_coords(1, 0, 5)
        assert abs(lon_max1 - lon_min2) < 1e-6

        lat_min1, _, lat_max1, _ = compute_bounds_from_tile_coords(0, 0, 5)
        lat_min2, _, lat_max2, _ = compute_bounds_from_tile_coords(0, 1, 5)
        assert abs(lat_min1 - lat_max2) < 1e-6


# ===================================================================
# 5.2-5.5 – TileCacheReader tests
# ===================================================================


class TestTileCacheReader:
    def test_jpeg_passthrough(self, tmp_path: Path) -> None:
        """JPEG passthrough: return raw bytes when no quality change."""
        jpeg_bytes = _make_jpeg()
        tile = tmp_path / "tile.jpeg"
        tile.write_bytes(jpeg_bytes)

        # Write world file
        _write_world_file(
            tile.with_suffix(".jgw"),
            pixel_size_x=0.01,
            pixel_size_y=-0.01,
            top_left_x=7.0,
            top_left_y=47.0,
        )

        reader = TileCacheReader()
        result_bytes, bounds = reader.read_tile(tile)
        assert result_bytes == jpeg_bytes  # Exact passthrough
        assert len(bounds) == 4

    def test_jpeg_with_quality_change(self, tmp_path: Path) -> None:
        """JPEG with quality change: re-encode at new quality."""
        jpeg_bytes = _make_jpeg()
        tile = tmp_path / "tile.jpeg"
        tile.write_bytes(jpeg_bytes)

        _write_world_file(
            tile.with_suffix(".jgw"),
            pixel_size_x=0.01,
            pixel_size_y=-0.01,
            top_left_x=7.0,
            top_left_y=47.0,
        )

        reader = TileCacheReader(target_quality=50)
        result_bytes, bounds = reader.read_tile(tile)
        assert result_bytes != jpeg_bytes  # Re-encoded
        assert len(result_bytes) > 0

    def test_png_to_jpeg_conversion(self, tmp_path: Path) -> None:
        """PNG tiles should be converted to JPEG."""
        png_bytes = _make_png()
        tile = tmp_path / "tile.png"
        tile.write_bytes(png_bytes)

        _write_world_file(
            tile.with_suffix(".pgw"),
            pixel_size_x=0.01,
            pixel_size_y=-0.01,
            top_left_x=7.0,
            top_left_y=47.0,
        )

        reader = TileCacheReader()
        result_bytes, bounds = reader.read_tile(tile)
        # Should be JPEG bytes (starts with FF D8)
        assert result_bytes[:2] == b"\xff\xd8"
        assert len(bounds) == 4

    def test_fallback_bounds_without_world_file(self, tmp_path: Path) -> None:
        """Without world file, bounds should come from tile coords."""
        jpeg_bytes = _make_jpeg()
        tile = tmp_path / "tile.jpeg"
        tile.write_bytes(jpeg_bytes)
        # No world file

        reader = TileCacheReader()
        result_bytes, bounds = reader.read_tile(tile, x=541, y=362, zoom=10)

        lat_min, lon_min, lat_max, lon_max = bounds
        assert lon_min < lon_max
        assert lat_min < lat_max
        # Tile (541, 362, z=10) should be in a reasonable range
        assert -180 <= lon_min <= 180
        assert -90 <= lat_min <= 90

    def test_missing_tile_raises(self, tmp_path: Path) -> None:
        reader = TileCacheReader()
        with pytest.raises(FileNotFoundError, match="Tile not found"):
            reader.read_tile(tmp_path / "missing.jpeg")

    def test_no_world_file_no_coords_raises(self, tmp_path: Path) -> None:
        """Without world file or tile coords, should raise ValueError."""
        tile = tmp_path / "tile.jpeg"
        tile.write_bytes(_make_jpeg())

        reader = TileCacheReader()
        with pytest.raises(ValueError, match="Cannot compute bounds"):
            reader.read_tile(tile)
