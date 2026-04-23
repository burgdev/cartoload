"""Tests for pipeline orchestration: factories, source resolution, build_layer."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from cartoload.config import LayerConfig, SourceConfig
from cartoload.downloader.geotiff import GeoTIFFDownloader
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
    @patch("cartoload.pipeline.RasterProcessor")
    @patch("cartoload.pipeline.get_downloader")
    def test_happy_path(
        self,
        mock_get_dl,
        mock_rp_cls,
        mock_get_exp,
        layer,
        sources,
        tmp_path,
    ):
        # --- download mock (spec=GeoTIFFDownloader so isinstance passes) ---
        mock_dl = MagicMock(spec=GeoTIFFDownloader)
        mock_dl.run.return_value = [tmp_path / "tile1.tif"]
        (tmp_path / "tile1.tif").write_bytes(b"fake-tile")
        mock_get_dl.return_value = mock_dl

        # --- processor mock ---
        mock_processor = MagicMock()
        mock_processor.process.return_value = tmp_path / "out.tif"
        (tmp_path / "out.tif").write_bytes(b"fake-geotiff")
        mock_rp_cls.return_value = mock_processor

        # --- exporter mock ---
        mock_exporter = MagicMock()
        output_img = tmp_path / "output" / "test_layer.img"

        def _create_on_export(*args, **kwargs):
            output_img.parent.mkdir(parents=True, exist_ok=True)
            output_img.write_bytes(b"fake-img")
            return [output_img]

        mock_exporter.export.side_effect = _create_on_export
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
        mock_processor.process.assert_called_once()
        mock_exporter.export.assert_called_once()

    @patch("cartoload.pipeline.get_exporter")
    @patch("cartoload.pipeline.RasterProcessor")
    @patch("cartoload.pipeline.get_downloader")
    def test_progress_callback(
        self,
        mock_get_dl,
        mock_rp_cls,
        mock_get_exp,
        layer,
        sources,
        tmp_path,
    ):
        mock_dl = MagicMock(spec=GeoTIFFDownloader)
        mock_dl.run.return_value = [tmp_path / "tile.tif"]
        (tmp_path / "tile.tif").write_bytes(b"x")
        mock_get_dl.return_value = mock_dl

        mock_processor = MagicMock()
        mock_processor.process.return_value = tmp_path / "out.tif"
        (tmp_path / "out.tif").write_bytes(b"x")
        mock_rp_cls.return_value = mock_processor

        mock_exporter = MagicMock()
        out = tmp_path / "output" / "test_layer.img"

        def _create_on_export(*args, **kwargs):
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"x")
            return [out]

        mock_exporter.export.side_effect = _create_on_export
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
    @patch("cartoload.pipeline.RasterProcessor")
    @patch("cartoload.pipeline.get_downloader")
    def test_download_skipped(
        self,
        mock_get_dl,
        mock_rp_cls,
        mock_get_exp,
        layer,
        sources,
        tmp_path,
    ):
        # Pre-create cached tiles
        cache_dir = tmp_path / "cache" / "swiss_topo"
        cache_dir.mkdir(parents=True)
        cached_tile = cache_dir / "tile.tif"
        cached_tile.write_bytes(b"cached")

        mock_processor = MagicMock()
        mock_processor.process.return_value = tmp_path / "out.tif"
        (tmp_path / "out.tif").write_bytes(b"x")
        mock_rp_cls.return_value = mock_processor

        mock_exporter = MagicMock()
        out = tmp_path / "output" / "test_layer.img"

        def _create_on_export(*args, **kwargs):
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"x")
            return [out]

        mock_exporter.export.side_effect = _create_on_export
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

        # get_downloader should NOT have been called
        mock_get_dl.assert_not_called()
        # Processor should have been called with the cached tile
        mock_processor.process.assert_called_once()
        called_tiles = mock_processor.process.call_args[0][0]
        assert cached_tile in called_tiles


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
        (tmp_path / "tile.tif").write_bytes(b"x")
        mock_get_dl.return_value = mock_dl

        with patch("cartoload.pipeline.RasterProcessor") as mock_rp:
            mock_rp.return_value.process.side_effect = RuntimeError("gdal fail")
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
    @patch("cartoload.pipeline.RasterProcessor")
    @patch("cartoload.pipeline.get_downloader")
    def test_export_error(
        self, mock_get_dl, mock_rp_cls, mock_get_exp, layer, sources, tmp_path
    ):
        mock_dl = MagicMock(spec=GeoTIFFDownloader)
        mock_dl.run.return_value = [tmp_path / "tile.tif"]
        (tmp_path / "tile.tif").write_bytes(b"x")
        mock_get_dl.return_value = mock_dl

        mock_processor = MagicMock()
        mock_processor.process.return_value = tmp_path / "out.tif"
        (tmp_path / "out.tif").write_bytes(b"x")
        mock_rp_cls.return_value = mock_processor

        mock_get_exp.return_value.export.side_effect = RuntimeError("disk full")

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

    @patch("cartoload.pipeline.RasterProcessor")
    @patch("cartoload.pipeline.get_downloader")
    def test_no_tiles_raises_processing_error(
        self, mock_get_dl, mock_rp_cls, layer, sources, tmp_path
    ):
        """When no tiles are downloaded and none cached, processing should fail."""
        mock_dl = MagicMock(spec=GeoTIFFDownloader)
        mock_dl.run.return_value = []  # no tiles
        mock_get_dl.return_value = mock_dl

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
