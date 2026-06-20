## ADDED Requirements

### Requirement: Pre-warp using gdalwarp CLI

The system SHALL use the `gdalwarp` CLI tool (invoked via `subprocess`) to pre-warp GeoTIFFs from their source CRS to EPSG:4326 with palette expansion to RGB. The system SHALL NOT use rasterio's `reproject()` for the warp operation.

#### Scenario: Pre-warp a paletted GeoTIFF with CRS transform

- **WHEN** a paletted GeoTIFF in a non-4326 CRS (e.g. EPSG:21781) needs pre-warping
- **THEN** the system SHALL invoke `gdalwarp` with `-t_srs EPSG:4326 -expand rgb` flags
- **AND** output SHALL be a 3-band uint8 RGB GeoTIFF with LZW compression and 256x256 tiling
- **AND** the output file SHALL be named `{source_stem}_4326.tif` in the same directory as the source

#### Scenario: Pre-warp a non-paletted GeoTIFF

- **WHEN** a non-paletted GeoTIFF (already RGB) needs CRS transformation
- **THEN** the system SHALL invoke `gdalwarp` with `-t_srs EPSG:4326` (no `-expand rgb`)
- **AND** output SHALL be a 3-band uint8 RGB GeoTIFF with LZW compression and 256x256 tiling

#### Scenario: Source already in EPSG:4326 and RGB

- **WHEN** a source GeoTIFF is already in EPSG:4326 and is 3-band RGB (not paletted)
- **THEN** the system SHALL skip pre-warping entirely
- **AND** the source path SHALL be returned as-is

#### Scenario: Cached pre-warp is reused

- **WHEN** a `{source_stem}_4326.tif` file already exists with mtime >= source file mtime
- **THEN** the system SHALL skip pre-warping and return the cached path

#### Scenario: gdalwarp failure

- **WHEN** `gdalwarp` exits with a non-zero return code
- **THEN** the system SHALL raise an error with the captured stderr output
- **AND** the system SHALL NOT delete the source file

### Requirement: VRT-based mosaic assembly

The system SHALL create a GDAL VRT (Virtual Raster Table) to merge pre-warped GeoTIFFs instead of a physical mosaic file. The VRT SHALL be created using the `gdalbuildvrt` CLI tool.

#### Scenario: Multiple pre-warped files merged into VRT

- **WHEN** more than one pre-warped GeoTIFF exists for a layer
- **THEN** the system SHALL invoke `gdalbuildvrt` to create a `mosaic.vrt` file referencing all pre-warped files
- **AND** the VRT file SHALL be a few KB in size (XML only, no pixel data)
- **AND** no physical mosaic GeoTIFF SHALL be created

#### Scenario: Single pre-warped file

- **WHEN** only one pre-warped GeoTIFF exists for a layer
- **THEN** the system SHALL skip VRT creation and use the single file directly

#### Scenario: VRT freshness check

- **WHEN** a `mosaic.vrt` already exists
- **AND** the VRT mtime >= all referenced source file mtimes
- **THEN** the system SHALL skip VRT creation and reuse the existing VRT

#### Scenario: VRT is readable by rasterio

- **WHEN** a VRT has been created
- **THEN** `rasterio.open("mosaic.vrt")` SHALL succeed and present the merged dataset as a single raster
- **AND** windowed reads SHALL return correct pixel data from the underlying GeoTIFFs

### Requirement: Post-warp cleanup of original files

The system SHALL delete original (source) GeoTIFF files after successful pre-warping and replace them with a JSON metadata file for cache invalidation.

#### Scenario: Original deleted after successful warp

- **WHEN** a source GeoTIFF has been successfully pre-warped to `{stem}_4326.tif`
- **THEN** the system SHALL delete the original `.tif` file
- **AND** the system SHALL write a `{stem}.json` file containing `{item_id, url, size, etag, last_modified}`
- **AND** the `{stem}_4326.tif` file SHALL be preserved

#### Scenario: Original preserved on warp failure

- **WHEN** pre-warping fails for a source GeoTIFF
- **THEN** the system SHALL NOT delete the original file

### Requirement: RAM usage bounded for pre-warp and mosaic

The system SHALL NOT allocate the full mosaic output as a single in-memory array. Peak RAM usage during pre-warping and mosaic assembly SHALL remain under 1GB regardless of geographic area size.

#### Scenario: Full Switzerland build at 10m resolution

- **WHEN** pre-warping and merging GeoTIFFs covering all of Switzerland at 10m resolution
- **THEN** peak Python process RAM SHALL NOT exceed 1GB
- **AND** individual file warps SHALL be handled by `gdalwarp` (which manages its own memory via `-wm` flag)
- **AND** mosaic assembly SHALL produce only a small XML file
