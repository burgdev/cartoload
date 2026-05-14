## 1. Pre-warp with gdalwarp CLI

- [x] 1.1 Add a `run_gdalwarp()` helper in `geotiff_prewarp.py` that invokes `gdalwarp` via `subprocess.run()` with the correct flags (`-t_srs EPSG:4326`, `-expand rgb` for paletted, `-of GTiff`, `-co COMPRESS=LZW`, `-co TILED=YES`, `-co BLOCKXSIZE=256`, `-co BLOCKYSIZE=256`, `-wo NUM_THREADS=ALL_CPUS`, `-multi`)
- [x] 1.2 Rewrite `prewarp_geotiff()` to use `run_gdalwarp()` instead of rasterio's `reproject()`. Keep the existing skip logic (already in 4326 + RGB, cached _4326.tif fresh). Remove the manual palette LUT expansion code.
- [x] 1.3 Remove the old rasterio-based warp code from `prewarp_geotiff()` (the `calculate_default_transform`, `reproject`, LUT expansion, and manual write logic)

## 2. VRT-based mosaic

- [x] 2.1 Add a `build_vrt()` helper in `geotiff_prewarp.py` that invokes `gdalbuildvrt` via `subprocess.run()` to create a `mosaic.vrt` from a list of pre-warped files
- [x] 2.2 Rewrite `merge_prewarped_geotiffs()` to call `build_vrt()` instead of allocating `np.zeros()` and doing per-file reprojection. Remove the full-array merge logic.
- [x] 2.3 Update the VRT freshness check: compare `mosaic.vrt` mtime against all referenced source file mtimes, similar to the current mosaic freshness check

## 3. Post-warp cleanup and metadata

- [x] 3.1 After successful `prewarp_geotiff()`, delete the original source `.tif` file and write a `{stem}.json` metadata file with `{item_id, url, size, etag, last_modified}` (ETag populated from STAC HEAD request or empty string)
- [x] 3.2 Ensure `prewarm_all_geotiffs()` returns the correct mapping from original paths to pre-warped paths (original path may no longer exist on disk, but the mapping is still needed by pipeline.py for tile reading)

## 4. STAC ETag freshness

- [x] 4.1 Add a `_check_freshness()` method to `STACDownloader` that issues `requests.head(asset_url)` and compares `ETag`/`Last-Modified` against cached `.json` metadata. Handle 405 (HEAD not supported) gracefully with fallback.
- [x] 4.2 Integrate `_check_freshness()` into `STACDownloader.run()` — before the download step, check freshness for items that have `.json` metadata but no original `.tif` (i.e., originals were deleted after warp). If fresh, skip download; if stale, re-download and re-warp.
- [x] 4.3 After successful download, issue a HEAD request to capture ETag/Last-Modified and write the `.json` metadata file alongside the cached file

## 5. Pipeline integration

- [x] 5.1 Update `pipeline.py` to handle VRT output from `merge_prewarped_geotiffs()` — the mosaic path will now be a `.vrt` file instead of `.tif`. Verify that `geotiff_tile_reader.py`'s `read_tile_from_warped_geotiff()` works with VRT (it should — rasterio opens VRTs natively)
- [x] 5.2 Remove any references to the old physical mosaic (`mosaic_4326.tif`) in pipeline code paths
- [x] 5.3 Verify the fallback path in `_render_single_tile()` still works when `prewarped_map` is provided (per-file mode) — the original paths in the map may no longer exist on disk, so ensure the code only uses the mapped pre-warped paths

## 6. Tests and verification

- [x] 6.1 Update existing tests in `tests/test_downloader_wmts.py` or create new tests for `geotiff_prewarp.py` covering: gdalwarp invocation, VRT creation, original deletion, metadata JSON output
- [x] 6.2 Add tests for STAC ETag freshness checking (HEAD request, ETag match/mismatch, 405 fallback)
- [x] 6.3 Run `just check`, `just check types`, and `just test` to verify formatting, linting, types, and tests pass
- [ ] 6.4 Run a manual integration test: `cartoload build -c examples/configs/layers/test.yaml -l ch_basemap_25k -y 46.93459 -x 7.51105 -W 5 -H 5 -f --preview --executor thread` and verify pre-warp speed improvement and VRT creation
