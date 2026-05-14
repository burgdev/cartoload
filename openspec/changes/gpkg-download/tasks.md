## 1. Config changes

- [ ] 1.1 Add `gpkg` to `ALLOWED_SOURCE_TYPES` and `SOURCE_TYPE_REQUIRED_FIELDS` in `src/cartoload/config.py`
- [ ] 1.2 Write test: config with `type: gpkg` is accepted and validates correctly

## 2. GPKG asset detection

- [ ] 2.1 Implement `_find_gpkg_asset()` function in `src/cartoload/downloader/gpkg.py` — detect GPKG assets by media type (`application/x.geopackage+zip`) and `.gpkg.zip` extension, with `asset_filter` support
- [ ] 2.2 Write tests for `_find_gpkg_asset()`: match by media type, match by extension, no match, multiple matches without filter, filter applied

## 3. GPKGDownloader class

- [ ] 3.1 Implement `GPKGDownloader` class with `run()` method: query STAC collection, download `.gpkg.zip`, extract to cache, return path to `.gpkg` file
- [ ] 3.2 Implement `query()` method: STAC items query with bbox filter, client-side spatial overlap check (follow `STACDownloader.query` pattern)
- [ ] 3.3 Implement zip extraction: scan for `.gpkg` files in archive, extract first match, warn on multiple, error on none
- [ ] 3.4 Implement cache path generation using `url_to_cache_key`, cache directory layout (`<source_id>/<cache_key>/<item>.zip` + `<item>.gpkg` + `<item>.json`)
- [ ] 3.5 Implement cache hit detection (`_is_cached`): check zip + gpkg + metadata sidecar exist
- [ ] 3.6 Implement freshness checking (`_check_freshness`): HTTP HEAD with ETag/Last-Modified comparison (reuse pattern from STAC downloader)
- [ ] 3.7 Implement metadata sidecar writing (`_write_metadata`): ETag, Last-Modified, download date
- [ ] 3.8 Write integration test for `GPKGDownloader.run()` with mocked STAC responses

## 4. Pipeline integration

- [ ] 4.1 Add `build_gpkg_layer()` function in `src/cartoload/pipeline.py`: create `GPKGDownloader`, run download, return `.gpkg` paths
- [ ] 4.2 Add `gpkg` dispatch branch in `build_layer()`: when `source.type == "gpkg"`, call `build_gpkg_layer()`
- [ ] 4.3 Write test: pipeline dispatches to `build_gpkg_layer` for `type: gpkg` source

## 5. Example config

- [ ] 5.1 Add example source config for swisstopo GPKG (e.g., skitouren) in `examples/configs/sources/`
