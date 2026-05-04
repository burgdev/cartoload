## Why

Writing 585K tiles to a Garmin IMG file takes ~30 minutes with 10 parallel workers. Profiling shows the bottleneck is the rasterio warp path: every EPSG:3857 source tile goes through a full rasterio open + compute transform + reproject + PIL re-encode cycle (~50ms/tile), even though Garmin raster tiles only need JPEG re-encoding at the target quality with bounds computed mathematically from tile coordinates. A PIL-only re-encode takes ~7ms/tile — a 7x speedup.

## What Changes

- **Add fast-path for EPSG:3857→4326 quality re-encoding**: When tiles are cached (no download needed) and only need quality re-encoding, skip the rasterio warp entirely. Read JPEG → PIL re-encode at target quality → compute bounds from tile coordinates.
- **Batch LBL28 offset writes**: Instead of 585K individual 4-byte `struct.pack` + write calls for LBL28 fixup, pre-allocate a bytearray and pack all offsets in one pass, then write as a single buffer.
- **Increase batch size**: Raise from 500 to 5000 tiles per batch to reduce ProcessPoolExecutor coordination overhead.
- **Pre-compute RGN2 jpeg sizes during LBL29 streaming**: Track actual JPEG sizes alongside LBL28 offsets to avoid the separate `_fixup_rgn2_jpeg_sizes` pass that seeks to each RGN2 record individually.

## Capabilities

### New Capabilities

- `fast-tile-encoding`: Fast-path JPEG re-encoding that skips rasterio warp for cached tiles, using PIL directly with mathematical bounds computation

### Modified Capabilities

- `rasterio-warp-processor`: Add fast-path detection — when source CRS differs from target but tiles are cached JPEGs that only need quality adjustment, use PIL re-encode instead of full rasterio warp
- `streaming-tile-processing`: Increase batch size, batch LBL28 and RGN2 fixup writes, reduce per-tile overhead

## Impact

- `src/cartoload/exporters/garmin_img_writer.py`: `_warp_tile_worker`, LBL28/RGN2 fixup paths, batch size constant
- `src/cartoload/processor/rasterio_warp.py`: `warp_tile_to_jpeg` — add fast-path for quality-only re-encoding
- No API changes, no breaking changes
- Expected wall-clock improvement: ~30 min → ~5 min for 585K tiles with 10 workers
