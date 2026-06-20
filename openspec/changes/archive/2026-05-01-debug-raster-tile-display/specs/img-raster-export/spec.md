## ADDED Requirements

### Requirement: Export IMG raster tiles as GeoTIFF
The system SHALL extract JPEG tiles from an IMG file's LBL29 section, decode their geographic bounds from RGN2 records, and mosaic them into a georeferenced GeoTIFF.

#### Scenario: Export all tiles to GeoTIFF
- **WHEN** user runs `cartoload analyze img export input.img -o output.tif`
- **THEN** system SHALL create a GeoTIFF containing all tiles with proper WGS84 georeferencing

#### Scenario: Exported GeoTIFF has correct CRS
- **WHEN** GeoTIFF is exported
- **THEN** coordinate reference system SHALL be EPSG:4326 (WGS84)

#### Scenario: Tiles are placed at correct coordinates
- **WHEN** a tile in RGN2 has bounds (46.5°N, 7.0°E, 46.6°N, 7.1°E)
- **THEN** that tile SHALL appear at those coordinates in the exported GeoTIFF

### Requirement: Support bounding box filtering
The system SHALL allow users to export only tiles within a specified bounding box via --bbox flag.

#### Scenario: Bbox filtering excludes tiles outside bounds
- **WHEN** --bbox "7.0,46.5,7.5,47.0" is specified
- **THEN** only tiles intersecting that bounds SHALL be exported

#### Scenario: Bbox with no matching tiles produces empty output
- **WHEN** --bbox specifies a region with no tiles
- **THEN** system SHALL report "No tiles found in specified bounds" and exit

### Requirement: Support zoom level filtering
The system SHALL allow users to export only tiles from specified zoom levels via --zoom flag.

#### Scenario: Export single zoom level
- **WHEN** --zoom 10 is specified
- **THEN** only tiles from zoom level 10 SHALL be exported

#### Scenario: Export zoom range
- **WHEN** --zoom "10-12" is specified
- **THEN** tiles from zoom levels 10, 11, and 12 SHALL be exported

### Requirement: Handle JPEG decoding errors gracefully
The system SHALL detect and report corrupted or invalid JPEG data in LBL29, skipping bad tiles and continuing export.

#### Scenario: Corrupted JPEG is skipped with warning
- **WHEN** a tile's JPEG data is corrupted
- **THEN** system SHALL log a warning with tile index and continue export

#### Scenario: All JPEGs corrupted produces error
- **WHEN** all tiles have corrupted JPEG data
- **THEN** system SHALL report "No valid tiles found" and exit with error code

### Requirement: Provide export statistics
The system SHALL report export statistics including tiles processed, tiles exported, output bounds, and resolution.

#### Scenario: Statistics show tile counts
- **WHEN** export completes successfully
- **THEN** output SHALL show "Exported N of M tiles"

#### Scenario: Statistics show output bounds
- **WHEN** export completes
- **THEN** output SHALL show the geographic bounds of the exported GeoTIFF

### Requirement: Validate RGN2-LBL28-LBL29 consistency
The system SHALL validate that the number of RGN2 records matches LBL28 entries and LBL29 has corresponding JPEG data for each tile.

#### Scenario: Inconsistent tile count is detected
- **WHEN** RGN2 has 100 records but LBL28 has 95 entries
- **THEN** system SHALL report a warning about inconsistent tile counts

#### Scenario: Missing JPEG data is detected
- **WHEN** LBL28 offset points beyond LBL29 size
- **THEN** system SHALL report error "JPEG data out of bounds for tile N"
