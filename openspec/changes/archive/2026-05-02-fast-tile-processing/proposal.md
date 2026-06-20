## Why

Processing 197K tiles (40×40km SwissTopo build) takes 15+ minutes and 5+ GB RAM because each tile spawns a `gdalwarp` subprocess (~65ms/tile) and all tiles accumulate in memory before writing. Rasterio can do the same warp in-process at ~2.4ms/tile — a 25x speedup — and streaming batches would cap memory at ~500MB regardless of tile count.

## What Changes

- Replace `gdalwarp` subprocess calls with in-process rasterio `reproject()`, outputting JPEG directly via `MemoryFile` (no TIFF intermediate)
- Switch from `ThreadPoolExecutor` to `ProcessPoolExecutor` (rasterio does not release the GIL — threads give 0x parallel speedup, processes give 4-5x with 8 workers)
- Drop the TIFF reprojection cache entirely (saves 50% per tile but costs 114x disk space — 35GB for 197K tiles; re-warping at 2.4ms is fast enough)
- Stream tiles in batches to the IMG writer using the existing `process_zoom_level_batched()` generator instead of accumulating all tiles in a dict
- Add visible per-zoom progress bars (CLI currently ignores the `"processing"` stage from BatchTileProcessor)

## Capabilities

### New Capabilities

- `rasterio-warp-processor`: In-process tile reprojection using rasterio instead of gdalwarp subprocess. Handles JPEG→JPEG warp with quality control, no TIFF intermediate.

### Modified Capabilities

- `streaming-tile-processing`: Switch from ThreadPoolExecutor to ProcessPoolExecutor for true parallelism; drop TIFF reprojection cache (re-warp is fast enough with rasterio)
- `tile-cache`: Remove TIFF reprojection cache tier (source JPEG cache remains)

## Impact

- **`src/cartoload/processor/batch.py`**: Major rewrite — rasterio warp, ProcessPoolExecutor, no TIFF cache
- **`src/cartoload/processor/reproject.py`**: Replaced entirely by rasterio in-process warp
- **`src/cartoload/processor/tile_reader.py`**: Simplified — no more TIFF reading, JPEG passthrough or rasterio warp only
- **`src/cartoload/pipeline.py`**: Switch to batched streaming, wire progress correctly
- **`src/cartoload/cli.py`**: Handle `"processing"` stage in progress callback, per-zoom labels
- **`src/cartoload/exporters/garmin_img.py`**: Accept batched tile stream instead of full dict
- **`src/cartoload/downloader/base.py`**: Remove reprojection cache methods
- **`src/cartoload/downloader/wmts.py`**: Remove reprojection cache path methods
