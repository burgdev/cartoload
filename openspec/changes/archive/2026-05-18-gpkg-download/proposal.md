## Why

Cartoload currently supports raster-only data sources (WMTS tiles, STAC GeoTIFFs). Many Swiss topographic datasets (skitours, hiking routes, etc.) are distributed as GeoPackage files via STAC endpoints. To support vector overlays — either rasterized into tiles (Path B) or converted to Garmin vector format via mkgmap (Path C) — we first need the ability to download and cache GPKG data.

## What Changes

- Add a new source type `gpkg` that downloads `.gpkg.zip` assets from STAC endpoints
- Extend the config system to accept `gpkg` as a valid source type
- Download and unzip GeoPackage files to the cache directory
- Provide the path to the extracted `.gpkg` file for downstream processors (style engine, rasterizer, mkgmap pipeline)
- Reuse existing STAC querying (bbox filtering, spatial overlap checks) from the `STACDownloader`
- Cache with freshness checking (ETag/Last-Modified) consistent with existing STAC caching

## Capabilities

### New Capabilities
- `gpkg-download`: Download, cache, and extract GeoPackage (.gpkg.zip) files from STAC endpoints

### Modified Capabilities
- `unified-config`: Add `gpkg` as an allowed source type with `url_template` as required field

## Impact

- **Config**: New source type `gpkg` alongside existing `wmts`, `stac`, `geotiff`
- **Pipeline**: New dispatch branch for `gpkg` source type, producing a `.gpkg` file path instead of tile images
- **Downloader**: New `GPKGDownloader` class in `src/cartoload/downloader/gpkg.py`
- **Dependencies**: No new dependencies (uses existing `requests`, `zipfile` from stdlib)
- **Downstream**: This is the foundation for the style engine, rasterizer (Path B), and mkgmap pipeline (Path C) changes
