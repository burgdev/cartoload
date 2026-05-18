"""Tests for pipeline orchestration: factories, source resolution, build_layer."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest

from cartoload.config import LayerConfig, SourceConfig, TargetConfig
from cartoload.downloader.wmts import WMTSDownloader
from cartoload.exporters.garmin_img import GarminImgExporter
from cartoload.pipeline import (
    DownloadError,
    ExportError,
    PipelineError,
    ProcessingError,
    build_layer,
    get_downloader,
    get_exporter,
    resolve_source,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jpeg(width: int = 256, height: int = 256) -> bytes:
    """Create a minimal JPEG image."""
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _write_tile_with_world_file(
    tile_path: Path, top_left_x: float = 7.0, top_left_y: float = 47.0
) -> Path:
    """Write a JPEG tile + world file to the given path."""
    tile_path.parent.mkdir(parents=True, exist_ok=True)
    tile_path.write_bytes(_make_jpeg())
    wf = tile_path.with_suffix(".jgw")
    wf.write_text(f"0.01\n0.0\n0.0\n-0.01\n{top_left_x}\n{top_left_y}\n")
    return tile_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def stac_source() -> SourceConfig:
    return SourceConfig(
        id="swiss_topo",
        type="stac",
        urls=["https://stac.example.com/collections/${layer}"],
        defaults={"layer": "test_collection"},
    )


@pytest.fixture
def wmts_source() -> SourceConfig:
    return SourceConfig(
        id="wmts_src",
        type="wmts",
        urls=["https://tiles.example.com/{z}/{x}/{y}.png"],
    )


@pytest.fixture
def layer(wmts_source: SourceConfig) -> LayerConfig:
    return LayerConfig(
        id="test_layer",
        name="Test Layer",
        source=wmts_source.id,
        format="wmts",
        zoom_levels=[12, 14],
        bounds={"west": 5.0, "south": 45.0, "east": 10.0, "north": 48.0},
    )


@pytest.fixture
def sources(wmts_source: SourceConfig) -> dict[str, SourceConfig]:
    return {wmts_source.id: wmts_source}


# ---------------------------------------------------------------------------
# get_downloader factory
# ---------------------------------------------------------------------------


class TestGetDownloader:
    def test_stac_raises_pipeline_error(self, stac_source, tmp_path):
        """STAC sources cannot be handled by get_downloader (WMTS-only)."""
        with pytest.raises(PipelineError, match="only supports 'wmts'"):
            get_downloader(stac_source, tmp_path)

    def test_wmts_returns_wmts_downloader(self, wmts_source, tmp_path):
        from cartoload.downloader.wmts import WMTSDownloader

        dl = get_downloader(wmts_source, tmp_path)
        assert isinstance(dl, WMTSDownloader)

    def test_unknown_type_raises_pipeline_error(self, tmp_path):
        unknown_source = SourceConfig(id="bad", type="xyz", urls=["https://x"])
        with pytest.raises(PipelineError, match="only supports 'wmts'"):
            get_downloader(unknown_source, tmp_path)


# ---------------------------------------------------------------------------
# get_exporter factory
# ---------------------------------------------------------------------------


class TestGetExporter:
    def test_garmin_img_returns_exporter(self, tmp_path):
        exporter = get_exporter("garmin_img", tmp_path)
        assert isinstance(exporter, GarminImgExporter)

    def test_garmin_img_dash_variant(self, tmp_path):
        exporter = get_exporter("garmin-img", tmp_path)
        assert isinstance(exporter, GarminImgExporter)

    def test_garmin_img_from_target(self, tmp_path):
        target = TargetConfig(
            id="t",
            exporter="garmin_img",
            output="out.img",
            layers=[],
        )
        exporter = get_exporter(target, tmp_path)
        assert isinstance(exporter, GarminImgExporter)

    def test_unknown_exporter_raises(self, tmp_path):
        with pytest.raises(PipelineError, match="Unknown exporter"):
            get_exporter("unknown", tmp_path)


# ---------------------------------------------------------------------------
# resolve_source
# ---------------------------------------------------------------------------


class TestResolveSource:
    def test_found(self, layer, sources):
        result = resolve_source(layer, sources)
        assert result.id == "wmts_src"

    def test_missing_raises(self, layer):
        with pytest.raises(PipelineError, match="unknown source"):
            resolve_source(layer, {})

    def test_missing_with_available(self, layer):
        extra = SourceConfig(id="other", type="stac", urls=["https://x"])
        with pytest.raises(PipelineError, match="other"):
            resolve_source(layer, {"other": extra})


# ---------------------------------------------------------------------------
# _layer_to_target adapter
# ---------------------------------------------------------------------------


class TestLayerToTarget:
    def test_single_layer_adapter(self):
        from cartoload.pipeline import _layer_to_target

        layer = LayerConfig(
            id="test",
            name="Test Layer",
            source="src1",
            format="wmts",
            zoom_levels=[10, 12],
            bounds={"west": 5.0, "south": 45.0, "east": 10.0, "north": 48.0},
        )
        target = _layer_to_target(layer)

        assert isinstance(target, TargetConfig)
        assert target.id == "test"
        assert target.name == "Test Layer"
        assert target.output == "test.img"  # defaults to {id}.img
        assert target.exporter == "garmin_img"  # default
        assert target.zoom_levels == [10, 12]
        assert target.bounds == {
            "west": 5.0,
            "south": 45.0,
            "east": 10.0,
            "north": 48.0,
        }
        assert len(target.layers) == 1
        assert target.layers[0].source == "src1"
        assert target.layers[0].format == "wmts"

    def test_single_layer_default_output(self):
        from cartoload.pipeline import _layer_to_target

        layer = LayerConfig(
            id="my_layer",
            name="N",
            source="s",
            format="geotiff",
            zoom_levels=[10],
        )
        target = _layer_to_target(layer)
        assert target.output == "my_layer.img"
        assert target.exporter == "garmin_img"


# ---------------------------------------------------------------------------
# Source type attribute tests
# ---------------------------------------------------------------------------


class TestSourceTypeAttributes:
    def test_stac_source(self):
        source = SourceConfig(
            id="test",
            type="stac",
            urls=["https://stac.example.com/collections/test"],
        )
        assert source.type == "stac"

    def test_wmts_source(self):
        source = SourceConfig(
            id="test",
            type="wmts",
            urls=["https://example.com/{z}/{x}/{y}.png"],
        )
        assert source.type == "wmts"

    def test_path_source(self):
        source = SourceConfig(
            id="test",
            type="path",
            urls=["./cache/geotiffs/"],
        )
        assert source.type == "path"


# ---------------------------------------------------------------------------
# Error propagation via build_layer adapter
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    def test_source_resolution_error(self, tmp_path):
        """PipelineError from source resolution is re-raised."""
        layer = LayerConfig(
            id="l",
            name="n",
            source="missing",
            format="wmts",
            zoom_levels=[10],
        )
        with pytest.raises(PipelineError, match="unknown source"):
            asyncio.run(
                build_layer(
                    layer,
                    {},
                    tmp_path / "cache",
                    tmp_path / "output",
                )
            )

    def test_pipeline_error_passes_through(self, tmp_path):
        """PipelineError from factory should pass through without wrapping."""
        layer = LayerConfig(
            id="l",
            name="n",
            source="s",
            format="wmts",
            zoom_levels=[10],
        )
        with pytest.raises(PipelineError):
            asyncio.run(
                build_layer(
                    layer,
                    {},
                    tmp_path / "cache",
                    tmp_path / "output",
                )
            )


# ---------------------------------------------------------------------------
# Domain exception attributes
# ---------------------------------------------------------------------------


class TestDomainExceptions:
    def test_download_error_attributes(self):
        err = DownloadError("src1", "timeout")
        assert err.source_id == "src1"
        assert "src1" in str(err)
        assert "timeout" in str(err)

    def test_processing_error_attributes(self):
        err = ProcessingError("lyr1", "bad data")
        assert err.layer_id == "lyr1"
        assert "lyr1" in str(err)

    def test_export_error_attributes(self):
        err = ExportError("lyr1", "disk full")
        assert err.layer_id == "lyr1"

    def test_cause_chaining(self):
        original = ValueError("root cause")
        err = DownloadError("src", "fail", cause=original)
        assert err.__cause__ is original


# ---------------------------------------------------------------------------
# Integration: cache → IMG via build_layer adapter
# ---------------------------------------------------------------------------


class TestIntegrationCacheToImg:
    """Integration test: full pipeline from cached tiles to IMG output."""

    def test_wmts_cache_to_img(self, tmp_path: Path) -> None:
        """Cached WMTS tiles should be read, processed, and written to IMG."""
        cache_dir = tmp_path / "cache"
        output_dir = tmp_path / "output"

        bounds = {
            "west": 6.21,
            "east": 6.56,
            "south": 45.0,
            "north": 45.5,
        }

        dl = WMTSDownloader(
            source_id="wmts_src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=cache_dir,
            delay_ms=0,
            crs="EPSG:4326",
        )

        from cartoload.pipeline import _compute_tile_coords

        layer_for_coords = LayerConfig(
            id="test",
            name="Test",
            source="wmts_src",
            format="wmts",
            zoom_levels=[10],
            bounds=bounds,
        )
        coords = _compute_tile_coords(layer_for_coords, 10)
        assert len(coords) > 0, f"No tile coords for bounds {bounds}"

        for x, y in coords:
            tile_path = dl._cache_path(x, y, 10)
            _write_tile_with_world_file(tile_path)

        source = SourceConfig(
            id="wmts_src",
            type="wmts",
            urls=["https://example.com/{z}/{x}/{y}.jpeg"],
            crs="EPSG:4326",
        )
        layer = LayerConfig(
            id="test_layer",
            name="Test Layer",
            source="wmts_src",
            format="wmts",
            zoom_levels=[10],
            bounds=bounds,
        )

        result = asyncio.run(
            build_layer(
                layer,
                {"wmts_src": source},
                cache_dir,
                output_dir,
                no_download=True,
            )
        )

        assert len(result) == 1
        assert result[0].exists()
        assert result[0].stat().st_size > 0


# ---------------------------------------------------------------------------
# Integration: download + reprojection + IMG
# ---------------------------------------------------------------------------


class TestIntegrationDownloadReprojectImg:
    """Integration test: full pipeline with download, reprojection, and IMG output."""

    def test_wmts_download_reproject_to_img(self, tmp_path: Path) -> None:
        """Full pipeline: mock download → real reprojection → real IMG write."""
        cache_dir = tmp_path / "cache"
        output_dir = tmp_path / "output"

        bounds = {
            "west": 7.0,
            "east": 7.5,
            "south": 46.0,
            "north": 46.5,
        }

        source_4326 = SourceConfig(
            id="wmts_src",
            type="wmts",
            urls=["https://example.com/{z}/{x}/{y}.jpeg"],
            crs="EPSG:4326",
        )
        layer = LayerConfig(
            id="test_layer",
            name="Test Layer",
            source="wmts_src",
            format="wmts",
            zoom_levels=[10],
            bounds=bounds,
        )

        dl = WMTSDownloader(
            source_id="wmts_src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=cache_dir,
            delay_ms=0,
            crs="EPSG:4326",
        )

        from cartoload.pipeline import _compute_tile_coords

        coords = _compute_tile_coords(layer, 10)
        assert len(coords) > 0, f"No tile coords for bounds {bounds}"

        for x, y in coords:
            tile_path = dl._cache_path(x, y, 10)
            _write_tile_with_world_file(tile_path)

        result = asyncio.run(
            build_layer(
                layer,
                {"wmts_src": source_4326},
                cache_dir,
                output_dir,
                no_download=True,
            )
        )

        assert len(result) == 1
        assert result[0].exists()
        assert result[0].stat().st_size > 0
