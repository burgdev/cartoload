## Why

Writing 585K tiles to a Garmin IMG file takes ~30 minutes with 10 parallel workers. Benchmarking identified the root cause: **the ProcessPoolExecutor is recreated per batch** (line 2643 in garmin_img_writer.py), meaning ~1170 process pool create/destroy cycles. Each cycle spawns N workers that each import rasterio/GDAL (~1 GB), process a few tiles, then get destroyed. This overhead dominates the actual tile processing cost.

Benchmark results (100 tiles, 256x256 JPEG, rasterio warp EPSG:3857→4326):

| Approach | 4 workers | 8 workers |
|----------|-----------|-----------|
| Current: recreate pool per batch | 31.9 ms/tile | 51.0 ms/tile |
| Persistent pool (1 executor) | 11.6 ms/tile | 8.5 ms/tile |
| Persistent + preloaded init | 10.4 ms/tile | 7.7 ms/tile |
| ThreadPool (for reference) | ~15-20 ms/tile | ~20-30 ms/tile |

ThreadPoolExecutor is slower than ProcessPoolExecutor because rasterio/numpy don't fully release the GIL — Python threads serialize on the Python-level glue between C calls. However, threads use ~1 GB total vs ~1 GB per worker, so threads may be preferable on memory-constrained systems. A `--workers` / `--executor` parameter allows users to choose.

## What Changes

- **Persistent ProcessPoolExecutor**: Move the executor outside the batch loop so workers are created once and reused across all batches. Use `initializer` to pre-import rasterio/numpy in each worker, avoiding repeated module loading.
- **Configurable executor mode**: Add CLI parameter (`--executor process|thread`) to choose between ProcessPoolExecutor (default, fastest) and ThreadPoolExecutor (lower memory, slightly slower). Environment variable `CARTOLOAD_EXECUTOR` as fallback.
- **Batch LBL28 offset writes**: Instead of 585K individual 4-byte `struct.pack` + `f.write` calls, pre-allocate a bytearray and write as a single buffer.
- **Inline JPEG size tracking**: Track actual JPEG sizes during LBL29 streaming to simplify the `_fixup_rgn2_jpeg_sizes` pass.
- **Increase batch size**: Raise from 500 to 5000 tiles per batch to reduce coordination overhead (less significant with persistent executor, but still beneficial for future ordering).

## Capabilities

### New Capabilities

- `parallel-executor-config`: Configurable executor backend (process/thread) with persistent worker pool, pre-loaded libraries, and CLI parameter

### Modified Capabilities

- `streaming-tile-processing`: Persistent executor, increased batch size, batched LBL28 writes, inline JPEG size tracking
- `rasterio-warp-processor`: No functional changes (the warp path is correct and necessary for EPSG:3857→4326 reprojection)

## Impact

- `src/cartoload/exporters/garmin_img_writer.py`: `_warp_tile_worker`, executor lifecycle, LBL28/RGN2 fixup paths, batch size constant
- `src/cartoload/cli.py` or relevant CLI module: `--executor` parameter
- No output format changes, no breaking changes
- Expected wall-clock improvement: ~30 min → ~8 min for 585K tiles with 10 workers (persistent pool + preloaded init)
