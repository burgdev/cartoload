## Context

The current IMG writer pipeline accumulates all tile JPEG data in a `compressed_tiles` dict before writing. The flow is:

```
pipeline.py: for each zoom → process_zoom_level() → accumulate in compressed_tiles
garmin_img.py: export_from_tiles(compressed_tiles) → generate_subdivisions() → LayoutComputer → IMGWriter
```

For a 5×5 km build (2,647 tiles), this uses ~70 MB — fine. For a 40×40 km build (197K tiles), memory reaches 5+ GB. A full-country Switzerland build (~2M tiles) would need ~50 GB.

The critical observation is that **three distinct pieces of information flow through the pipeline**, with very different memory profiles:

1. **Tile coordinates** `(x, y, zoom)` — tiny, deterministic math, no I/O needed
2. **Tile bounds** `(lat_min, lon_min, lat_max, lon_max)` — tiny, computable from coordinates deterministically
3. **JPEG data** — large (~25 KB/tile), requires I/O and processing

Currently, all three are bundled together in `(jpeg_bytes, bounds)` tuples and accumulated before any writing begins. The JPEG data dominates memory usage but is only needed during the final write phase.

Key files:
- `pipeline.py` — accumulates all tiles in `compressed_tiles` dict
- `exporters/garmin_img.py` — `export_from_tiles()` accepts full dict, calls `generate_subdivisions()`
- `exporters/garmin_img_writer.py` — `LayoutComputer` needs JPEG sizes for layout, `GMPWriter` writes all data

The batch processor already has `process_zoom_level_batched()` which yields tiles incrementally — it's just not connected to the writer.

## Goals / Non-Goals

**Goals:**
- Cap peak memory at ~500 MB regardless of tile count (down from 5+ GB for 197K tiles)
- Support full-country builds (~2M tiles, ~50 GB of JPEG data) on machines with 8 GB RAM
- Maintain identical binary output (bit-for-bit compatibility with current writer)
- Show per-zoom progress during both processing and writing phases

**Non-Goals:**
- Changing the IMG binary format or Garmin protocol
- Optimizing JPEG processing speed (already fast with rasterio)
- Supporting resume mid-write (checkpoint remains at zoom level granularity)
- Parallelizing the write pass (sequential writes to a single file)

## Decisions

### D1: Tile metadata struct separates concerns

**Decision**: Introduce a `TileMetadata` dataclass that holds `(x, y, zoom, lat_min, lon_min, lat_max, lon_max, jpeg_size)` — everything needed for layout computation without holding JPEG bytes.

**Rationale**: The layout pass needs bounds (for subdivisions and RGN2 records) and JPEG sizes (for LBL28/LBL29 offset computation). Neither requires the actual JPEG data. By computing bounds from tile coordinates deterministically (Web Mercator math) and JPEG sizes from source file sizes on disk, we can compute the complete layout without ever loading JPEG data into memory.

**Key properties**:
- Bounds: ~30 bytes per tile (6 floats + 3 ints) vs ~25 KB for JPEG data — 800x smaller
- JPEG size: available from `os.path.getsize(source_path)` — single stat call, no file read
- All subdivision generation (`generate_subdivisions()`) can work with `TileMetadata` instead of `(bytes, bounds)` tuples

### D2: Two-pass architecture — layout then stream-write

**Decision**: Split the writer into two completely separate passes:

**Pass 1 (Layout)**: From `TileMetadata` only, compute:
- Spatial subdivisions (TRE2 records with bounds and RGN2 offsets)
- All section sizes and byte offsets (TRE, RGN, LBL headers and data)
- FAT table layout
- Per-tile file offsets within the IMG file

**Pass 2 (Stream Write)**: Write the IMG file sequentially:
- Write headers and fixed sections (same as now)
- For each tile in order, read JPEG from source cache, process (warp/reproject if needed), write to IMG at pre-computed offset
- Only one batch of JPEG data (~500 tiles ≈ 12 MB) in memory at a time

**Rationale**: The Garmin IMG format requires knowing all offsets before writing (FAT tables, section headers), so true append-only streaming is impossible. But a layout pass from metadata is cheap — 197K tiles of metadata is ~6 MB. The write pass then streams JPEG data through without accumulation.

**Alternative considered**: Write all headers with placeholder offsets, then seek back to fill them in. Rejected because seeking backwards in a large file is fragile and the layout pass is cheap enough to do upfront.

### D3: Pipeline streams per-zoom, not per-batch

**Decision**: The pipeline processes and writes one zoom level at a time. Within each zoom, tiles are streamed in batches to the writer.

