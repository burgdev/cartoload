from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from cartoload.config import (
    LayerConfig,
    SourceConfig,
    load_config,
    load_layers_file,
    load_sources_file,
    merge_layers,
    merge_sources,
    resolve_references,
)


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


# Test load_sources_file


def test_load_sources_file_valid():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "sources": {
                    "test_wmts": {
                        "type": "wmts",
                        "url_template": "https://example.com/{z}/{x}/{y}.png",
                        "attribution": "Test",
                    },
                    "test_geotiff": {
                        "type": "geotiff",
                        "stac_url": "https://stac.example.com",
                    },
                }
            },
            f,
        )
        f.flush()

        sources = load_sources_file(f.name)
        Path(f.name).unlink()

        assert len(sources) == 2
        assert "test_wmts" in sources
        assert "test_geotiff" in sources
        assert sources["test_wmts"].type == "wmts"
        assert (
            sources["test_wmts"].url_template == "https://example.com/{z}/{x}/{y}.png"
        )
        assert sources["test_geotiff"].stac_url == "https://stac.example.com"


def test_load_sources_file_missing_sources_key():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"other_key": {}}, f)
        f.flush()

        with pytest.raises(
            ValueError, match="Missing required top-level 'sources' key"
        ):
            load_sources_file(f.name)
        Path(f.name).unlink()


def test_load_sources_file_missing_type():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "sources": {
                    "bad_source": {
                        "url_template": "https://example.com",
                    }
                }
            },
            f,
        )
        f.flush()

        with pytest.raises(ValueError, match="missing required field 'type'"):
            load_sources_file(f.name)
        Path(f.name).unlink()


def test_load_sources_file_invalid_type():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "sources": {
                    "bad_source": {
                        "type": "invalid_type",
                    }
                }
            },
            f,
        )
        f.flush()

        with pytest.raises(ValueError, match="has invalid type 'invalid_type'"):
            load_sources_file(f.name)
        Path(f.name).unlink()


def test_load_sources_file_missing_required_field():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "sources": {
                    "wmts_source": {
                        "type": "wmts",
                        # missing url_template
                    }
                }
            },
            f,
        )
        f.flush()

        with pytest.raises(ValueError, match="missing required field 'url_template'"):
            load_sources_file(f.name)
        Path(f.name).unlink()


def test_load_sources_file_nonexistent():
    with pytest.raises(FileNotFoundError):
        load_sources_file("/nonexistent/path.yaml")


# Test load_layers_file


def test_load_layers_file_valid():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "bounds": {
                    "west": 5.0,
                    "east": 10.0,
                    "south": 45.0,
                    "north": 48.0,
                },
                "layers": {
                    "test_layer": {
                        "name": "Test Layer",
                        "source": "test_source",
                        "zoom_levels": [10, 12, 14],
                        "exporter": "garmin_img",
                        "output": "test.img",
                    }
                },
            },
            f,
        )
        f.flush()

        layers, bounds = load_layers_file(f.name)
        Path(f.name).unlink()

        assert len(layers) == 1
        assert "test_layer" in layers
        assert layers["test_layer"].name == "Test Layer"
        assert layers["test_layer"].zoom_levels == [10, 12, 14]
        assert bounds is not None
        assert bounds["west"] == 5.0
        assert bounds["north"] == 48.0


def test_load_layers_file_missing_layers_key():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"other_key": {}}, f)
        f.flush()

        with pytest.raises(ValueError, match="Missing required top-level 'layers' key"):
            load_layers_file(f.name)
        Path(f.name).unlink()


def test_load_layers_file_missing_required_field():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "layers": {
                    "bad_layer": {
                        "name": "Bad Layer",
                        # missing source, zoom_levels, exporter, output
                    }
                }
            },
            f,
        )
        f.flush()

        with pytest.raises(ValueError, match="missing required field"):
            load_layers_file(f.name)
        Path(f.name).unlink()


def test_load_layers_file_invalid_zoom_levels():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "layers": {
                    "bad_layer": {
                        "name": "Bad Layer",
                        "source": "test",
                        "zoom_levels": [10, 25],  # 25 is out of range
                        "exporter": "garmin_img",
                        "output": "test.img",
                    }
                }
            },
            f,
        )
        f.flush()

        with pytest.raises(ValueError, match="has invalid zoom level 25"):
            load_layers_file(f.name)
        Path(f.name).unlink()


