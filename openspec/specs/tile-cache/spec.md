## ADDED Requirements

### Requirement: Two-tier cache structure

The system SHALL maintain two separate cache tiers: a download cache for raw source tiles and a reprojection cache for tiles that have been warped to EPSG:4326. Both caches SHALL be organized by source, zoom level, and tile coordinates.

#### Scenario: Download cache structure

- **WHEN** tiles are downloaded from a WMTS source
- **THEN** they SHALL be stored at `cache/{source_id}/{zoom}/{x}/{y}.{format}` (e.g., `cache/swisstopo/20/420/280.jpeg`)
- **AND** a world file (`.jgw` or `.pgw`) SHALL accompany each tile for georeferencing

#### Scenario: Reprojection cache structure

- **WHEN** a tile is reprojected from EPSG:3857 to EPSG:4326
- **THEN** the reprojected result SHALL be stored at `cache/{source_id}_4326/{zoom}/{x}/{y}.{format}`
- **AND** the reprojected tile SHALL include an updated world file reflecting the new projection

#### Scenario: Cache directory configuration

- **WHEN** the user specifies a custom cache directory via CLI or config
- **THEN** both cache tiers SHALL be created under that directory
- **AND** the default location SHALL be `.cartoload_cache/` relative to the project root

### Requirement: Cache invalidation based on source tile freshness

The reprojection cache SHALL detect when a source tile has been updated and invalidate the corresponding reprojected tile. Detection SHALL use file modification time (mtime) comparison.

#### Scenario: Source tile newer than cached reprojection

- **WHEN** a source tile's mtime is newer than the corresponding reprojected tile's mtime
- **THEN** the system SHALL re-reproject the source tile and overwrite the stale cache entry

#### Scenario: Source tile unchanged

- **WHEN** a source tile's mtime is older than or equal to the reprojected tile's mtime
- **THEN** the system SHALL use the cached reprojected tile without re-running reprojection

### Requirement: Cache size management

The system SHALL provide a mechanism to inspect and clean the cache. A `cartoload cache` CLI subcommand SHALL be available.

#### Scenario: Cache status

- **WHEN** the user runs `cartoload cache status`
- **THEN** the system SHALL report total cache size, number of tiles in download cache, and number of tiles in reprojection cache, broken down by source

#### Scenario: Cache clean

- **WHEN** the user runs `cartoload cache clean`
- **THEN** the system SHALL remove all cached tiles (both download and reprojection)
- **AND** the user MAY specify `--source` to clean only a specific source's cache
- **AND** the user MAY specify `--reprojection-only` to clean only the reprojection cache

### Requirement: Skip reprojection for EPSG:4326 sources

The system SHALL NOT create reprojection cache entries for tiles that are already in EPSG:4326. These tiles SHALL be used directly from the download cache.

#### Scenario: Source already in EPSG:4326

- **WHEN** a source's CRS is declared as EPSG:4326 in the config
- **THEN** no reprojection cache SHALL be created for that source
- **AND** the download cache tiles SHALL be used directly in the fast pipeline
