from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cartoload.config import (
    LayerConfig,
    SettingsConfig,
    SourceConfig,
    _parse_layers_section,
    _parse_settings_section,
    _parse_sources_section,
    _resolve_source_method,
    load_config,
    merge_layers,
    merge_settings,
    merge_sources,
    resolve_references,
    resolve_settings,
)
from cartoload.downloader.base import BaseDownloader


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


def test_source_config_wmts():
    source = SourceConfig(
        id="swisstopo_wmts",
        type="wmts",
        urls=["https://wmts.example.com/{layer}/{z}/{x}/{y}.jpeg"],
        attribution="© swisstopo",
        rate_limit_ms=150,
        max_threads=4,
    )
    assert source.id == "swisstopo_wmts"
    assert source.type == "wmts"
    assert source.urls is not None
    assert source.rate_limit_ms == 150
    assert source.max_threads == 4


def test_source_config_geotiff():
    source = SourceConfig(
        id="swisstopo_stac",
        type="geotiff",
        urls=["https://data.geo.admin.ch/api/stac/v1/collections/test"],
        source_method="stac",
        attribution="© swisstopo",
    )
    assert source.id == "swisstopo_stac"
    assert source.type == "geotiff"
    assert source.source_method == "stac"
    assert source.urls is not None


def test_source_config_defaults():
    source = SourceConfig(id="minimal", type="wmts")
    assert source.urls == []
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


def test_settings_config_defaults():
    settings = SettingsConfig()
    assert settings.cache_dir is None
    assert settings.output_dir is None
    assert settings.executor is None
    assert settings.quality is None
    assert settings.rate_limit_ms is None


# ---------------------------------------------------------------------------
# _parse_sources_section tests
# ---------------------------------------------------------------------------


def test_parse_sources_section_valid():
    data = {
        "sources": {
            "test_wmts": {
                "type": "wmts",
                "urls": ["https://example.com/{z}/{x}/{y}.png"],
                "attribution": "Test",
            },
            "test_geotiff": {
                "type": "geotiff",
                "urls": ["https://stac.example.com/collections/test"],
            },
        }
    }
    sources = _parse_sources_section(data, "test.yaml")
    assert len(sources) == 2
    assert "test_wmts" in sources
    assert "test_geotiff" in sources
    assert sources["test_wmts"].type == "wmts"
    assert sources["test_geotiff"].urls == ["https://stac.example.com/collections/test"]


def test_parse_sources_section_missing():
    """When no sources key, returns empty dict."""
    sources = _parse_sources_section({}, "test.yaml")
    assert sources == {}


def test_parse_sources_section_missing_type():
    with pytest.raises(ValueError, match="missing required field 'type'"):
        _parse_sources_section(
            {"sources": {"bad": {"urls": ["https://example.com"]}}},
            "test.yaml",
        )


def test_parse_sources_section_invalid_type():
    with pytest.raises(ValueError, match="has invalid type 'invalid_type'"):
        _parse_sources_section(
            {"sources": {"bad": {"type": "invalid_type"}}},
            "test.yaml",
        )


def test_parse_sources_section_missing_required_field():
    with pytest.raises(ValueError, match="missing required field 'urls'"):
        _parse_sources_section(
            {"sources": {"wmts_source": {"type": "wmts"}}},
            "test.yaml",
        )


def test_parse_sources_section_crs_field():
    data = {
        "sources": {
            "test_wmts": {
                "type": "wmts",
                "urls": ["https://example.com/{z}/{x}/{y}.png"],
                "crs": "EPSG:3857",
            }
        }
    }
    sources = _parse_sources_section(data, "test.yaml")
    assert sources["test_wmts"].crs == "EPSG:3857"


def test_parse_sources_section_crs_default_none():
    data = {
        "sources": {
            "test_wmts": {
                "type": "wmts",
                "urls": ["https://example.com/{z}/{x}/{y}.png"],
            }
        }
    }
    sources = _parse_sources_section(data, "test.yaml")
    assert sources["test_wmts"].crs is None


