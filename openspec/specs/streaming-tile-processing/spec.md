## ADDED Requirements

### Requirement: Tiles processed in batches, not all at once

The system SHALL process tiles in configurable batches rather than loading all tiles into memory simultaneously. Each batch SHALL be processed (read from cache, reproject if needed, encode to JPEG, write to IMG) and then released before the next batch begins.

#### Scenario: Default batch size

- **WHEN** the system processes tiles with default settings
- **THEN** tiles SHALL be processed in batches of 500 tiles per batch
- **AND** only one batch's worth of raw tile data SHALL be in memory at a time

#### Scenario: Custom batch size

- **WHEN** the user specifies `--batch-size 1000`
- **THEN** tiles SHALL be processed 1000 at a time

#### Scenario: Memory footprint bounded

- **WHEN** processing 300,000 tiles with batch size 500
- **THEN** peak memory usage SHALL be approximately `500 tiles × ~200 KB/tile ≈ 100 MB` for tile data
- **AND** memory usage SHALL NOT grow proportionally to total tile count

### Requirement: Stream tiles directly from cache as JPEG bytes

When the source CRS matches the target CRS (EPSG:4326) or a reprojected tile exists in cache, the system SHALL read tiles as raw JPEG bytes without decoding to a numpy array. This avoids the memory and CPU cost of image decompression.

#### Scenario: CRS match — JPEG pass-through

- **WHEN** a source tile is already in EPSG:4326 and the target quality matches the source quality
- **THEN** the system SHALL read the raw JPEG bytes from cache and pass them directly to the IMG writer
- **AND** no image decoding or re-encoding SHALL occur

#### Scenario: CRS match — quality change required

- **WHEN** a source tile is in EPSG:4326 but the target quality differs
- **THEN** the system SHALL decode, re-encode at target quality, and discard the decoded data immediately

#### Scenario: Reprojection needed

- **WHEN** a source tile is in EPSG:3857 and must be reprojected to EPSG:4326
- **THEN** the system SHALL read the reprojected JPEG from cache (if cached) or perform per-tile reprojection and cache the result
- **AND** the reprojected JPEG bytes SHALL be passed directly to the IMG writer without further decoding

### Requirement: IMG writer accepts JPEG bytes, not numpy arrays

The `TileExtractor` / `TileEncoder` interface SHALL be updated so that the fast pipeline passes pre-encoded JPEG bytes directly to the IMG writer. The writer SHALL NOT require decompressed pixel data.

#### Scenario: Pre-encoded tiles bypass encoding step

- **WHEN** the pipeline has JPEG bytes ready (from cache pass-through or reprojection cache)
- **THEN** those bytes SHALL be written to the IMG file as-is
- **AND** the `TileEncoder.encode_tile()` step SHALL be skipped for that tile

#### Scenario: Mixed pre-encoded and raw tiles

- **WHEN** some tiles are available as JPEG bytes and others need encoding
- **THEN** the system SHALL handle both in the same batch without issue
