## MODIFIED Requirements

### Requirement: export_from_tiles accepts tile metadata, not accumulated JPEG data

The `GarminImgExporter.export_from_tiles()` method SHALL accept tile metadata per zoom level instead of requiring the full `compressed_tiles` dict with all JPEG data in memory. It SHALL perform a two-pass write: layout from metadata, then stream-write JPEG data in batches.

#### Scenario: Export from tile metadata

- **WHEN** the exporter receives tile metadata for all zoom levels
- **THEN** it SHALL compute the complete file layout from metadata alone (subdivisions, section sizes, byte offsets)
- **AND** it SHALL stream-write JPEG data from source cache files in batches during the write pass
- **AND** the full `compressed_tiles` dict SHALL NOT be required

#### Scenario: Backward compatibility with compressed_tiles

- **WHEN** the exporter receives a `compressed_tiles` dict (legacy API)
- **THEN** it SHALL extract metadata from the tiles and proceed with the two-pass write
- **AND** the legacy API SHALL continue to work but log a deprecation warning

### Requirement: 4GB file splitting works with streaming writer

The `_write_with_splitting()` method SHALL work with the two-pass streaming writer, splitting large builds across multiple IMG files when the estimated size exceeds 4 GB.

#### Scenario: Size estimation from metadata

- **WHEN** the exporter estimates output file size to decide on splitting
- **THEN** it SHALL compute the estimate from tile metadata (JPEG sizes) without loading JPEG data
- **AND** the estimate SHALL be accurate to within 1% of the actual written size

#### Scenario: Multi-file split with streaming

- **WHEN** the estimated size exceeds 4 GB
- **THEN** the exporter SHALL assign zoom levels to files and write each file using the two-pass streaming approach
- **AND** each output file SHALL be independently valid
