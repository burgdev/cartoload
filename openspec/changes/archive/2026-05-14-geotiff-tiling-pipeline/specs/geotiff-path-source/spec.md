## ADDED Requirements

### Requirement: GeoTIFF source references files by path or URL

The system SHALL accept `type: geotiff` sources where `urls` entries are local paths (relative to config file or absolute), HTTP URLs, or directory paths. Local files are used in-place; HTTP URLs are downloaded to cache.

#### Scenario: Local directory path

- **WHEN** a source config specifies `type: geotiff` with `urls: ["../cache/my_source/"]`
- **THEN** the system SHALL resolve the path relative to the config file
- **AND** scan the directory recursively for `.tif` and `.tiff` files
- **AND** use those files directly (no download)

#### Scenario: Local file paths

- **WHEN** a source config specifies `type: geotiff` with `urls: ["/data/tiles/a.tif", "/data/tiles/b.tif"]`
- **THEN** the system SHALL use those files directly

#### Scenario: Relative paths resolved from config file

- **WHEN** a source config at `/project/configs/sources/my.yaml` specifies `urls: ["../../geotiffs/"]`
- **THEN** the path SHALL resolve to `/project/geotiffs/`
- **AND** the system SHALL scan that directory for GeoTIFF files

#### Scenario: HTTP URLs downloaded to cache

- **WHEN** a source config specifies `type: geotiff` with `urls: ["https://example.com/tile1.tif", "https://example.com/tile2.tif"]`
- **THEN** the system SHALL download each URL to `cache/{source_id}/`
- **AND** already-cached files SHALL be skipped

#### Scenario: Mixed local and remote URLs

- **WHEN** a source config specifies both local paths and HTTP URLs
- **THEN** local files SHALL be used in-place
- **AND** HTTP URLs SHALL be downloaded to cache

#### Scenario: Non-existent local path

- **WHEN** a local path does not exist
- **THEN** the system SHALL raise a clear error indicating the path is invalid

#### Scenario: Directory with no GeoTIFF files

- **WHEN** a directory exists but contains no `.tif` or `.tiff` files
- **THEN** the system SHALL raise a clear error indicating no GeoTIFF files were found
