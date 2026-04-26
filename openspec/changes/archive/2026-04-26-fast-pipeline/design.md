## Context

The current cartoload pipeline follows a traditional raster processing approach:

```
Download tiles (JPEG/PNG, EPSG:3857)
  → gdalbuildvrt (VRT mosaic)
  → gdalwarp (reproject to EPSG:4326 GeoTIFF, ~GBs)
  → gdaladdo (build overviews)
  → gdal_translate × N (extract 256×256 tiles, ~30k subprocess spawns)
  → PIL JPEG encode
  → Binary IMG write
```

Each step writes to disk and the next reads it back. For 30k tiles this takes 100+ minutes, mostly spent spawning `gdal_translate` processes. For 300k tiles (France), the GeoTIFF alone would be tens of GB and memory usage (~57 GB for all tiles as numpy arrays) makes it infeasible.

Garmin IMG stores tile coordinates as linear WGS84 degrees (equirectangular/plate carrée), not Mercator. This means each tile needs to be reprojected from Web Mercator to equirectangular — but this can be done per-tile, not as a monolithic warp.

## Goals / Non-Goals

**Goals:**
- IMG from cached tiles in under 5 minutes for 30k tiles
- Bounded memory (~100 MB peak) regardless of tile count
- Resume after interruption without restarting from scratch
- Multi-URL parallel downloads with per-host rate limiting
- Preview images for quick visual verification
- Cache warmup mode for pre-populating before builds

**Non-Goals:**
- Vector map support (this is raster-only)
- Supporting CRS other than EPSG:4326 as target (Garmin requires WGS84)
- Rewriting in another language (Python is sufficient; optional C extensions via turbojpeg if available)
- Modifying the Garmin IMG binary format or subdivision strategy (that's a separate concern)

## Decisions

### Decision 1: Eliminate GeoTIFF pipeline entirely

**Choice**: Remove `gdalbuildvrt` → `gdalwarp` → `gdaladdo` → `gdal_translate` pipeline. Read tiles directly from cache.

**Alternatives considered**:
- Keep old pipeline as fallback: Adds complexity for no benefit. The direct pipeline handles all cases.
- Use GDAL Python bindings instead of CLI: Adds heavy dependency (GDAL Python is notoriously hard to install). CLI tools are already available.

**Rationale**: The GeoTIFF pipeline was a convenience for development. It's fundamentally wasteful (mosaic then split). The direct pipeline is simpler and faster.

### Decision 2: Per-tile reprojection via gdalwarp CLI

**Choice**: When a tile needs reprojection (EPSG:3857→4326), call `gdalwarp` on the individual tile. Cache the result.

**Alternatives considered**:
- Use rasterio/GDAL Python bindings for in-process reprojection: Heavy dependency, hard to install.
- Use PIL affine transform: Not a true CRS reprojection, would produce incorrect results for Mercator→equirectangular.
- Batch reprojection with gdalwarp on VRT: Still needs VRT, still monolithic.

**Rationale**: Per-tile `gdalwarp` is simple, correct, and the results are cached permanently. Each tile is warped at most once. For 30k tiles this is 30k gdalwarp calls, but with caching, subsequent builds are zero processing.

### Decision 3: JPEG passthrough when possible

**Choice**: When source CRS matches target CRS and quality matches, pass raw JPEG bytes through without decoding.

**Rationale**: Avoiding the decode→re-encode cycle saves significant CPU and preserves quality. For the common case of re-running a build with all tiles cached, this means near-zero image processing.

### Decision 4: Batch processing with configurable batch size

**Choice**: Process tiles in batches of 500 (default). Load batch → process → encode → write → release → next batch.

**Alternatives considered**:
- Pure streaming (one tile at a time): Too many small I/O operations, poor throughput.
- Load all tiles: OOM for 300k tiles.

**Rationale**: Batching amortizes overhead while keeping memory bounded. 500 tiles × ~30 KB JPEG ≈ 15 MB per batch in memory.

### Decision 5: JSON checkpoint per zoom level

**Choice**: Write a JSON `.checkpoint` file after each zoom level completes. Resume by skipping completed zooms.

**Alternatives considered**:
- Checkpoint per tile: Too granular, excessive I/O.
- Checkpoint per subdivision: Tied to IMG internal structure, fragile.
- Database (SQLite): Over-engineered for this use case.

**Rationale**: Zoom level granularity is the natural boundary — it's coarse enough to avoid overhead but fine enough to avoid reprocessing large amounts of work.

### Decision 6: Source CRS explicit in config, stored in cache metadata

**Choice**: Add optional `crs` field to `SourceConfig`. Write `metadata.json` in cache dir. Default to current behavior (WMTS→3857, GeoTIFF→from file).

**Rationale**: The hardcoded assumption works for now but will break when non-3857 WMTS sources are added. Making it explicit costs nothing and enables future sources.

### Decision 7: Multi-URL via round-robin with per-URL rate limiters

**Choice**: Accept list of URL templates in config. Round-robin distribution with independent rate limiters per URL. Thread pool = `max(4, len(urls) * 2)`.

**Alternatives considered**:
- Random distribution: Less predictable, harder to debug.
- Least-loaded distribution: Over-complicated for this use case.

**Rationale**: Round-robin is simple, fair, and deterministic. Per-URL rate limiting allows full utilization of each endpoint independently.

## Risks / Trade-offs

- **[Risk] Per-tile gdalwarp may have edge artifacts at tile boundaries** → Mitigation: tiles overlap by design in WMTS. If seams appear, add 1-pixel overlap during reprojection and crop during encoding.
- **[Risk] Reprojection cache doubles disk usage** → Mitigation: `cartoload cache clean --reprojection-only` to reclaim space. Document expected disk usage.
- **[Risk] Removing GeoTIFF pipeline loses ability to inspect intermediate output** → Mitigation: `--dry-run` and preview images provide better inspection than a massive GeoTIFF.
- **[Risk] Checkpoint JSON could get out of sync with cache** → Mitigation: On resume, verify that cached tiles for "completed" zooms still exist. If tiles were deleted, force restart.
- **[Trade-off] gdalwarp per tile is slower on first run than monolithic gdalwarp** → Accepted: First run is slower, but all subsequent runs are near-instant (cached). Cache warmup mode makes this a one-time cost.
- **[Trade-off] Only supports JPEG output in IMG** → Accepted: Garmin devices handle JPEG natively. PNG tiles are converted to JPEG during processing.