def test_load_layers_file_empty_zoom_levels():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "layers": {
                    "bad_layer": {
                        "name": "Bad Layer",
                        "source": "test",
                        "zoom_levels": [],
                        "exporter": "garmin_img",
                        "output": "test.img",
                    }
                }
            },
            f,
        )
        f.flush()

        with pytest.raises(ValueError, match="'zoom_levels' cannot be empty"):
            load_layers_file(f.name)
        Path(f.name).unlink()


def test_load_layers_file_invalid_bounds():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "bounds": {
                    "west": 10.0,
                    "east": 5.0,  # west >= east is invalid
                    "south": 45.0,
                    "north": 48.0,
                },
                "layers": {
                    "test_layer": {
                        "name": "Test",
                        "source": "test",
                        "zoom_levels": [10],
                        "exporter": "garmin_img",
                        "output": "test.img",
                    }
                },
            },
            f,
        )
        f.flush()

        with pytest.raises(ValueError, match="'bounds' invalid.*west.*>=.*east"):
            load_layers_file(f.name)
        Path(f.name).unlink()


# Test merge functions


def test_merge_sources():
    sources1 = {
        "source1": SourceConfig(id="source1", type="wmts"),
        "source2": SourceConfig(id="source2", type="geotiff"),
    }
    sources2 = {
        "source2": SourceConfig(id="source2", type="wmts"),  # overwrite
        "source3": SourceConfig(id="source3", type="wmts"),
    }

    merged = merge_sources(sources1, sources2)

    assert len(merged) == 3
    assert "source1" in merged
    assert "source2" in merged
    assert "source3" in merged
    assert merged["source2"].type == "wmts"  # last wins


def test_merge_layers():
    layers1 = {
        "layer1": LayerConfig(id="layer1", name="Layer 1"),
    }
    bounds1 = {"west": 5.0, "east": 10.0, "south": 45.0, "north": 48.0}

    layers2 = {
        "layer2": LayerConfig(id="layer2", name="Layer 2"),
    }
    bounds2 = {"west": 6.0, "east": 11.0, "south": 46.0, "north": 49.0}

    merged_layers, merged_bounds = merge_layers((layers1, bounds1), (layers2, bounds2))

    assert len(merged_layers) == 2
    assert "layer1" in merged_layers
    assert "layer2" in merged_layers
    assert merged_bounds == bounds2  # last wins


# Test resolve_references


def test_resolve_references_valid():
    sources = {
        "source1": SourceConfig(id="source1", type="wmts"),
    }
    layers = {
        "layer1": LayerConfig(id="layer1", name="Layer 1", source="source1"),
    }

    # Should not raise
    resolve_references(layers, sources)


def test_resolve_references_invalid():
    sources = {
        "source1": SourceConfig(id="source1", type="wmts"),
    }
    layers = {
        "layer1": LayerConfig(id="layer1", name="Layer 1", source="nonexistent"),
    }

    with pytest.raises(ValueError, match="Unresolved source references"):
        resolve_references(layers, sources)


# Test load_config


def test_load_config_integration(tmp_path):
    # Create source file
    sources_file = tmp_path / "sources.yaml"
    sources_file.write_text(
        yaml.dump(
            {
                "sources": {
                    "test_source": {
                        "type": "wmts",
                        "url_template": "https://example.com/{z}/{x}/{y}.png",
                    }
                }
            }
        )
    )

    # Create layers file
    layers_file = tmp_path / "layers.yaml"
    layers_file.write_text(
        yaml.dump(
            {
                "bounds": {
                    "west": 5.0,
                    "east": 10.0,
                    "south": 45.0,
                    "north": 48.0,
                },
                "layers": {
                    "test_layer": {
                        "name": "Test Layer",
                        "source": "test_source",
                        "zoom_levels": [10, 12],
                        "exporter": "garmin_img",
                        "output": "test.img",
                    }
                },
            }
        )
    )

    config = load_config([str(sources_file)], [str(layers_file)])

    assert len(config.sources) == 1
    assert len(config.layers) == 1
    assert config.bounds is not None
    assert config.bounds["west"] == 5.0


def test_load_config_no_files():
    config = load_config([], [])

    assert len(config.sources) == 0
    assert len(config.layers) == 0
    assert config.bounds is None
