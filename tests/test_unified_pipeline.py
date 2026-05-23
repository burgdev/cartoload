"""Integration tests for the unified pipeline: build_target with TargetConfig.

Tests the full pipeline from config resolution through export for:
- Single-layer targets (WMTS format, the only format that works without
  external dependencies like GDAL/fiona)
- Multi-layer composite targets (multiple WMTS layers)
- TargetConfig resolution (zoom_levels, bounds inheritance)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from cartoload.config import (
    LayerConfig,
    SourceConfig,
    TargetConfig,
    TargetLayerEntry,
)
from cartoload.source.wmts.download import WmtsDownloader
from cartoload.pipeline import _compute_tile_coords
from cartoload.processor.pipeline import build_target

from helpers import write_tile_with_world_file as _write_tile_with_world_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cache_tiles_for_bounds(
    cache_dir: Path, bounds: dict, zoom: int, source_id: str = "wmts_src"
) -> list[tuple[int, int]]:
    """Pre-cache WMTS tiles for the given bounds and return coordinates."""
    layer = LayerConfig(
        id="_helper",
        name="helper",
        source=source_id,
        format="wmts",
        zoom_levels=[zoom],
        bounds=bounds,
    )
    dl = WmtsDownloader(
        source_id=source_id,
        url_template="https://example.com/{z}/{x}/{y}.jpeg",
        cache_dir=cache_dir,
        delay_ms=0,
        crs="EPSG:4326",
    )
    coords = _compute_tile_coords(layer, zoom)
    for x, y in coords:
        tile_path = dl._cache_path(x, y, zoom)
        _write_tile_with_world_file(tile_path)
    return coords


def _make_wmts_source(source_id: str = "wmts_src") -> SourceConfig:
    return SourceConfig(
        id=source_id,
        type="wmts",
        urls=["https://example.com/{z}/{x}/{y}.jpeg"],
        crs="EPSG:4326",
    )


# ---------------------------------------------------------------------------
# Single-layer target tests
# ---------------------------------------------------------------------------


class TestSingleLayerTarget:
    """Integration tests for single-layer WMTS targets via build_target."""

    def test_single_wmts_target(self, tmp_path: Path) -> None:
        """Single WMTS layer target should produce an IMG file."""
        cache_dir = tmp_path / "cache"
        output_dir = tmp_path / "output"
        bounds = {"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5}

        # Create layer and source configs
        layer = LayerConfig(
            id="basemap",
            name="Basemap",
            source="wmts_src",
            format="wmts",
            zoom_levels=[10],
            bounds=bounds,
        )
        source = _make_wmts_source()
        target = TargetConfig(
            id="basemap_target",
            name="Basemap Target",
            output="basemap.img",
            layers=[TargetLayerEntry(ref="basemap")],
            zoom_levels=[10],
            bounds=bounds,
        )

        # Pre-cache tiles
        _cache_tiles_for_bounds(cache_dir, bounds, 10)

        result = asyncio.run(
            build_target(
                target,
                {"basemap": layer},
                {"wmts_src": source},
                cache_dir,
                output_dir,
                no_download=True,
            )
        )

        assert len(result) == 1
        assert result[0].exists()
        assert result[0].stat().st_size > 0

    def test_single_target_inherits_zoom_levels(self, tmp_path: Path) -> None:
        """Target without zoom_levels should inherit from referenced layers."""
        cache_dir = tmp_path / "cache"
        output_dir = tmp_path / "output"
        bounds = {"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5}

        layer = LayerConfig(
            id="basemap",
            name="Basemap",
            source="wmts_src",
            format="wmts",
            zoom_levels=[10],
            bounds=bounds,
        )
        source = _make_wmts_source()
        target = TargetConfig(
            id="inherited_zoom",
            output="inherited.img",
            layers=[TargetLayerEntry(ref="basemap")],
            # zoom_levels intentionally omitted — should be inherited
            bounds=bounds,
        )

        _cache_tiles_for_bounds(cache_dir, bounds, 10)

        result = asyncio.run(
            build_target(
                target,
                {"basemap": layer},
                {"wmts_src": source},
                cache_dir,
                output_dir,
                no_download=True,
            )
        )

        assert len(result) == 1
        assert result[0].exists()

    def test_single_target_inherits_bounds(self, tmp_path: Path) -> None:
        """Target without bounds should inherit from file/layers."""
        cache_dir = tmp_path / "cache"
        output_dir = tmp_path / "output"
        bounds = {"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5}

        layer = LayerConfig(
            id="basemap",
            name="Basemap",
            source="wmts_src",
            format="wmts",
            zoom_levels=[10],
            bounds=bounds,
        )
        source = _make_wmts_source()
        target = TargetConfig(
            id="inherited_bounds",
            output="inherited_bounds.img",
            layers=[TargetLayerEntry(ref="basemap")],
            zoom_levels=[10],
            # bounds intentionally omitted — should be inherited
        )

        _cache_tiles_for_bounds(cache_dir, bounds, 10)

        result = asyncio.run(
            build_target(
                target,
                {"basemap": layer},
                {"wmts_src": source},
                cache_dir,
                output_dir,
                no_download=True,
            )
        )

        assert len(result) == 1
        assert result[0].exists()


# ---------------------------------------------------------------------------
# Multi-layer composite target tests
# ---------------------------------------------------------------------------


class TestCompositeTarget:
    """Integration tests for multi-layer composite targets."""

    def test_two_layer_composite(self, tmp_path: Path) -> None:
        """Two WMTS layers composited should produce an IMG file."""
        cache_dir = tmp_path / "cache"
        output_dir = tmp_path / "output"
        bounds = {"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5}

        basemap = LayerConfig(
            id="basemap",
            name="Basemap",
            source="wmts_src",
            format="wmts",
            zoom_levels=[10],
            bounds=bounds,
        )
        overlay = LayerConfig(
            id="overlay",
            name="Overlay",
            source="wmts_src",
            format="wmts",
            zoom_levels=[10],
            bounds=bounds,
        )
        source = _make_wmts_source()
        target = TargetConfig(
            id="composite_target",
            name="Composite",
            output="composite.img",
            layers=[
                TargetLayerEntry(ref="basemap"),
                TargetLayerEntry(ref="overlay"),
            ],
            zoom_levels=[10],
            bounds=bounds,
        )

        _cache_tiles_for_bounds(cache_dir, bounds, 10)

        result = asyncio.run(
            build_target(
                target,
                {"basemap": basemap, "overlay": overlay},
                {"wmts_src": source},
                cache_dir,
                output_dir,
                no_download=True,
            )
        )

        assert len(result) == 1
        assert result[0].exists()
        assert result[0].stat().st_size > 0

    def test_composite_with_opacity(self, tmp_path: Path) -> None:
        """Composite with opacity on overlay should produce an IMG file."""
        cache_dir = tmp_path / "cache"
        output_dir = tmp_path / "output"
        bounds = {"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5}

        basemap = LayerConfig(
            id="basemap",
            name="Basemap",
            source="wmts_src",
            format="wmts",
            zoom_levels=[10],
            bounds=bounds,
        )
        overlay = LayerConfig(
            id="overlay",
            name="Overlay",
            source="wmts_src",
            format="wmts",
            zoom_levels=[10],
            bounds=bounds,
        )
        source = _make_wmts_source()
        target = TargetConfig(
            id="opacity_target",
            output="opacity.img",
            layers=[
                TargetLayerEntry(ref="basemap"),
                TargetLayerEntry(ref="overlay", opacity={10: 0.5}),
            ],
            zoom_levels=[10],
            bounds=bounds,
        )

        _cache_tiles_for_bounds(cache_dir, bounds, 10)

        result = asyncio.run(
            build_target(
                target,
                {"basemap": basemap, "overlay": overlay},
                {"wmts_src": source},
                cache_dir,
                output_dir,
                no_download=True,
            )
        )

        assert len(result) == 1
        assert result[0].exists()

    def test_composite_zoom_level_override(self, tmp_path: Path) -> None:
        """Layer entries with zoom_level overrides should only render at those zooms."""
        cache_dir = tmp_path / "cache"
        output_dir = tmp_path / "output"
        bounds = {"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5}

        basemap = LayerConfig(
            id="basemap",
            name="Basemap",
            source="wmts_src",
            format="wmts",
            zoom_levels=[10, 11],
            bounds=bounds,
        )
        overlay = LayerConfig(
            id="overlay",
            name="Overlay",
            source="wmts_src",
            format="wmts",
            zoom_levels=[10, 11],
            bounds=bounds,
        )
        source = _make_wmts_source()
        target = TargetConfig(
            id="zoom_override_target",
            output="zoom_override.img",
            layers=[
                TargetLayerEntry(ref="basemap"),
                # Overlay only at zoom 11
                TargetLayerEntry(ref="overlay", zoom_levels=[11]),
            ],
            zoom_levels=[10, 11],
            bounds=bounds,
        )

        _cache_tiles_for_bounds(cache_dir, bounds, 10)
        _cache_tiles_for_bounds(cache_dir, bounds, 11)

        result = asyncio.run(
            build_target(
                target,
                {"basemap": basemap, "overlay": overlay},
                {"wmts_src": source},
                cache_dir,
                output_dir,
                no_download=True,
            )
        )

        assert len(result) == 1
        assert result[0].exists()


# ---------------------------------------------------------------------------
# Inline layer entries
# ---------------------------------------------------------------------------


class TestInlineLayerEntries:
    """Test targets with inline layer definitions (no ref)."""

    def test_inline_wmts_entry(self, tmp_path: Path) -> None:
        """Target with inline WMTS layer definition should work."""
        cache_dir = tmp_path / "cache"
        output_dir = tmp_path / "output"
        bounds = {"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5}

        source = _make_wmts_source()
        target = TargetConfig(
            id="inline_target",
            output="inline.img",
            layers=[
                TargetLayerEntry(
                    name="Inline Basemap",
                    source="wmts_src",
                    format="wmts",
                    zoom_levels=[10],
                )
            ],
            zoom_levels=[10],
            bounds=bounds,
        )

        _cache_tiles_for_bounds(cache_dir, bounds, 10)

        result = asyncio.run(
            build_target(
                target,
                {},  # no layer definitions — fully inline
                {"wmts_src": source},
                cache_dir,
                output_dir,
                no_download=True,
            )
        )

        assert len(result) == 1
        assert result[0].exists()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestBuildTargetErrors:
    """Test error conditions in build_target."""

    def test_missing_source_raises(self, tmp_path: Path) -> None:
        """Target referencing missing source should raise PipelineError."""
        from cartoload.pipeline import PipelineError

        layer = LayerConfig(
            id="l",
            name="L",
            source="missing_src",
            format="wmts",
            zoom_levels=[10],
            bounds={"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5},
        )
        target = TargetConfig(
            id="t",
            output="out.img",
            layers=[TargetLayerEntry(ref="l")],
            zoom_levels=[10],
            bounds={"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5},
        )

        with pytest.raises(PipelineError, match="unknown source"):
            asyncio.run(
                build_target(
                    target,
                    {"l": layer},
                    {},  # empty sources
                    tmp_path / "cache",
                    tmp_path / "output",
                )
            )

    def test_missing_layer_ref_raises(self, tmp_path: Path) -> None:
        """Target referencing missing layer should raise PipelineError."""
        from cartoload.pipeline import PipelineError

        target = TargetConfig(
            id="t",
            output="out.img",
            layers=[TargetLayerEntry(ref="nonexistent")],
            zoom_levels=[10],
            bounds={"west": 7.0, "east": 7.5, "south": 46.0, "north": 46.5},
        )

        with pytest.raises(PipelineError, match="references unknown layer"):
            asyncio.run(
                build_target(
                    target,
                    {},  # no layers defined
                    {},
                    tmp_path / "cache",
                    tmp_path / "output",
                )
            )
