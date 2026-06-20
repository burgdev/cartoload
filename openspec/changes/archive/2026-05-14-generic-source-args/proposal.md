## Why

Currently, URL template variables in source configs are limited to a hardcoded set (`{x}`, `{y}`, `{z}`, `{layer}`, `{source_id}`). The `{layer}` variable is populated via a dedicated `wmts_layer` field on the layer config, creating a tightly coupled one-off mechanism. This doesn't scale — as new source types or URL patterns are introduced (e.g., GeoTIFF, custom importers), each would need its own dedicated config field. A generic template variable system would decouple source URL structure from config schema, allowing any source field to be parameterized without code changes.

## What Changes

- **New `defaults` field on `SourceConfig`**: A dict of default variable values for template substitution in source string fields (urls, attribution). Uses `${name}` or `${name:-default}` syntax.
- **New `source_args` mechanism on layers**: Layer configs (and composite sub-layers) can provide a dict of variable values that override source defaults. This replaces the `wmts_layer` field as the primary way to pass layer-specific values into source templates.
- **Generic template substitution**: All source string fields (urls, attribution) will be processed through a central template engine (vendored, simplified expandvars) that resolves `${var}` and `${var:-default}` patterns using merged defaults + layer args. Bare `$var` is also supported. `$$` produces a literal `$`.
- **Backward compatibility**: `wmts_layer` on LayerConfig and CompositeSubLayer remains supported as a shorthand that maps to `source_args: {layer: <value>}`. Existing configs continue to work. The WMTS downloader's per-tile `{x}`, `{y}`, `{z}` substitution is preserved as-is.
- **Built-in variables**: Certain variables are always available depending on source type: `${x}`, `${y}`, `${z}`/`${zoom}` for WMTS, `${source_id}` for all sources.

## Capabilities

### New Capabilities
- `generic-source-args`: A generic template variable system for source configs — `defaults` on sources, `source_args` on layers, `${var}` / `${var:-default}` syntax (vendored from expandvars), backward-compatible `wmts_layer` mapping

### Modified Capabilities
- `fast-img-pipeline`: Pipeline dispatch must pass `source_args` through to the downloader instead of only `layer_name`
- `rasterio-warp-processor`: No functional change, but template resolution must complete before tile paths are resolved

## Impact

- **Config model** (`src/cartoload/config.py`): `SourceConfig` gains `defaults` dict; `LayerConfig` and `CompositeSubLayer` gain `source_args` dict; parsing logic updated
- **Template engine** (`src/cartoload/template.py`): New module — vendored, simplified expandvars (MIT) providing `expand(text, variables)` and `check_unresolved(text)`
- **WMTS downloader** (`src/cartoload/downloader/wmts.py`): `_build_tile_url` updated to use generic variable substitution instead of hardcoded `.replace()` calls
- **Pipeline** (`src/cartoload/pipeline.py`): `get_downloader()` and callers updated to pass `source_args` instead of just `layer_name`
- **Documentation** (`docs/configuration/`): Source and layer docs updated with template variable syntax
- **No new dependencies**: Template engine is a vendored, simplified version of expandvars (MIT) — no pip dependency
- **Backward compatible**: Existing configs with `wmts_layer` continue to work without changes
