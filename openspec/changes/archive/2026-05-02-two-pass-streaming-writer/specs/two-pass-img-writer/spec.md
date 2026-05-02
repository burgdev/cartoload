## ADDED Requirements

### Requirement: Tile metadata struct for layout-only computation

The system SHALL define a `TileMetadata` dataclass holding `(x, y, zoom, lat_min, lon_min, lat_max, lon_max, jpeg_size, source_path)` — all information needed for IMG layout computation without loading JPEG data into memory.

#### Scenario: TileMetadata computed from tile coordinates

- **WHEN** the system has tile coordinates (x, y) at zoom level z for an EPSG:3857 source
- **THEN** it SHALL compute geographic bounds deterministically using Web Mercator tile grid math
- **AND** it SHALL determine the JPEG file size from the source cache file via `os.path.getsize()`
- **AND** no JPEG data SHALL be loaded into memory during metadata computation

#### Scenario: TileMetadata for EPSG:4326 sources

- **WHEN** the source CRS is EPSG:4326
- **THEN** bounds SHALL be computed from tile coordinates using the standard `n = 2^zoom` formula
- **AND** the source JPEG SHALL be used directly without warping

### Requirement: Two-pass IMG writer architecture

The system SHALL split the IMG writer into two passes: a layout pass that uses only `TileMetadata`, and a stream-write pass that processes and writes JPEG data in batches.

#### Scenario: Layout pass produces complete file layout

- **WHEN** the system has `TileMetadata` for all tiles across all zoom levels
- **THEN** it SHALL generate spatial subdivisions, compute all section sizes and byte offsets, and produce a complete file layout
- **AND** the layout SHALL include per-tile write positions within the IMG file
- **AND** no JPEG data SHALL be loaded during the layout pass

#### Scenario: Write pass streams JPEG data in batches

- **WHEN** the layout pass is complete and the write pass begins
- **THEN** it SHALL process tiles in batches of ~500 tiles
- **AND** for each tile in a batch, it SHALL read the source JPEG, warp to EPSG:4326 if needed, and write to the IMG file at the pre-computed offset
- **AND** each batch's JPEG data SHALL be released before the next batch is processed
- **AND** only one batch of JPEG data SHALL be in memory at a time

#### Scenario: Output identical to non-streaming writer

- **WHEN** the two-pass writer produces an IMG file
- **THEN** the binary output SHALL be bit-for-bit identical to the output of the non-streaming writer for the same input tiles
- **AND** all validation tools (gmt, GPXSee) SHALL accept the file

### Requirement: Memory bounded regardless of tile count

Peak memory for the writer SHALL NOT exceed ~500 MB regardless of the number of tiles being written.

#### Scenario: 197K tile build memory usage

- **WHEN** writing 197,000 tiles across 9 zoom levels
- **THEN** peak memory SHALL be approximately 6 MB (metadata) + 12 MB (batch) + 400 MB (worker processes) ≈ 420 MB
- **AND** memory SHALL NOT grow proportionally to tile count

#### Scenario: 2M tile build memory usage

- **WHEN** writing 2,000,000 tiles (full-country build)
- **THEN** peak memory SHALL remain under 500 MB
- **AND** the build SHALL complete without out-of-memory errors on a machine with 8 GB RAM