def test_parse_sources_section_crs_invalid_type():
    with pytest.raises(ValueError, match="field 'crs' must be a string"):
        _parse_sources_section(
            {
                "sources": {
                    "test_wmts": {
                        "type": "wmts",
                        "urls": ["https://x"],
                        "crs": 3857,
                    }
                }
            },
            "test.yaml",
        )


def test_parse_sources_section_urls_list():
    data = {
        "sources": {
            "test_wmts": {
                "type": "wmts",
                "urls": [
                    "https://s1.example.com/{z}/{x}/{y}.png",
                    "https://s2.example.com/{z}/{x}/{y}.png",
                ],
            }
        }
    }
    sources = _parse_sources_section(data, "test.yaml")
    assert len(sources["test_wmts"].urls) == 2


def test_parse_sources_section_urls_string():
    data = {
        "sources": {
            "test_wmts": {
                "type": "wmts",
                "urls": "https://example.com/{z}/{x}/{y}.png",
            }
        }
    }
    sources = _parse_sources_section(data, "test.yaml")
    assert sources["test_wmts"].urls == ["https://example.com/{z}/{x}/{y}.png"]


def test_parse_sources_section_asset_filter():
    data = {
        "sources": {
            "test_stac": {
                "type": "geotiff",
                "urls": ["https://stac.example.com/collections/test"],
                "defaults": {
                    "layer": "my_collection",
                    "asset_filter": {"geoadmin:variant": "komb"},
                },
            }
        }
    }
    sources = _parse_sources_section(data, "test.yaml")
    assert sources["test_stac"].asset_filter == {"geoadmin:variant": "komb"}
    assert "asset_filter" not in sources["test_stac"].defaults
    assert sources["test_stac"].defaults == {"layer": "my_collection"}


def test_parse_sources_section_no_asset_filter():
    data = {
        "sources": {
            "test_stac": {
                "type": "geotiff",
                "urls": ["https://stac.example.com/collections/test"],
                "defaults": {"layer": "my_collection"},
            }
        }
    }
    sources = _parse_sources_section(data, "test.yaml")
    assert sources["test_stac"].asset_filter is None


def test_parse_sources_section_asset_filter_invalid_type():
    with pytest.raises(ValueError, match="defaults.asset_filter.*must be a dict"):
        _parse_sources_section(
            {
                "sources": {
                    "test_stac": {
                        "type": "geotiff",
                        "urls": ["https://stac.example.com/collections/test"],
                        "defaults": {
                            "layer": "my_collection",
                            "asset_filter": "not_a_dict",
                        },
                    }
                }
            },
            "test.yaml",
        )


# ---------------------------------------------------------------------------
# _parse_layers_section tests
# ---------------------------------------------------------------------------


def test_parse_layers_section_valid():
    data = {
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
    }
    layers, bounds = _parse_layers_section(data, "test.yaml")
    assert len(layers) == 1
    assert "test_layer" in layers
    assert layers["test_layer"].name == "Test Layer"
    assert layers["test_layer"].zoom_levels == [10, 12, 14]
    assert bounds is not None
    assert bounds["west"] == 5.0
    assert bounds["north"] == 48.0


def test_parse_layers_section_missing():
    """When no layers key, returns empty."""
    layers, bounds = _parse_layers_section({}, "test.yaml")
    assert layers == {}
    assert bounds is None


def test_parse_layers_section_missing_required_field():
    with pytest.raises(ValueError, match="missing required field"):
        _parse_layers_section(
            {
                "layers": {
                    "bad_layer": {
                        "name": "Bad Layer",
                    }
                }
            },
            "test.yaml",
        )


def test_parse_layers_section_invalid_zoom_levels():
    with pytest.raises(ValueError, match="has invalid zoom level 25"):
        _parse_layers_section(
            {
                "layers": {
                    "bad_layer": {
                        "name": "Bad Layer",
                        "source": "test",
                        "zoom_levels": [10, 25],
                        "exporter": "garmin_img",
                        "output": "test.img",
                    }
                }
            },
            "test.yaml",
        )


