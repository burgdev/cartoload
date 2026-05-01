## MODIFIED Requirements

### Requirement: Tiles processed in batches, not all at once

The system SHALL process tiles in configurable batches rather than loading all tiles into memory simultaneously. Batches SHALL be processed in parallel using `ProcessPoolExecutor` (not `ThreadPoolExecutor`) because rasterio's warp operation holds the GIL. Each batch SHALL be reprojected, encoded to JPEG, and streamed to the IMG writer before the next batch begins.

#### Scenario: Default batch size

- **WHEN** the system processes tiles with default settings
- **THEN** tiles SHALL be processed in batches of 500 tiles per batch
- **AND** only one batch's worth of raw tile data SHALL be in memory at a time

#### Scenario: ProcessPoolExecutor used for parallelism

- **WHEN** the system processes a batch of tiles
- **THEN** it SHALL use `concurrent.futures.ProcessPoolExecutor` with `min(cpu_count, 8)` workers
- **AND** each worker SHALL independently open the source file, warp, and return JPEG bytes

#### Scenario: Memory footprint bounded

- **WHEN** processing 197,000 tiles with batch size 500
- **THEN** peak memory for tile data SHALL be approximately `500 × 25KB ≈ 12MB` per batch
- **AND** memory usage SHALL NOT grow proportionally to total tile count

#### Scenario: Small tile count uses single process

- **WHEN** processing fewer than 100 tiles in a batch
- **THEN** the system MAY use a single process to avoid ProcessPoolExecutor startup overhead

### Requirement: Stream tiles directly from cache as JPEG bytes

When the source CRS matches the target CRS (EPSG:4326), the system SHALL read tiles as raw JPEG bytes without decoding. When reprojection is needed, the system SHALL warp in-process via rasterio and output JPEG bytes directly without writing a TIFF intermediate to disk.

#### Scenario: CRS match — JPEG pass-through

- **WHEN** a source tile is already in EPSG:4326 and the target quality matches the source quality
- **THEN** the system SHALL read the raw JPEG bytes from cache and pass them directly to the IMG writer
- **AND** no image decoding or re-encoding SHALL occur

#### Scenario: CRS match — quality change required

- **WHEN** a source tile is in EPSG:4326 but the target quality differs
- **THEN** the system SHALL decode, re-encode at target quality, and discard the decoded data immediately

#### Scenario: Reprojection needed — in-process warp

- **WHEN** a source tile is in EPSG:3857 and needs reprojection to EPSG:4326
- **THEN** the system SHALL warp the tile in-process using rasterio and output JPEG bytes
- **AND** no TIFF file SHALL be written to disk at any point
- **AND** no `gdalwarp` subprocess SHALL be spawned
