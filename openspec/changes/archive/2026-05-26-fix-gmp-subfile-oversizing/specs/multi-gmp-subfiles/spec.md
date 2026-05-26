## MODIFIED Requirements

### Requirement: Geographic band tile assignment
When splitting into multiple GMP subfiles, the system SHALL assign tiles to GMP subfiles based on geographic latitude bands. Tiles SHALL be sorted by center latitude and partitioned into contiguous bands, each fitting within the per-GMP target. Split decisions SHALL use quality-adjusted JPEG size estimates (not original source file sizes) to determine band boundaries.

#### Scenario: Tile partitioning by latitude with quality adjustment
- **WHEN** total map data has original JPEG sizes of 12 GB but quality 25 produces ~3.5 GB actual output
- **AND** MAX_GMP_SIZE is 600 MB
- **THEN** tiles are sorted by latitude and split into at least 6 bands
- **AND** each band's estimated size is computed using quality-adjusted JPEG sizes

#### Scenario: Band size respects limit
- **WHEN** tiles are assigned to bands using quality-adjusted estimates
- **THEN** each band's estimated size (JPEG data + headers + RGN2 + LBL28 + LBL29) is under MAX_GMP_SIZE (600 MB)

#### Scenario: Quality 100 uses original sizes
- **WHEN** JPEG quality is 100 (or None for passthrough)
- **THEN** the quality ratio is 1.0 and split estimates use original JPEG sizes unchanged

#### Scenario: Small map uses single GMP
- **WHEN** building a map whose total quality-adjusted data fits within MAX_GMP_SIZE
- **THEN** the system writes one `.img` file with a single GMP subfile (existing behavior unchanged)

### Requirement: Multiple GMP subfiles in single IMG file
The export system SHALL write multiple GMP subfiles within a single IMG file when the total map data exceeds `MAX_GMP_SIZE` (600 MB). Each GMP subfile SHALL have a unique 8-byte FAT name and contain its own TRE/RGN/LBL/NET sub-headers. The split decision SHALL be based on quality-adjusted estimated sizes.

#### Scenario: Large map produces single IMG with multiple GMPs
- **WHEN** building a map whose total quality-adjusted data exceeds MAX_GMP_SIZE (600 MB)
- **THEN** the system writes one `.img` file containing multiple GMP subfiles, each under MAX_GMP_SIZE

#### Scenario: Split uses quality-adjusted estimates
- **WHEN** building a map with JPEG quality 25 and original JPEG sizes of 12 GB
- **THEN** the split decision uses quality-adjusted estimated sizes (~3.5 GB), not original sizes (12 GB)
- **AND** the number of GMP subfiles reflects the actual output size, not the inflated original size
