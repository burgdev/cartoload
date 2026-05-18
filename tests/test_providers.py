"""Tests for the LayerProvider abstraction layer.

Tests cover:
- Provider registry (register, make, errors)
- GeotiffProvider: supported_extensions, lifecycle methods
- GpkgProvider: supported_extensions, lifecycle methods
- WmtsProvider: supported_extensions, lifecycle methods
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cartoload.config import LayerConfig, SourceConfig
from cartoload.processor.provider import (
    LayerProvider,
    get_provider_registry,
    make_provider,
    register_provider,
)
from cartoload.processor.geotiff_provider import GeotiffProvider
from cartoload.processor.gpkg_provider import GpkgProvider
from cartoload.processor.wmts_provider import WmtsProvider


# ---------------------------------------------------------------------------
# Provider registry tests
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    def test_builtin_providers_registered(self):
        registry = get_provider_registry()
        assert "geotiff" in registry
        assert "gpkg" in registry
        assert "wmts" in registry

    def test_make_geotiff(self):
        source = MagicMock()
        sc = SourceConfig(id="s", type="stac", urls=["https://x"])
        lc = LayerConfig(
            id="l", name="L", source="s", format="geotiff", zoom_levels=[10]
        )
        p = make_provider("geotiff", source, sc, lc, Path("/tmp"))
        assert isinstance(p, GeotiffProvider)

    def test_make_gpkg(self):
        source = MagicMock()
        sc = SourceConfig(id="s", type="stac", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", format="gpkg", zoom_levels=[10])
        p = make_provider("gpkg", source, sc, lc, Path("/tmp"))
        assert isinstance(p, GpkgProvider)

    def test_make_wmts(self):
        source = MagicMock()
        sc = SourceConfig(id="s", type="wmts", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", format="wmts", zoom_levels=[10])
        p = make_provider("wmts", source, sc, lc, Path("/tmp"))
        assert isinstance(p, WmtsProvider)

    def test_make_unknown_raises(self):
        source = MagicMock()
        sc = SourceConfig(id="s", type="stac", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", zoom_levels=[10])
        with pytest.raises(ValueError, match="Unknown provider format 'geojson'"):
            make_provider("geojson", source, sc, lc, Path("/tmp"))

    def test_register_custom_provider(self):
        class CustomProvider(LayerProvider):
            @property
            def supported_extensions(self):
                return [".custom"]

            def download(self, **kwargs):
                return []

            def prepare(self):
                pass

            def to_raster(self, x, y, z):
                return None

        register_provider("custom", CustomProvider)
        assert "custom" in get_provider_registry()

        # Clean up
        from cartoload.processor import provider as provider_mod

        provider_mod._PROVIDER_TYPES.pop("custom", None)


# ---------------------------------------------------------------------------
# GeotiffProvider tests
# ---------------------------------------------------------------------------


class TestGeotiffProvider:
    def test_supported_extensions(self):
        source = MagicMock()
        sc = SourceConfig(id="s", type="stac", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", zoom_levels=[10])
        p = GeotiffProvider(source, sc, lc, Path("/tmp"))
        assert ".tif" in p.supported_extensions
        assert ".tiff" in p.supported_extensions

    def test_download_delegates_to_source(self):
        source = MagicMock()
        source.download.return_value = [Path("/cache/data.tif")]
        sc = SourceConfig(id="s", type="stac", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", zoom_levels=[10])

        p = GeotiffProvider(source, sc, lc, Path("/cache"))
        result = p.download(offline=False)

        source.download.assert_called_once_with(
            sc, lc, Path("/cache"), offline=False, update=False, max_age_days=None
        )
        assert result == [Path("/cache/data.tif")]

    def test_to_raster_returns_none_before_prepare(self):
        source = MagicMock()
        sc = SourceConfig(id="s", type="stac", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", zoom_levels=[10])
        p = GeotiffProvider(source, sc, lc, Path("/cache"))
        assert p.to_raster(0, 0, 0) is None
        assert p.mosaic_path is None

    def test_prepare_with_no_downloaded_files(self):
        source = MagicMock()
        source.download.return_value = []
        sc = SourceConfig(id="s", type="stac", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", zoom_levels=[10])

        p = GeotiffProvider(source, sc, lc, Path("/cache"))
        p.download(offline=True)
        # Should not raise, just log warning
        p.prepare()


# ---------------------------------------------------------------------------
# GpkgProvider tests
# ---------------------------------------------------------------------------


class TestGpkgProvider:
    def test_supported_extensions(self):
        source = MagicMock()
        sc = SourceConfig(id="s", type="stac", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", zoom_levels=[10])
        p = GpkgProvider(source, sc, lc, Path("/tmp"))
        assert ".gpkg" in p.supported_extensions

    def test_download_delegates_to_source(self):
        source = MagicMock()
        source.download.return_value = [Path("/cache/data.gpkg")]
        sc = SourceConfig(id="s", type="stac", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", zoom_levels=[10])

        p = GpkgProvider(source, sc, lc, Path("/cache"))
        result = p.download(offline=True)

        source.download.assert_called_once_with(
            sc, lc, Path("/cache"), offline=True, update=False, max_age_days=None
        )
        assert result == [Path("/cache/data.gpkg")]

    def test_to_raster_returns_none_before_prepare(self):
        source = MagicMock()
        sc = SourceConfig(id="s", type="stac", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", zoom_levels=[10])
        p = GpkgProvider(source, sc, lc, Path("/cache"))
        assert p.to_raster(0, 0, 0) is None

    def test_prepare_with_no_downloaded_files(self):
        source = MagicMock()
        source.download.return_value = []
        sc = SourceConfig(id="s", type="stac", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", zoom_levels=[10])

        p = GpkgProvider(source, sc, lc, Path("/cache"))
        p.download(offline=True)
        # Should not raise, just log warning
        p.prepare()


# ---------------------------------------------------------------------------
# WmtsProvider tests
# ---------------------------------------------------------------------------


class TestWmtsProvider:
    def test_supported_extensions(self):
        source = MagicMock()
        sc = SourceConfig(id="s", type="wmts", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", zoom_levels=[10])
        p = WmtsProvider(source, sc, lc, Path("/tmp"))
        assert ".jpeg" in p.supported_extensions
        assert ".png" in p.supported_extensions

    def test_prepare_is_noop(self):
        source = MagicMock()
        sc = SourceConfig(id="s", type="wmts", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", zoom_levels=[10])
        p = WmtsProvider(source, sc, lc, Path("/cache"))
        # Should not raise
        p.prepare()

    def test_to_raster_returns_none_without_downloader(self):
        source = MagicMock()
        sc = SourceConfig(id="s", type="wmts", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", zoom_levels=[10])
        p = WmtsProvider(source, sc, lc, Path("/cache"))
        assert p.to_raster(0, 0, 0) is None

    def test_downloader_property_none_before_download(self):
        source = MagicMock()
        sc = SourceConfig(id="s", type="wmts", urls=["https://x"])
        lc = LayerConfig(id="l", name="L", source="s", zoom_levels=[10])
        p = WmtsProvider(source, sc, lc, Path("/cache"))
        assert p.downloader is None


# ---------------------------------------------------------------------------
# Lifecycle integration tests
# ---------------------------------------------------------------------------


class TestProviderLifecycle:
    """Test the download → prepare → to_raster lifecycle with mocks."""

    def test_geotiff_full_lifecycle_with_mock(self, tmp_path):
        """GeotiffProvider downloads, prepares, and returns tiles."""
        source = MagicMock()
        # Simulate a downloaded tif file
        tif_path = tmp_path / "data.tif"
        tif_path.write_bytes(b"fake tif")
        source.download.return_value = [tif_path]

        sc = SourceConfig(id="s", type="stac", urls=["https://x"])
        lc = LayerConfig(
            id="l",
            name="L",
            source="s",
            format="geotiff",
            bounds={"west": 5.0, "east": 10.0, "south": 45.0, "north": 48.0},
            zoom_levels=[10],
        )

        p = GeotiffProvider(source, sc, lc, tmp_path)

        # Download
        result = p.download()
        assert len(result) == 1

        # Prepare — mock prewarp at the source module to avoid GDAL dependency
        with (
            patch(
                "cartoload.processor.geotiff_prewarp.prewarp_all_geotiffs"
            ) as mock_prewarp,
            patch("cartoload.processor.geotiff_prewarp.merge_prewarped_geotiffs"),
        ):
            # Simulate prewarp returning the same file (no warp needed)
            mock_prewarp.return_value = {tif_path: tif_path}
            p.prepare()
            mock_prewarp.assert_called_once()

        # Mosaic path should be set
        assert p.mosaic_path == tif_path

    def test_gpkg_full_lifecycle_with_mock(self, tmp_path):
        """GpkgProvider downloads and prepares with vector rasterizer."""
        import sys
        import types

        source = MagicMock()
        gpkg_path = tmp_path / "data.gpkg"
        gpkg_path.write_bytes(b"fake gpkg")
        source.download.return_value = [gpkg_path]

        sc = SourceConfig(id="s", type="stac", urls=["https://x"])
        lc = LayerConfig(
            id="l",
            name="L",
            source="s",
            format="gpkg",
            zoom_levels=[10],
            rules=[{"filter": "type=trail", "color": "#FF0000", "width": 2}],
        )

        p = GpkgProvider(source, sc, lc, tmp_path)

        # Download
        result = p.download()
        assert len(result) == 1

        # Prepare — inject mock modules for VectorRasterizer and StyleEngine
        mock_vr_class = MagicMock()
        mock_se_class = MagicMock()
        mock_se_class.default.return_value = MagicMock()

        vr_module = types.ModuleType("cartoload.processor.vector_rasterizer")
        vr_module.VectorRasterizer = mock_vr_class
        se_module = types.ModuleType("cartoload.style.engine")
        se_module.StyleEngine = mock_se_class

        saved_vr = sys.modules.get("cartoload.processor.vector_rasterizer")
        saved_se = sys.modules.get("cartoload.style.engine")
        sys.modules["cartoload.processor.vector_rasterizer"] = vr_module
        sys.modules["cartoload.style.engine"] = se_module
        try:
            p.prepare()
            mock_vr_class.assert_called_once()
        finally:
            if saved_vr is not None:
                sys.modules["cartoload.processor.vector_rasterizer"] = saved_vr
            else:
                sys.modules.pop("cartoload.processor.vector_rasterizer", None)
            if saved_se is not None:
                sys.modules["cartoload.style.engine"] = saved_se
            else:
                sys.modules.pop("cartoload.style.engine", None)

    def test_wmts_download_creates_downloader(self, tmp_path):
        """WmtsProvider.download() creates internal WMTSDownloader."""
        from cartoload.downloader.wmts_source import WmtsSource
        from cartoload.downloader.wmts import WMTSDownloader

        wmts_source = WmtsSource()
        sc = SourceConfig(
            id="s",
            type="wmts",
            urls=["https://wmts.example.com/${z}/${x}/${y}.jpeg"],
        )
        lc = LayerConfig(
            id="l",
            name="L",
            source="s",
            format="wmts",
            source_args={"layer": "test"},
            zoom_levels=[10],
        )

        p = WmtsProvider(wmts_source, sc, lc, tmp_path)
        p.download()

        assert p.downloader is not None
        assert isinstance(p.downloader, WMTSDownloader)
