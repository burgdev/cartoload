## Context

WMTS is the primary input source for raster basemaps. swisstopo, basemap.at, and IGN France all expose their data via OGC WMTS or compatible XYZ/TMS tile services. The pipeline needs a downloader that can fetch tiles within a bounding box at specified zoom levels, respecting rate limits and supporting concurrent downloads.

The project scaffolding change established stubs in `src/cartoload/downloader/base.py` (abstract `BaseDownloader`) and `src/cartoload/downloader/wmts.py` (empty `WMTSDownloader`). This change fills those stubs with working implementations.

The WMTS download process has three stages:
1. **Tile grid computation** -- convert a bounding box (min_lon, min_lat, max_lon, max_lat) and zoom level into the set of (x, y) tile indices that cover the area, using the standard Web Mercator (EPSG:3857) tile scheme.
2. **URL template interpolation** -- expand a URL template like `https://wmts.example.com/{zoom}/{x}/{y}.jpeg` or a KVP-style WMTS URL with the computed tile coordinates.
3. **Concurrent download loop** -- fetch all tiles, respecting rate limits, caching completed tiles to disk, and retrying on transient failures.

The `requests` library is already a runtime dependency and handles HTTP. The `rich` library is already a dependency and provides progress bar output.

## Goals / Non-Goals

**Goals:**
- Working WMTS downloader with tile grid computation from bbox + zoom
- Concurrent downloads with configurable thread count
- Rate limiting between requests to avoid provider throttling
- Disk-based caching that skips already-downloaded tiles
- Retry with exponential backoff on HTTP errors (429, 5xx)
- Rich progress bar output during downloads

**Non-Goals:**
- GeoTIFF downloading (separate `geotiff-downloader` change)
- Raster processing (merging, reprojecting -- separate `raster-processor` change)
- Exporting tiles to Garmin `.img` (separate `garmin-img-exporter` change)
- Authentication/API key management (providers currently use open endpoints; can be added later)
- WMTS GetCapabilities parsing (users provide URL templates directly in config)

## Decisions

### 1. ThreadPoolExecutor for concurrency

**Choice**: Use `concurrent.futures.ThreadPoolExecutor` with a configurable `max_workers` parameter.

**Rationale**: Tile downloads are I/O-bound (HTTP requests), so threads are the natural fit. `ThreadPoolExecutor` is in the standard library, well-tested, and easy to reason about. The alternative would be `asyncio` with `aiohttp`, but that would add a dependency and requires the rest of the codebase to be async-aware.

**Alternative considered**: `asyncio` + `aiohttp` -- rejected because it introduces a new dependency and would require async propagation through the pipeline.

### 2. `time.sleep` for rate limiting

**Choice**: Use `time.sleep` with a configurable delay (default 150ms) between requests per thread.

**Rationale**: Simple and predictable. Each thread sleeps before making a request, ensuring a minimum interval between consecutive requests. The delay is configurable via the `WMTS_DELAY_MS` environment variable or the source config.

**Alternative considered**: Token bucket algorithm -- overkill for this use case. A simple sleep is sufficient and easier to debug.

### 3. `requests` library for HTTP

**Choice**: Use the `requests` library (already a runtime dependency) for all HTTP operations.

**Rationale**: `requests` is already in the dependency list, widely used, and handles connection pooling, timeouts, and redirects out of the box. No new dependency needed.

### 4. Cache directory structure: `cache/{source_id}/{zoom}/{x}/{y}.{ext}`

**Choice**: Tiles are stored on disk at `cache/{source_id}/{zoom}/{x}/{y}.{ext}`, where `ext` is derived from the tile format (e.g., `jpeg`, `png`).

**Rationale**: This mirrors the tile pyramid structure and makes it easy to inspect the cache manually. Using `source_id` as the top-level directory prevents collisions between different sources at the same zoom/x/y. The cache directory is configurable via `--cache-dir`.

### 5. Skip existing files in cache

**Choice**: If a tile file already exists in the cache directory, skip the download.

**Rationale**: This enables resumable downloads. If a large download is interrupted, re-running it only fetches the missing tiles. The file's existence is the cache check -- no metadata database needed.

**Trade-off**: A partially written file (from a crash during download) would be treated as cached. Mitigated by writing to a `.tmp` file first and renaming on completion.

### 6. Exponential backoff on retries

**Choice**: Retry up to 3 times with exponential backoff (1s, 2s, 4s) on HTTP 429 and 5xx errors.

**Rationale**: Transient failures are common with tile servers under load. Exponential backoff gives the server time to recover. A maximum of 3 retries balances reliability against hanging forever.

### 7. Rich progress bar output

**Choice**: Use `rich.progress.Progress` to display download progress with columns: spinner, description, bar, percentage, count (`{done}/{total}`), and elapsed time.

**Rationale**: `rich` is already a dependency. The progress bar gives users real-time feedback during long downloads. Using the `Progress` context manager ensures cleanup on completion or error.

## Risks / Trade-offs

- **Rate limits unknown for providers** -- Start conservative at 150ms delay and 4 threads. These defaults can be tuned per-source in the config. Users can override via environment variables (`WMTS_DELAY_MS`, `WMTS_THREADS`) if they know their provider allows more.
- **Some providers may require API keys** -- swisstopo, basemap.at, and IGN France currently have open endpoints, but this could change. The design supports adding headers (including `Referer` and `User-Agent`) in the URL template config, but full API key auth is deferred to a future change.
- **Thread safety of cache writes** -- Two threads could theoretically write the same tile if the grid overlaps or the cache is shared. Mitigated by the per-tile lock-free design: writing to a `.tmp` file and renaming is atomic on POSIX, and duplicate downloads are harmless (same content).
- **Large tile counts at high zoom** -- At zoom 16, a single country (e.g., Switzerland) requires ~100k tiles. The tile grid computation must be efficient and the download loop must handle this volume without excessive memory usage.