def test_parse_layers_section_empty_zoom_levels():
    with pytest.raises(ValueError, match="'zoom_levels' cannot be empty"):
        _parse_layers_section(
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
            "test.yaml",
        )


def test_parse_layers_section_invalid_bounds():
    with pytest.raises(ValueError, match="'bounds' invalid.*west.*>=.*east"):
        _parse_layers_section(
            {
                "bounds": {
                    "west": 10.0,
                    "east": 5.0,
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
            "test.yaml",
        )


def test_parse_layers_section_asset_filter_in_source_dict():
    data = {
        "bounds": {
            "west": 5.0,
            "east": 10.0,
            "south": 45.0,
            "north": 48.0,
        },
        "layers": {
            "test_layer": {
                "name": "Test Layer",
                "source": {
                    "ref": "test_stac",
                    "asset_filter": {"geoadmin:variant": "krel"},
                },
                "zoom_levels": [10],
                "exporter": "garmin_img",
                "output": "test.img",
            }
        },
    }
    layers, _ = _parse_layers_section(data, "test.yaml")
    assert layers["test_layer"].asset_filter == {"geoadmin:variant": "krel"}
    assert "asset_filter" not in layers["test_layer"].source_args


def test_parse_layers_section_no_asset_filter():
    data = {
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
                "zoom_levels": [10],
                "exporter": "garmin_img",
                "output": "test.img",
            }
        },
    }
    layers, _ = _parse_layers_section(data, "test.yaml")
    assert layers["test_layer"].asset_filter is None


# ---------------------------------------------------------------------------
# Merge tests
# ---------------------------------------------------------------------------


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


def test_merge_settings():
    s1 = SettingsConfig(cache_dir="./a", quality=80)
    s2 = SettingsConfig(quality=90, executor="thread")

    merged = merge_settings(s1, s2)
    assert merged.cache_dir == "./a"
    assert merged.quality == 90  # last wins
    assert merged.executor == "thread"
    assert merged.output_dir is None


# ---------------------------------------------------------------------------
# resolve_references tests
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# load_config integration tests
# ---------------------------------------------------------------------------


def _write_yaml(tmp_path: Path, name: str, data: dict) -> Path:
    """Helper to write a YAML file."""
    p = tmp_path / name
    p.write_text(yaml.dump(data, default_flow_style=False))
    return p


def test_load_config_single_file(tmp_path):
    """Single file with sources, bounds, and layers."""
    cfg = _write_yaml(
        tmp_path,
        "config.yaml",
        {
            "sources": {
                "test_source": {
                    "type": "wmts",
                    "urls": ["https://example.com/{z}/{x}/{y}.png"],
                }
            },
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
        },
    )

    config = load_config([str(cfg)])
    assert len(config.sources) == 1
    assert len(config.layers) == 1
    assert config.bounds is not None
    assert config.bounds["west"] == 5.0


def test_load_config_sources_only(tmp_path):
    """File with only sources section."""
    cfg = _write_yaml(
        tmp_path,
        "sources.yaml",
        {
            "sources": {
                "test_source": {
                    "type": "wmts",
                    "urls": ["https://example.com/{z}/{x}/{y}.png"],
                }
            }
        },
    )
    config = load_config([str(cfg)])
    assert len(config.sources) == 1
    assert len(config.layers) == 0
    assert config.bounds is None


def test_load_config_layers_only_no_sources(tmp_path):
    """File with only layers and bounds — will fail on reference resolution."""
    cfg = _write_yaml(
        tmp_path,
        "layers.yaml",
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
                    "source": "missing_source",
                    "zoom_levels": [10],
                    "exporter": "garmin_img",
                    "output": "test.img",
                }
            },
        },
    )
    with pytest.raises(ValueError, match="Unresolved source references"):
        load_config([str(cfg)])


