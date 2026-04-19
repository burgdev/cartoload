## 1. Base Downloader Interface

- [ ] 1.1 Implement `BaseDownloader` abstract class in `src/cartoload/downloader/base.py` with abstract methods `download_tile(x, y, zoom)` and `download_grid(bbox, zoom)`, and concrete properties for `cache_dir`, `source_id`, and `max_workers`
- [ ] 1.2 Add `__init__` to `BaseDownloader` accepting `source_id`, `cache_dir`, `max_workers`, and `delay_ms` parameters with sensible defaults

## 2. Tile Grid Computation

- [ ] 2.1 Implement `_bbox_to_tile_indices(bbox, zoom)` static method on `WMTSDownloader` that converts a WGS84 bounding box to the set of `(x, y)` tile coordinates at the given zoom level using the Web Mercator tile scheme
- [ ] 2.2 Handle edge cases: single-tile bbox, bbox at zoom 0, bbox near tile boundaries, and antimeridian wrapping
- [ ] 2.3 Write unit tests for tile grid computation with known bbox/zoom inputs and expected tile index outputs

## 3. URL Template Interpolation

- [ ] 3.1 Implement `_build_tile_url(template, x, y, zoom, source_id)` static method that substitutes `{zoom}`, `{x}`, `{y}`, and `{source_id}` placeholders in the URL template
- [ ] 3.2 Write unit tests for URL interpolation covering XYZ-style, KVP-style WMTS, and `{source_id}` templates

## 4. Concurrent Download Loop

- [ ] 4.1 Implement `download_grid(bbox, zoom)` on `WMTSDownloader` that computes the tile grid, filters out cached tiles, and submits remaining tiles to a `ThreadPoolExecutor`
- [ ] 4.2 Wire the executor's `max_workers` to the configurable thread limit
- [ ] 4.3 Write integration tests (mocked HTTP) that verify concurrency behavior and that all tiles in the grid are fetched

## 5. Rate Limiting

- [ ] 5.1 Implement per-thread rate limiting using `time.sleep(delay_seconds)` before each HTTP request in the download worker function
- [ ] 5.2 Wire the delay to the configurable `delay_ms` parameter (default 150ms)
- [ ] 5.3 Write tests verifying that the minimum delay is enforced between requests (using mocked `time.sleep`)

## 6. Caching Logic

- [ ] 6.1 Implement `_cache_path(x, y, zoom)` method returning `cache/{source_id}/{zoom}/{x}/{y}.{ext}` based on the tile format from the URL template
- [ ] 6.2 Implement cache hit check: if the file at `_cache_path` exists, skip the download and return immediately
- [ ] 6.3 Implement atomic cache write: download to a `.tmp` file in the same directory, then `os.rename` to the final path
- [ ] 6.4 Ensure the cache directory structure is created (`os.makedirs(exist_ok=True)`) before writing
- [ ] 6.5 Write tests for cache miss (downloads and writes), cache hit (skips download), and atomic write (tmp file is renamed)

## 7. Retry with Backoff

- [ ] 7.1 Implement `_download_with_retry(url, x, y, zoom)` method that wraps the HTTP request in a retry loop (max 3 attempts) for HTTP 429 and 5xx responses
- [ ] 7.2 Implement exponential backoff: sleep 1s after first failure, 2s after second, 4s after third
- [ ] 7.3 Record tiles that exhaust all retries as failed (log warning, continue with remaining tiles)
- [ ] 7.4 Do not retry on HTTP 404 or other non-transient errors
- [ ] 7.5 Write tests for retry on 503, retry on 429, exhausted retries, and no-retry on 404

## 8. Rich Progress Output

- [ ] 8.1 Add `rich.progress.Progress` context manager to `download_grid` with columns: spinner, description, progress bar, percentage, download count (`{done}/{total}`), and elapsed time
- [ ] 8.2 Pre-populate the progress bar with cached tile count (fast-forward the counter for skipped tiles)
- [ ] 8.3 Advance the progress bar after each successful download or cache hit
- [ ] 8.4 Write tests verifying that progress output is produced (capture rich output)

## 9. Integration Tests

- [ ] 9.1 Write end-to-end test with mocked HTTP server: configure a WMTS source, provide a bbox and zoom, run `download_grid`, and verify all tiles are cached on disk
- [ ] 9.2 Write test for resumable download: download half the grid, stop, resume, and verify only uncached tiles are fetched on the second run
- [ ] 9.3 Write test for mixed success/failure: some tiles return 200, some return 503 then 200, some return 404 -- verify correct tiles are cached and failures are reported
