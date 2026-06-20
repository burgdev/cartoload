"""Tests for build summary: tile grid pre-computation, cache status scan, summary formatting."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from cartoload.config import LayerConfig
from cartoload.source.wmts.download import WmtsDownloader
from cartoload.processor.summary import (
    _FALLBACK_TILE_SIZE_BYTES,
    BuildSummary,
    ZoomSummary,
    _sample_tile_size,
    compute_build_summary,
    format_build_summary,
    print_build_summary,
)


def _make_jpeg(color: tuple = (128, 128, 128), quality: int = 85) -> bytes:
    """Create a JPEG tile. Uses random-ish noise for realistic compression."""
    import random

    random.seed(42)
    img = Image.new("RGB", (256, 256))
    pixels = []
    for i in range(256 * 256):
        r = (color[0] + random.randint(-50, 50)) % 256
        g = (color[1] + random.randint(-50, 50)) % 256
        b = (color[2] + random.randint(-50, 50)) % 256
        pixels.append((r, g, b))
    img.putdata(pixels)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# ZoomSummary unit tests
# ---------------------------------------------------------------------------


class TestZoomSummary:
    def test_to_process(self):
        z = ZoomSummary(zoom=10, total_tiles=100, cached_tiles=30)
        assert z.to_process == 70

    def test_to_process_all_cached(self):
        z = ZoomSummary(zoom=12, total_tiles=50, cached_tiles=50)
        assert z.to_process == 0


class TestBuildSummary:
    def test_total_tiles(self):
        s = BuildSummary(
            layer_id="test",
            zooms=[
                ZoomSummary(zoom=10, total_tiles=100),
                ZoomSummary(zoom=12, total_tiles=400),
            ],
        )
        assert s.total_tiles == 500

    def test_cached_tiles(self):
        s = BuildSummary(
            layer_id="test",
            zooms=[
                ZoomSummary(zoom=10, total_tiles=100, cached_tiles=80),
                ZoomSummary(zoom=12, total_tiles=400, cached_tiles=200),
            ],
        )
        assert s.cached_tiles == 280

    def test_to_process(self):
        s = BuildSummary(
            layer_id="test",
            zooms=[
                ZoomSummary(zoom=10, total_tiles=100, cached_tiles=80),
                ZoomSummary(zoom=12, total_tiles=400, cached_tiles=200),
            ],
        )
        assert s.to_process == 220

    def test_all_cached_true(self):
        s = BuildSummary(
            layer_id="test",
            zooms=[
                ZoomSummary(zoom=10, total_tiles=10, cached_tiles=10),
            ],
        )
        assert s.all_cached is True

    def test_all_cached_false_when_none_cached(self):
        s = BuildSummary(
            layer_id="test",
            zooms=[
                ZoomSummary(zoom=10, total_tiles=10, cached_tiles=0),
            ],
        )
        assert s.all_cached is False

    def test_all_cached_false_when_empty(self):
        s = BuildSummary(layer_id="test")
        assert s.all_cached is False

    def test_estimated_output_size_default(self):
        s = BuildSummary(
            layer_id="test",
            zooms=[
                ZoomSummary(zoom=10, total_tiles=100),
            ],
        )
        # Default _avg_tile_bytes is the fallback
        assert s.estimated_output_size == 100 * _FALLBACK_TILE_SIZE_BYTES

    def test_estimated_output_size_with_sampled_avg(self):
        s = BuildSummary(
            layer_id="test",
            zooms=[
                ZoomSummary(zoom=10, total_tiles=100),
            ],
            _avg_tile_bytes=15_000,
        )
        assert s.estimated_output_size == 1_500_000


# ---------------------------------------------------------------------------
# compute_build_summary tests
# ---------------------------------------------------------------------------


class TestComputeBuildSummary:
    def test_empty_zoom_levels(self, tmp_path: Path):
        layer = LayerConfig(id="test", name="Test")
        dl = WmtsDownloader(
            source_id="src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=tmp_path,
        )
        summary = compute_build_summary(layer, dl)
        assert len(summary.zooms) == 0
        assert summary.total_tiles == 0

    def test_zoom_with_bounds(self, tmp_path: Path):
        layer = LayerConfig(
            id="test",
            name="Test",
            zoom_levels=[10],
            bounds={"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5},
        )
        dl = WmtsDownloader(
            source_id="src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=tmp_path,
        )
        summary = compute_build_summary(layer, dl)
        assert len(summary.zooms) == 1
        assert summary.zooms[0].total_tiles > 0
        assert summary.zooms[0].cached_tiles == 0

    def test_cached_tiles_counted(self, tmp_path: Path):
        layer = LayerConfig(
            id="test",
            name="Test",
            zoom_levels=[10],
            bounds={"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5},
        )
        dl = WmtsDownloader(
            source_id="src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=tmp_path,
        )
        # Pre-create one cached tile
        from cartoload.pipeline import _compute_tile_coords

        coords = _compute_tile_coords(layer, 10)
        if coords:
            x, y = coords[0]
            cache_path = dl._cache_path(x, y, 10)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(b"fake tile")

        summary = compute_build_summary(layer, dl)
        assert summary.zooms[0].cached_tiles >= 1

    def test_quality_affects_estimate_with_cached_tiles(self, tmp_path: Path):
        """Cached tiles are re-encoded at target quality for estimation."""
        layer = LayerConfig(
            id="test",
            name="Test",
            zoom_levels=[10],
            bounds={"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5},
        )
        dl = WmtsDownloader(
            source_id="src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=tmp_path,
        )
        from cartoload.pipeline import _compute_tile_coords

        coords = _compute_tile_coords(layer, 10)
        # Write real JPEG tiles to cache
        for x, y in coords[:3]:
            cache_path = dl._cache_path(x, y, 10)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(_make_jpeg(quality=95))

        summary_low = compute_build_summary(layer, dl, quality=30)
        summary_high = compute_build_summary(layer, dl, quality=95)

        # Low quality should produce smaller estimate than high quality
        assert summary_low.estimated_output_size < summary_high.estimated_output_size
        # Both should be reasonable (not the fallback)
        assert summary_low._avg_tile_bytes < _FALLBACK_TILE_SIZE_BYTES
        assert summary_high._avg_tile_bytes > 0

    def test_no_cached_tiles_uses_fallback(self, tmp_path: Path):
        """When no tiles are cached and download is not possible, use fallback."""
        layer = LayerConfig(
            id="test",
            name="Test",
            zoom_levels=[10],
            bounds={"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5},
        )
        dl = WmtsDownloader(
            source_id="src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=tmp_path,
        )
        # No tiles cached, download will fail (no real server)
        summary = compute_build_summary(layer, dl, quality=85)
        assert summary._avg_tile_bytes == _FALLBACK_TILE_SIZE_BYTES


# ---------------------------------------------------------------------------
# _sample_tile_size tests
# ---------------------------------------------------------------------------


class TestSampleTileSize:
    def test_returns_int_for_valid_jpeg(self, tmp_path: Path):
        tile = tmp_path / "tile.jpeg"
        tile.write_bytes(_make_jpeg(quality=85))
        result = _sample_tile_size([tile], quality=85)
        assert isinstance(result, int)
        assert result > 0

    def test_low_quality_smaller_than_high(self, tmp_path: Path):
        tile = tmp_path / "tile.jpeg"
        tile.write_bytes(_make_jpeg(quality=95))
        low = _sample_tile_size([tile], quality=30)
        high = _sample_tile_size([tile], quality=95)
        assert low < high

    def test_returns_fallback_on_corrupt_file(self, tmp_path: Path):
        tile = tmp_path / "tile.jpeg"
        tile.write_bytes(b"not a real image")
        result = _sample_tile_size([tile], quality=85)
        assert result == _FALLBACK_TILE_SIZE_BYTES

    def test_returns_fallback_on_empty_list(self):
        result = _sample_tile_size([], quality=85)
        assert result == _FALLBACK_TILE_SIZE_BYTES


# ---------------------------------------------------------------------------
# format_build_summary tests
# ---------------------------------------------------------------------------


class TestFormatBuildSummary:
    def test_basic_format(self):
        summary = BuildSummary(
            layer_id="switzerland",
            zooms=[
                ZoomSummary(zoom=10, total_tiles=25, cached_tiles=10),
                ZoomSummary(zoom=12, total_tiles=100, cached_tiles=80),
            ],
        )
        text = format_build_summary(summary)

        assert "switzerland" in text
        assert "Zoom" in text
        assert "Tiles" in text
        assert "Cached" in text
        assert "To process" in text
        assert "25" in text
        assert "100" in text
        assert "Total" in text

    def test_fast_build_message(self):
        summary = BuildSummary(
            layer_id="test",
            zooms=[
                ZoomSummary(zoom=10, total_tiles=10, cached_tiles=10),
            ],
        )
        text = format_build_summary(summary, fast_build=True)
        assert "Fast build expected" in text

    def test_estimated_output_size_shown(self):
        summary = BuildSummary(
            layer_id="test",
            zooms=[
                ZoomSummary(zoom=10, total_tiles=100),
            ],
        )
        text = format_build_summary(summary)
        assert "Estimated output size" in text


# ---------------------------------------------------------------------------
# print_build_summary tests (Rich console)
# ---------------------------------------------------------------------------


class TestPrintBuildSummary:
    def test_prints_to_console(self):
        summary = BuildSummary(
            layer_id="test",
            zooms=[
                ZoomSummary(zoom=10, total_tiles=50, cached_tiles=20),
            ],
        )
        # Capture Rich output
        from rich.console import Console

        buf = io.StringIO()
        console = Console(file=buf, force_terminal=True)
        print_build_summary(summary, console=console)

        output = buf.getvalue()
        assert "test" in output
        assert "50" in output