def test_load_config_empty_file(tmp_path):
    cfg = _write_yaml(tmp_path, "empty.yaml", {})
    config = load_config([str(cfg)])
    assert len(config.sources) == 0
    assert len(config.layers) == 0
    assert config.bounds is None


def test_load_config_no_files():
    config = load_config([])
    assert len(config.sources) == 0
    assert len(config.layers) == 0
    assert config.bounds is None


def test_load_config_nonexistent_file():
    with pytest.raises(FileNotFoundError):
        load_config(["/nonexistent/path.yaml"])


# ---------------------------------------------------------------------------
# Include tests
# ---------------------------------------------------------------------------


def test_load_config_single_include(tmp_path):
    """Config file includes a sources file."""
    _write_yaml(
        tmp_path,
        "sources.yaml",
        {
            "sources": {
                "test_source": {
                    "type": "wmts",
                    "urls": ["https://example.com/{z}/{x}/{y}.png"],
                }
            }
        },
    )
    main_cfg = _write_yaml(
        tmp_path,
        "main.yaml",
        {
            "includes": ["sources.yaml"],
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
                    "zoom_levels": [10],
                    "exporter": "garmin_img",
                    "output": "test.img",
                }
            },
        },
    )

    config = load_config([str(main_cfg)])
    assert "test_source" in config.sources
    assert "test_layer" in config.layers


def test_load_config_multiple_includes(tmp_path):
    """Config includes two files in order."""
    _write_yaml(
        tmp_path,
        "src1.yaml",
        {
            "sources": {
                "s1": {
                    "type": "wmts",
                    "urls": ["https://s1.example.com"],
                }
            }
        },
    )
    _write_yaml(
        tmp_path,
        "src2.yaml",
        {
            "sources": {
                "s2": {
                    "type": "geotiff",
                    "urls": ["https://s2.example.com/collections/test"],
                }
            }
        },
    )
    main_cfg = _write_yaml(
        tmp_path,
        "main.yaml",
        {
            "includes": ["src1.yaml", "src2.yaml"],
            "layers": {
                "test": {
                    "name": "Test",
                    "source": "s1",
                    "zoom_levels": [10],
                    "exporter": "garmin_img",
                    "output": "test.img",
                }
            },
        },
    )

    config = load_config([str(main_cfg)])
    assert "s1" in config.sources
    assert "s2" in config.sources


def test_load_config_nested_includes(tmp_path):
    """Included file itself includes another file."""
    _write_yaml(
        tmp_path,
        "base.yaml",
        {
            "sources": {
                "base_src": {
                    "type": "wmts",
                    "urls": ["https://base.example.com"],
                }
            }
        },
    )
    _write_yaml(
        tmp_path,
        "mid.yaml",
        {
            "includes": ["base.yaml"],
            "layers": {
                "mid_layer": {
                    "name": "Mid Layer",
                    "source": "base_src",
                    "zoom_levels": [10],
                    "exporter": "garmin_img",
                    "output": "mid.img",
                }
            },
        },
    )
    main_cfg = _write_yaml(
        tmp_path,
        "main.yaml",
        {"includes": ["mid.yaml"]},
    )

    config = load_config([str(main_cfg)])
    assert "base_src" in config.sources
    assert "mid_layer" in config.layers


def test_load_config_missing_include(tmp_path):
    """Including a nonexistent file raises FileNotFoundError."""
    cfg = _write_yaml(
        tmp_path,
        "main.yaml",
        {"includes": ["nonexistent.yaml"]},
    )
    with pytest.raises(FileNotFoundError):
        load_config([str(cfg)])


