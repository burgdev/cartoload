## REMOVED Requirements

### Requirement: Two-tier cache structure
**Reason**: The TIFF reprojection cache is no longer needed. In-process rasterio warp at ~2.4ms/tile makes re-warping fast enough that caching costs more than it saves (TIFF files are 114x larger than source JPEG). Only the download cache for source tiles remains.
**Migration**: The `cache/{source}_4326/` TIFF reprojection cache directory is no longer created or read. Existing cached TIFFs can be deleted. The download cache at `cache/{source_id}/{zoom}/{x}/{y}.{format}` is unchanged.

### Requirement: Cache invalidation based on source tile freshness
**Reason**: Only applied to the reprojection cache, which is being removed. Source tile cache invalidation is handled by the download stage.
**Migration**: No action needed. Download cache freshness continues to work as before.

### Requirement: Cache size management
**Reason**: Only applied to the reprojection cache, which is being removed. Download cache management is unaffected.
**Migration**: No action needed.

## MODIFIED Requirements

### Requirement: Per-tile reprojection cached to disk
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
