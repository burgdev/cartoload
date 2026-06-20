## ADDED Requirements

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

### Requirement: Per-tile reprojection cached to disk

The system SHALL cache reprojected tiles to avoid repeating the warp operation on subsequent builds. The cache SHALL be stored in a separate directory from the download cache.

#### Scenario: Reprojected tile cache hit

- **WHEN** a tile has been previously reprojected and the reprojected version exists in the reprojection cache
- **THEN** the system SHALL read the cached reprojected tile instead of re-running `gdalwarp`
- **AND** the build SHALL proceed faster due to the cache hit

#### Scenario: Reprojected tile cache miss

- **WHEN** a tile has not been previously reprojected
- **THEN** the system SHALL reproject the tile, store the result in the reprojection cache, and continue

#### Scenario: Source tile updated

- **WHEN** the source tile in the download cache has been updated (newer mtime) after the reprojected version was cached
- **THEN** the system SHALL detect the stale cache entry and re-reproject the tile

### Requirement: No gdal_translate subprocess spawning per tile

The fast pipeline SHALL NOT spawn `gdal_translate` as a subprocess for each tile. Instead, the system SHALL read cached tile images directly using Python image libraries (PIL/Pillow, or optional libjpeg-turbo via `jpegtran` if available on the system).

#### Scenario: Direct tile read with PIL

- **WHEN** the fast path reads a cached JPEG tile
- **THEN** it SHALL use PIL/Pillow `Image.open()` to read the file directly, not `gdal_translate`

#### Scenario: Optional libjpeg-turbo acceleration

- **WHEN** `jpegtran` or `libjpeg-turbo` tools are available on the system PATH
- **THEN** the system MAY use them for faster JPEG operations (decode, transcode, quality change)
- **AND** if not available, the system SHALL fall back to PIL/Pillow without error

### Requirement: Performance target — IMG from cache in under 5 minutes for 30k tiles

The fast pipeline SHALL produce an IMG file from cached tiles in under 5 minutes for a map covering ~30,000 tiles (e.g., Switzerland at 1:25k with 5 zoom levels).

#### Scenario: Switzerland 1:25k from cache

- **WHEN** all ~30,000 tiles are already cached for a Switzerland 1:25k map with zoom levels [20-24]
- **THEN** the fast pipeline SHALL produce the IMG file in under 5 minutes
- **AND** this SHALL NOT include download time (tiles already cached)

#### Scenario: Large map — France 1:25k from cache

- **WHEN** all ~300,000 tiles are cached for a France 1:25k map
- **THEN** the fast pipeline SHALL produce the IMG file proportionally faster than the current pipeline
- **AND** the per-tile processing time SHALL remain under 10ms on average (excluding I/O wait)

### Requirement: Garmin IMG uses equirectangular (plate carrée) coordinate encoding

The system SHALL store tile geographic bounds using Garmin's linear degree coordinate system (`degrees × 2^31 / 180`). This is equirectangular / plate carrée — NOT Mercator projection. The Web Mercator math (`log(tan(lat) + 1/cos(lat))`) is used only for computing which source tiles to download from WMTS servers, not for coordinate storage in the IMG.

#### Scenario: Coordinate conversion is linear

- **WHEN** the system converts a latitude of 47.0° to Garmin coordinate units
- **THEN** the result SHALL be `int(47.0 * 2^31 / 180)` = 560,680,876
- **AND** NO trigonometric functions SHALL be applied during this conversion

#### Scenario: Source tile reprojection accounts for Mercator distortion

- **WHEN** a Web Mercator (EPSG:3857) tile is reprojected to EPSG:4326 for the IMG
- **THEN** the reprojected tile SHALL correctly account for the area distortion inherent in Mercator vs. equirectangular
- **AND** the resulting tile image SHALL be warped so that it renders correctly when stretched to fit its lat/lon bounding box linearly