def test_load_config_include_relative_path(tmp_path):
    """Include paths are relative to the declaring file's directory."""
    subdir = tmp_path / "sub"
    subdir.mkdir()
    _write_yaml(
        subdir,
        "nested_src.yaml",
        {
            "sources": {
                "nested": {
                    "type": "wmts",
                    "urls": ["https://nested.example.com"],
                }
            }
        },
    )
    main_cfg = _write_yaml(
        tmp_path,
        "main.yaml",
        {
            "includes": ["sub/nested_src.yaml"],
            "layers": {
                "test": {
                    "name": "Test",
                    "source": "nested",
                    "zoom_levels": [10],
                    "exporter": "garmin_img",
                    "output": "test.img",
                }
            },
        },
    )

    config = load_config([str(main_cfg)])
    assert "nested" in config.sources


# ---------------------------------------------------------------------------
# Circular include tests
# ---------------------------------------------------------------------------


def test_load_config_circular_include_direct(tmp_path):
    """File A includes file B, file B includes file A."""
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text(yaml.dump({"includes": ["b.yaml"]}))
    b.write_text(yaml.dump({"includes": ["a.yaml"]}))

    with pytest.raises(ValueError, match="Circular include"):
        load_config([str(a)])


def test_load_config_circular_include_indirect(tmp_path):
    """A → B → C → A."""
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    c = tmp_path / "c.yaml"
    a.write_text(yaml.dump({"includes": ["b.yaml"]}))
    b.write_text(yaml.dump({"includes": ["c.yaml"]}))
    c.write_text(yaml.dump({"includes": ["a.yaml"]}))

    with pytest.raises(ValueError, match="Circular include"):
        load_config([str(a)])


# ---------------------------------------------------------------------------
# Merge semantics tests
# ---------------------------------------------------------------------------


def test_load_config_duplicate_source_across_includes(tmp_path):
    """Same source key in include and including file — later wins."""
    _write_yaml(
        tmp_path,
        "base.yaml",
        {
            "sources": {
                "shared": {
                    "type": "wmts",
                    "urls": ["https://base.example.com"],
                }
            }
        },
    )
    main_cfg = _write_yaml(
        tmp_path,
        "main.yaml",
        {
            "includes": ["base.yaml"],
            "sources": {
                "shared": {
                    "type": "geotiff",
                    "urls": ["https://override.example.com/collections/test"],
                }
            },
        },
    )

    config = load_config([str(main_cfg)])
    assert config.sources["shared"].type == "geotiff"


def test_load_config_duplicate_layer_across_cli_flags(tmp_path):
    """Same layer key across multiple -c flags — last wins."""
    cfg1 = _write_yaml(
        tmp_path,
        "first.yaml",
        {
            "sources": {
                "s": {
                    "type": "wmts",
                    "urls": ["https://example.com"],
                }
            },
            "layers": {
                "layer1": {
                    "name": "First",
                    "source": "s",
                    "zoom_levels": [10],
                    "exporter": "garmin_img",
                    "output": "first.img",
                }
            },
        },
    )
    cfg2 = _write_yaml(
        tmp_path,
        "second.yaml",
        {
            "layers": {
                "layer1": {
                    "name": "Second",
                    "source": "s",
                    "zoom_levels": [12],
                    "exporter": "garmin_img",
                    "output": "second.img",
                }
            },
        },
    )

    config = load_config([str(cfg1), str(cfg2)])
    assert config.layers["layer1"].name == "Second"


def test_load_config_duplicate_bounds(tmp_path):
    """Bounds defined in multiple includes — last wins."""
    _write_yaml(
        tmp_path,
        "base.yaml",
        {
            "bounds": {"west": 1.0, "east": 2.0, "south": 3.0, "north": 4.0},
            "sources": {"s": {"type": "wmts", "urls": ["https://example.com"]}},
            "layers": {
                "l": {
                    "name": "L",
                    "source": "s",
                    "zoom_levels": [10],
                    "exporter": "garmin_img",
                    "output": "l.img",
                }
            },
        },
    )
    main_cfg = _write_yaml(
        tmp_path,
        "main.yaml",
        {
            "includes": ["base.yaml"],
            "bounds": {"west": 5.0, "east": 10.0, "south": 45.0, "north": 48.0},
        },
    )

    config = load_config([str(main_cfg)])
    assert config.bounds["west"] == 5.0


