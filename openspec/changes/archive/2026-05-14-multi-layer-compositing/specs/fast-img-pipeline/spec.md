## MODIFIED Requirements

### Requirement: Direct tile-to-IMG pipeline replaces GeoTIFF intermediate

The system SHALL use a direct pipeline that reads tiles from cache and writes IMG output without ever creating an intermediate GeoTIFF. The old pipeline (VRT → gdalwarp → gdaladdo → gdal_translate × N) is eliminated entirely.

#### Scenario: Build with cached tiles

- **WHEN** the user runs `cartoload build` and all tiles for the requested zoom levels and bounds are already in the cache directory
- **THEN** the system SHALL read tiles directly from cache, reproject per-tile if needed, and write IMG output
- **AND** no `gdalbuildvrt`, `gdalwarp`, `gdaladdo`, or `gdal_translate` SHALL be invoked

#### Scenario: Build with some tiles missing

- **WHEN** the user runs `cartoload build` and some tiles are missing from cache
- **THEN** the system SHALL download missing tiles first, then proceed with the direct pipeline
- **AND** no GeoTIFF intermediate SHALL ever be created

#### Scenario: Build a composite layer with cached tiles

- **WHEN** the user runs `cartoload build` for a layer that has a `layers` sub-field (composite layer) and tiles for all sub-layers are cached
- **THEN** the system SHALL download tiles from each sub-layer's source independently, composite them per tile position, and write the composited result to IMG
- **AND** no GeoTIFF intermediate SHALL ever be created

#### Scenario: Build a composite layer with tiles missing from some sub-layers

- **WHEN** the user runs `cartoload build` for a composite layer and some sub-layers have missing tiles at certain positions
- **THEN** the system SHALL download available tiles, composite the sub-layers that have tiles at each position, and write the result to IMG
- **AND** tile positions with no sub-layer tiles at all SHALL be skipped

### Requirement: Per-tile reprojection replaces monolithic gdalwarp

Instead of reprojecting the entire map area in one `gdalwarp` operation, the system SHALL reproject individual tiles. Each tile SHALL be warped from its source CRS (e.g., EPSG:3857) to EPSG:4326 independently.

#### Scenario: Source tiles in EPSG:3857

- **WHEN** cached tiles are in Web Mercator (EPSG:3857) projection
- **THEN** each tile SHALL be individually reprojected to EPSG:4326 before being written to the IMG
- **AND** the reprojection SHALL use the tile's world file (`.jgw` / `.pgw`) for georeferencing

#### Scenario: Source tiles already in EPSG:4326

- **WHEN** cached tiles are already in WGS84 (EPSG:4326) projection
- **THEN** the system SHALL skip reprojection entirely for those tiles
- **AND** tiles SHALL be read directly from cache and passed to the IMG writer

#### Scenario: Mixed CRS sources

- **WHEN** tiles from different sources use different CRS
- **THEN** each tile SHALL be checked individually and reprojected only if needed

#### Scenario: Composite layer with sub-layers in different CRS

- **WHEN** a composite layer has sub-layers where some use EPSG:3857 and others use EPSG:4326
- **THEN** each sub-layer's tiles SHALL be individually reprojected to EPSG:4326 before compositing
- **AND** compositing SHALL always occur in EPSG:4326 space

## ADDED Requirements

### Requirement: Composite pipeline stage

The pipeline SHALL support a compositing stage for layers with sub-layers. When a layer has a `layers` field, the pipeline SHALL download tiles from each sub-layer's source independently, then composite per tile position before exporting to IMG.

#### Scenario: Composite layer pipeline flow

- **WHEN** the pipeline processes a composite layer (has `layers` sub-field)
- **THEN** the pipeline SHALL:
  1. Resolve each sub-layer's source configuration
  2. Download tiles from each sub-layer's source (parallel across sub-layers where possible)
  3. For each tile position, load available sub-layer tiles, apply opacity, and alpha-composite bottom-to-top
  4. Encode composited tiles as JPEG
  5. Write to IMG via the existing streaming writer
- **AND** the output SHALL be a single IMG file containing the composited result

#### Scenario: Single-layer pipeline unchanged

- **WHEN** the pipeline processes a layer without a `layers` sub-field
- **THEN** the pipeline SHALL behave exactly as before (single source, no compositing)
- **AND** no compositing code path SHALL be triggered
