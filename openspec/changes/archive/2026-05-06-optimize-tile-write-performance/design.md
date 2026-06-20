## Context

Tile writing to Garmin IMG currently processes 585K tiles in ~30 minutes with 10 parallel workers. Benchmarking revealed the primary bottleneck is not per-tile processing speed but **process pool lifecycle overhead**: the `ProcessPoolExecutor` is created and destroyed per batch (~1170 cycles for 585K tiles with BATCH_SIZE=500). Each cycle spawns workers that import rasterio/GDAL (~1 GB per worker), process a handful of tiles, then get killed.

Secondary bottlenecks: LBL28 offsets written one-at-a-time (585K individual syscalls), and `_fixup_rgn2_jpeg_sizes` computes sizes from LBL28 offset differences instead of tracking them inline.

ThreadPoolExecutor was tested but performs worse (1.3-1.8x speedup vs 3-3.6x for ProcessPool) because rasterio/numpy don't fully release the GIL. However, threads use ~1 GB total memory vs ~1 GB per process worker, making them useful on memory-constrained systems.

## Goals / Non-Goals

**Goals:**
- Reduce tile writing time from ~30 min to ~8 min for 585K tiles with 10 workers
- Persistent executor that survives across batches (biggest single win: 3-6x)
- Pre-load rasterio/numpy in worker initializer to avoid repeated module loading
- Configurable executor mode (process/thread) for memory vs speed trade-off
- Batch I/O for LBL28 offsets (single write instead of 585K)
- Inline JPEG size tracking to simplify RGN2 fixup

**Non-Goals:**
- Changing the Garmin IMG binary format output (same bytes)
- Optimizing tile download or cache I/O (separate concern)
- GPU-accelerated JPEG encoding
- Skipping rasterio warp for EPSG:3857 tiles (the warp is geometrically necessary for pixel reprojection)

## Decisions

### Decision 1: Persistent ProcessPoolExecutor outside the batch loop

**Choice**: Create the `ProcessPoolExecutor` once before the batch loop, reuse it for all batches, destroy after all tiles are processed.

**Rationale**: Benchmarking showed recreating the pool per batch causes 31-51 ms/tile (dominated by process spawn + library import). A persistent pool achieves 7.7-10.4 ms/tile — a 3-6x improvement. The code change is minimal: move the `with ProcessPoolExecutor(...)` from inside the batch loop to outside it.

**Current code** (line 2643):
```python
for batch_start in range(0, len(all_tiles), batch_size):
    batch = all_tiles[batch_start : batch_start + batch_size]
    if use_parallel:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:  # RECREATED PER BATCH
            ...
```

**New code**:
```python
executor = None
if use_parallel:
    executor = ProcessPoolExecutor(max_workers=max_workers, initializer=_init_worker)
try:
    for batch_start in range(0, len(all_tiles), batch_size):
        batch = all_tiles[batch_start : batch_start + batch_size]
        if executor is not None:
            ...  # submit to existing executor
finally:
    if executor is not None:
        executor.shutdown(wait=True)
```

### Decision 2: Pre-load libraries in worker initializer

**Choice**: Use `initializer` parameter of ProcessPoolExecutor to import rasterio/numpy once per worker process.

**Rationale**: Currently `_warp_tile_worker` does `from ..processor.rasterio_warp import warp_tile_to_jpeg` on every invocation. With persistent workers, this import happens on every tile instead of once per worker. Pre-loading via initializer avoids this.

**Implementation**:
```python
def _init_worker():
    """Pre-load heavy libraries in worker process."""
    from cartoload.processor.rasterio_warp import warp_tile_to_jpeg
    global _warp_func
    _warp_func = warp_tile_to_jpeg

def _warp_tile_worker(source_path, x, y, zoom, source_crs, target_crs, quality):
    if quality is None:
        return (x, y, zoom, source_path.read_bytes())
    result = _warp_func(source_path, x, y, zoom, source_crs, target_crs, quality)
    ...
```

### Decision 3: Configurable executor mode via CLI/environment

**Choice**: Add `--executor` CLI parameter (values: `process`, `thread`) with environment variable `CARTOLOAD_EXECUTOR` as fallback. Default: `process`.

**Rationale**: ProcessPoolExecutor is faster but uses ~1 GB/worker. ThreadPoolExecutor uses ~1 GB total but is 30-50% slower. Users on memory-constrained systems (e.g., 8 GB RAM with 10 workers = 10 GB needed) can switch to threads. The parameter flows from CLI → pipeline → writer.

**Implementation**:
- Add `_get_executor_mode()` function (similar to existing `_get_worker_count()`)
- In `_write_gmp_data`, choose `ProcessPoolExecutor` or `ThreadPoolExecutor` based on the mode
- Both share the same `initializer` pattern (pre-loading is a no-op for threads but harmless)

### Decision 4: Batch LBL28 offset writes

**Choice**: Pre-allocate a bytearray for all LBL28 offsets and write as a single `f.write()` call.

**Rationale**: 585K individual `struct.pack("<I", offset)` + `f.write()` calls become one buffered write. The offsets are already accumulated in `lbl28_offsets` list, so memory impact is negligible (2.3 MB for 585K offsets).

### Decision 5: Inline JPEG size tracking

**Choice**: Collect `jpeg_sizes: list[int]` alongside `lbl28_offsets` during the LBL29 streaming loop. Pass directly to `_fixup_rgn2_jpeg_sizes` instead of computing sizes from offset differences.

**Rationale**: Eliminates the `actual_size = lbl28_offsets[idx+1] - lbl28_offsets[idx]` computation per tile. Minor code simplification.

### Decision 6: Increase batch size from 500 to 5000

**Choice**: Raise `BATCH_SIZE` from 500 to 5000.

**Rationale**: Less significant with persistent executor (no more pool recreation), but still reduces future coordination overhead from ~1170 to ~117 cycles. Memory: 5000 × ~12 KB = ~60 MB per batch, well within typical system memory.

## Risks / Trade-offs

- **ThreadPoolExecutor is slower**: Benchmarked at 1.3-1.8x speedup vs 3-3.6x for ProcessPoolExecutor. Users must understand the trade-off. → **Document in --help text and CLI output.**

- **Memory for ProcessPoolExecutor**: Still ~1 GB/worker. With 10 workers that's ~10 GB. → **Default worker count is cpu_count/2, and user can reduce via CARTOLOAD_WORKERS. Thread mode available for constrained systems.**

- **Persistent pool error handling**: If a worker crashes, the executor may become broken. → **Use try/finally with executor.shutdown(). Wrap per-batch submission in try/except to handle individual tile failures gracefully (already done via as_completed).**

- **initializer global variable**: Using `global _warp_func` in worker is standard pattern for ProcessPoolExecutor initializer. → **No risk, well-documented pattern.**
