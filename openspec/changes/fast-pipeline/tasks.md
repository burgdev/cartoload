## 1. Source Config & CRS

- [ ] 1.1 Add optional `crs` field to `SourceConfig` dataclass (default `None` for backward compat)
- [ ] 1.2 Update config YAML loader to parse `crs` field from source definitions
- [ ] 1.3 Write `metadata.json` with `{"crs": "..."}` to cache dir on first download
- [ ] 1.4 Update pipeline to read source CRS from config (falling back to hardcoded defaults: WMTS→3857, GeoTIFF→from file)
- [ ] 1.5 Add tests for CRS field parsing, default behavior, and cache metadata

## 2. Multi-URL Download

- [ ] 2.1 Update `SourceConfig` to accept `url_template` (string) or `urls` (list of strings) for URL templates
- [ ] 2.2 Implement per-URL rate limiter (each URL gets its own `threading.Event`-based throttle)
- [ ] 2.3 Implement round-robin URL distribution across the tile grid
- [ ] 2.4 Scale thread pool to `max(4, len(urls) * 2)` when multiple URLs configured
- [ ] 2.5 Implement graceful failover: stop sending to failing URLs, redistribute tiles to healthy ones
- [ ] 2.6 Add tests for multi-URL distribution, rate limiting, and failover

## 3. Two-Tier Cache

- [ ] 3.1 Define reprojection cache path: `cache/{source_id}_4326/{zoom}/{x}/{y}.{format}`
- [ ] 3.2 Implement mtime-based invalidation: compare source tile mtime vs reprojected tile mtime
- [ ] 3.3 Skip reprojection cache creation for EPSG:4326 sources (use download cache directly)
- [ ] 3.4 Add `cartoload cache status` subcommand: report total size, tile counts per source, download vs reprojection cache
- [ ] 3.5 Add `cartoload cache clean` subcommand with `--source` and `--reprojection-only` filters
- [ ] 3.6 Add tests for cache structure, invalidation, and CLI commands

## 4. Per-Tile Reprojection

- [ ] 4.1 Implement `reproject_tile(source_path, source_crs, target_crs, output_path)` using `gdalwarp` CLI
- [ ] 4.2 Implement cache-aware wrapper: check reprojection cache first, only warp if cache miss or stale
- [ ] 4.3 Add world file generation for reprojected tiles (`.jgw` with EPSG:4326 coordinates)
- [ ] 4.4 Add tests for per-tile reprojection, cache hit/miss, and world file output

## 5. Direct Tile Reader (no gdal_translate)

- [ ] 5.1 Implement world file parser (`parse_world_file(path)`) returning `(pixel_size_x, rotation_y, rotation_x, pixel_size_y, top_left_x, top_left_y)`
- [ ] 5.2 Implement `TileCacheReader` class that reads tiles from cache, returns `(jpeg_bytes, bounds)` tuples
- [ ] 5.3 Add JPEG passthrough: return raw bytes when quality matches and no reprojection needed
- [ ] 5.4 Add PNG→JPEG conversion path when source is PNG
- [ ] 5.5 Implement fallback bounds computation from Web Mercator tile grid math when world file missing
- [ ] 5.6 Add tests for world file parsing, JPEG passthrough, PNG conversion, and fallback bounds

## 6. Streaming / Batch Processing

- [ ] 6.1 Refactor `TileExtractor` to support batch processing with configurable batch size (default 500)
- [ ] 6.2 Update pipeline to process batches: load batch → read/reproject/encode → pass to IMG writer → release
- [ ] 6.3 Implement parallel batch reads using `ThreadPoolExecutor` with `min(32, cpu_count * 4)` threads
- [ ] 6.4 Update `IMGWriter` to accept pre-encoded JPEG bytes directly (skip `TileEncoder.encode_tile()`)
- [ ] 6.5 Add tests for batch processing, memory bounds verification, and parallel reads

## 7. Pipeline Rewrite

- [ ] 7.1 Rewrite `build_layer()` in `pipeline.py` to use direct tile-to-IMG pipeline (remove GeoTIFF path)
- [ ] 7.2 Wire up: download (multi-URL) → cache check → per-tile reprojection (if needed) → batch read → IMG write
- [ ] 7.3 Remove `RasterProcessor` usage from main pipeline (keep module for legacy/debug)
- [ ] 7.4 Add integration test: full pipeline from cache → IMG for a small tile set
- [ ] 7.5 Add integration test: full pipeline with download + reprojection + IMG for a small tile set

## 8. Resume / Checkpoint

- [ ] 8.1 Define checkpoint JSON schema: `{layer, completed_zoom_levels, remaining_zoom_levels, total_tiles, processed_tiles, started_at, updated_at}`
- [ ] 8.2 Implement checkpoint write after each zoom level (atomic: temp file + rename)
- [ ] 8.3 Implement checkpoint detection on build start: print resume message, skip completed zooms
- [ ] 8.4 Implement `--force` flag to discard checkpoint and start fresh
- [ ] 8.5 Implement corrupt/invalid checkpoint handling (delete and start fresh with warning)
- [ ] 8.6 Delete checkpoint on successful build completion
- [ ] 8.7 Add tests for checkpoint create, resume, force-restart, corrupt handling, and cleanup

## 9. Build Summary & Progress

- [ ] 9.1 Implement tile grid pre-computation: count tiles per zoom level within bounds
- [ ] 9.2 Implement cache status scan: count cached vs missing tiles per zoom from download and reprojection caches
- [ ] 9.3 Implement build summary printer: table with zoom/tiles/cached/to-process + estimated output size
- [ ] 9.4 Add `TimeRemainingColumn` to Rich progress bars for ETA
- [ ] 9.5 Implement multi-stage progress: download → processing → writing with overall + per-zoom indicators
- [ ] 9.6 Handle "all cached" case: skip download stage display, show "fast build expected"
- [ ] 9.7 Add tests for summary output formatting and cache status computation

## 10. Dry Run

- [ ] 10.1 Add `--dry-run` CLI flag that triggers build plan computation without execution
- [ ] 10.2 Implement dry-run output: full summary table + "Dry run — no files will be created" message
- [ ] 10.3 Verify dry-run creates no files (no cache writes, no output directory, no IMG)
- [ ] 10.4 Add tests for dry-run flag behavior

## 11. Cache Warmup

- [ ] 11.1 Add `--cache-warmup` CLI flag on build command
- [ ] 11.2 Implement warmup mode: download all tiles + reproject (if needed) + populate cache, then exit
- [ ] 11.3 Ensure warmup creates no files outside cache directory
- [ ] 11.4 Add warmup progress: "N cached, M to download" summary
- [ ] 11.5 Add tests for warmup mode behavior

## 12. Preview Images

- [ ] 12.1 Add `--preview`, `--preview-tiles` / `-P`, `--preview-center` CLI flags
- [ ] 12.2 Implement preview center computation: default to bbox center, override from `--preview-center`
- [ ] 12.3 Implement adaptive tile count: compute available tiles around center, shrink grid if fewer than requested
- [ ] 12.4 Implement tile mosaic assembler: read cached tiles, stitch into single JPEG image
- [ ] 12.5 Write previews to `previews/{layer_name}_zoom{Z}.jpg` relative to output directory
- [ ] 12.6 Skip preview generation for zoom levels with zero available tiles
- [ ] 12.7 Add tests for preview generation, adaptive grid, and output location
