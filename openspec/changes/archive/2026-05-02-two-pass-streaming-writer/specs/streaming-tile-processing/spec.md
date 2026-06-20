## MODIFIED Requirements

### Requirement: Tiles processed in batches, not all at once

The system SHALL process tiles in configurable batches rather than loading all tiles into memory simultaneously. Batches SHALL be processed in parallel using `ProcessPoolExecutor` during the write pass of the IMG writer, not during a separate pipeline processing stage. The pipeline stage SHALL produce only `TileMetadata` (no JPEG data), and JPEG processing SHALL happen during the write pass.

#### Scenario: Default batch size

- **WHEN** the system writes tiles with default settings
- **THEN** tiles SHALL be written in batches of 500 tiles per batch
- **AND** only one batch's worth of JPEG data SHALL be in memory at a time

#### Scenario: ProcessPoolExecutor used during write pass

- **WHEN** the system writes a batch of tiles
- **THEN** it SHALL use `concurrent.futures.ProcessPoolExecutor` with `min(cpu_count, 8)` workers
- **AND** each worker SHALL read the source JPEG, warp to EPSG:4326, and return JPEG bytes for writing

#### Scenario: Memory footprint bounded

- **WHEN** processing 197,000 tiles with batch size 500
- **THEN** peak memory for tile data SHALL be approximately `500 × 25KB ≈ 12MB` per batch
- **AND** memory usage SHALL NOT grow proportionally to total tile count

#### Scenario: Small tile count uses single process

- **WHEN** processing fewer than 100 tiles in a batch
- **THEN** the system MAY use a single process to avoid ProcessPoolExecutor startup overhead

### Requirement: Stream tiles directly from cache as JPEG bytes

When the source CRS matches the target CRS (EPSG:4326), the system SHALL read tiles as raw JPEG bytes without decoding during the write pass. When reprojection is needed, the system SHALL warp in-process via rasterio during the write pass and output JPEG bytes directly without writing a TIFF intermediate to disk.

#### Scenario: CRS match — JPEG pass-through during write

- **WHEN** a source tile is already in EPSG:4326 and the target quality matches the source quality
- **THEN** the system SHALL read the raw JPEG bytes from cache and write them directly to the IMG file
- **AND** no image decoding or re-encoding SHALL occur

#### Scenario: CRS match — quality change required

- **WHEN** a source tile is in EPSG:4326 but the target quality differs
- **THEN** the system SHALL decode, re-encode at target quality, and write to IMG immediately

#### Scenario: Reprojection needed — in-process warp during write

- **WHEN** a source tile is in EPSG:3857 and needs reprojection to EPSG:4326
- **THEN** the system SHALL warp the tile in-process using rasterio and write JPEG bytes to the IMG file
- **AND** no TIFF file SHALL be written to disk at any point
