## MODIFIED Requirements

### Requirement: Stream tiles directly from cache as JPEG bytes

When the source CRS matches the target CRS (EPSG:4326), the system SHALL read tiles from cache and re-encode them at the configured quality level before writing to the IMG file. When reprojection is needed, the system SHALL warp in-process via rasterio and encode to JPEG at the configured quality using PIL.

#### Scenario: CRS match — quality re-encoding

- **WHEN** a source tile is already in EPSG:4326 and the user specifies `--quality 50`
- **THEN** the system SHALL decode the cached JPEG, re-encode it at quality=50 using PIL, and write the re-encoded bytes to the IMG file
- **AND** the output file size SHALL reflect the specified quality level

#### Scenario: CRS match — high quality passthrough

- **WHEN** a source tile is already in EPSG:4326 and the user specifies `--quality 95` (at or above typical server quality)
- **THEN** the system SHALL decode the cached JPEG and re-encode it at quality=95
- **AND** the output SHALL be visually indistinguishable from the source

#### Scenario: Reprojection needed — quality applied via PIL

- **WHEN** a source tile is in EPSG:3857 and needs reprojection to EPSG:4326
- **THEN** the system SHALL warp the tile in-process using rasterio and encode JPEG bytes via PIL at the configured quality
- **AND** no TIFF file SHALL be written to disk at any point

#### Scenario: Quality default preserves existing behavior

- **WHEN** the user does not specify `--quality` (default 85)
- **THEN** the system SHALL re-encode tiles at quality=85
- **AND** output sizes SHALL be comparable to the current (broken) behavior since SwissTopo serves tiles at approximately Q85
