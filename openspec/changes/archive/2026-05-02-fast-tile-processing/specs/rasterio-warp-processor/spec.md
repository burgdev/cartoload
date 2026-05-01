## ADDED Requirements

### Requirement: In-process tile reprojection via rasterio

The system SHALL reproject tiles from source CRS to EPSG:4326 using rasterio's `reproject()` function in-process, without spawning external processes. Output SHALL be JPEG bytes produced via rasterio's `MemoryFile` with the JPEG driver.

#### Scenario: EPSG:3857 to EPSG:4326 reprojection

- **WHEN** a source tile is in EPSG:3857 and the target CRS is EPSG:4326
- **THEN** the system SHALL open the source JPEG with rasterio, compute the target transform via `calculate_default_transform`, warp using `reproject()` with bilinear resampling, and write the output to a `MemoryFile` with JPEG driver
- **AND** the output SHALL be JPEG bytes with the configured quality setting
- **AND** no TIFF intermediate file SHALL be created on disk

#### Scenario: Source CRS matches target CRS

- **WHEN** the source CRS is already EPSG:4326
- **THEN** the system SHALL read the raw JPEG bytes from cache and pass them through without decoding or re-encoding
- **AND** no rasterio warp operation SHALL occur

#### Scenario: Quality parameter applied during warp output

- **WHEN** the user specifies `--quality 90` and reprojection is needed
- **THEN** the rasterio JPEG output SHALL use quality=90 via GDAL JPEG creation options
- **AND** the output file size SHALL reflect the specified quality level

### Requirement: Source georeferencing from tile coordinates

The system SHALL compute the source affine transform programmatically from tile coordinates (x, y, zoom) using standard Web Mercator tile grid math, instead of relying on world file sidecar files (.jgw/.pgw).

#### Scenario: EPSG:3857 tile transform computed from coordinates

- **WHEN** processing a tile at coordinates (x, y, zoom) from an EPSG:3857 source
- **THEN** the system SHALL compute the EPSG:3857 affine transform from the tile coordinates using Web Mercator projection math
- **AND** the transform SHALL produce the same geographic bounds as the equivalent world file

#### Scenario: EPSG:4326 tile bounds computed from coordinates

- **WHEN** processing a tile at coordinates (x, y, zoom) that is already in EPSG:4326
- **THEN** the system SHALL compute WGS84 bounds from tile coordinates using the standard `n = 2^zoom` tile grid formula
- **AND** the bounds SHALL be returned as `(lat_min, lon_min, lat_max, lon_max)`