**Rationale**: The IMG format groups data by zoom level (TRE2 subdivisions, RGN2 records, LBL sections). Processing zoom-by-zoom matches the natural structure. Within a zoom, the writer can stream tiles in batches because it knows exactly where each tile goes (from the layout pass).

The pipeline flow becomes:
```
for each zoom:
    1. Compute tile coords → TileMetadata list (tiny)
    2. Accumulate metadata for layout pass

Layout pass (all zooms):
    3. Generate subdivisions from TileMetadata
    4. Compute all offsets and section sizes

Write pass:
    5. Write headers, TRE, RGN2 records (bounds only)
    6. For each zoom, for each batch of 500 tiles:
        - Read source JPEG from cache
        - Warp to EPSG:4326 (rasterio)
        - Write JPEG bytes to IMG at pre-computed offset
    7. Write trailing sections, close file
```

Memory profile: ~6 MB for metadata (197K tiles) + ~12 MB per batch (500 tiles × 25 KB) + ~400 MB for ProcessPoolExecutor workers = **~420 MB peak**.

**Alternative considered**: Process all zooms in parallel. Rejected because the layout pass needs all zoom metadata, and the write pass must be sequential (single file). Zoom-by-zoom processing is simpler and matches checkpoint granularity.

### D4: JPEG processing moves from pipeline to writer

**Decision**: The JPEG warp/reprocessing happens during the write pass, not during the pipeline's process stage. The pipeline only produces `TileMetadata`. The writer's write pass reads source files and processes them on-demand.

**Rationale**: Currently `BatchTileProcessor.process_zoom_level()` warps JPEGs and returns `(bytes, bounds)` tuples. This loads all JPEG data into memory in the pipeline, before the writer even starts. By deferring JPEG processing to the write pass, we only process one batch at a time.

The writer's write pass calls `rasterio_warp.warp_tile_to_jpeg()` for each batch — same function, same speed, but only ~12 MB in memory at once.

**Trade-off**: Source file I/O happens twice (once for `os.path.getsize()` in layout, once for actual reading in write pass). The stat calls are negligible (~0.1ms per tile). The benefit is eliminating the 5+ GB memory spike.

### D5: LayoutComputer accepts TileMetadata, not CompressedTiles

**Decision**: Refactor `LayoutComputer` to accept `list[TileMetadata]` (organized by zoom) instead of `CompressedTiles` (which contains JPEG bytes). The `compute_gmp_size()` method reads only tile counts and JPEG sizes from metadata.

**Rationale**: Currently `_compute_gmp_size()` iterates tiles to sum JPEG lengths (`len(jpeg_data)`). With `TileMetadata`, it reads `metadata.jpeg_size` instead — same value, no JPEG data loaded.

### D6: generate_subdivisions accepts TileMetadata

**Decision**: Refactor `generate_subdivisions()` to accept `dict[int, list[TileMetadata]]` instead of `CompressedTiles`. The function only uses bounds (for grid assignment and center computation) and tile counts — never the JPEG data.

**Rationale**: The function iterates tiles to extract bounds (`tile_entry[1]` for the bounds tuple). With `TileMetadata`, bounds are directly available as fields. No behavioral change.

## Risks / Trade-offs

- **[Double I/O for source files]**: Source JPEGs are stat'd in the layout pass and read in the write pass. → Negligible: stat calls take ~0.1ms each. The alternative (caching file sizes) adds complexity for no measurable benefit.

- **[JPEG size mismatch between source and warped output]**: Layout pass uses source JPEG file size, but write pass produces a differently-sized warped JPEG. This would cause incorrect LBL29 offset computation. → **Mitigation**: For EPSG:3857→4326 warps, the output JPEG size differs from input. Solution: use the bounds-only layout approach where LBL29 section size is computed during the write pass itself, with a final fixup of LBL section headers. OR: use a two-phase write where LBL29 offsets are computed relative to a running counter during the write pass, and the LBL28 index is written in a second seek-back pass. The cleanest approach: compute JPEG size during warp (it's deterministic from quality + pixel dimensions + warp transform), or accept the seek-back for LBL headers.

- **[ProcessPoolExecutor memory during write pass]**: Each worker loads ~50 MB of GDAL context. With 8 workers, that's ~400 MB baseline. → Acceptable: total peak stays under 500 MB with 12 MB batch memory.

- **[Complexity of refactoring GMPWriter]**: The GMPWriter currently writes everything in one pass. Splitting it into a layout phase and a streaming write phase is the largest code change. → Mitigation: write the streaming writer alongside the existing writer, validate with tests, then switch over.
