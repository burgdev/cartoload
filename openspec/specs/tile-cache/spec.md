## ADDED Requirements

### Requirement: Download cache structure

The system SHALL maintain a download cache for raw source tiles, organized by source, zoom level, and tile coordinates.

#### Scenario: Download cache structure

- **WHEN** tiles are downloaded from a WMTS source
- **THEN** they SHALL be stored at `cache/{source_id}/{zoom}/{x}/{y}.{format}` (e.g., `cache/swisstopo/20/420/280.jpeg`)
- **AND** a world file (`.jgw` or `.pgw`) SHALL accompany each tile for georeferencing

#### Scenario: Cache directory configuration

- **WHEN** the user specifies a custom cache directory via CLI or config
- **THEN** the cache SHALL be created under that directory
- **AND** the default location SHALL be `.cartoload_cache/` relative to the project root

### Requirement: Per-tile reprojection performed in-process

The system SHALL reproject tiles in-process using rasterio without writing intermediate files to disk. No reprojection cache SHALL be maintained.

#### Scenario: Reprojection always performed in-process

- **WHEN** a tile requires reprojection from EPSG:3857 to EPSG:4326
- **THEN** the system SHALL warp the tile in-process via rasterio and return JPEG bytes
- **AND** no TIFF or other intermediate file SHALL be written to disk
- **AND** re-warping on subsequent builds is acceptable at ~2.4ms/tile

#### Scenario: No reprojection cache directory created

- **WHEN** the system processes tiles requiring reprojection
- **THEN** no `cache/{source}_4326/` directory SHALL be created
- **AND** no `.tif` files SHALL be written as reprojection intermediates

### Requirement: Skip reprojection for EPSG:4326 sources

The system SHALL NOT create reprojection cache entries for tiles that are already in EPSG:4326. These tiles SHALL be used directly from the download cache.

#### Scenario: Source already in EPSG:4326

- **WHEN** a source's CRS is declared as EPSG:4326 in the config
- **THEN** no reprojection SHALL occur for that source
- **AND** the download cache tiles SHALL be used directly in the fast pipeline
