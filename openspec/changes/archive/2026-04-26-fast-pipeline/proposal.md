## Why

Building a Garmin IMG from downloaded tiles currently takes 100+ minutes for a 30k-tile map (e.g., Switzerland 1:25k) because the pipeline mosaics all tiles into a single GeoTIFF via `gdalbuildvrt` → `gdalwarp` → `gdaladdo`, then extracts individual tiles back out by spawning `gdal_translate` per tile (~30k subprocess spawns). This is wasteful — we download individual tiles, glue them together, then split them apart again. For large maps (France 1:25k = 300k+ tiles), the current pipeline is impractical due to both time and memory constraints (all tiles loaded into memory as numpy arrays = ~57 GB).

## What Changes

- **BREAKING**: Eliminate the GeoTIFF intermediate pipeline entirely (`gdalbuildvrt`, `gdalwarp`, `gdaladdo`, `gdal_translate` per-tile). Replace with a direct tile-to-IMG pipeline that reads cached tiles and writes binary IMG output.
- Add per-tile reprojection (instead of monolithic `gdalwarp`) with a reprojection cache so each tile is warped only once.
- Add explicit `crs` field on source config (currently hardcoded: WMTS→3857, GeoTIFF→read from file).
- Add multi-URL download support with per-URL rate limiting and automatic thread pool scaling.
- Add two-tier cache: download cache (raw tiles) + reprojection cache (EPSG:4326 tiles), with mtime-based invalidation and `cartoload cache` CLI management.
- Add streaming/batched tile processing to bound memory usage (~100 MB peak regardless of tile count).
- Add resume-from-checkpoint capability (JSON checkpoint per zoom level, survives process kill).
- Add preview image generation (`--preview`, `-P/--preview-tiles`, `--preview-center`).
- Add cache warmup mode (`--cache-warmup`) — fill cache only, no output.
- Add `--dry-run` flag to show build plan without executing.
- Add build summary table (tile counts per zoom, cache status, ETA) and Rich ETA progress bars.

## Capabilities

### New Capabilities
- `fast-img-pipeline`: Direct tile-to-IMG pipeline, per-tile reprojection, no GeoTIFF intermediate, equirectangular coordinate encoding
- `tile-cache`: Two-tier cache (download + reprojection), mtime invalidation, cache CLI commands
- `source-crs`: Explicit CRS field on source config, CRS stored in cache metadata
- `multi-url-download`: Multiple URL templates per source, per-URL rate limiting, graceful failover
- `direct-tile-writer`: Read tiles from cache via PIL (no gdal_translate), world file bounds, JPEG pass-through, parallel reads
- `streaming-tile-processing`: Batched tile processing, bounded memory, pre-encoded JPEG passthrough
- `preview-images`: Per-zoom preview mosaics, adaptive tile count, configurable center and grid size
- `cache-warmup`: Cache-only build mode, progress reporting, reprojection cache warmup
- `resume-build`: JSON checkpoint per zoom level, resume on restart, atomic writes
- `dry-run`: Build plan without execution, tile counts, cache status, estimated size
- `eta-progress`: Rich ETA/time-remaining, multi-stage progress, per-zoom breakdown
- `build-summary`: Tile count table before build, cache status per zoom, reprojection status

### Modified Capabilities

## Impact

- **Core pipeline** (`src/cartoload/pipeline.py`): Major rewrite — remove GeoTIFF processing path, add direct tile-to-IMG fast path
- **Garmin IMG exporter** (`src/cartoload/exporters/garmin_img.py`, `garmin_img_writer.py`): `TileExtractor` rewritten to read from cache instead of GeoTIFF; `TileEncoder` updated for JPEG passthrough
- **Raster processor** (`src/cartoload/processors/`): Removed from the main pipeline (may keep for legacy/debug use)
- **WMTS downloader** (`src/cartoload/downloaders/`): Add multi-URL support, per-URL rate limiters
- **Config** (`src/cartoload/config/`): Add `crs` field to `SourceConfig`, add `urls` list support
- **CLI** (`src/cartoload/cli/`): Add `--cache-warmup`, `--dry-run`, `--preview`, `--preview-tiles`, `--preview-center`, `--batch-size` flags; add `cache` subcommand
- **Dependencies**: No new required deps; optional `turbojpeg` if available for faster JPEG ops
- **Disk**: Reprojection cache doubles cache size for non-4326 sources
