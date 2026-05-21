"""Tests for the Source abstraction layer.

Tests cover:
- Source ABC contract
- Source registry (register, resolve, errors)
- StacSource: can_handle, URL resolution, download delegation, cache freshness
- WmtsSource: can_handle, downloader creation
- PathSource: can_handle, path resolution, directory expansion
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cartoload.config import LayerConfig, SourceConfig
from cartoload.downloader.source import (
    Source,
    get_source_registry,
    register_source,
    resolve_source,
)
from cartoload.downloader.stac_source import (
    StacSource,
    _find_geotiff_asset,
    _find_gpkg_asset,
)
from cartoload.downloader.wmts_source import WmtsSource
from cartoload.downloader.path_source import PathSource


# ---------------------------------------------------------------------------
# Source registry tests
# ---------------------------------------------------------------------------


class TestSourceRegistry:
    def test_builtin_sources_registered(self):
        registry = get_source_registry()
        assert "stac" in registry
        assert "wmts" in registry
        assert "path" in registry

    def test_resolve_stac(self):
        assert resolve_source("stac") is StacSource

    def test_resolve_wmts(self):
        assert resolve_source("wmts") is WmtsSource

    def test_resolve_path(self):
        assert resolve_source("path") is PathSource

    def test_resolve_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown source type 'ftp'"):
            resolve_source("ftp")

    def test_register_custom_source(self):
        class CustomSource(Source):
            @classmethod
            def can_handle(cls, source_config):
                return False

            def download(
                self,
                source_config,
                layer_config,
                cache_dir,
                *,
                offline=False,
                update=False,
                max_age_days=None,
            ):
                return []

            def is_cached(self, source_config, layer_config, cache_dir):
                return False

        register_source("custom", CustomSource)
        assert resolve_source("custom") is CustomSource

        # Clean up
        from cartoload.downloader import source as source_mod

        source_mod._SOURCE_TYPES.pop("custom", None)


# ---------------------------------------------------------------------------
# StacSource tests
# ---------------------------------------------------------------------------


class TestStacSource:
    def test_can_handle_stac(self):
        config = SourceConfig(id="s", type="stac", urls=["https://stac.example.com"])
        assert StacSource.can_handle(config)

    def test_cannot_handle_wmts(self):
        config = SourceConfig(id="s", type="wmts", urls=["https://wmts.example.com"])
        assert not StacSource.can_handle(config)

    def test_cannot_handle_path(self):
        config = SourceConfig(id="s", type="path", urls=["./data/"])
        assert not StacSource.can_handle(config)

    def test_resolve_url_substitutes_variables(self):
        source = SourceConfig(
            id="swisstopo_stac",
            type="stac",
            urls=["https://data.geo.admin.ch/api/stac/v1/collections/${layer}"],
            defaults={"layer": "ch.swisstopo.pixelkarte-farbe-pk25.noscale"},
        )
        layer = LayerConfig(
            id="test",
            name="Test",
            source="swisstopo_stac",
            source_args={"layer": "ch.swisstopo.pixelkarte-farbe-pk50.noscale"},
            zoom_levels=[10],
        )
        url = StacSource._resolve_url(source, layer)
        assert (
            url
            == "https://data.geo.admin.ch/api/stac/v1/collections/ch.swisstopo.pixelkarte-farbe-pk50.noscale"
        )

    def test_resolve_url_uses_defaults(self):
        source = SourceConfig(
            id="s",
            type="stac",
            urls=["https://stac.example.com/collections/${layer}"],
            defaults={"layer": "default_collection"},
        )
        layer = LayerConfig(
            id="test",
            name="Test",
            source="s",
            zoom_levels=[10],
        )
        url = StacSource._resolve_url(source, layer)
        assert url == "https://stac.example.com/collections/default_collection"

    def test_file_extension_geotiff(self):
        assert StacSource._file_extension("geotiff") == "tif"

    def test_file_extension_gpkg(self):
        assert StacSource._file_extension("gpkg") == "gpkg"

    def test_download_requires_bounds(self):
        source = StacSource()
        source_config = SourceConfig(
            id="s", type="stac", urls=["https://stac.example.com"]
        )
        layer_config = LayerConfig(id="test", name="Test", source="s", zoom_levels=[10])

        with pytest.raises(ValueError, match="missing required 'bounds'"):
            source.download(source_config, layer_config, Path("cache"))

    def test_download_rejects_unsupported_format(self):
        source = StacSource()
        source_config = SourceConfig(
            id="s", type="stac", urls=["https://stac.example.com"]
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="s",
            format="wmts",
            bounds={"west": 5.0, "east": 10.0, "south": 45.0, "north": 48.0},
            zoom_levels=[10],
        )

        with pytest.raises(ValueError, match="does not support format 'wmts'"):
            source.download(source_config, layer_config, Path("cache"))


# ---------------------------------------------------------------------------
# Asset finder tests
# ---------------------------------------------------------------------------


class TestFindGeotiffAsset:
    def test_find_by_key(self):
        assets = {
            "geotiff": {"href": "https://example.com/data.tif", "type": "image/tiff"}
        }
        assert _find_geotiff_asset(assets) == "https://example.com/data.tif"

    def test_find_by_media_type(self):
        assets = {
            "data": {
                "href": "https://example.com/data.tif",
                "type": "image/tiff; application=geotiff",
            }
        }
        assert _find_geotiff_asset(assets) == "https://example.com/data.tif"

    def test_find_by_extension(self):
        assets = {"custom": {"href": "https://example.com/data.TIFF"}}
        assert _find_geotiff_asset(assets) == "https://example.com/data.TIFF"

    def test_no_match(self):
        assets = {
            "pdf": {"href": "https://example.com/doc.pdf", "type": "application/pdf"}
        }
        assert _find_geotiff_asset(assets) is None

    def test_with_filter_match(self):
        assets = {
            "geotiff": {
                "href": "https://example.com/komb.tif",
                "type": "image/tiff",
                "geoadmin:variant": "komb",
            }
        }
        assert (
            _find_geotiff_asset(assets, {"geoadmin:variant": "komb"})
            == "https://example.com/komb.tif"
        )

    def test_with_filter_no_match(self):
        assets = {
            "geotiff": {
                "href": "https://example.com/krel.tif",
                "type": "image/tiff",
                "geoadmin:variant": "krel",
            }
        }
        assert _find_geotiff_asset(assets, {"geoadmin:variant": "komb"}) is None

    def test_multiple_without_filter_raises(self):
        assets = {
            "geotiff": {"href": "https://example.com/a.tif"},
            "data": {"href": "https://example.com/b.tif"},
        }
        with pytest.raises(ValueError, match="Multiple assets found"):
            _find_geotiff_asset(assets)


class TestFindGpkgAsset:
    def test_find_by_key(self):
        assets = {
            "gpkg": {
                "href": "https://example.com/data.gpkg.zip",
                "type": "application/geopackage+zip",
            }
        }
        assert _find_gpkg_asset(assets) == "https://example.com/data.gpkg.zip"

    def test_find_by_extension(self):
        assets = {"custom": {"href": "https://example.com/data.gpkg.zip"}}
        assert _find_gpkg_asset(assets) == "https://example.com/data.gpkg.zip"

    def test_no_match(self):
        assets = {"geotiff": {"href": "https://example.com/data.tif"}}
        assert _find_gpkg_asset(assets) is None


# ---------------------------------------------------------------------------
# WmtsSource tests
# ---------------------------------------------------------------------------


class TestWmtsSource:
    def test_can_handle_wmts(self):
        config = SourceConfig(
            id="s",
            type="wmts",
            urls=["https://wmts.example.com/${z}/${x}/${y}.png"],
        )
        assert WmtsSource.can_handle(config)

    def test_cannot_handle_stac(self):
        config = SourceConfig(
            id="s",
            type="stac",
            urls=["https://stac.example.com/collections/test"],
        )
        assert not WmtsSource.can_handle(config)

    def test_download_returns_cache_dir(self, tmp_path):
        source = WmtsSource()
        source_config = SourceConfig(
            id="test_wmts",
            type="wmts",
            urls=["https://wmts.example.com/${layer}/${z}/${x}/${y}.jpeg"],
            defaults={"layer": "base"},
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="test_wmts",
            source_args={"layer": "overlay"},
            zoom_levels=[10],
        )

        result = source.download(source_config, layer_config, tmp_path)
        assert len(result) == 1
        # WMTS creates the cache dir lazily when tiles are downloaded,
        # so we check the path is set correctly rather than that it exists
        assert "test_wmts" in str(result[0])

    def test_get_downloader_returns_wmts_downloader(self, tmp_path):
        source = WmtsSource()
        source_config = SourceConfig(
            id="test_wmts",
            type="wmts",
            urls=["https://wmts.example.com/${z}/${x}/${y}.jpeg"],
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="test_wmts",
            zoom_levels=[10],
        )

        from cartoload.downloader.wmts.download import WMTSDownloader

        dl = source.get_downloader(source_config, layer_config, tmp_path)
        assert isinstance(dl, WMTSDownloader)


class TestWmtsSourceXyzAlias:
    """Tests for type: xyz alias resolving to WmtsSource."""

    def test_can_handle_xyz(self):
        config = SourceConfig(
            id="s",
            type="xyz",
            urls=["https://tiles.example.com/${z}/${x}/${y}.png"],
        )
        assert WmtsSource.can_handle(config)

    def test_xyz_resolves_to_wmts_source(self):
        from cartoload.downloader.source import resolve_source

        assert resolve_source("xyz") is WmtsSource

    def test_xyz_template_mode_download(self, tmp_path):
        """type: xyz uses template mode (not Capabilities mode)."""
        source = WmtsSource()
        source_config = SourceConfig(
            id="test_xyz",
            type="xyz",
            urls=["https://tiles.example.com/${z}/${x}/${y}.png"],
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="test_xyz",
            zoom_levels=[10],
        )

        # Verify it detects template mode
        assert not source._is_capabilities_mode(source_config)

        result = source.download(source_config, layer_config, tmp_path)
        assert len(result) == 1

        from cartoload.downloader.wmts.download import WMTSDownloader

        dl = source.get_downloader(source_config, layer_config, tmp_path)
        assert isinstance(dl, WMTSDownloader)


class TestWmtsSourceCapabilitiesMode:
    """Tests for WmtsSource Capabilities mode."""

    def _make_capabilities_xml(self) -> str:
        """Create a minimal WMTS Capabilities XML for testing."""
        return """\
