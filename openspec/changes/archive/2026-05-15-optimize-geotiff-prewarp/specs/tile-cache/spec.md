## ADDED Requirements

### Requirement: STAC ETag-based staleness detection

The system SHALL use HTTP HEAD requests to check ETag and Last-Modified headers for STAC GeoTIFF assets before downloading. Cached items SHALL be validated against stored metadata to detect remote changes.

#### Scenario: HEAD request returns ETag matching cached value

- **WHEN** a STAC item has a cached `.json` metadata file with an `etag` field
- **AND** a HEAD request to the asset URL returns an `ETag` header matching the cached value
- **THEN** the system SHALL skip re-downloading the asset
- **AND** the system SHALL skip re-warping if the pre-warped file exists and is fresh

#### Scenario: HEAD request returns new ETag

- **WHEN** a STAC item has a cached `.json` metadata file with an `etag` field
- **AND** a HEAD request returns an `ETag` header that does NOT match the cached value
- **THEN** the system SHALL re-download the asset
- **AND** the system SHALL update the `.json` metadata with the new ETag
- **AND** the system SHALL re-warp the new file

#### Scenario: HEAD request returns Last-Modified but no ETag

- **WHEN** a HEAD request does not return an `ETag` header
- **AND** returns a `Last-Modified` header that matches the cached value
- **THEN** the system SHALL treat the item as unchanged and skip re-downloading

#### Scenario: HEAD request not supported (HTTP 405)

- **WHEN** a HEAD request to the asset URL returns HTTP 405
- **THEN** the system SHALL fall back to file-existence checking only (current behavior)
- **AND** the system SHALL log a debug message about the unsupported HEAD method

#### Scenario: New item with no cached metadata

- **WHEN** a STAC item has no cached `.json` metadata file
- **THEN** the system SHALL download the asset
- **AND** after successful download, SHALL issue a HEAD request to capture ETag/Last-Modified
- **AND** SHALL write the `.json` metadata file

## MODIFIED Requirements

### Requirement: Download cache structure

The system SHALL maintain a download cache for raw source tiles, organized by source, URL-path-derived cache key, zoom level, and tile coordinates. The cache key SHALL be produced by the following algorithm:

1. Strip scheme and host from the URL
2. Remove per-tile template variables (`${x}`, `${y}`, `${z}`, `${zoom}` and `$VAR` forms)
3. Split on `/`, remove empty segments, strip leading/trailing `.` from each segment
4. Append `extra` string if provided (for STAC asset filters)
5. Join segments with `-`
6. Replace `?` with `-`, `=` and `&` with `_`
7. Apply `urllib.parse.quote(safe="-_.")` for filesystem safety

For STAC sources, after successful pre-warping, the original `.tif` file SHALL be deleted and replaced with a `.json` metadata file. The pre-warped `{stem}_4326.tif` file SHALL be preserved. A `mosaic.vrt` file SHALL replace any physical mosaic.

#### Scenario: WMTS download cache structure with human-readable key

- **WHEN** tiles are downloaded from a WMTS source with URL template `https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/${z}/${x}/${y}.jpeg`
- **THEN** the cache key SHALL be `1.0.0-ch.swisstopo.pixelkarte-farbe-default-current-3857-jpeg`
- **AND** tiles SHALL be stored at `cache/{source_id}/1.0.0-ch.swisstopo.pixelkarte-farbe-default-current-3857-jpeg/{zoom}/{x}/{y}.{format}`
- **AND** a world file (`.jgw` or `.pgw`) SHALL accompany each tile for georeferencing

#### Scenario: STAC download cache structure with human-readable key

- **WHEN** GeoTIFF assets are downloaded from a STAC source with collection URL `https://data.geo.admin.ch/api/stac/v1/collections/ch.swisstopo.pixelkarte-farbe`
- **THEN** the cache key SHALL be `api-stac-v1-collections-ch.swisstopo.pixelkarte-farbe`
- **AND** assets SHALL be cached at `cache/{source_id}/api-stac-v1-collections-ch.swisstopo.pixelkarte-farbe/{item_id}.tif`
- **AND** if asset filters are provided as `extra`, the encoded filter SHALL be appended to the key

#### Scenario: STAC cache after pre-warping

- **WHEN** STAC GeoTIFFs have been downloaded and pre-warped
- **THEN** the cache directory SHALL contain `{item_id}_4326.tif` (pre-warped), `{item_id}.json` (metadata)
- **AND** the original `{item_id}.tif` SHALL NOT exist
- **AND** a `mosaic.vrt` file SHALL exist if more than one pre-warped file is present
- **AND** no `mosaic_4326.tif` physical mosaic SHALL exist

#### Scenario: Query-style URL encoding

- **WHEN** a WMTS URL uses query parameters (e.g. `.../wmts?SERVICE=WMTS&...&TILECOL=${x}`)
- **THEN** `?` SHALL be replaced with `-`
- **AND** `=` and `&` SHALL be replaced with `_`
- **AND** the resulting key SHALL be filesystem-safe

#### Scenario: Cache directory configuration

- **WHEN** the user specifies a custom cache directory via CLI or config
- **THEN** the cache SHALL be created under that directory
- **AND** the default location SHALL be `.cartoload_cache/` relative to the project root

#### Scenario: Cache key determinism

- **WHEN** the same URL template is processed multiple times
- **THEN** the system SHALL always produce the same cache key
- **AND** `https://` and `http://` prefixes SHALL be treated identically (both stripped with host)

#### Scenario: Per-tile template variables removed from key

- **WHEN** a URL template contains `${x}`, `${y}`, `${z}`, `${zoom}` (or `$x`, `$y`, `$z`, `$zoom`)
- **THEN** these variables SHALL be removed before encoding the cache key
- **AND** resulting empty path segments SHALL be removed (no empty segments between separators)