# ---------------------------------------------------------------------------
# Settings tests
# ---------------------------------------------------------------------------


def test_parse_settings_section_valid():
    data = {"settings": {"cache_dir": "./my_cache", "quality": 85}}
    settings = _parse_settings_section(data, "test.yaml")
    assert settings.cache_dir == "./my_cache"
    assert settings.quality == 85
    assert settings.output_dir is None


def test_parse_settings_section_absent():
    settings = _parse_settings_section({}, "test.yaml")
    assert settings.cache_dir is None


def test_parse_settings_section_unknown_key():
    with pytest.raises(ValueError, match="Unknown settings key 'bad_key'"):
        _parse_settings_section({"settings": {"bad_key": "value"}}, "test.yaml")


def test_settings_merge_across_includes(tmp_path):
    _write_yaml(
        tmp_path,
        "base.yaml",
        {"settings": {"cache_dir": "./a"}},
    )
    main_cfg = _write_yaml(
        tmp_path,
        "main.yaml",
        {"includes": ["base.yaml"], "settings": {"quality": 90}},
    )

    config = load_config([str(main_cfg)])
    assert config.settings.cache_dir == "./a"
    assert config.settings.quality == 90


# ---------------------------------------------------------------------------
# resolve_settings / env var tests
# ---------------------------------------------------------------------------


def test_resolve_settings_config_only():
    settings = SettingsConfig(cache_dir="./cache", quality=85)
    resolved = resolve_settings(settings)
    assert resolved["cache_dir"] == "./cache"
    assert resolved["quality"] == 85


def test_resolve_settings_env_overrides_config(monkeypatch):
    monkeypatch.setenv("CARTOLOAD_CACHE_DIR", "/tmp/cache")
    settings = SettingsConfig(cache_dir="./cache")
    resolved = resolve_settings(settings)
    assert resolved["cache_dir"] == "/tmp/cache"


def test_resolve_settings_env_with_no_config(monkeypatch):
    monkeypatch.setenv("CARTOLOAD_QUALITY", "70")
    settings = SettingsConfig()
    resolved = resolve_settings(settings)
    assert resolved["quality"] == 70


def test_resolve_settings_quality_env_coerced_to_int(monkeypatch):
    monkeypatch.setenv("CARTOLOAD_QUALITY", "50")
    resolved = resolve_settings(SettingsConfig())
    assert resolved["quality"] == 50
    assert isinstance(resolved["quality"], int)


def test_resolve_settings_rate_limit_env_coerced_to_int(monkeypatch):
    monkeypatch.setenv("CARTOLOAD_RATE_LIMIT_MS", "200")
    resolved = resolve_settings(SettingsConfig())
    assert resolved["rate_limit_ms"] == 200
    assert isinstance(resolved["rate_limit_ms"], int)


# ---------------------------------------------------------------------------
# Cache metadata tests (kept from original)
# ---------------------------------------------------------------------------


class _DummyDownloader(BaseDownloader):
    """Minimal concrete downloader for testing base class methods."""

    def download_tile(self, x: int, y: int, zoom: int) -> Path:
        return Path("/dummy")

    def download_grid(
        self, bbox: tuple[float, float, float, float], zoom: int
    ) -> list[Path]:
        return []


def test_cache_metadata_write(tmp_path):
    dl = _DummyDownloader("test_source", tmp_path, crs="EPSG:3857")
    dl.write_cache_metadata()

    metadata_path = tmp_path / "test_source" / "metadata.json"
    assert metadata_path.exists()
    import json

    data = json.loads(metadata_path.read_text())
    assert data["crs"] == "EPSG:3857"


def test_cache_metadata_no_crs(tmp_path):
    dl = _DummyDownloader("test_source", tmp_path, crs=None)
    dl.write_cache_metadata()

    metadata_path = tmp_path / "test_source" / "metadata.json"
    assert metadata_path.exists()
    import json

    data = json.loads(metadata_path.read_text())
    assert "crs" not in data


