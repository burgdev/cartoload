## MODIFIED Requirements

### Requirement: Direct tile read from cache into IMG writer

The `TileExtractor` SHALL support reading tiles directly from the download cache (or reprojection cache) without requiring an intermediate GeoTIFF. When the fast path is active, the extractor SHALL read JPEG/PNG files from disk and return them as encoded bytes with geographic bounds, skipping the `gdal_translate` subprocess entirely.

#### Scenario: Read cached JPEG tile directly

- **WHEN** the fast path is active and a tile exists at `cache/swisstopo/20/420/280.jpeg`
- **THEN** the extractor SHALL read the file using PIL `Image.open()`, encode to JPEG at target quality, and return `(jpeg_bytes, (lat_min, lon_min, lat_max, lon_max))`
- **AND** NO `gdal_translate` subprocess SHALL be spawned

#### Scenario: Read cached PNG tile directly

- **WHEN** the fast path is active and a tile exists at `cache/source/18/100/200.png`
- **THEN** the extractor SHALL read the PNG, convert to JPEG at target quality, and return the encoded bytes with bounds

#### Scenario: Read cached PNG tile for compositing

- **WHEN** the compositing path is active and a PNG tile is needed for blending
- **THEN** the extractor SHALL read the PNG and return it as a PIL Image in RGBA mode (preserving transparency)
- **AND** the tile SHALL NOT be converted to JPEG at this stage (JPEG encoding happens after compositing)

#### Scenario: Tile bounds from world file

- **WHEN** the extractor reads a cached tile
- **THEN** the geographic bounds SHALL be read from the accompanying world file (`.jgw` for JPEG, `.pgw` for PNG)
- **AND** the bounds SHALL match the tile's actual geographic extent in EPSG:4326

### Requirement: Batch tile encoding with optional quality change

The system SHALL support re-encoding tiles at a different JPEG quality when specified. If the source quality matches the target quality, the system SHALL pass through the raw JPEG bytes without re-encoding.

#### Scenario: Quality matches — pass through

- **WHEN** the target quality matches the source tile quality (or quality is not specified)
- **THEN** the extractor SHALL return the raw JPEG bytes from cache without re-encoding
- **AND** zero image processing overhead SHALL be incurred

#### Scenario: Quality differs — re-encode

- **WHEN** the target quality is different from the source quality
- **THEN** the extractor SHALL decode the JPEG, re-encode at the target quality, and return the new bytes

#### Scenario: Composited tile encoding

- **WHEN** the compositing path produces an RGBA PIL Image
- **THEN** the system SHALL convert the image to RGB and encode as JPEG at the configured quality
- **AND** the alpha channel SHALL be discarded during the conversion
