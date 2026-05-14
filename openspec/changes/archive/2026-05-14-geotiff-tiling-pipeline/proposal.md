## Why

The existing GeoTIFF downloader can fetch files from STAC APIs and store them in cache, but the pipeline cannot actually use these files — there is no code to read pixel data from GeoTIFFs and feed it into the tile export pipeline. This means the `geotiff` source type is dead code: downloaded GeoTIFFs just sit in cache with nothing consuming them.

High-resolution GeoTIFFs from providers like swisstopo offer much better quality than WMTS tiles at equivalent zoom levels. For the swisstopo 1:25k raster map, GeoTIFFs are the only way to get the full-resolution source data (264 tiles covering Switzerland at 1.25m resolution in EPSG:2056).

## What Changes

- Split source types into three: `wmts` (existing), `stac` (STAC API → download assets → route by format), and `geotiff` (local paths or remote URLs to GeoTIFF files).
- `stac` sources use `urls`/`url_template` with `${layer}` substitution (same config pattern as WMTS), pointing to STAC collection endpoints. Downloads assets and routes to the appropriate processor based on media type (currently GeoTIFF only, extensible).
- `geotiff` sources use `urls` to reference GeoTIFF files directly — local paths (relative to config file or absolute), HTTP URLs (downloaded to cache), or directory paths (scanned recursively). This is effectively what's in the cache after a `stac` download.
- Add a **GeoTIFF tile reader** that, for a given (x, y, zoom) tile coordinate, finds the relevant GeoTIFF, reads the overlapping pixel window via rasterio, warps to EPSG:4326, and returns JPEG bytes.
- Build a **GeoTIFF spatial index** after download/collection: read each file's CRS and bounds from metadata for fast tile-to-file mapping.
- Wire into the existing build pipeline so both `stac` and `geotiff` sources flow through the same export path as WMTS.

## Capabilities

### New Capabilities
- `geotiff-tile-reader`: On-the-fly tile extraction from GeoTIFF files using rasterio windowed reads. For each (x, y, zoom), reads only the needed pixel window, warps to EPSG:4326, and returns JPEG bytes.
- `geotiff-spatial-index`: Read each GeoTIFF's CRS and bounds to build a spatial index for fast tile-to-file lookup.
- `stac-source`: STAC API source type that queries collection endpoints and downloads assets. Uses `urls`/`url_template` with `${layer}` substitution. Routes to format-specific processor based on asset media type.
- `geotiff-path-source`: `geotiff` source type that references GeoTIFF files via local paths (relative/absolute), HTTP URLs, or directory paths. Local files used in-place; remote URLs downloaded to cache.

### Modified Capabilities
- `source-crs`: Extend to handle non-3857 source CRS from GeoTIFF files (e.g. EPSG:2056), with auto-detection from file metadata.

## Impact

- **Code**: `pipeline.py` (stac/geotiff branches), `downloader/geotiff.py` → `downloader/stac.py` (renamed, uses `urls`), new `processor/geotiff_tile_reader.py`, `config.py` (add `stac` type, redefine `geotiff` type, remove `stac_url`/`geotiff_product`)
- **Dependencies**: No new dependencies needed.
- **Config format**: **BREAKING** — existing `type: geotiff` with `stac_url` becomes `type: stac` with `urls`. New `type: geotiff` points at local/remote GeoTIFF files.
- **Existing behavior**: No changes to WMTS pipeline.
