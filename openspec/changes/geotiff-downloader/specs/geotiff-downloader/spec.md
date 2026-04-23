## ADDED Requirements

### Requirement: STAC API query by product and bounding box

The `GeoTIFFDownloader` SHALL accept a STAC API URL, a product ID (STAC collection name), and a bounding box (west, south, east, north in EPSG:4326), and return a list of matching STAC items using pystac-client.

#### Scenario: Query returns matching items

- **WHEN** `GeoTIFFDownloader.query(stac_url, product_id, bbox)` is called with a valid STAC endpoint, an existing collection name, and a bounding box intersecting available data
- **THEN** it returns a list of STAC items belonging to the specified collection and intersecting the bounding box

#### Scenario: Query with no matching items

- **WHEN** `GeoTIFFDownloader.query(stac_url, product_id, bbox)` is called with a product ID or bounding box that has no matching items
- **THEN** it returns an empty list and logs a warning indicating no items were found

#### Scenario: Query with invalid STAC URL

- **WHEN** `GeoTIFFDownloader.query(stac_url, product_id, bbox)` is called with a STAC URL that is unreachable or not a valid STAC API
- **THEN** it raises a descriptive exception indicating the STAC API connection failure

### Requirement: GeoTIFF asset download

The `GeoTIFFDownloader` SHALL download GeoTIFF assets from STAC items to the local cache directory using streaming HTTP requests.

#### Scenario: Download a GeoTIFF asset

- **WHEN** `GeoTIFFDownloader.download(item, asset_key, dest_path)` is called for a STAC item containing a GeoTIFF asset
- **THEN** it streams the asset to `dest_path` using chunk-based writing and returns the path to the downloaded file

#### Scenario: Download verifies file completeness

- **WHEN** a download completes and the response included a `Content-Length` header
- **THEN** the downloader verifies the written file size matches the expected size; if it does not match, the partial file is deleted and an error is raised

### Requirement: Cache directory structure

Downloaded GeoTIFF files SHALL be stored under `{cache_dir}/{source_id}/{product_id}/{filename}` where `filename` is derived from the STAC item ID with a `.tif` extension.

#### Scenario: Files are cached in structured directory

- **WHEN** a GeoTIFF is downloaded for source `swisstopo_stac` and product `ch.swisstopo.swissmap-raster25_komb`
- **THEN** the file is stored at `{cache_dir}/swisstopo_stac/ch.swisstopo.swissmap-raster25_komb/{item_id}.tif`

#### Scenario: Cache directories are created automatically

- **WHEN** a download is initiated and the target cache directory does not exist
- **THEN** the directory is created before the download begins

### Requirement: Skip existing cached files

The downloader SHALL check whether a target file already exists in the cache before downloading. If the file exists and has non-zero size, the download is skipped.

#### Scenario: Existing file is skipped

- **WHEN** a download is requested for a file that already exists in the cache with non-zero size
- **THEN** the downloader skips the download and logs that the file was already cached

#### Scenario: Partial file is re-downloaded

- **WHEN** a previous download was interrupted and the cached file exists but has a size smaller than the expected `Content-Length`
- **THEN** the downloader deletes the partial file and re-downloads it

### Requirement: Progress output

The downloader SHALL display download progress using rich, showing the filename, download speed, and percentage complete for each file.

#### Scenario: Progress shown during download

- **WHEN** a GeoTIFF download is in progress
- **THEN** a rich progress bar is displayed showing the filename, bytes downloaded, total bytes, download speed, and ETA

#### Scenario: Progress summary after completion

- **WHEN** all downloads for a query have completed
- **THEN** a summary is printed indicating the total number of files downloaded and the total number skipped (already cached)

### Requirement: Integration with SourceConfig and LayerConfig

The `GeoTIFFDownloader` SHALL accept a `SourceConfig` (providing `stac_url`) and a `LayerConfig` (providing `geotiff_product` and bounding box) and use them to drive the query and download process.

#### Scenario: Download from config objects

- **WHEN** `GeoTIFFDownloader.run(source_config, layer_config, cache_dir)` is called with a source of `type: geotiff` and a layer with a `geotiff_product` and `bounds`
- **THEN** it queries the STAC API using `source_config.stac_url`, `layer_config.geotiff_product`, and the layer bounds, downloads all matching GeoTIFF assets to the cache, and returns a list of local file paths

#### Scenario: Wrong source type raises error

- **WHEN** `GeoTIFFDownloader.run(source_config, layer_config, cache_dir)` is called with a source config where `type` is not `geotiff`
- **THEN** it raises a `ValueError` indicating the source type is not supported by the GeoTIFF downloader
