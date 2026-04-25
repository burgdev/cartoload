## Why

WMTS/XYZ tile services are the primary input source for raster basemaps. swisstopo, basemap.at, and IGN France all expose their data via WMTS. The pipeline needs a downloader that can fetch tiles within a bounding box at specified zoom levels, respecting rate limits and supporting concurrent downloads.

## What Changes

- Implement `BaseDownloader` abstract class in `downloader/base.py` with the interface the pipeline expects
- Implement `WMTSDownloader` in `downloader/wmts.py` that: computes the tile grid for a given bbox + zoom level, downloads tiles concurrently with configurable thread count and rate limiting, retries on HTTP errors (429, 5xx), stores tiles in the cache directory organized by source/layer/zoom/x/y, and skips already-cached tiles
- Add rich progress bar output during downloads

## Capabilities

### New Capabilities

- `wmts-downloader`: Download tiles from any OGC WMTS or XYZ/TMS tile service within a bounding box at specified zoom levels, with concurrent downloads, rate limiting, caching, and retry logic

### Modified Capabilities

_(none — depends on config-loader but doesn't modify it)_

## Impact

- **Code**: `src/cartoload/downloader/base.py` and `src/cartoload/downloader/wmts.py` go from stubs to working implementations
- **Dependencies**: `requests` (already in deps), `rich` (already in deps) — no new dependencies
- **Tests**: `tests/test_downloader_wmts.py` with tile grid computation, download logic (mocked HTTP), caching, rate limiting, and retry behavior
