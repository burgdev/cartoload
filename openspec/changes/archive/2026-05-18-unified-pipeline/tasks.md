## 1. Config model refactor

- [x] 1.1 Add `format` field to `CompositeSubLayer` (and the future layer definition model) — values: `geotiff`, `gpkg`, `wmts`
- [x] 1.2 Create `TargetConfig` dataclass with `id`, `name`, `description`, `output`, `exporter`, `layers` (ordered list of sub-layer references/inline definitions), `zoom_levels`, `bounds`
- [x] 1.3 Refactor `LayerConfig` to be definition-only (remove `output`, `exporter` fields)
- [x] 1.4 Update config parser to handle `targets:` section alongside `layers:` section
- [x] 1.5 Update `resolve_sub_layer_refs` to work with target layer entries referencing top-level layer definitions
- [x] 1.6 Update `load_config()` and unified config loading to return `Config` with both `layers` and `targets` dicts
- [x] 1.7 Verify: config parsing works with new structure — write/update unit tests for config loading

## 2. Source abstraction

- [x] 2.1 Create `Source` ABC in `src/cartoload/downloader/source.py` with `can_handle(cls, url)`, `download(layer_config)`, `is_cached(cache_path)` methods
- [x] 2.2 Create `StacSource` — refactor shared logic from `STACDownloader` and `GPKGDownloader` into one class. Use `query_stac_collection()` with format-aware asset finding driven by `layer_config.format`
- [x] 2.3 Create `WmtsSource` — wrapping current `WMTSDownloader` logic
- [x] 2.4 Create `PathSource` — resolving local file paths (currently inline in `build_geotiff_layer` and `build_gpkg_layer`)
- [x] 2.5 Implement cache lifecycle: `is_cached()` checks file + metadata sidecar OR processor completion marker
- [x] 2.6 Create source registry (`SOURCE_REGISTRY`, `register_source()`, `resolve_source()`) with built-in registrations
- [x] 2.7 Write unit tests for each Source implementation (mock HTTP for STAC, mock filesystem for Path, mock tile grid for WMTS)

## 3. LayerProvider abstraction

- [x] 3.1 Create `LayerProvider` ABC in `src/cartoload/processor/provider.py` with `download()`, `prepare()`, `to_raster(x, y, z)`, `supported_extensions` methods
- [x] 3.2 Create `GeotiffProvider` — extract pre-warp + VRT + tile reading from `build_geotiff_layer` and `_make_geotiff_processor`
- [x] 3.3 Create `GpkgProvider` — extract rasterization logic from `build_gpkg_layer` and `VectorRasterizer` integration
- [x] 3.4 Create `WmtsProvider` — extract tile loading from WMTS pipeline path and `_sub_layer_cache_path` logic
- [x] 3.5 Create provider registry (`PROVIDER_REGISTRY`, `register_provider()`, `make_provider()`) with built-in registrations
- [x] 3.6 Write unit tests for each Provider (mock Source, verify download→prepare→to_raster lifecycle)

## 4. Unified pipeline

- [x] 4.1 Create `build_target()` function that takes `TargetConfig` and orchestrates download→prepare→metadata→export for all providers
- [x] 4.2 Implement metadata computation for multi-provider case (estimate from sub-layers, refine by sampling)
- [x] 4.3 Implement single-provider fast path: detect `len(providers) == 1` and no opacity overrides → stream raw bytes without RGBA round-trip
- [x] 4.4 Implement multi-provider composite path: per-tile RGBA compositing with opacity, re-encode to JPEG
- [x] 4.5 Wire up tile fallback logic (upscale from lower zoom when tile missing)
- [x] 4.6 Wire up checkpoint/resume support from the unified pipeline
- [x] 4.7 Wire up preview generation from the unified pipeline
- [x] 4.8 Remove old dispatch paths: `build_geotiff_layer`, `build_gpkg_layer`, `build_composite_layer`, and inline WMTS path in `build_layer`
- [x] 4.9 Write integration tests for the unified pipeline: single-layer target (each format), multi-layer target, mixed formats

## 5. CLI update

- [x] 5.1 Update CLI `build` command: `-l` flag selects from `targets:` section instead of `layers:`
- [x] 5.2 Update build summary computation to work with `TargetConfig`
- [x] 5.3 Update error messages to reference "target" instead of "layer" where appropriate
- [x] 5.4 Verify: all CLI flags (`--force`, `--dry-run`, `--quality`, `--preview`, `--executor`, etc.) work with new pipeline
- [x] 5.5 Update CLI tests for new target-based flow

## 6. Example configs migration

- [x] 6.1 Update `examples/configs/layers/test.yaml` to new `layers` + `targets` structure
- [x] 6.2 Update `examples/configs/layers/switzerland.yaml` to new structure
- [x] 6.3 Update `examples/configs/sources/swisstopo.yaml` to use source types as fetch methods (remove format coupling)
- [x] 6.4 Update other example configs if present
- [x] 6.5 Verify: example configs parse correctly with new config model

## 7. Documentation

- [x] 7.1 Rewrite `docs/configuration/layers.md`: document `layers` (definitions) + `targets` (build instructions) structure with examples
- [x] 7.2 Update `docs/configuration/sources.md`: document source types as fetch methods (stac, wmts, path), explain `format` field on layers
- [x] 7.3 Update `docs/getting-started.md` if it references the old layer structure
- [x] 7.4 Update `docs/cli.md` to reflect `-l` selecting targets

## 8. Cleanup and verification

- [x] 8.1 Remove dead code from `pipeline.py` (old build functions, old helper functions that are now in providers)
- [x] 8.2 Remove unused imports across the codebase
- [x] 8.3 Run `just check` and `just check types` — fix any formatting, linting, or type errors
- [x] 8.4 Run `just test` — fix any test failures
- [x] 8.5 Run the full example command: `cartoload build -c examples/configs/layers/test.yaml -l ch_stac -y 46.496 -x 7.669 -W 20 -H 20 -f --preview --executor thread --quality 30` and verify it completes successfully
