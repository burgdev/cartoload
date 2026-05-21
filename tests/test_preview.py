"""Tests for preview image generation: center computation, adaptive grid, mosaic assembly, output."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from cartoload.config import LayerConfig
from cartoload.downloader.wmts.download import WMTSDownloader
from cartoload.processor.preview import (
    assemble_preview,
    compute_preview_center,
    compute_preview_grid,
    generate_previews,
)
from cartoload.pipeline import _compute_tile_coords


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jpeg(
    width: int = 256, height: int = 256, color: tuple = (128, 128, 128)
) -> bytes:
    """Create a minimal JPEG image."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _cache_tiles(
    dl: WMTSDownloader,
    coords: list[tuple[int, int]],
    zoom: int,
) -> None:
    """Write fake JPEG tiles to the downloader's cache."""
    for i, (x, y) in enumerate(coords):
        path = dl._cache_path(x, y, zoom)
        path.parent.mkdir(parents=True, exist_ok=True)
        color = ((i * 30) % 256, (i * 60) % 256, (i * 90) % 256)
        path.write_bytes(_make_jpeg(color=color))


# ---------------------------------------------------------------------------
# compute_preview_center
# ---------------------------------------------------------------------------


class TestComputePreviewCenter:
    def test_center_of_bounds(self):
        lng, lat = compute_preview_center(
            {
                "west": 5.0,
                "east": 10.0,
                "south": 45.0,
                "north": 48.0,
            }
        )
        assert abs(lng - 7.5) < 1e-6
        assert abs(lat - 46.5) < 1e-6

    def test_center_of_square(self):
        lng, lat = compute_preview_center(
            {
                "west": 0.0,
                "east": 2.0,
                "south": 0.0,
                "north": 2.0,
            }
        )
        assert abs(lng - 1.0) < 1e-6
        assert abs(lat - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# compute_preview_grid
# ---------------------------------------------------------------------------


class TestComputePreviewGrid:
    def test_returns_subset(self):
        layer = LayerConfig(
            id="test",
            name="Test",
            zoom_levels=[10],
            bounds={"west": 5.0, "east": 10.0, "south": 45.0, "north": 48.0},
        )
        coords = compute_preview_grid(layer, 10, max_tiles=4)
        assert len(coords) <= 4
        assert len(coords) > 0

    def test_all_coords_when_few(self):
        """When total tiles <= max_tiles, return all."""
        layer = LayerConfig(
            id="test",
            name="Test",
            zoom_levels=[5],
            bounds={"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5},
        )
        all_coords = _compute_tile_coords(layer, 5)
        coords = compute_preview_grid(layer, 5, max_tiles=100)
        assert coords == all_coords

    def test_empty_bounds_returns_empty(self):
        layer = LayerConfig(id="test", name="Test")
        coords = compute_preview_grid(layer, 10)
        assert coords == []


# ---------------------------------------------------------------------------
# assemble_preview
# ---------------------------------------------------------------------------


class TestAssemblePreview:
    def test_single_tile(self, tmp_path: Path):
        dl = WMTSDownloader(
            source_id="src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=tmp_path,
        )
        coords = [(100, 200)]
        _cache_tiles(dl, coords, 10)

        result = assemble_preview(dl, coords, 10)
        assert result is not None
        assert result[:2] == b"\xff\xd8"  # JPEG magic

    def test_multiple_tiles(self, tmp_path: Path):
        dl = WMTSDownloader(
            source_id="src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=tmp_path,
        )
        coords = [(100, 200), (101, 200), (100, 201)]
        _cache_tiles(dl, coords, 10)

        result = assemble_preview(dl, coords, 10)
        assert result is not None
        # Mosaic should be larger than a single tile
        img = Image.open(io.BytesIO(result))
        assert img.width > 256 or img.height > 256

    def test_no_tiles_returns_none(self, tmp_path: Path):
        dl = WMTSDownloader(
            source_id="src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=tmp_path,
        )
        result = assemble_preview(dl, [(999, 999)], 10)
        assert result is None

    def test_empty_coords_returns_none(self, tmp_path: Path):
        dl = WMTSDownloader(
            source_id="src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=tmp_path,
        )
        result = assemble_preview(dl, [], 10)
        assert result is None


# ---------------------------------------------------------------------------
# generate_previews
# ---------------------------------------------------------------------------


class TestGeneratePreviews:
    def test_generates_preview_file(self, tmp_path: Path):
        dl = WMTSDownloader(
            source_id="src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=tmp_path / "cache",
            crs="EPSG:4326",
        )
        layer = LayerConfig(
            id="test_layer",
            name="Test",
            zoom_levels=[10],
            bounds={"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5},
        )
        # Cache some tiles
        coords = _compute_tile_coords(layer, 10)
        _cache_tiles(dl, coords[:3], 10)

        output_dir = tmp_path / "output"
        paths = generate_previews(layer, dl, output_dir)

        assert len(paths) >= 1
        assert paths[0].exists()
        assert paths[0].name == "test_layer_zoom10.jpg"
        assert paths[0].stat().st_size > 0

    def test_skips_zoom_with_no_tiles(self, tmp_path: Path):
        dl = WMTSDownloader(
            source_id="src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=tmp_path / "cache",
        )
        layer = LayerConfig(
            id="test_layer",
            name="Test",
            zoom_levels=[10, 12],
            bounds={"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5},
        )
        # Only cache tiles for zoom 10
        coords_10 = _compute_tile_coords(layer, 10)
        _cache_tiles(dl, coords_10[:3], 10)
        # No tiles for zoom 12

        output_dir = tmp_path / "output"
        paths = generate_previews(layer, dl, output_dir)

        # Should only have zoom 10 preview
        assert len(paths) == 1
        assert "zoom10" in paths[0].name

    def test_prefers_cached_tiles(self, tmp_path: Path):
        """When cached_coords is provided, only cached tiles are selected."""
        layer = LayerConfig(
            id="test",
            name="Test",
            zoom_levels=[10],
            bounds={"west": 7.0, "east": 9.0, "south": 46.0, "north": 48.0},
        )
        all_coords = _compute_tile_coords(layer, 10)
        if len(all_coords) <= 9:
            pytest.skip("Need enough tiles to test filtering")

        # Only cache the last 3 tiles
        cached = set(all_coords[-3:])
        result = compute_preview_grid(layer, 10, max_tiles=9, cached_coords=cached)
        assert len(result) > 0
        # All returned coords should be from the cached set
        for c in result:
            assert c in cached

    def test_output_location(self, tmp_path: Path):
        dl = WMTSDownloader(
            source_id="src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=tmp_path / "cache",
        )
        layer = LayerConfig(
            id="test",
            name="Test",
            zoom_levels=[10],
            bounds={"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5},
        )
        coords = _compute_tile_coords(layer, 10)
        _cache_tiles(dl, coords[:1], 10)

        output_dir = tmp_path / "output"
        paths = generate_previews(layer, dl, output_dir)

        assert len(paths) >= 1
        # Should be in previews/ subdirectory
        assert paths[0].parent.name == "previews"
