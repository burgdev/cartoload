## ADDED Requirements

### Requirement: Download GeoPackage from STAC endpoint
The system SHALL download `.gpkg.zip` assets from STAC collection items matching a bounding box.

#### Scenario: Download single GPKG item
- **WHEN** a source config has `type: gpkg` and a STAC URL pointing to a collection with `.gpkg.zip` assets
- **THEN** the system SHALL query the STAC collection for items matching the layer bounds, download the `.gpkg.zip` asset, and return the path to the extracted `.gpkg` file

#### Scenario: STAC item without GPKG asset
- **WHEN** a STAC item has no asset matching `application/x.geopackage+zip` media type or `.gpkg.zip` extension
- **THEN** the system SHALL skip that item and log a warning

#### Scenario: Multiple GPKG assets without filter
- **WHEN** a STAC item has multiple `.gpkg.zip` assets and no `asset_filter` is configured
- **THEN** the system SHALL raise an error indicating ambiguous assets

#### Scenario: Multiple items matching bbox
- **WHEN** the STAC query returns multiple items within the bounding box
- **THEN** the system SHALL download all matching items and return paths to all extracted `.gpkg` files

#### Scenario: No items matching bbox
- **WHEN** the STAC query returns no items for the given bounding box
- **THEN** the system SHALL log a warning and return an empty list

### Requirement: Extract GeoPackage from zip
The system SHALL extract the `.gpkg` file from the downloaded `.gpkg.zip` archive.

#### Scenario: Single GPKG in zip
- **WHEN** the downloaded zip contains one `.gpkg` file (at any path within the archive)
- **THEN** the system SHALL extract it to the cache directory and return its path

#### Scenario: Multiple GPKG files in zip
- **WHEN** the downloaded zip contains multiple `.gpkg` files
- **THEN** the system SHALL extract the first one found and log a warning about multiple files

#### Scenario: No GPKG in zip
- **WHEN** the downloaded zip contains no `.gpkg` file
- **THEN** the system SHALL raise an error indicating the archive has no GeoPackage

### Requirement: Cache downloaded GeoPackages
The system SHALL cache downloaded `.gpkg.zip` files and extracted `.gpkg` files in a cache directory structure consistent with existing STAC caching.

#### Scenario: Cache directory structure
- **WHEN** a GPKG is downloaded and extracted
- **THEN** the cache directory SHALL contain the `.zip` file, the extracted `.gpkg` file, and a `.json` metadata sidecar with ETag and Last-Modified headers

#### Scenario: Cached file reuse
- **WHEN** the same GPKG is requested again and the cached file exists with valid metadata
- **THEN** the system SHALL skip downloading and return the cached `.gpkg` path

#### Scenario: Offline mode uses cache
- **WHEN** offline mode is enabled and a cached `.gpkg` exists
- **THEN** the system SHALL return the cached path without network requests

### Requirement: Freshness checking for cached GeoPackages
The system SHALL check freshness of cached GPKG files via HTTP HEAD requests, consistent with existing STAC freshness logic.

#### Scenario: ETag match
- **WHEN** the cached metadata ETag matches the remote ETag
- **THEN** the system SHALL consider the file fresh and skip re-download

#### Scenario: ETag mismatch
- **WHEN** the cached metadata ETag does not match the remote ETag
- **THEN** the system SHALL re-download and re-extract the GPKG

#### Scenario: Freshness check not possible
- **WHEN** the remote server does not support HEAD or returns no cache headers
- **THEN** the system SHALL fall back to using the cached file

### Requirement: Asset type detection for GPKG
The system SHALL detect GPKG assets by media type and file extension.

#### Scenario: Detection by media type
- **WHEN** a STAC asset has `type: application/x.geopackage+zip`
- **THEN** the system SHALL identify it as a GPKG asset

#### Scenario: Detection by extension
- **WHEN** a STAC asset has an `href` ending in `.gpkg.zip`
- **THEN** the system SHALL identify it as a GPKG asset

#### Scenario: Asset filter support
- **WHEN** an `asset_filter` is configured on the source or layer
- **THEN** the system SHALL only consider GPKG assets whose properties match all filter key-value pairs
