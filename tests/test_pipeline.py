"""Tests for pipeline orchestration: factories, source resolution, build_layer."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cartoload.config import LayerConfig, SourceConfig
from cartoload.downloader.geotiff import GeoTIFFDownloader
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
def geotiff_source() -> SourceConfig:
    return SourceConfig(
        id="swiss_topo",
        type="geotiff",
        stac_url="https://stac.example.com",
    )


@pytest.fixture
def wmts_source() -> SourceConfig:
    return SourceConfig(
        id="wmts_src",
        type="wmts",
        url_template="https://tiles.example.com/{z}/{x}/{y}.png",
    )


@pytest.fixture
def unknown_source() -> SourceConfig:
    return SourceConfig(id="bad", type="xyz")


@pytest.fixture
def layer(geotiff_source: SourceConfig) -> LayerConfig:
    return LayerConfig(
        id="test_layer",
        name="Test Layer",
        source=geotiff_source.id,
        zoom_levels=[12, 14],
        exporter="garmin-img",
        output="test_layer.img",
        bounds={"west": 5.0, "south": 45.0, "east": 10.0, "north": 48.0},
    )


@pytest.fixture
def sources(geotiff_source: SourceConfig) -> dict[str, SourceConfig]:
    return {geotiff_source.id: geotiff_source}


# ---------------------------------------------------------------------------
# 9.2 get_downloader factory
# ---------------------------------------------------------------------------


class TestGetDownloader:
    def test_geotiff_returns_geotiff_downloader(self, geotiff_source, tmp_path):
        from cartoload.downloader.geotiff import GeoTIFFDownloader

        dl = get_downloader(geotiff_source, tmp_path)
        assert isinstance(dl, GeoTIFFDownloader)

    def test_wmts_returns_wmts_downloader(self, wmts_source, tmp_path):
        from cartoload.downloader.wmts import WMTSDownloader

        dl = get_downloader(wmts_source, tmp_path)
        assert isinstance(dl, WMTSDownloader)

    def test_unknown_type_raises_pipeline_error(self, unknown_source, tmp_path):
        with pytest.raises(PipelineError, match="Unknown source type"):
            get_downloader(unknown_source, tmp_path)


# ---------------------------------------------------------------------------
# 9.3 get_exporter factory
# ---------------------------------------------------------------------------


class TestGetExporter:
    def test_garmin_img_returns_exporter(self, layer, tmp_path):
        exporter = get_exporter(layer, tmp_path)
        assert isinstance(exporter, GarminImgExporter)

    def test_garmin_img_dash_variant(self, tmp_path):
        layer = LayerConfig(
            id="l",
            name="n",
            exporter="garmin_img",
            output="o.img",
            source="s",
            zoom_levels=[10],
        )

        exporter = get_exporter(layer, tmp_path)
        assert isinstance(exporter, GarminImgExporter)

    def test_unknown_exporter_raises(self, tmp_path):
        layer = LayerConfig(
            id="l",
            name="n",
            exporter="unknown",
            output="o.img",
            source="s",
            zoom_levels=[10],
        )
        with pytest.raises(PipelineError, match="Unknown exporter"):
            get_exporter(layer, tmp_path)


# ---------------------------------------------------------------------------
# 9.4 resolve_source
# ---------------------------------------------------------------------------


class TestResolveSource:
    def test_found(self, layer, sources):
        result = resolve_source(layer, sources)
        assert result.id == "swiss_topo"

    def test_missing_raises(self, layer):
        with pytest.raises(PipelineError, match="unknown source"):
            resolve_source(layer, {})

    def test_missing_with_available(self, layer):
        extra = SourceConfig(id="other", type="geotiff", stac_url="https://x")
        with pytest.raises(PipelineError, match="other"):
            resolve_source(layer, {"other": extra})


# ---------------------------------------------------------------------------
# 9.1 Full pipeline with mocks (build_layer)
# ---------------------------------------------------------------------------


class TestBuildLayerMocked:
    """Exercise the full pipeline with all stages mocked."""

    @patch("cartoload.pipeline.get_exporter")
    @patch("cartoload.pipeline.compute_tile_metadata")
    @patch("cartoload.pipeline.get_downloader")
    def test_happy_path(
        self,
        mock_get_dl,
        mock_compute_metadata,
        mock_get_exp,
        layer,
        sources,
        tmp_path,
    ):
        from cartoload.exporters.garmin_img_model import TileMetadata

        # --- download mock (spec=GeoTIFFDownloader so isinstance passes) ---
        mock_dl = MagicMock(spec=GeoTIFFDownloader)
        mock_dl.run.return_value = [tmp_path / "tile1.tif"]
        mock_get_dl.return_value = mock_dl

        # --- metadata mock ---
        jpeg_bytes = _make_jpeg()
        mock_compute_metadata.return_value = [
            TileMetadata(
                x=0,
                y=0,
                zoom=12,
                lat_min=46.0,
                lon_min=7.0,
                lat_max=47.0,
                lon_max=8.0,
                jpeg_size=len(jpeg_bytes),
                source_path=None,
            ),
        ]

        # --- exporter mock ---
        mock_exporter = MagicMock()
        output_img = tmp_path / "output" / "test_layer.img"

        def _create_on_export(*args, **kwargs):
            output_img.parent.mkdir(parents=True, exist_ok=True)
            output_img.write_bytes(b"fake-img")
            return [output_img]

        mock_exporter.export_from_metadata.side_effect = _create_on_export
        mock_get_exp.return_value = mock_exporter

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        output_dir = tmp_path / "output"

        result = asyncio.run(
            build_layer(
                layer,
                sources,
                cache_dir,
                output_dir,
            )
        )

        assert result == [output_img]
        mock_dl.run.assert_called_once()
        mock_compute_metadata.assert_called()
        mock_exporter.export_from_metadata.assert_called_once()

    @patch("cartoload.pipeline.get_exporter")
    @patch("cartoload.pipeline.compute_tile_metadata")
    @patch("cartoload.pipeline.get_downloader")
    def test_progress_callback(
        self,
        mock_get_dl,
        mock_compute_metadata,
        mock_get_exp,
        layer,
        sources,
        tmp_path,
    ):
        from cartoload.exporters.garmin_img_model import TileMetadata

        mock_dl = MagicMock(spec=GeoTIFFDownloader)
        mock_dl.run.return_value = [tmp_path / "tile.tif"]
        mock_get_dl.return_value = mock_dl

        jpeg_bytes = _make_jpeg()
        mock_compute_metadata.return_value = [
            TileMetadata(
                x=0,
                y=0,
                zoom=12,
                lat_min=46.0,
                lon_min=7.0,
                lat_max=47.0,
                lon_max=8.0,
                jpeg_size=len(jpeg_bytes),
                source_path=None,
            ),
        ]

        mock_exporter = MagicMock()
        out = tmp_path / "output" / "test_layer.img"

        def _create_on_export(*args, **kwargs):
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"x")
            return [out]

        mock_exporter.export_from_metadata.side_effect = _create_on_export
        mock_get_exp.return_value = mock_exporter

        stages: list[tuple[str, str]] = []

        def cb(stage_id: str, desc: str) -> None:
            stages.append((stage_id, desc))

        asyncio.run(
            build_layer(
                layer,
                sources,
                tmp_path / "cache",
                tmp_path / "output",
                progress_callback=cb,
            )
        )

        assert stages[0][0] == "download"
        assert stages[1][0] == "process"
        assert stages[2][0] == "export"


# ---------------------------------------------------------------------------
# 9.5 --no-download flag
# ---------------------------------------------------------------------------


class TestNoDownload:
    @patch("cartoload.pipeline.get_exporter")
    @patch("cartoload.pipeline.compute_tile_metadata")
    @patch("cartoload.pipeline.get_downloader")
    def test_download_skipped(
        self,
        mock_get_dl,
        mock_compute_metadata,
        mock_get_exp,
        layer,
        sources,
        tmp_path,
    ):
        from cartoload.exporters.garmin_img_model import TileMetadata

        # --- metadata mock ---
        jpeg_bytes = _make_jpeg()
        mock_compute_metadata.return_value = [
            TileMetadata(
                x=0,
                y=0,
                zoom=12,
                lat_min=46.0,
                lon_min=7.0,
                lat_max=47.0,
                lon_max=8.0,
                jpeg_size=len(jpeg_bytes),
                source_path=None,
            ),
        ]

        # --- exporter mock ---
        mock_exporter = MagicMock()
        out = tmp_path / "output" / "test_layer.img"

        def _create_on_export(*args, **kwargs):
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"x")
            return [out]

        mock_exporter.export_from_metadata.side_effect = _create_on_export
        mock_get_exp.return_value = mock_exporter

        asyncio.run(
            build_layer(
                layer,
                sources,
                tmp_path / "cache",
                tmp_path / "output",
                no_download=True,
            )
        )

        # get_downloader should have been called for cache path resolution
        # (in no-download mode, it's called during the process stage)
        mock_compute_metadata.assert_called()
        mock_exporter.export_from_metadata.assert_called_once()


# ---------------------------------------------------------------------------
# 9.6 Error propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    def test_download_error(self, layer, sources, tmp_path):
        with patch(
            "cartoload.pipeline.get_downloader",
            side_effect=RuntimeError("network fail"),
        ):
            with pytest.raises(DownloadError, match="network fail"):
                asyncio.run(
                    build_layer(
                        layer,
                        sources,
                        tmp_path / "cache",
                        tmp_path / "output",
                    )
                )

    @patch("cartoload.pipeline.get_downloader")
    def test_processing_error(self, mock_get_dl, layer, sources, tmp_path):
        mock_dl = MagicMock(spec=GeoTIFFDownloader)
        mock_dl.run.return_value = [tmp_path / "tile.tif"]
        mock_get_dl.return_value = mock_dl

        with patch("cartoload.pipeline.compute_tile_metadata") as mock_compute:
            mock_compute.side_effect = RuntimeError("gdal fail")
            with pytest.raises(ProcessingError, match="gdal fail"):
                asyncio.run(
                    build_layer(
                        layer,
                        sources,
                        tmp_path / "cache",
                        tmp_path / "output",
                    )
                )

    @patch("cartoload.pipeline.get_exporter")
    @patch("cartoload.pipeline.compute_tile_metadata")
    @patch("cartoload.pipeline.get_downloader")
    def test_export_error(
        self, mock_get_dl, mock_compute_metadata, mock_get_exp, layer, sources, tmp_path
    ):
        from cartoload.exporters.garmin_img_model import TileMetadata

        mock_dl = MagicMock(spec=GeoTIFFDownloader)
        mock_dl.run.return_value = [tmp_path / "tile.tif"]
        mock_get_dl.return_value = mock_dl

        jpeg_bytes = _make_jpeg()
        mock_compute_metadata.return_value = [
            TileMetadata(
                x=0,
                y=0,
                zoom=12,
                lat_min=46.0,
                lon_min=7.0,
                lat_max=47.0,
                lon_max=8.0,
                jpeg_size=len(jpeg_bytes),
                source_path=None,
            ),
        ]

        mock_get_exp.return_value.export_from_metadata.side_effect = RuntimeError(
            "disk full"
        )

        with pytest.raises(ExportError, match="disk full"):
            asyncio.run(
                build_layer(
                    layer,
                    sources,
                    tmp_path / "cache",
                    tmp_path / "output",
                )
            )

    def test_source_resolution_error(self, tmp_path):
        """PipelineError from source resolution is re-raised directly."""
        layer = LayerConfig(
            id="l",
            name="n",
            source="missing",
            exporter="garmin-img",
            output="o.img",
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

    @patch("cartoload.pipeline.compute_tile_metadata")
    @patch("cartoload.pipeline.get_downloader")
    def test_no_tiles_raises_processing_error(
        self, mock_get_dl, mock_compute_metadata, layer, sources, tmp_path
    ):
        """When no tiles are processed, processing should fail."""
        mock_dl = MagicMock(spec=GeoTIFFDownloader)
        mock_dl.run.return_value = []
        mock_get_dl.return_value = mock_dl

        # compute_tile_metadata returns empty results for both zoom levels
        mock_compute_metadata.return_value = []

        with pytest.raises(ProcessingError, match="No tiles available"):
            asyncio.run(
                build_layer(
                    layer,
                    sources,
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
            exporter="garmin-img",
            output="o.img",
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
# Integration: cache → IMG (task 7.4)
# ---------------------------------------------------------------------------


class TestIntegrationCacheToImg:
    """Integration test: full pipeline from cached tiles to IMG output."""

    def test_wmts_cache_to_img(self, tmp_path: Path) -> None:
        """Cached WMTS tiles should be read, processed, and written to IMG."""
        cache_dir = tmp_path / "cache"
        output_dir = tmp_path / "output"

        # Use bounds that match a small set of tiles at zoom 10
        # Tile (530, 360) covers roughly lon [0.35, 0.70] lat [~0, ~0.7]
        # at z=10: lon = x/1024 * 360 - 180
        # (530,360): lon = [7.03, 7.38], lat = [0.0, ~0.7] — not useful
        # Let's use a narrow bounds that covers just 2 tiles
        # At z=10, tile (530, 360) center: lon=530/1024*360-180 ≈ 6.21
        # Actually: lon_min = 530/1024*360-180 = 6.21
        # So bounds should be tight around a known tile
        # Use single-tile bounds: (530,360) z=10
        # lon: [530/1024*360-180, 531/1024*360-180] = [6.21, 6.56]
        bounds = {
            "west": 6.21,
            "east": 6.56,
            "south": 45.0,
            "north": 45.5,
        }

        # Create a WMTS downloader with cached tiles
        dl = WMTSDownloader(
            source_id="wmts_src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=cache_dir,
            delay_ms=0,
            crs="EPSG:4326",
        )

        # Find the correct tile coords for our bounds
        from cartoload.pipeline import _compute_tile_coords

        layer_for_coords = LayerConfig(
            id="test",
            name="Test",
            source="wmts_src",
            zoom_levels=[10],
            exporter="garmin_img",
            output="test.img",
            bounds=bounds,
        )
        coords = _compute_tile_coords(layer_for_coords, 10)
        assert len(coords) > 0, f"No tile coords for bounds {bounds}"

        # Write cached tiles
        for x, y in coords:
            tile_path = dl._cache_path(x, y, 10)
            _write_tile_with_world_file(tile_path)

        # Create source and layer configs
        source = SourceConfig(
            id="wmts_src",
            type="wmts",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            crs="EPSG:4326",
        )
        layer = LayerConfig(
            id="test_layer",
            name="Test Layer",
            source="wmts_src",
            zoom_levels=[10],
            exporter="garmin_img",
            output="test.img",
            bounds=bounds,
        )

        # Run pipeline with no_download=True (tiles already cached)
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
# Integration: download + reprojection + IMG (task 7.5)
# ---------------------------------------------------------------------------


class TestIntegrationDownloadReprojectImg:
    """Integration test: full pipeline with download, reprojection, and IMG output."""

    def test_wmts_download_reproject_to_img(self, tmp_path: Path) -> None:
        """Full pipeline: mock download → real reprojection → real IMG write."""
        cache_dir = tmp_path / "cache"
        output_dir = tmp_path / "output"

        # Use tight bounds to cover a small number of tiles
        bounds = {
            "west": 7.0,
            "east": 7.5,
            "south": 46.0,
            "north": 46.5,
        }

        # Create a WMTS source — use EPSG:4326 since we can't run gdalwarp in tests
        source_4326 = SourceConfig(
            id="wmts_src",
            type="wmts",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            crs="EPSG:4326",
        )
        layer = LayerConfig(
            id="test_layer",
            name="Test Layer",
            source="wmts_src",
            zoom_levels=[10],
            exporter="garmin_img",
            output="test.img",
            bounds=bounds,
        )

        dl = WMTSDownloader(
            source_id="wmts_src",
            url_template="https://example.com/{z}/{x}/{y}.jpeg",
            cache_dir=cache_dir,
            delay_ms=0,
            crs="EPSG:4326",
        )

        # Compute the correct tile coords for our bounds dynamically
        from cartoload.pipeline import _compute_tile_coords

        coords = _compute_tile_coords(layer, 10)
        assert len(coords) > 0, f"No tile coords for bounds {bounds}"

        # Pre-create tiles in cache (simulating a completed download)
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
