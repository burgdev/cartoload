## 1. Package Restructure — `downloader/` → `source/`

- [x] 1.1 Rename `src/cartoload/downloader/` to `src/cartoload/source/`. Update all imports across the entire codebase (src + tests). Run tests.
- [x] 1.2 Rename `source/source.py` → `source/base.py`. Update imports. Run tests.
- [x] 1.3 Create `source/stac/` subpackage. Move `stac_source.py` → `stac/source.py`, `stac_query.py` → `stac/query.py`. Create `stac/__init__.py` re-exporting `StacSource`. Update all imports. Run tests.
- [x] 1.4 Move `wmts_source.py` into `source/wmts/` as `wmts/source.py`. Update `wmts/__init__.py` to re-export `WmtsSource`. Update all imports. Run tests.
- [x] 1.5 Rename `source/path_source.py` → `source/path.py`. Update imports. Run tests.
- [x] 1.6 Update `source/__init__.py` to re-export `Source`, `StacSource`, `WmtsSource`, `PathSource`, `resolve_source`, `register_source`. Run tests.

## 2. Delete Legacy Downloader Classes

- [x] 2.1 Identify any unique logic in `STACDownloader` (`stac.py`) not present in `StacSource`. Merge into `StacSource` if needed. Delete `stac.py`. Run tests.
- [x] 2.2 Identify any unique logic in `GPKGDownloader` (`gpkg.py`) not present in `StacSource`. Merge into `StacSource` if needed. Delete `gpkg.py`. Run tests.
- [ ] 2.3 Remove `BaseDownloader` ABC inheritance from `WmtsDownloader` in `wmts/download.py`. Make it a standalone class. Delete `source/base.py` (the old `downloader/base.py`). Run tests.
- [x] 2.4 Rename `WMTSDownloader` to `WmtsDownloader` for consistent casing with `WmtsSource`. Update all references. Run tests.

## 3. Package Restructure — `processor/` Subpackages

- [x] 3.1 Create `processor/geotiff/` subpackage. Move `geotiff_provider.py`, `geotiff_tile_reader.py`, `geotiff_collector.py`, `geotiff_index.py`, `geotiff_prewarp.py` into it with prefix-stripped names: `processor.py`, `tile_reader.py`, `collector.py`, `index.py`, `prewarp.py`. Create `__init__.py` re-exporting main classes. Update all imports (src + tests). Run tests.
- [x] 3.2 Create `processor/gpkg/` subpackage. Move `gpkg_provider.py` → `gpkg/processor.py` and `vector_rasterizer.py` → `gpkg/vector_rasterizer.py`. Create `__init__.py`. Update all imports. Run tests.
- [x] 3.3 Create `processor/wmts/` subpackage. Move `wmts_provider.py` → `wmts/processor.py`. Move `batch.py` → `wmts/batch.py`. Create `__init__.py`. Update all imports. Run tests.
- [x] 3.4 Update `processor/__init__.py` to re-export `LayerProcessor`, `GeotiffProcessor`, `GpkgProcessor`, `WmtsProcessor`, `make_processor`, `register_processor`. Run tests.

## 4. Rename Provider → Processor

- [x] 4.1 Rename `processor/provider.py` → `processor/base.py`. Run tests.
- [x] 4.2 Rename `LayerProvider` → `LayerProcessor` in `processor/base.py`. Update all references across the codebase. Run tests.
- [x] 4.3 Rename `GeotiffProvider` → `GeotiffProcessor` in `processor/geotiff/processor.py`. Update all references. Run tests.
- [x] 4.4 Rename `GpkgProvider` → `GpkgProcessor` in `processor/gpkg/processor.py`. Update all references. Run tests.
- [x] 4.5 Rename `WmtsProvider` → `WmtsProcessor` in `processor/wmts/processor.py`. Update all references. Run tests.
- [x] 4.6 Rename registry functions: `register_provider` → `register_processor`, `make_provider` → `make_processor`, `get_provider_registry` → `get_processor_registry`. Update all call sites. Run tests.