def test_cache_metadata_idempotent(tmp_path):
    dl = _DummyDownloader("test_source", tmp_path, crs="EPSG:3857")
    dl.write_cache_metadata()

    metadata_path = tmp_path / "test_source" / "metadata.json"

    original = metadata_path.read_text()

    # Second write should not overwrite
    dl2 = _DummyDownloader("test_source", tmp_path, crs="EPSG:4326")
    dl2.write_cache_metadata()
    assert metadata_path.read_text() == original


def test_read_cache_crs(tmp_path):
    import json

    cache_dir = tmp_path / "cache"
    source_dir = cache_dir / "my_source"
    source_dir.mkdir(parents=True)
    (source_dir / "metadata.json").write_text(json.dumps({"crs": "EPSG:3857"}) + "\n")

    assert BaseDownloader.read_cache_crs(cache_dir, "my_source") == "EPSG:3857"


def test_read_cache_crs_missing(tmp_path):
    assert BaseDownloader.read_cache_crs(tmp_path, "nonexistent") is None


def test_read_cache_crs_corrupt(tmp_path):
    source_dir = tmp_path / "broken_source"
    source_dir.mkdir()
    (source_dir / "metadata.json").write_text("not valid json{{{")

    assert BaseDownloader.read_cache_crs(tmp_path, "broken_source") is None


# ---------------------------------------------------------------------------
# Source method resolution tests (Task 1.7)
# ---------------------------------------------------------------------------


class TestResolveSourceMethod:
    """Tests for _resolve_source_method() auto-detection logic."""

    def test_auto_detect_stac_collections_url(self):
        assert (
            _resolve_source_method(
                ["https://example.com/api/stac/v1/collections/my_layer"]
            )
            == "stac"
        )

    def test_auto_detect_stac_in_path(self):
        assert _resolve_source_method(["https://example.com/stac/items"]) == "stac"

    def test_auto_detect_local_path_relative(self):
        assert _resolve_source_method(["./cache/geotiffs/"]) == "path"

    def test_auto_detect_local_path_relative_parent(self):
        assert _resolve_source_method(["../data/tiles/"]) == "path"

    def test_auto_detect_local_path_absolute(self):
        assert _resolve_source_method(["/data/tiles/"]) == "path"

    def test_auto_detect_local_path_no_scheme(self):
        assert _resolve_source_method(["cache/geotiffs/"]) == "path"

    def test_explicit_stac_override(self):
        assert _resolve_source_method(["./local/path"], explicit="stac") == "stac"

    def test_explicit_path_override(self):
        assert (
            _resolve_source_method(
                ["https://stac.example.com/collections/test"], explicit="path"
            )
            == "path"
        )

    def test_explicit_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid source method 'invalid'"):
            _resolve_source_method(["https://x"], explicit="invalid")

    def test_auto_detect_empty_urls_raises(self):
        with pytest.raises(ValueError, match="no URLs provided"):
            _resolve_source_method([], explicit=None)

    def test_auto_detect_unrecognized_url_raises(self):
        with pytest.raises(ValueError, match="Cannot auto-detect source method"):
            _resolve_source_method(["https://example.com/data"])


