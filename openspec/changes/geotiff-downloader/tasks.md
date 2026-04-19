## 1. GeoTIFFDownloader Class

- [ ] 1.1 Create `GeoTIFFDownloader` class in `src/cartoload/downloader/geotiff.py` with an `__init__` method accepting `cache_dir` (path to the cache root directory)
- [ ] 1.2 Add a `run(source_config, layer_config)` method that orchestrates the full query-download-cache workflow and returns a list of local file paths
- [ ] 1.3 Add validation in `run` that `source_config.type == "geotiff"`, raising `ValueError` if not
- [ ] 1.4 Register `GeoTIFFDownloader` in `src/cartoload/downloader/__init__.py` for import by the pipeline

## 2. STAC Query Logic

- [ ] 2.1 Implement `query(stac_url, product_id, bbox)` method that opens a STAC catalog with `pystac_client.Client.open(stac_url)` and searches by `collections=[product_id]` and `bbox=[west, south, east, north]`
- [ ] 2.2 Handle connection failures from `pystac_client.Client.open` by raising a descriptive exception with the STAC URL and original error
- [ ] 2.3 Return an empty list and log a warning when the search returns no items
- [ ] 2.4 Extract the first GeoTIFF asset key (e.g., `"geotiff"` or the asset with `"image/tiff"` media type) from each STAC item returned by the search

## 3. GeoTIFF Download

- [ ] 3.1 Implement `download(asset_url, dest_path, expected_size=None)` method that streams the file via `requests.get(asset_url, stream=True)` in configurable chunk sizes (default 1 MB)
- [ ] 3.2 Write chunks to disk using binary file I/O, creating parent directories if they do not exist
- [ ] 3.3 After download completes, verify file size against `Content-Length` header if available; delete the file and raise an error on mismatch
- [ ] 3.4 Handle HTTP errors (non-200 responses) by raising a descriptive exception with the URL and status code

## 4. Caching

- [ ] 4.1 Implement cache path resolution: `{cache_dir}/{source_id}/{product_id}/{item_id}.tif`
- [ ] 4.2 Before each download, check if the target file exists and has non-zero size; if so, skip the download and log a "already cached" message
- [ ] 4.3 If a partial file exists (size < Content-Length), delete it and re-download
- [ ] 4.4 Create cache directories automatically using `pathlib.Path.mkdir(parents=True, exist_ok=True)`

## 5. Progress Output

- [ ] 5.1 Integrate `rich.progress.Progress` to display a progress bar for each file download showing filename, bytes downloaded, total bytes, speed, and ETA
- [ ] 5.2 Print a summary after all downloads complete indicating total files downloaded and total files skipped (cached)

## 6. Tests

- [ ] 6.1 Create `tests/test_downloader_geotiff.py` with pytest fixtures for mock `SourceConfig` and `LayerConfig` dataclass instances (geotiff type with stac_url, product_id, and bounds)
- [ ] 6.2 Test STAC query logic: mock `pystac_client.Client.open` and `.search()` to return a list of STAC items with GeoTIFF assets; verify correct search parameters (collection, bbox)
- [ ] 6.3 Test STAC query with no results: mock empty search result and verify empty list return with no errors
- [ ] 6.4 Test STAC query connection failure: mock `Client.open` to raise an exception and verify the downloader raises a descriptive error
- [ ] 6.5 Test download: mock `requests.get` to return streaming GeoTIFF data and verify the file is written to the correct cache path
- [ ] 6.6 Test caching: create a pre-existing file in the cache directory and verify the download is skipped
- [ ] 6.7 Test partial file re-download: create a file smaller than Content-Length and verify it is deleted and re-downloaded
- [ ] 6.8 Test wrong source type: call `run` with a source config of `type: wmts` and verify `ValueError` is raised
- [ ] 6.9 Test file size verification: mock a response where the written file size does not match Content-Length and verify the partial file is deleted and an error is raised