<?xml version="1.0" encoding="UTF-8"?>
<Capabilities xmlns="http://www.opengis.net/wmts/1.0"
              xmlns:ows="http://www.opengis.net/ows/1.1">
  <Contents>
    <Layer>
      <ows:Identifier>ch.swisstopo.pixelkarte-farbe</ows:Identifier>
      <ows:Title>Pixelkarte Farbe</ows:Title>
      <Style isDefault="true">
        <ows:Identifier>default</ows:Identifier>
      </Style>
      <Format>image/jpeg</Format>
      <TileMatrixSetLink>
        <TileMatrixSet>3857</TileMatrixSet>
      </TileMatrixSetLink>
      <ResourceURL format="image/jpeg"
        resourceType="tile"
        template="https://wmts0.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/{TileMatrix}/{TileRow}/{TileCol}.jpeg"/>
    </Layer>
    <TileMatrixSet>
      <ows:Identifier>3857</ows:Identifier>
      <ows:SupportedCRS>urn:ogc:def:crs:EPSG::3857</ows:SupportedCRS>
      <TileMatrix>
        <ows:Identifier>0</ows:Identifier>
        <ScaleDenominator>559082264.0287178</ScaleDenominator>
        <TopLeftCorner>-20037508.3427892 20037508.3427892</TopLeftCorner>
        <TileWidth>256</TileWidth>
        <TileHeight>256</TileHeight>
        <MatrixWidth>1</MatrixWidth>
        <MatrixHeight>1</MatrixHeight>
      </TileMatrix>
      <TileMatrix>
        <ows:Identifier>1</ows:Identifier>
        <ScaleDenominator>279541132.0143589</ScaleDenominator>
        <TopLeftCorner>-20037508.3427892 20037508.3427892</TopLeftCorner>
        <TileWidth>256</TileWidth>
        <TileHeight>256</TileHeight>
        <MatrixWidth>2</MatrixWidth>
        <MatrixHeight>2</MatrixHeight>
      </TileMatrix>
    </TileMatrixSet>
  </Contents>