## 5. File Renames in `processor/`

- [x] 5.1 Rename `processor/unified_pipeline.py` → `processor/pipeline.py`. Update all imports. Run tests.
- [x] 5.2 Rename `processor/rasterio_warp.py` → `processor/warp.py`. Update all imports. Run tests.
- [x] 5.3 Rename `processor/build_summary.py` → `processor/summary.py`. Update all imports. Run tests.
- [x] 5.4 Rename `processor/raster.py` → `processor/gdal.py`. Update all imports. Run tests.

## 6. Move `cli_analyze.py` to `analysis/cli.py`

- [x] 6.1 Move `src/cartoload/cli_analyze.py` → `src/cartoload/analysis/cli.py`. Update `cli.py` import. Update `analysis/__init__.py` if needed. Run tests.

## 7. Shared Tile Math Module

- [x] 7.1 Create `src/cartoload/tile_math.py` with canonical `lon_to_tile_x`, `lat_to_tile_y`, `tile_x_to_lon`, `tile_y_to_lat`, `compute_bounds_4326`, `bounds_to_tile_coords`, and `ProcessedTile` type alias. Write unit tests for all functions.
- [x] 7.2 Update `pipeline.py` to import tile math from `tile_math.py`. Remove `_compute_tile_coords` and inline `lat_to_y`/`lon_to_x`. Run tests.
- [x] 7.3 Update `processor/pipeline.py` to import from `tile_math.py`. Remove its `_compute_tile_coords`. Run tests.
- [x] 7.4 Update `processor/gpkg/vector_rasterizer.py` to import from `tile_math.py`. Remove its `_compute_tile_coords`. Run tests.
- [x] 7.5 Update `source/wmts/download.py` to import from `tile_math.py`. Remove `_lon_to_tile_x`, `_lat_to_tile_y`, `_bbox_to_tile_indices`. Run tests.
- [x] 7.6 Update `exporters/garmin_img_writer.py` to import from `tile_math.py` for its `lon_to_x`/`lat_to_y` closures. Run tests.
- [x] 7.7 Update `processor/preview.py` to import from `tile_math.py`. Remove its `_lat_lon_to_tile`. Run tests.
- [x] 7.8 Update `processor/geotiff/tile_reader.py` to import `compute_bounds_4326` and `ProcessedTile` from `tile_math.py`. Run tests.
- [x] 7.9 Update `processor/warp.py` to import `compute_bounds_4326` and `ProcessedTile` from `tile_math.py`. Run tests.

## 8. Shared Utilities Module

- [x] 8.1 Create `src/cartoload/utils.py` with `human_size`, `encode_jpeg`, `ensure_rgba`, `normalize_bands`, and callback type aliases (`ProgressCallback`, `ExportProgressCallback`). Write unit tests.
- [x] 8.2 Replace 4 copies of `_human_size` in `cli.py`, `analysis/cli.py`, `processor/pipeline.py`, and `processor/summary.py` with imports from `utils.py`. Run tests.
- [x] 8.3 Replace inline JPEG encoding patterns in `processor/compositor.py`, `processor/warp.py`, `processor/pipeline.py`, `processor/geotiff/tile_reader.py`, and `exporters/garmin_img_writer.py` with `encode_jpeg` from `utils.py`. Run tests.
- [x] 8.4 Replace RGBA normalization patterns in `processor/warp.py`, `processor/compositor.py`, and `source/wmts/` provider with `ensure_rgba` from `utils.py`. Run tests.
- [x] 8.5 Replace band normalization logic in `processor/warp.py` and `processor/geotiff/tile_reader.py` with `normalize_bands` from `utils.py`. Run tests. (Skipped: band normalization is domain-specific to rasterio warp and differs between RGB/RGBA targets — not a good candidate for shared utility.)
- [x] 8.6 Replace duplicated `ProgressCallback` and `ExportProgressCallback` type aliases in `pipeline.py`, `processor/pipeline.py`, `processor/wmts/batch.py`, and `exporters/garmin_img.py` with imports from `utils.py`. Run tests.

