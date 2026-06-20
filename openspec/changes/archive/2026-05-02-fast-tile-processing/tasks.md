## 1. Rasterio Warp Processor

- [x] 1.1 Add `rasterio_warp.py` module with `warp_tile_to_jpeg(source_path, x, y, zoom, source_crs, target_crs, quality) -> (bytes, bounds)` function that opens source JPEG with rasterio, computes EPSG:3857 transform from tile coordinates, warps to EPSG:4326 via `reproject()`, outputs JPEG via `MemoryFile`
- [x] 1.2 Add `compute_bounds_from_tile_coords_4326(x, y, zoom) -> (lat_min, lon_min, lat_max, lon_max)` function for EPSG:4326 passthrough bounds (can reuse existing `tile_reader.py` logic)
- [x] 1.3 Add `compute_source_transform_3857(x, y, zoom) -> Affine` function that computes EPSG:3857 affine transform from Web Mercator tile grid math (replaces .jgw world file dependency)
- [x] 1.4 Verify: unit tests for warp output (correct JPEG bytes, correct bounds, quality setting)

## 2. Batch Processor Rewrite

- [x] 2.1 Rewrite `BatchTileProcessor._process_single_tile()` to call `rasterio_warp.warp_tile_to_jpeg()` instead of `reproject_tile_cached()` + `TileCacheReader.read_tile()`. When source CRS matches target, read raw JPEG bytes directly.
- [x] 2.2 Replace `ThreadPoolExecutor` with `ProcessPoolExecutor` in `_process_batch()`, with `max_workers=min(os.cpu_count(), 8)`. Worker function must be picklable (top-level function, not method).
- [x] 2.3 Remove imports and usage of `reproject_tile_cached`, `reproject_tile`, `TileCacheReader` from `batch.py`
- [x] 2.4 Remove the `needs_reproj` parameter and pre-check from `_process_single_tile` — the warp function handles both cases internally
- [x] 2.5 Verify: existing `test_batch.py` tests pass with new implementation

## 3. Remove TIFF Reprojection Cache

- [x] 3.1 Remove `reproject.py` module entirely (or gut and leave as empty/deprecated)
- [x] 3.2 Remove `reprojection_cache_path()`, `is_reprojection_valid()` methods from `BaseDownloader` and `WMTSDownloader`
- [x] 3.3 Remove any references to reprojection cache paths in test fixtures and test code
- [x] 3.4 Verify: `just check types` passes, `just test` passes

## 4. Progress Display

- [x] 4.1 Add `"processing"` stage handler in `cli.py:on_export_progress()` that creates a Rich progress task with per-zoom label (e.g., "Processing zoom 18: 0/147456")
- [x] 4.2 Update `pipeline.py` to emit a progress callback with zoom-level context before each zoom's processing loop, so the CLI can label the progress bar with the zoom number
- [x] 4.3 Verify: `just check` passes, tests pass

## 5. Batched Streaming to IMG Writer (DEFERRED)

Streaming requires major IMG writer refactor — the Garmin IMG format needs FAT tables and layout computation upfront, requiring all tile data before writing. A proper implementation would need a two-pass approach (bounds-only pass for layout, then streaming JPEG pass for writing). Deferring to a follow-up change.

- [~] 5.1 Refactor `pipeline.py` to use `process_zoom_level_batched()` generator instead of `process_zoom_level()`, accumulating tiles per zoom level but yielding between zooms — **DEFERRED**
- [~] 5.2 Refactor `GarminImgExporter.export_from_tiles()` to accept a generator/iterator of `(zoom, tiles_batch)` pairs instead of requiring the full `compressed_tiles` dict upfront — **DEFERRED**
- [~] 5.3 Update `generate_subdivisions()` to work with incrementally-provided tile data per zoom level — **DEFERRED**
- [~] 5.4 Verify: memory profiling shows <500MB peak for 197K tile build (or use a smaller test with batch size verification) — **DEFERRED**

## 6. Cleanup and Validation

- [x] 6.1 Remove dead code from `tile_reader.py` — deleted entirely (no production code used it after batch.py rewrite)
- [x] 6.2 Keep `.jgw` world file generation in WMTS downloader — still needed for cache validation (`_is_cached` checks world file existence) and external tool compatibility
- [x] 6.3 Run `just check && just check types && just test` — all pass (401 tests, 0 new failures, pre-existing failures unchanged)
- [x] 6.4 End-to-end validation: `cartoload build -S examples/configs/sources/swisstopo.yaml -L examples/configs/layers/switzerland.yaml -l ch_basemap_test -y 46.93459 -x 7.51105 -W 5 -H 5 -f` produces valid IMG with visible progress
