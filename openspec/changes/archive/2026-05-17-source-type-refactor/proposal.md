## Why

Currently `stac` is both a source type AND a download method. This conflates *what the data is* (GeoTIFF, GPKG) with *how to get it* (STAC API, local path, direct URL). The `geotiff` type already works around this — it handles local/remote GeoTIFF paths while `stac` handles GeoTIFFs via STAC download. With GPKG support added (also via STAC), the conflation gets worse.

The cleaner model:

- **Type** = what the data is → determines processing pipeline (raster tiles, vector rasterization, etc.)
- **Source** = how to get it → determines download/cache strategy (STAC query, local path, direct URL)

## What Changes

- Rename source type `stac` to `geotiff` (it was always GeoTIFF-via-STAC; now the type name reflects the data format)
- Remove `gpkg` from being a separate download path — instead make `type: gpkg` use a configurable source method
- Introduce a `source` field on source configs: `stac` (default when URL looks like STAC), `path`
- Auto-detect the source method from the URL when not explicitly set
- Keep `wmts` as its own type (inherently tile-based, different pipeline)
- **Remove `url_template`** — consolidate to `urls` as the single field for source locations (URLs, paths, STAC endpoints). A string value is auto-wrapped into a list.
- Update all example configs to use the new model

## Capabilities

### New Capabilities
- `source-method-resolution`: Auto-detect or explicitly configure how a source is fetched (stac, path, url)

### Modified Capabilities
- `unified-config`: Source type now means data format (geotiff, gpkg, wmts). `stac` type removed. New optional `source` field for download method.

## Impact

- **Config**: Breaking change — `type: stac` → `type: geotiff` + auto-detected STAC source. `url_template` removed, use `urls` instead. Existing `type: geotiff` sources unchanged (already use path source).
- **Downloader**: Source method resolution logic extracts common STAC querying from both `STACDownloader` and `GPKGDownloader`
- **Pipeline**: Dispatch based on type only (geotiff, gpkg, wmts). Source method determines how files are obtained before processing.
- **Example configs**: Update all configs referencing `type: stac` and `url_template`