## 9. Generic Registry

- [x] 9.1 Implement `Registry[T]` generic class in `src/cartoload/utils.py`. Write unit tests for register, resolve, unknown key error, and get_all.
- [x] 9.2 Refactor `source/base.py` to use `Registry[Source]`. Keep public API (`register_source`, `resolve_source`, `get_source_registry`) unchanged. Run tests.
- [x] 9.3 Refactor `processor/base.py` to use `Registry[LayerProcessor]`. Keep public API (`register_processor`, `make_processor`, `get_processor_registry`) unchanged. Run tests.
- [x] 9.4 Rename `pipeline.resolve_source` to `resolve_source_config` to eliminate name collision with `source.resolve_source`. Update all call sites (`cli.py`, `processor/pipeline.py`). Run tests.

## 10. CLI and Pipeline Refactoring

- [x] 10.1 Add `"xyz"` to `ALLOWED_SOURCE_TYPES` in `config.py`. Verify XYZ source configs validate. Run tests.
- [x] 10.2 Remove unused `--exporter` option from the `build` CLI command. Run tests.
- [x] 10.3 Fix `download` command to resolve `-l` against both `config.targets` and `config.layers` (matching `build` behavior). Run tests.
- [x] 10.4 Replace `sys.exit(1)` with `raise click.ClickException(...)` in `list_layers` command. Run tests.
- [x] 10.5 Remove duplicate `import shutil` inside `cache_clean` function body. Run tests.
- [x] 10.6 Extract core build orchestration logic from the `build` CLI command into `processor/pipeline.py`. Keep CLI as thin wrapper (parse args, setup logging, display progress). Run tests. (Skipped: the CLI already delegates all business logic to `build_target()`. What remains in the CLI is arg parsing, progress display, and output formatting — which is the CLI's proper responsibility.)

## 11. Processor Base Class Cleanup

- [x] 11.1 Add default `download()` implementation to `LayerProcessor` base class in `processor/base.py`. Move shared logic from `GeotiffProcessor` and `GpkgProcessor`. Run tests.
- [x] 11.2 Remove `download()` overrides from `GeotiffProcessor` and `GpkgProcessor` (use base class default). Verify `WmtsProcessor` still overrides correctly. Run tests.

## 12. Test Infrastructure Consolidation

- [x] 12.1 Create `tests/helpers.py` with shared utilities: `make_jpeg`, `write_tile_with_world_file`.
- [x] 12.2 Replace duplicated `_make_jpeg` in `test_pipeline.py`, `test_batch.py`, `test_unified_pipeline.py`, and `test_preview.py` with imports from `helpers.py`. Run tests. (Left specialized variants in `test_summary.py` and `test_exporter_garmin_img.py` — they use random noise for realistic compression, not solid-color.)
- [x] 12.3 Replace duplicated `_write_tile_with_world_file` in `test_pipeline.py`, `test_batch.py`, and `test_unified_pipeline.py` with imports from `helpers.py`. Run tests.
- [x] 12.4 Remove skipped tests for removed tile index table feature in `test_exporter_garmin_img.py`. Run tests.

## 13. Final Validation

- [x] 13.1 Run full test suite (`just test`) and verify all tests pass.
- [x] 13.2 Run `just check` and `just check types` — zero errors.
- [x] 13.3 Verify no remaining duplicate definitions: search for `_human_size`, `_compute_tile_coords`, `compute_bounds_4326`, `_make_jpeg`, `ProcessedTile =`, `class.*Provider`, `from cartoload.downloader`.
- [x] 13.4 Verify directory structure matches design: `source/` with `stac/`, `wmts/` subpackages; `processor/` with `geotiff/`, `gpkg/`, `wmts/` subpackages; `analysis/cli.py` exists.
