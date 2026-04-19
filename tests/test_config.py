from __future__ import annotations

from cartoload.config import LayerConfig, SourceConfig


def test_source_config_wmts():
    source = SourceConfig(
        id="swisstopo_wmts",
        type="wmts",
        url_template="https://wmts.example.com/{layer}/{z}/{x}/{y}.jpeg",
        attribution="© swisstopo",
        rate_limit_ms=150,
        max_threads=4,
    )
    assert source.id == "swisstopo_wmts"
    assert source.type == "wmts"
    assert source.url_template is not None
    assert source.rate_limit_ms == 150
    assert source.max_threads == 4


def test_source_config_geotiff():
    source = SourceConfig(
        id="swisstopo_stac",
        type="geotiff",
        stac_url="https://data.geo.admin.ch/api/stac/v0.9/",
        attribution="© swisstopo",
    )
    assert source.id == "swisstopo_stac"
    assert source.type == "geotiff"
    assert source.url_template is None
    assert source.stac_url is not None


def test_source_config_defaults():
    source = SourceConfig(id="minimal", type="wmts")
    assert source.url_template is None
    assert source.attribution == ""
    assert source.rate_limit_ms == 150
    assert source.max_threads == 4


def test_layer_config_raster():
    layer = LayerConfig(
        id="ch_basemap_25k",
        name="Switzerland 1:25k",
        description="swisstopo national map",
        type="raster",
        source="swisstopo_stac",
        wmts_fallback="swisstopo_wmts",
        zoom_levels=[10, 12, 14],
        exporter="garmin_img",
        output="ch_basemap_25k.img",
    )
    assert layer.id == "ch_basemap_25k"
    assert layer.type == "raster"
    assert layer.wmts_fallback == "swisstopo_wmts"
    assert layer.zoom_levels == [10, 12, 14]
    assert layer.exporter == "garmin_img"


def test_layer_config_defaults():
    layer = LayerConfig(id="minimal", name="Minimal Layer")
    assert layer.type == "raster"
    assert layer.zoom_levels == []
    assert layer.exporter == "garmin_img"
    assert layer.bounds is None