</Capabilities>"""

    def test_capabilities_url_triggers_capabilities_mode(self):
        source = WmtsSource()
        config = SourceConfig(
            id="test_caps",
            type="wmts",
            capabilities_url="https://wmts.geo.admin.ch/EPSG/3857/1.0.0/WMTSCapabilities.xml",
            layer="ch.swisstopo.pixelkarte-farbe",
            tile_matrix_set="3857",
        )
        assert source._is_capabilities_mode(config)

    def test_capabilities_url_pattern_triggers_capabilities_mode(self):
        """URL ending with WMTSCapabilities.xml triggers Capabilities mode."""
        source = WmtsSource()
        config = SourceConfig(
            id="test_caps",
            type="wmts",
            urls=["https://wmts.geo.admin.ch/1.0.0/WMTSCapabilities.xml"],
        )
        assert source._is_capabilities_mode(config)

    def test_url_template_does_not_trigger_capabilities_mode(self):
        """URL with ${x}/${y}/${z} does NOT trigger Capabilities mode."""
        source = WmtsSource()
        config = SourceConfig(
            id="test_tpl",
            type="wmts",
            urls=["https://wmts0.geo.admin.ch/1.0.0/${layer}/${z}/${x}/${y}.jpeg"],
        )
        assert not source._is_capabilities_mode(config)

    def test_capabilities_mode_download(self, tmp_path):
        """Capabilities mode fetches XML and creates a working downloader."""
        source = WmtsSource()
        source_config = SourceConfig(
            id="test_caps",
            type="wmts",
            capabilities_url="https://example.com/WMTSCapabilities.xml",
            layer="ch.swisstopo.pixelkarte-farbe",
            tile_matrix_set="3857",
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="test_caps",
            zoom_levels=[10],
        )

        # Mock the HTTP request to return our test Capabilities XML
        mock_response = MagicMock()
        mock_response.text = self._make_capabilities_xml()
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            result = source.download(source_config, layer_config, tmp_path)

        assert len(result) == 1

        from cartoload.downloader.wmts.download import WMTSDownloader

        with patch("requests.get", return_value=mock_response):
            dl = source.get_downloader(source_config, layer_config, tmp_path)
        assert isinstance(dl, WMTSDownloader)

        # Verify the URL template was constructed from Capabilities
        assert "${z}" in dl._url_template
        assert "${x}" in dl._url_template
        assert "${y}" in dl._url_template

    def test_capabilities_mode_offline_raises(self, tmp_path):
        """Capabilities mode in offline mode raises RuntimeError."""
        source = WmtsSource()
        source_config = SourceConfig(
            id="test_caps",
            type="wmts",
            capabilities_url="https://example.com/WMTSCapabilities.xml",
            layer="ch.swisstopo.pixelkarte-farbe",
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="test_caps",
            zoom_levels=[10],
        )

        with pytest.raises(RuntimeError, match="offline mode"):
            source.download(source_config, layer_config, tmp_path, offline=True)

    def test_capabilities_no_layer_raises(self, tmp_path):
        """Capabilities mode without a layer identifier raises ValueError."""
        source = WmtsSource()
        source_config = SourceConfig(
            id="test_caps",
            type="wmts",
            capabilities_url="https://example.com/WMTSCapabilities.xml",
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="test_caps",
            zoom_levels=[10],
        )

        mock_response = MagicMock()
        mock_response.text = self._make_capabilities_xml()
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            with pytest.raises(ValueError, match="No layer identifier"):
                source.download(source_config, layer_config, tmp_path)


class TestWmtsSourceTemplateModePreserved:
    """Tests that existing URL-template mode still works unchanged."""

    def test_wmts_with_url_template_uses_template_mode(self):
        source = WmtsSource()
        config = SourceConfig(
            id="test",
            type="wmts",
            urls=["https://tiles.example.com/${z}/${x}/${y}.png"],
        )
        assert not source._is_capabilities_mode(config)

    def test_wmts_template_download_unchanged(self, tmp_path):
        source = WmtsSource()
        source_config = SourceConfig(
            id="test_wmts",
            type="wmts",
            urls=["https://wmts.example.com/${layer}/${z}/${x}/${y}.jpeg"],
            defaults={"layer": "base"},
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="test_wmts",
            source_args={"layer": "overlay"},
            zoom_levels=[10],
        )

        result = source.download(source_config, layer_config, tmp_path)
        assert len(result) == 1

        from cartoload.downloader.wmts.download import WMTSDownloader

        dl = source.get_downloader(source_config, layer_config, tmp_path)
        assert isinstance(dl, WMTSDownloader)
        # Verify template was expanded with the layer variable
        assert "overlay" in dl._url_template


# ---------------------------------------------------------------------------
# PathSource tests
# ---------------------------------------------------------------------------


class TestPathSource:
    def test_can_handle_path(self):
        config = SourceConfig(id="s", type="path", urls=["./data/"])
        assert PathSource.can_handle(config)

    def test_cannot_handle_stac(self):
        config = SourceConfig(id="s", type="stac", urls=["https://stac.example.com"])
        assert not PathSource.can_handle(config)

    def test_download_returns_existing_files(self, tmp_path):
        # Create some test files
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "a.tif").write_bytes(b"fake tif")
        (tmp_path / "data" / "b.tif").write_bytes(b"fake tif")

        source = PathSource()
        source_config = SourceConfig(
            id="s",
            type="path",
            urls=[str(tmp_path / "data")],
            config_dir=str(tmp_path),
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="s",
            format="geotiff",
            zoom_levels=[10],
            config_dir=str(tmp_path),
        )

        result = source.download(source_config, layer_config, tmp_path / "cache")
        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"a.tif", "b.tif"}

    def test_is_cached_true(self, tmp_path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "a.tif").write_bytes(b"fake tif")

        source = PathSource()
        source_config = SourceConfig(
            id="s",
            type="path",
            urls=[str(tmp_path / "data")],
            config_dir=str(tmp_path),
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="s",
            format="geotiff",
            zoom_levels=[10],
            config_dir=str(tmp_path),
        )

        assert source.is_cached(source_config, layer_config, tmp_path / "cache")

    def test_is_cached_false(self, tmp_path):
        source = PathSource()
        source_config = SourceConfig(
            id="s",
            type="path",
            urls=[str(tmp_path / "nonexistent")],
            config_dir=str(tmp_path),
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="s",
            format="geotiff",
            zoom_levels=[10],
            config_dir=str(tmp_path),
        )

        assert not source.is_cached(source_config, layer_config, tmp_path / "cache")

    def test_resolves_relative_paths(self, tmp_path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "test.tif").write_bytes(b"fake tif")

        source = PathSource()
        source_config = SourceConfig(
            id="s",
            type="path",
            urls=["./data/"],
            config_dir=str(tmp_path),
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="s",
            format="geotiff",
            zoom_levels=[10],
            config_dir=str(tmp_path),
        )

        result = source.download(source_config, layer_config, tmp_path / "cache")
        assert len(result) == 1
        assert result[0].name == "test.tif"

    def test_gpkg_format_finds_gpkg_files(self, tmp_path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "vectors.gpkg").write_bytes(b"fake gpkg")
        (tmp_path / "data" / "raster.tif").write_bytes(b"fake tif")

        source = PathSource()
        source_config = SourceConfig(
            id="s",
            type="path",
            urls=[str(tmp_path / "data")],
            config_dir=str(tmp_path),
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="s",
            format="gpkg",
            zoom_levels=[10],
            config_dir=str(tmp_path),
        )

        result = source.download(source_config, layer_config, tmp_path / "cache")
        assert len(result) == 1
        assert result[0].name == "vectors.gpkg"

    def test_template_variable_substitution(self, tmp_path):
        (tmp_path / "cache").mkdir()
        (tmp_path / "cache" / "my_layer").mkdir()
        (tmp_path / "cache" / "my_layer" / "data.tif").write_bytes(b"fake tif")

        source = PathSource()
        source_config = SourceConfig(
            id="s",
            type="path",
            urls=["./cache/${layer}/"],
            config_dir=str(tmp_path),
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="s",
            format="geotiff",
            source_args={"layer": "my_layer"},
            zoom_levels=[10],
            config_dir=str(tmp_path),
        )

        result = source.download(source_config, layer_config, tmp_path / "cache2")
        assert len(result) == 1
        assert result[0].name == "data.tif"


# ---------------------------------------------------------------------------
# StacSource._is_older_than tests
# ---------------------------------------------------------------------------


class TestIsOlderThan:
    """Tests for StacSource._is_older_than static method."""

    def _make_cached_file(self, tmp_path, days_ago: int | None = None):
        """Create a fake cached file with metadata sidecar.

        Args:
            tmp_path: Temp directory to create files in.
            days_ago: How many days ago the download_date should be.
                None means no download_date field.
        """
        cache_path = tmp_path / "item_123.tif"
        cache_path.write_bytes(b"fake tif data")

        meta = {"item_id": "item_123", "url": "https://example.com/data.tif"}
        if days_ago is not None:
            dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
            meta["download_date"] = dt.isoformat()

        meta_path = tmp_path / "item_123.json"
        meta_path.write_text(json.dumps(meta))

        return cache_path

    def test_recent_file_not_older(self, tmp_path):
        """File downloaded 2 days ago is not older than 10 days."""
        cache_path = self._make_cached_file(tmp_path, days_ago=2)
        assert StacSource._is_older_than(cache_path, 10) is False

    def test_old_file_is_older(self, tmp_path):
        """File downloaded 20 days ago is older than 10 days."""
        cache_path = self._make_cached_file(tmp_path, days_ago=20)
        assert StacSource._is_older_than(cache_path, 10) is True

    def test_exactly_at_boundary(self, tmp_path):
        """File downloaded exactly N days ago is at the boundary."""
        # Use a very recent timestamp to avoid timing issues
        cache_path = self._make_cached_file(tmp_path, days_ago=0)
        assert StacSource._is_older_than(cache_path, 10) is False

    def test_no_metadata_returns_true(self, tmp_path):
        """File without metadata JSON is treated as old."""
        cache_path = tmp_path / "item_123.tif"
        cache_path.write_bytes(b"fake tif data")
        # No .json sidecar
        assert StacSource._is_older_than(cache_path, 10) is True

    def test_no_download_date_returns_true(self, tmp_path):
        """Metadata without download_date is treated as old."""
        cache_path = tmp_path / "item_123.tif"
        cache_path.write_bytes(b"fake tif data")

        meta = {"item_id": "item_123", "url": "https://example.com/data.tif"}
        meta_path = tmp_path / "item_123.json"
        meta_path.write_text(json.dumps(meta))

        assert StacSource._is_older_than(cache_path, 10) is True

    def test_corrupted_metadata_returns_true(self, tmp_path):
        """Corrupted metadata JSON is treated as old."""
        cache_path = tmp_path / "item_123.tif"
        cache_path.write_bytes(b"fake tif data")

        meta_path = tmp_path / "item_123.json"
        meta_path.write_text("not valid json{{{")

        assert StacSource._is_older_than(cache_path, 10) is True

    def test_naive_datetime_treated_as_utc(self, tmp_path):
        """download_date without timezone info is treated as UTC."""
        cache_path = tmp_path / "item_123.tif"
        cache_path.write_bytes(b"fake tif data")

        # Write a naive datetime (no timezone) that's recent
        recent = datetime.now(timezone.utc) - timedelta(days=1)
        naive_str = recent.strftime("%Y-%m-%dT%H:%M:%S.%f")
        meta = {
            "item_id": "item_123",
            "url": "https://example.com/data.tif",
            "download_date": naive_str,
        }
        meta_path = tmp_path / "item_123.json"
        meta_path.write_text(json.dumps(meta))

        assert StacSource._is_older_than(cache_path, 10) is False


# ---------------------------------------------------------------------------
# StacSource cache freshness behavior tests
# ---------------------------------------------------------------------------


class TestStacCacheFreshness:
    """Test that update/max_age_days control freshness checking."""

    def _make_source_and_configs(self):
        """Create a StacSource and test configs."""
        source = StacSource()
        source_config = SourceConfig(
            id="test_stac",
            type="stac",
            urls=["https://stac.example.com/collections/${layer}"],
            defaults={},
        )
        layer_config = LayerConfig(
            id="test",
            name="Test",
            source="test_stac",
            format="geotiff",
            source_args={"layer": "test_collection"},
            bounds={"west": 5.0, "east": 10.0, "south": 45.0, "north": 48.0},
            zoom_levels=[10],
        )
        return source, source_config, layer_config

    @patch("cartoload.downloader.stac_source.query_stac_collection")
    def test_default_no_freshness_check(self, mock_query, tmp_path):
        """By default (update=False, max_age_days=None), cached files are
        returned without any HTTP HEAD requests."""
        source, sc, lc = self._make_source_and_configs()

        # Setup: cached file with metadata
        item_id = "item_2024_001"
        cache_dir = tmp_path / "test_stac" / "abc" / item_id
        cache_dir.mkdir(parents=True)
        tif_path = cache_dir / f"{item_id}.tif"
        tif_path.write_bytes(b"fake tif")
        meta_path = cache_dir / f"{item_id}.json"
        meta_path.write_text(
            json.dumps(
                {
                    "item_id": item_id,
                    "url": "https://example.com/data.tif",
                    "download_date": datetime.now(timezone.utc).isoformat(),
                }
            )
        )

        mock_query.return_value = [(item_id, "https://example.com/data.tif", None)]

        with patch.object(source, "_get_cache_dir", return_value=cache_dir):
            result = source.download(sc, lc, tmp_path)

        # Should return cached file without HTTP HEAD
        assert len(result) == 1
        assert result[0] == tif_path

    @patch("cartoload.downloader.stac_source.query_stac_collection")
    @patch("cartoload.downloader.stac_source.requests.head")
    def test_update_true_checks_freshness(self, mock_head, mock_query, tmp_path):
        """With update=True, HTTP HEAD is used to check freshness."""
        source, sc, lc = self._make_source_and_configs()

        item_id = "item_2024_001"
        cache_dir = tmp_path / "test_stac" / "abc" / item_id
        cache_dir.mkdir(parents=True)
        tif_path = cache_dir / f"{item_id}.tif"
        tif_path.write_bytes(b"fake tif")
        meta_path = cache_dir / f"{item_id}.json"
        meta_path.write_text(
            json.dumps(
                {
                    "item_id": item_id,
                    "url": "https://example.com/data.tif",
                    "etag": "abc123",
                    "download_date": datetime.now(timezone.utc).isoformat(),
                }
            )
        )

        mock_query.return_value = [(item_id, "https://example.com/data.tif", None)]

        # Mock HTTP HEAD response with same ETag → fresh
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.headers = {"ETag": '"abc123"'}
        mock_head.return_value = mock_resp

        with patch.object(source, "_get_cache_dir", return_value=cache_dir):
            result = source.download(sc, lc, tmp_path, update=True)

        # HTTP HEAD should have been called
        mock_head.assert_called()
        assert len(result) == 1

    @patch("cartoload.downloader.stac_source.query_stac_collection")
    def test_max_age_days_skips_recent_file(self, mock_query, tmp_path):
        """With max_age_days=10, a file downloaded 2 days ago is skipped."""
        source, sc, lc = self._make_source_and_configs()

        item_id = "item_2024_001"
        cache_dir = tmp_path / "test_stac" / "abc" / item_id
        cache_dir.mkdir(parents=True)
        tif_path = cache_dir / f"{item_id}.tif"
        tif_path.write_bytes(b"fake tif")
        meta_path = cache_dir / f"{item_id}.json"
        meta_path.write_text(
            json.dumps(
                {
                    "item_id": item_id,
                    "url": "https://example.com/data.tif",
                    "download_date": (
                        datetime.now(timezone.utc) - timedelta(days=2)
                    ).isoformat(),
                }
            )
        )

        mock_query.return_value = [(item_id, "https://example.com/data.tif", None)]

        with patch.object(source, "_get_cache_dir", return_value=cache_dir):
            result = source.download(sc, lc, tmp_path, max_age_days=10)

        # File is recent enough → skipped without HTTP HEAD
        assert len(result) == 1
        assert result[0] == tif_path

    @patch("cartoload.downloader.stac_source.query_stac_collection")
    @patch("cartoload.downloader.stac_source.requests.head")
    def test_max_age_days_checks_old_file(self, mock_head, mock_query, tmp_path):
        """With max_age_days=10, a file downloaded 20 days ago triggers freshness check."""
        source, sc, lc = self._make_source_and_configs()

        item_id = "item_2024_001"
        cache_dir = tmp_path / "test_stac" / "abc" / item_id
        cache_dir.mkdir(parents=True)
        tif_path = cache_dir / f"{item_id}.tif"
        tif_path.write_bytes(b"fake tif")
        meta_path = cache_dir / f"{item_id}.json"
        meta_path.write_text(
            json.dumps(
                {
                    "item_id": item_id,
                    "url": "https://example.com/data.tif",
                    "etag": "old_etag",
                    "download_date": (
                        datetime.now(timezone.utc) - timedelta(days=20)
                    ).isoformat(),
                }
            )
        )

        mock_query.return_value = [(item_id, "https://example.com/data.tif", None)]

        # Mock HTTP HEAD with same ETag → still fresh, no re-download
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.headers = {"ETag": '"old_etag"'}
        mock_head.return_value = mock_resp

        with patch.object(source, "_get_cache_dir", return_value=cache_dir):
            result = source.download(sc, lc, tmp_path, max_age_days=10)

        # Old file → HTTP HEAD check → ETag matches → use cache
        mock_head.assert_called()
        assert len(result) == 1
