## 1. World File Computation

- [x] 1.1 Add a `_compute_tile_bounds(x, y, zoom)` static method to `WMTSDownloader` that returns `(left, top, right, bottom)` in EPSG:3857 meters using the Web Mercator tile grid formula
- [x] 1.2 Add a `_write_world_file(cache_path, x, y, zoom, tile_pixels=256)` method that computes the 6-line affine transform and writes the `.jgw` (JPEG) or `.pgw` (PNG) world file alongside the tile

## 2. Integrate World File Writing into Download Path

- [x] 2.1 Call `_write_world_file` in `download_tile` after `_write_to_cache` succeeds
- [x] 2.2 Call `_write_world_file` in `_download_worker` after `_write_to_cache` succeeds
- [x] 2.3 In `_is_cached`, also check for the corresponding world file; if the tile exists but the world file is missing, return `False` (or handle separately) so the tile is re-processed
- [x] 2.4 Add world file regeneration logic: when a tile is cached but the world file is missing, generate the world file without re-downloading

## 3. CRS Declaration in Raster Processor

- [x] 3.1 Add an optional `source_crs` parameter to `RasterProcessor.__init__` (default `None`)
- [x] 3.2 In `_build_vrt`, pass `-a_srs EPSG:3857` (or the configured `source_crs`) to the `gdalbuildvrt` command when a source CRS is specified

## 4. Pipeline Integration

- [x] 4.1 Pass the appropriate `source_crs` (EPSG:3857 for WMTS sources) when constructing `RasterProcessor` in the pipeline

## 5. Tests

- [x] 5.1 Unit test for `_compute_tile_bounds` with known tile coordinates (e.g., z=10, x=541, y=362)
- [x] 5.2 Unit test for `_write_world_file` verifying correct affine transform values in the output file
- [x] 5.3 Unit test for `_is_cached` behavior when world file is missing
- [x] 5.4 Integration test: download tiles → build VRT → verify no "ungeoreferenced" warning
