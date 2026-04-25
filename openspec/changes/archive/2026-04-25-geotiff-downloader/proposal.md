## Why

GeoTIFF via STAC API is the preferred source for high-quality basemaps (e.g., swisstopo SMR25). The SPEC.md implementation order puts GeoTIFF support as step 5 — after the WMTS downloader and pipeline are working. This downloader queries a STAC API for available tiles, downloads GeoTIFF files, and stores them in the cache directory.

## What Changes

- Implement `GeoTIFFDownloader` in `downloader/geotiff.py` that: queries a STAC API for items matching a product ID and bounding box, downloads GeoTIFF assets, stores them in the cache directory organized by source/product/bbox, and skips already-cached files
- Add progress output via rich

## Capabilities

### New Capabilities

- `geotiff-downloader`: Query STAC APIs and download GeoTIFF tiles for a given product and bounding box, with caching and progress output

### Modified Capabilities

_(none)_

## Impact

- **Code**: `src/cartoload/downloader/geotiff.py` goes from stub to working implementation
- **Dependencies**: `pystac-client` (already in deps) — no new dependencies
- **Tests**: `tests/test_downloader_geotiff.py` with STAC query logic (mocked API), download, and caching
