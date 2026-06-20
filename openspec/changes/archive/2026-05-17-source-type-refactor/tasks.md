## 1. Config model changes

- [x] 1.1 Remove `url_template` from `SourceConfig` dataclass. Remove `url_template` from `SOURCE_TYPE_REQUIRED_FIELDS` and all validation logic. Add a helpful error message when `url_template` is used, suggesting `urls` instead.
- [x] 1.2 Remove `stac` from `ALLOWED_SOURCE_TYPES`. Add a helpful error message when `stac` is used, suggesting `type: geotiff` with STAC source method.
- [x] 1.3 Add `source_method` field to `SourceConfig` dataclass (type: `str | None`, default `None`). Valid values: `stac`, `path`, `None` (auto-detect).
- [x] 1.4 Add `_resolve_source_method()` function that auto-detects from URL pattern: URLs containing `/collections/` or `/stac/` → `stac`; local paths (starts with `./`, `../`, `/`, or no scheme) → `path`.
- [x] 1.5 Wire `_resolve_source_method()` into `_parse_sources_section()`: resolve and store on `SourceConfig`. Raise error if method cannot be determined and no explicit `source` field is provided.
- [x] 1.6 Parse the `source` field from source config YAML and use it as explicit override for `source_method` (skip auto-detection).
- [x] 1.7 Write tests: auto-detect STAC URL, auto-detect local path, explicit `source` override, `type: stac` rejected with helpful message, `url_template` rejected with helpful message, `wmts` unaffected, `urls` as string auto-wrapped to list.

## 2. Remove url_template from downstream code

- [x] 2.1 Update `pipeline.py`: remove all references to `source.url_template` (in `get_downloader()`, `_resolve_wmts_urls()`, and anywhere else). Use `source.urls` exclusively.
- [x] 2.2 Update `downloader/wmts.py` if it references `url_template` in its constructor or elsewhere.
- [x] 2.3 Update any other files referencing `source.url_template` or `SourceConfig.url_template`.

## 3. Extract shared STAC query logic

- [x] 3.1 Create `src/cartoload/downloader/stac_query.py` with a `query_stac_collection()` function extracting the shared query logic from `STACDownloader.query()` and `GPKGDownloader.query()`: HTTP request to `/items`, bbox filtering, spatial overlap check.
- [x] 3.2 Refactor `STACDownloader.query()` to delegate to `query_stac_collection()`, then apply `_find_geotiff_asset()` to results.
- [x] 3.3 Refactor `GPKGDownloader.query()` to delegate to `query_stac_collection()`, then apply `_find_gpkg_asset()` to results.
- [x] 3.4 Write tests for `query_stac_collection()` with mocked HTTP responses.

## 4. Pipeline dispatch refactor

- [x] 4.1 Update `build_layer()` dispatch in `src/cartoload/pipeline.py`: use `source.type` only (no more `source.type in ("stac", "geotiff")` — just `source.type == "geotiff"`). Use `source.source_method` to determine how to obtain files.
- [x] 4.2 Refactor `build_geotiff_layer()` to check `source.source_method`: if `"stac"` → use `STACDownloader`, if `"path"` → use `collect_geotiff_files`. Remove the `source.type == "stac"` / `source.type == "geotiff"` branching inside.
- [x] 4.3 Update `build_gpkg_layer()` to check `source.source_method`: if `"stac"` → use `GPKGDownloader`. If `"path"` → load local `.gpkg` file directly (new, simple path).
- [x] 4.4 Write tests: pipeline dispatches correctly for `type: geotiff` + `source: stac`, `type: geotiff` + `source: path`, `type: gpkg` + `source: stac`.

## 5. Update example configs

- [x] 5.1 Update `examples/configs/sources/swisstopo.yaml`: change `type: stac` to `type: geotiff`, convert `url_template` to `urls` if present. Keep `type: gpkg` and `type: wmts` as-is.
- [x] 5.2 Update `examples/configs/sources/france_ign.yaml` and `examples/configs/sources/basemap_at.yaml`: convert any `url_template` to `urls`.
- [x] 5.3 Update `examples/configs/layers/test.yaml` and `examples/configs/layers/switzerland.yaml`: verify source refs still work (source names unchanged, only definitions change).

## 6. Cleanup

- [x] 6.1 Remove any dead code paths that handled `source.type == "stac"` specifically.
- [x] 6.2 Run `just check` and `just check types` to verify formatting, linting, and type correctness.
- [x] 6.3 Run `just test` to verify all tests pass.
