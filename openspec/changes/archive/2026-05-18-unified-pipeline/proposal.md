## Why

The pipeline has four separate build paths (composite, geotiff, gpkg, wmts) that duplicate download→metadata→export logic with subtle differences. Adding a new data type (e.g. GeoJSON) requires changes across multiple functions and is error-prone. The composite layer pipeline doesn't support gpkg sub-layers, causing a crash when vector overlays are included. The config conflates "what data to fetch" (source) with "how to process it" (format), and layer definitions serve double duty as both reusable definitions and build targets.

## What Changes

- **BREAKING**: Replace the four pipeline dispatch paths with a single unified pipeline where "single layer" is a composite with one sub-layer.
- **BREAKING**: Restructure config into `layers` (reusable definitions with defaults, no output) and `targets` (build instructions with output and ordered layer stack). CLI `-l` flag selects a target.
- **BREAKING**: Introduce `Source` and `LayerProvider` abstractions. Sources handle download to cache (STAC, WMTS, Path). Providers handle format-specific processing (Geotiff, Gpkg, Wmts, future: GeoJSON). The format field on a layer definition selects the provider.
- Source `type` becomes purely "how to fetch" (`stac`, `wmts`, `path`) — auto-detected from URLs with override. The `format` field on layers becomes "what the data is" (`geotiff`, `gpkg`, `wmts`) — selects the provider.
- Providers implement `download()`, `prepare()`, `to_raster(x, y, z)`. Future: `to_vector(x, y, z)`.
- Clean cache lifecycle: source owns metadata sidecar, processor can delete original files after processing (leaving marker).
- Fast path for single-provider targets with no opacity overrides (stream raw bytes, no RGBA round-trip).
- Update docs (`docs/configuration/layers.md`, `docs/configuration/sources.md`) for new config structure.

## Capabilities

### New Capabilities
- `unified-pipeline`: Single pipeline architecture with Source/Provider abstraction, replacing the four-path dispatch. Config split into `layers` (definitions) and `targets` (build instructions).
- `source-provider-registry`: Registry pattern for Sources and LayerProviders, making it easy to add new types (GeoJSON) and source methods (FTP).

### Modified Capabilities
- `source-method-resolution`: Source type becomes purely fetch method (stac/path/wmts), auto-detected from URLs. Format selection moves to layer definition.

## Impact

- **`src/cartoload/pipeline.py`**: Major rewrite — remove `build_geotiff_layer`, `build_gpkg_layer`, and inline WMTS path. Unified `build_target` function.
- **`src/cartoload/config.py`**: New `TargetConfig` dataclass, split `LayerConfig` into definition-only (no output). New `format` field. Parser changes for `targets:` section.
- **`src/cartoload/downloader/`**: Refactor into Source abstraction (StacSource, WmtsSource, PathSource). Shared cache lifecycle with metadata sidecar.
- **`src/cartoload/processor/`**: New LayerProvider abstraction (GeotiffProvider, GpkgProvider, WmtsProvider).
- **`src/cartoload/cli.py`**: CLI `-l` flag selects target instead of layer. Build summary adapts to unified pipeline.
- **`examples/configs/`**: All example configs updated to new `layers` + `targets` structure.
- **`docs/configuration/`**: Rewrite layers.md and sources.md for new config format.
- **`tests/`**: All tests updated for new config structure and pipeline.
