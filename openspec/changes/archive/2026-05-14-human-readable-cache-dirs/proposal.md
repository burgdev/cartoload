## Why

Cache directories use a 12-char SHA-256 hash of the URL (e.g. `cache/swisstopo/a1b2c3d4e5f6/`), making it impossible to tell which layer or URL a cached tile set belongs to without looking up the config. A human-readable directory name derived from the URL path would make inspection, debugging, and manual cache management straightforward.

## What Changes

- Replace the hash-based `_url_cache_key()` in WMTS downloader with a URL-path-derived, filesystem-safe encoding: strip scheme and host, remove per-tile template variables (`${x}`, `${y}`, `${z}`, `${zoom}`), collapse empty path segments, replace `.` with `-`, replace remaining unsafe chars with `_`
- Replace the hash-based cache key in STAC downloader with the same encoding, using an optional `extra` string parameter for asset filters
- Auto-migrate old hash-based cache directories to the new format on build (when a hash-keyed directory is found, rename it)
- Update the existing `tile-cache` spec to reflect the new directory naming scheme

### Encoding example

```
URL:   https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/${z}/${x}/${y}.jpeg
Key:   1-0-0_ch-swisstopo-pixelkarte-farbe_default_current_3857_jpeg
Cache: cache/swisstopo/1-0-0_ch-swisstopo-pixelkarte-farbe_default_current_3857_jpeg/20/420/280.jpeg
```

## Capabilities

### New Capabilities

- `cache-migration`: Auto-migration of old hash-based cache directories to the new human-readable format, triggered on build

### Modified Capabilities

- `tile-cache`: Cache key derivation changes from SHA-256 hash to URL-path-encoded directory name, affecting WMTS downloader, STAC downloader, pipeline, and compositor

## Impact

- **Existing caches**: Old hash-based directories are auto-migrated on first build — no manual step required
- `src/cartoload/downloader/cache_key.py` — new shared `url_to_cache_key()` utility (replaces `_url_cache_key`)
- `src/cartoload/downloader/wmts.py` — use new `url_to_cache_key()`, remove old `_url_cache_key()`
- `src/cartoload/downloader/stac.py` — use new `url_to_cache_key()` with `extra` parameter
- `src/cartoload/pipeline.py` — update imports (uses `_url_cache_key` in 2 places)
- `src/cartoload/processor/compositor.py` — receives cache_key as passthrough, no logic change needed
- `openspec/specs/tile-cache/spec.md` — update cache directory path examples
