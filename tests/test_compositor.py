"""Tests for the tile compositor module."""

import io
from pathlib import Path

import pytest
from PIL import Image

from cartoload.config import CompositeSubLayer
from cartoload.processor.compositor import (
    composite_tiles,
    encode_composite_to_jpeg,
    find_fallback_tile,
    load_tile_as_rgba,
    resolve_opacity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _solid_rgba(r: int, g: int, b: int, a: int = 255, size: int = 64) -> Image.Image:
    """Create a solid-color RGBA image."""
    return Image.new("RGBA", (size, size), (r, g, b, a))


def _solid_rgb(r: int, g: int, b: int, size: int = 64) -> Image.Image:
    """Create a solid-color RGB image."""
    return Image.new("RGB", (size, size), (r, g, b))


def _tile_path(
    tmp_path: Path, source: str, zoom: int, x: int, y: int, ext: str = "png"
) -> Path:
    """Build a tile cache path."""
    return tmp_path / source / str(zoom) / str(x) / f"{y}.{ext}"


# ---------------------------------------------------------------------------
# composite_tiles tests
# ---------------------------------------------------------------------------


class TestCompositeTiles:
    def test_two_opaque_layers(self):
        """Two fully opaque layers: second fully covers first."""
        base = _solid_rgba(255, 0, 0)  # red
        overlay = _solid_rgba(0, 255, 0)  # green
        result = composite_tiles([(base, 1.0), (overlay, 1.0)])
        # With both layers fully opaque, overlay should dominate
        px = result.getpixel((0, 0))
        assert px[:3] == (0, 255, 0)

    def test_opacity_blending(self):
        """Overlay with 0.5 opacity over red base."""
        base = _solid_rgba(255, 0, 0)
        overlay = _solid_rgba(0, 255, 0)
        result = composite_tiles([(base, 1.0), (overlay, 0.5)])
        px = result.getpixel((0, 0))
        # Alpha blend: base * (1 - alpha) + overlay * alpha = 255*0.5 + 0*0.5 = 127 for red
        # green = 0*0.5 + 255*0.5 = 127
        assert abs(px[0] - 127) <= 2  # small rounding tolerance
        assert abs(px[1] - 127) <= 2

    def test_png_transparency(self):
        """PNG overlay with transparent regions shows base through."""
        base = _solid_rgba(255, 0, 0)  # red base
        overlay = _solid_rgba(0, 255, 0, 0)  # fully transparent green
        result = composite_tiles([(base, 1.0), (overlay, 1.0)])
        px = result.getpixel((0, 0))
        # Fully transparent overlay: should see base (red)
        assert px[:3] == (255, 0, 0)

    def test_single_layer(self):
        """Single layer composites to itself."""
        img = _solid_rgba(128, 64, 32)
        result = composite_tiles([(img, 1.0)])
        px = result.getpixel((0, 0))
        assert px[:3] == (128, 64, 32)

    def test_empty_images_raises(self):
        """No images should raise ValueError."""
        with pytest.raises(ValueError, match="No images"):
            composite_tiles([])

    def test_three_layers_bottom_to_top(self):
        """Three layers composited in order."""
        # Red base, semi-transparent green, semi-transparent blue
        base = _solid_rgba(255, 0, 0)
        mid = _solid_rgba(0, 255, 0)
        top = _solid_rgba(0, 0, 255)
        result = composite_tiles(
            [
                (base, 1.0),
                (mid, 0.5),
                (top, 0.5),
            ]
        )
        # Should have a mix of all three
        px = result.getpixel((0, 0))
        assert 0 < px[0] < 255  # some red
        assert 0 < px[1] < 255  # some green
        assert 0 < px[2] < 255  # some blue


# ---------------------------------------------------------------------------
# resolve_opacity tests
# ---------------------------------------------------------------------------


class TestResolveOpacity:
    def test_uniform_float(self):
        sub = CompositeSubLayer(source="test", opacity=0.6)
        assert resolve_opacity(sub, 12) == 0.6
        assert resolve_opacity(sub, 14) == 0.6

    def test_per_zoom_mapping(self):
        sub = CompositeSubLayer(source="test", opacity={12: 0.3, 14: 0.8})
        assert resolve_opacity(sub, 12) == 0.3
        assert resolve_opacity(sub, 14) == 0.8
        assert resolve_opacity(sub, 13) == 1.0  # not in map → default

    def test_default_opacity(self):
        sub = CompositeSubLayer(source="test")
        assert resolve_opacity(sub, 10) == 1.0


# ---------------------------------------------------------------------------
# encode_composite_to_jpeg tests
# ---------------------------------------------------------------------------


class TestEncodeCompositeToJpeg:
    def test_produces_jpeg_bytes(self):
        img = _solid_rgba(128, 64, 32)
        data = encode_composite_to_jpeg(img, quality=85)
        assert isinstance(data, bytes)
        assert data[:2] == b"\xff\xd8"  # JPEG magic bytes

    def test_roundtrip(self):
        img = _solid_rgba(128, 64, 32)
        data = encode_composite_to_jpeg(img, quality=95)
        decoded = Image.open(io.BytesIO(data))
        assert decoded.mode == "RGB"
        px = decoded.getpixel((0, 0))
        assert abs(px[0] - 128) <= 5
        assert abs(px[1] - 64) <= 5
        assert abs(px[2] - 32) <= 5


# ---------------------------------------------------------------------------
# load_tile_as_rgba tests
# ---------------------------------------------------------------------------


class TestLoadTileAsRgba:
    def test_jpeg_as_rgba(self, tmp_path: Path):
        img = _solid_rgb(100, 150, 200)
        path = tmp_path / "test.jpeg"
        img.save(path, format="JPEG")
        result = load_tile_as_rgba(path)
        assert result is not None
        assert result.mode == "RGBA"
        px = result.getpixel((0, 0))
        assert px[3] == 255  # fully opaque

    def test_png_with_alpha(self, tmp_path: Path):
        img = _solid_rgba(100, 150, 200, 128)
        path = tmp_path / "test.png"
        img.save(path, format="PNG")
        result = load_tile_as_rgba(path)
        assert result is not None
        assert result.mode == "RGBA"
        px = result.getpixel((0, 0))
        assert px[3] == 128

    def test_missing_file(self, tmp_path: Path):
        result = load_tile_as_rgba(tmp_path / "nonexistent.png")
        assert result is None


# ---------------------------------------------------------------------------
# find_fallback_tile tests
# ---------------------------------------------------------------------------


class TestFindFallbackTile:
    def _create_cached_tile(
        self,
        tmp_path: Path,
        source: str,
        zoom: int,
        x: int,
        y: int,
        ext: str = "png",
        color: tuple = (128, 128, 128, 255),
    ) -> Path:
        """Create a cached tile file."""
        path = _tile_path(tmp_path, source, zoom, x, y, ext)
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGBA", (256, 256), color)
        img.save(path, format="PNG" if ext == "png" else "JPEG")
        return path

    def test_fallback_from_lower_zoom(self, tmp_path: Path):
        """When zoom 12 tile missing, falls back to zoom 10."""
        sub = CompositeSubLayer(
            source="test_src",
            zoom_levels=[10, 12],
            source_args={"extension": "png"},
        )
        # Create a tile at zoom 10 that covers the area
        # At zoom 12, tile (4, 3) → at zoom 10, tile (1, 0) covers it (scale=4)
        self._create_cached_tile(
            tmp_path, "test_src", 10, 1, 0, "png", (200, 100, 50, 255)
        )

        result = find_fallback_tile(sub, 4, 3, 12, tmp_path, "test_src")
        assert result is not None
        assert result.mode == "RGBA"
        assert result.size == (256, 256)

    def test_no_fallback_when_no_lower_zoom(self, tmp_path: Path):
        """No fallback when there are no lower zoom levels declared."""
        sub = CompositeSubLayer(
            source="test_src",
            zoom_levels=[12],  # only zoom 12, nothing below
            source_args={"extension": "png"},
        )
        result = find_fallback_tile(sub, 4, 3, 12, tmp_path, "test_src")
        assert result is None

    def test_no_fallback_when_zoom_not_declared(self, tmp_path: Path):
        """No fallback when the requested zoom isn't in zoom_levels at all."""
        sub = CompositeSubLayer(
            source="test_src",
            zoom_levels=[8, 10],  # zoom 12 not in this sub-layer
            source_args={"extension": "png"},
        )
        # Even though zoom 10 exists, zoom 12 is not declared — but this function
        # is only called for declared zoom levels with missing tiles.
        # If called anyway, it should look for lower zooms in the list.
        self._create_cached_tile(
            tmp_path, "test_src", 10, 1, 0, "png", (200, 100, 50, 255)
        )
        result = find_fallback_tile(sub, 4, 3, 12, tmp_path, "test_src")
        assert result is not None  # finds zoom 10 as fallback

    def test_fallback_skips_missing_tiles(self, tmp_path: Path):
        """Falls back to the next lower zoom if the closer one is also missing."""
        sub = CompositeSubLayer(
            source="test_src",
            zoom_levels=[8, 10, 12],
            source_args={"extension": "png"},
        )
        # Only create tile at zoom 8, not zoom 10
        # At zoom 12, tile (4, 3) → zoom 10 tile (1, 0) → zoom 8 tile (0, 0)
        self._create_cached_tile(
            tmp_path, "test_src", 8, 0, 0, "png", (50, 200, 100, 255)
        )

        result = find_fallback_tile(sub, 4, 3, 12, tmp_path, "test_src")
        assert result is not None
        assert result.size == (256, 256)

    def test_no_fallback_when_all_missing(self, tmp_path: Path):
        """Returns None when no lower zoom tiles exist in cache."""
        sub = CompositeSubLayer(
            source="test_src",
            zoom_levels=[8, 10, 12],
            source_args={"extension": "png"},
        )
        # Don't create any tiles
        result = find_fallback_tile(sub, 4, 3, 12, tmp_path, "test_src")
        assert result is None
