## 1. Config — Three Source Types

- [x] 1.1 Add `stac` to `ALLOWED_SOURCE_TYPES` in `config.py`, redefine `geotiff` type
- [x] 1.2 Remove `stac_url` from `SourceConfig` — stac sources use `urls`/`url_template` (same as WMTS)
- [x] 1.3 Remove `geotiff_product` from `LayerConfig` — collection ID comes from `source_args.layer`
- [x] 1.4 Update `SOURCE_TYPE_REQUIRED_FIELDS`: `stac` requires `urls`/`url_template`, `geotiff` requires `urls`
- [x] 1.5 Update existing `swisstopo_stac` source in `swisstopo.yaml` to `type: stac` with `urls` + `${layer}` template
- [x] 1.6 Create example `geotiff` source entry in swisstopo.yaml (pointing at cache directory)
- [x] 1.7 Create example layer entries for both `stac` and `geotiff` sources

## 2. STAC Downloader (rename + refactor)

- [x] 2.1 Rename `downloader/geotiff.py` → `downloader/stac.py`, rename class to `STACDownloader`
- [x] 2.2 Update `STACDownloader` to accept resolved URL from `urls`/`url_template` (STAC collection endpoint)
- [x] 2.3 Extract collection ID from `source_args.layer` instead of `layer_config.geotiff_product`
- [x] 2.4 Update `downloader/__init__.py` exports
- [x] 2.5 Update `pipeline.py` imports (GeoTIFFDownloader → STACDownloader)

## 3. GeoTIFF Path Source (new)

- [x] 3.1 Add GeoTIFF path resolution in pipeline: distinguish local paths (relative/absolute) from HTTP URLs
- [x] 3.2 For local directories: scan recursively for `.tif`/`.tiff` files, return list of paths
- [x] 3.3 For local files: validate existence, return as-is
- [x] 3.4 For HTTP URLs: download to cache (reuse existing download logic from STACDownloader)
- [x] 3.5 Resolve relative paths from the source config file's directory
- [ ] 3.6 Write tests for path resolution: relative, absolute, directory scan, HTTP URLs, mixed

## 4. GeoTIFF Spatial Index

- [x] 4.1 Create `src/cartoload/processor/geotiff_index.py` with a `GeoTIFFIndex` class that reads CRS and bounds from GeoTIFF files via rasterio
- [x] 4.2 Implement `find_geotiff(lon_min, lat_min, lon_max, lat_max)` lookup returning the filepath covering a given extent
- [ ] 4.3 Write tests for the spatial index: single GeoTIFF, multiple GeoTIFFs, no match, CRS detection

## 5. GeoTIFF Tile Reader

- [x] 5.1 Create `src/cartoload/processor/geotiff_tile_reader.py` with a function that takes (x, y, zoom, geotiff_path) and returns JPEG bytes via rasterio windowed read + warp to EPSG:4326
- [x] 5.2 Implement window computation: given tile geographic extent, compute the pixel window in the GeoTIFF's CRS and transform
- [x] 5.3 Handle CRS conversion: transform tile bounds from WGS84 to GeoTIFF native CRS before computing read window
- [ ] 5.4 Write tests: basic windowed read, CRS reprojection, tile outside extent returns None

## 6. Pipeline Integration

- [x] 6.1 Update `build_layer()` in `pipeline.py`: for `stac` type, run STACDownloader then build spatial index
- [x] 6.2 Update `build_layer()` for `geotiff` type: resolve paths, build spatial index
- [x] 6.3 Wire GeoTIFF tile reader into streaming export as `tile_processor_override` (same pattern as compositing)
- [x] 6.4 Update `get_downloader()` to handle `stac` type
- [x] 6.5 Ensure checkpoint/resume: downloaded GeoTIFFs are cached, spatial index rebuilt from cache

## 7. Example Configs & Documentation

- [x] 7.1 Update `swisstopo_stac` in `examples/configs/sources/swisstopo.yaml` to `type: stac`
- [x] 7.2 Add example `geotiff` source entry pointing at a cache directory
- [x] 7.3 Add example layer entries for stac and geotiff sources
- [x] 7.4 Update `docs/` with page on STAC and GeoTIFF sources

## 8. Verification

- [x] 8.1 Run `just check` and `just check types` — formatting, linting, type correctness pass
- [x] 8.2 Run `just test` — all existing and new tests pass
- [ ] 8.3 End-to-end test: build a small-area layer from swisstopo STAC source and verify IMG output