class TestSourceMethodInParsedConfig:
    """Tests that source_method is correctly set during config parsing."""

    def test_geotiff_with_stac_url_auto_detected(self):
        data = {
            "sources": {
                "my_geotiff": {
                    "type": "geotiff",
                    "urls": ["https://data.geo.admin.ch/api/stac/v1/collections/test"],
                }
            }
        }
        sources = _parse_sources_section(data, "test.yaml")
        assert sources["my_geotiff"].source_method == "stac"

    def test_geotiff_with_local_path_auto_detected(self):
        data = {
            "sources": {
                "my_geotiff": {
                    "type": "geotiff",
                    "urls": ["./cache/geotiffs/"],
                }
            }
        }
        sources = _parse_sources_section(data, "test.yaml")
        assert sources["my_geotiff"].source_method == "path"

    def test_gpkg_with_stac_url_auto_detected(self):
        data = {
            "sources": {
                "my_gpkg": {
                    "type": "gpkg",
                    "urls": [
                        "https://data.geo.admin.ch/api/stac/v0.9/collections/test"
                    ],
                }
            }
        }
        sources = _parse_sources_section(data, "test.yaml")
        assert sources["my_gpkg"].source_method == "stac"

    def test_explicit_source_field_stac(self):
        data = {
            "sources": {
                "my_geotiff": {
                    "type": "geotiff",
                    "source": "stac",
                    "urls": ["https://example.com/data"],
                }
            }
        }
        sources = _parse_sources_section(data, "test.yaml")
        assert sources["my_geotiff"].source_method == "stac"

    def test_explicit_source_field_path(self):
        data = {
            "sources": {
                "my_geotiff": {
                    "type": "geotiff",
                    "source": "path",
                    "urls": ["https://example.com/data"],
                }
            }
        }
        sources = _parse_sources_section(data, "test.yaml")
        assert sources["my_geotiff"].source_method == "path"

    def test_wmts_url_no_source_method_needed(self):
        """WMTS sources don't need source_method — it's skipped for WMTS."""
        data = {
            "sources": {
                "my_wmts": {
                    "type": "wmts",
                    "urls": ["https://wmts.example.com/{z}/{x}/{y}.png"],
                }
            }
        }
        sources = _parse_sources_section(data, "test.yaml")
        assert sources["my_wmts"].type == "wmts"
        assert sources["my_wmts"].source_method is None


class TestDeprecatedFieldRejection:
    """Tests that deprecated config fields are rejected with helpful messages."""

    def test_type_stac_rejected(self):
        data = {
            "sources": {
                "bad": {
                    "type": "stac",
                    "urls": ["https://stac.example.com/collections/test"],
                }
            }
        }
        with pytest.raises(
            ValueError, match="deprecated type 'stac'.*Use type 'geotiff'"
        ):
            _parse_sources_section(data, "test.yaml")

    def test_url_template_rejected(self):
        data = {
            "sources": {
                "bad": {
                    "type": "wmts",
                    "url_template": "https://example.com/{z}/{x}/{y}.png",
                }
            }
        }
        with pytest.raises(
            ValueError, match="deprecated field 'url_template'.*Use 'urls'"
        ):
            _parse_sources_section(data, "test.yaml")


class TestUrlsFieldParsing:
    """Tests for the urls field accepting both string and list."""

    def test_urls_as_string_auto_wrapped(self):
        data = {
            "sources": {
                "test": {
                    "type": "geotiff",
                    "urls": "https://stac.example.com/collections/test",
                }
            }
        }
        sources = _parse_sources_section(data, "test.yaml")
        assert sources["test"].urls == ["https://stac.example.com/collections/test"]
        assert sources["test"].source_method == "stac"

    def test_urls_as_list(self):
        data = {
            "sources": {
                "test": {
                    "type": "geotiff",
                    "urls": [
                        "https://stac.example.com/collections/test1",
                        "https://stac.example.com/collections/test2",
                    ],
                }
            }
        }
        sources = _parse_sources_section(data, "test.yaml")
        assert len(sources["test"].urls) == 2
        assert sources["test"].source_method == "stac"

    def test_urls_empty_list_rejected(self):
        data = {
            "sources": {
                "test": {
                    "type": "geotiff",
                    "urls": [],
                }
            }
        }
        with pytest.raises(ValueError, match="missing required field 'urls'"):
            _parse_sources_section(data, "test.yaml")

    def test_urls_missing_rejected(self):
        data = {
            "sources": {
                "test": {
                    "type": "geotiff",
                }
            }
        }
        with pytest.raises(ValueError, match="missing required field 'urls'"):
            _parse_sources_section(data, "test.yaml")
