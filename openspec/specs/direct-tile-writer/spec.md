## ADDED Requirements

### Requirement: Direct tile read from cache into IMG writer

The `TileExtractor` SHALL support reading tiles directly from the download cache (or reprojection cache) without requiring an intermediate GeoTIFF. When the fast path is active, the extractor SHALL read JPEG/PNG files from disk and return them as encoded bytes with geographic bounds, skipping the `gdal_translate` subprocess entirely.

#### Scenario: Read cached JPEG tile directly

- **WHEN** the fast path is active and a tile exists at `cache/swisstopo/20/420/280.jpeg`
- **THEN** the extractor SHALL read the file using PIL `Image.open()`, encode to JPEG at target quality, and return `(jpeg_bytes, (lat_min, lon_min, lat_max, lon_max))`
- **AND** NO `gdal_translate` subprocess SHALL be spawned

#### Scenario: Read cached PNG tile directly

- **WHEN** the fast path is active and a tile exists at `cache/source/18/100/200.png`
- **THEN** the extractor SHALL read the PNG, convert to JPEG at target quality, and return the encoded bytes with bounds

#### Scenario: Tile bounds from world file

- **WHEN** the extractor reads a cached tile
- **THEN** the geographic bounds SHALL be read from the accompanying world file (`.jgw` for JPEG, `.pgw` for PNG)
- **AND** the bounds SHALL match the tile's actual geographic extent in EPSG:4326

### Requirement: Tile bounds computed from world file

The system SHALL parse ESRI world files (`.jgw`, `.pgw`) to extract the geographic bounds of each cached tile. The world file format is 6 lines: pixel size X, rotation Y, rotation X, pixel size Y, top-left X, top-left Y.

#### Scenario: Parse world file for JPEG tile

- **WHEN** the extractor reads `cache/swisstopo/20/420/280.jgw`
- **THEN** it SHALL parse the 6 world file parameters and compute bounds:
  - `lon_min = line5 (top-left X)`
  - `lat_max = line6 (top-left Y)`
  - `lon_max = lon_min + (pixel_size_x × width)`
  - `lat_min = lat_max - abs(pixel_size_y) × height`
- **AND** return bounds as `(lat_min, lon_min, lat_max, lon_max)`

#### Scenario: Missing world file

- **WHEN** a tile file exists but its world file is missing
- **THEN** the extractor SHALL fall back to computing bounds from the tile grid math (Web Mercator tile coordinate to lat/lon)
- **AND** a warning SHALL be logged

### Requirement: Batch tile encoding with optional quality change

The system SHALL support re-encoding tiles at a different JPEG quality when specified. If the source quality matches the target quality, the system SHALL pass through the raw JPEG bytes without re-encoding.

#### Scenario: Quality matches — pass through

- **WHEN** the target quality matches the source tile quality (or quality is not specified)
- **THEN** the extractor SHALL return the raw JPEG bytes from cache without re-encoding
- **AND** zero image processing overhead SHALL be incurred

#### Scenario: Quality differs — re-encode

- **WHEN** the target quality is different from the source quality
- **THEN** the extractor SHALL decode the JPEG, re-encode at the target quality, and return the new bytes

### Requirement: Parallel tile reading with ThreadPoolExecutor

The fast path SHALL read tiles from cache in parallel using a `ThreadPoolExecutor`. The parallelism SHALL be I/O-bound (disk reads, not CPU), so thread count SHALL be configurable but default to `min(32, cpu_count * 4)`.

#### Scenario: Parallel cache reads for 30k tiles

- **WHEN** the fast path processes 30,000 cached tiles
- **THEN** tile reads SHALL be distributed across the thread pool
- **AND** the reading phase SHALL complete in under 60 seconds on SSD storage

#### Scenario: Sequential fallback on error

- **WHEN** parallel reading encounters repeated file system errors
- **THEN** the system MAY fall back to sequential reading to reduce contention
- **AND** a warning SHALL be logged
