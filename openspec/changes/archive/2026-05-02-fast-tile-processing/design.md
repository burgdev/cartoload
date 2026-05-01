## Context

The tile processing pipeline (`BatchTileProcessor`) currently uses `gdalwarp` subprocess calls for per-tile reprojection from EPSG:3857 to EPSG:4326. Each call spawns a new OS process (~65ms overhead). With 197K tiles in a typical 40×40km SwissTopo build, this results in 15+ minute processing times. Additionally, all processed tiles accumulate in a `compressed_tiles` dict before writing, causing 5+ GB memory usage.

Key files in current pipeline:
- `processor/batch.py` — orchestrates batch processing with `ThreadPoolExecutor`
- `processor/reproject.py` — spawns `gdalwarp` subprocess, manages TIFF reprojection cache
- `processor/tile_reader.py` — reads tiles, converts TIFF→JPEG via PIL
- `pipeline.py` — accumulates all tiles in `compressed_tiles` dict, passes to exporter
- `exporters/garmin_img.py` — receives full dict, generates subdivisions, writes IMG
- `cli.py` — progress callback only handles `"extracting"` / `"encoding"` stages

Benchmarks (256×256 JPEG tile, EPSG:3857 → 4326):
```
gdalwarp subprocess:     65ms/tile
rasterio in-process:     2.4ms/tile  (25x faster)
rasterio + MemoryFile:   2.6ms/tile  (JPEG output directly)
PIL read + re-encode:    0.6ms/tile  (no warp baseline)
```

Parallelism (200 tiles):
```
ThreadPoolExecutor x4:   1.0x speedup (GIL blocks)
ThreadPoolExecutor x8:   0.9x speedup (worse!)
ProcessPoolExecutor x4:  2.5x speedup
ProcessPoolExecutor x8:  4.4x speedup
ProcessPoolExecutor x20: 5.1x speedup
```

## Goals / Non-Goals

**Goals:**
- Process 197K tiles in ~1 minute (down from 15+ minutes)
- Cap memory at ~500MB regardless of tile count (down from 5+ GB)
- Show per-zoom progress with tile counts during processing
- Eliminate TIFF reprojection cache (unnecessary at 2.4ms/tile warp speed)

**Non-Goals:**
- Changing the IMG binary output format or writer
- Optimizing the download stage
- Changing the cache structure for source tiles (download cache stays as-is)
- Supporting CRS other than EPSG:3857 → EPSG:4326 (though the code will be general)
- GPU-accelerated warp or exotic GDAL drivers

## Decisions

### D1: rasterio in-process warp replaces gdalwarp subprocess

**Decision**: Use `rasterio.open()` + `rasterio.warp.reproject()` directly in Python, writing output JPEG via `MemoryFile`.

**Rationale**: 25x faster per tile (2.4ms vs 65ms) by eliminating process spawn overhead. rasterio is already a project dependency (v1.5.0). The warp kernel is the same GDAL C code — no quality difference.

**Alternative considered**: Batch `gdalwarp` with VRT input (warp many tiles in one subprocess call). Rejected because VRT construction adds complexity and doesn't help with the in-memory streaming goal.

### D2: ProcessPoolExecutor replaces ThreadPoolExecutor

**Decision**: Use `concurrent.futures.ProcessPoolExecutor` for parallel tile processing.

**Rationale**: rasterio's `reproject()` holds the GIL — threads give exactly 0x speedup. Processes give 4-5x with 8 workers. Each worker opens its own GDAL dataset handles; no shared state needed.

**Worker count**: Default to `min(os.cpu_count(), 8)`. Diminishing returns above 8 workers due to GDAL internal locking and disk I/O saturation.

**Alternative considered**: Python 3.13 free-threaded build (no-GIL). Experimental and requires custom build; ProcessPoolExecutor is reliable.

### D3: Drop TIFF reprojection cache entirely

**Decision**: Remove the reprojection cache (`cache/{source}_4326/` TIFF files and associated logic). Always warp from source JPEG in-process.

**Rationale**: At 2.4ms/tile, re-warping is fast enough that caching costs more than it saves. The TIFF cache was 114x larger than source JPEG (188KB vs 1.6KB per tile) — 35GB for 197K tiles. The time saved by cache reads (1.2ms) doesn't justify the disk space or cache invalidation complexity.

**Impact on incremental builds**: Checkpoint/resume support already handles partial builds at the zoom level. Re-processing tiles on resume is acceptable at 2.4ms/tile.

### D4: Stream tiles in batches to IMG writer

**Decision**: Use the existing `process_zoom_level_batched()` generator to yield tiles in batches of 500. Refactor `export_from_tiles` to process one batch at a time instead of requiring the full `compressed_tiles` dict upfront.

**Rationale**: Eliminates the 5GB memory spike. Each batch of 500 tiles occupies ~12MB of JPEG data. The IMG writer writes sequentially, so no batch needs to remain in memory after processing.

**Constraint**: Subdivision generation currently needs all tiles to compute spatial grid. Solution: generate subdivisions from tile coordinates (which are known before processing), then fill in JPEG data as batches arrive. Alternatively, accumulate tiles per zoom level (the dominant zoom is 18 at 147K tiles, but even that is ~3.5GB — so batches within a zoom are needed too).

**Alternative considered**: Write IMG file in a streaming fashion (append-only). Rejected because the Garmin IMG format requires FAT tables and offset pointers that need layout computation upfront. Two-pass approach (layout first, then write) is simpler.

### D5: Quality control via rasterio MemoryFile JPEG driver

**Decision**: Use rasterio's `MemoryFile` with JPEG driver and quality creation option for output encoding. This replaces PIL-based TIFF→JPEG conversion.

**Rationale**: Eliminates the TIFF intermediate file and the PIL decode/encode step. GDAL's JPEG encoder supports quality settings directly. When no reprojection is needed (source CRS matches target), raw JPEG bytes pass through without decoding.

### D6: Per-zoom progress bars

**Decision**: Add a `"processing"` stage handler in the CLI progress callback, with per-zoom labels (e.g., "Processing zoom 18: 50K/147K tiles").

**Rationale**: Current callback only handles `"extracting"` and `"encoding"`, so the user sees no progress during the longest stage. The `BatchTileProcessor` already emits `(stage, current, total)` tuples — just needs a matching handler in `cli.py`.

## Risks / Trade-offs

- **[Process spawn overhead for small builds]**: For small tile counts (<100), ProcessPoolExecutor startup may add overhead. → Mitigation: fall back to single-process for <100 tiles, or accept the ~1s startup cost.
- **[Memory usage during subdivision generation]**: Generating subdivisions from tile coordinates requires knowing bounds, which currently requires reading tiles. → Mitigation: compute bounds from tile coordinates (x, y, zoom) using Web Mercator math, which is deterministic and requires no I/O.
- **[World file dependency]**: rasterio needs georeferencing to warp. Currently relies on `.jgw` world files alongside cached JPEGs. → Mitigation: compute the source affine transform from tile coordinates programmatically (same math as world file generation), removing the world file dependency entirely.
- **[rasterio MemoryFile JPEG quality]**: GDAL's JPEG driver via rasterio may not support all PIL quality options. → Mitigation: benchmark quality output; if needed, fall back to numpy→PIL for the final encode step.
- **[Large process pool memory]**: Each ProcessPoolExecutor worker loads its own GDAL/rasterio context (~50MB). 8 workers = ~400MB baseline. → Acceptable trade-off vs current 5GB tile accumulation.
