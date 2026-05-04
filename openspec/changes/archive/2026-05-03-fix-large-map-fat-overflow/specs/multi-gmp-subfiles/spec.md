## ADDED Requirements

### Requirement: Multiple GMP subfiles in single IMG file
The export system SHALL write multiple GMP subfiles within a single IMG file when the total map data exceeds `MAX_GMP_SIZE` (~1.8 GB). Each GMP subfile SHALL have a unique 8-byte FAT name and contain its own TRE/RGN/LBL/NET sub-headers.

#### Scenario: Large map produces single IMG with multiple GMPs
- **WHEN** building a map whose total data exceeds MAX_GMP_SIZE
- **THEN** the system writes one `.img` file containing multiple GMP subfiles, each under MAX_GMP_SIZE

#### Scenario: Small map uses single GMP
- **WHEN** building a map whose total data fits within MAX_GMP_SIZE
- **THEN** the system writes one `.img` file with a single GMP subfile (existing behavior unchanged)

### Requirement: Geographic band tile assignment
When splitting into multiple GMP subfiles, the system SHALL assign tiles to GMP subfiles based on geographic latitude bands. Tiles SHALL be sorted by center latitude and partitioned into contiguous bands, each fitting within MAX_GMP_SIZE.

#### Scenario: Tile partitioning by latitude
- **WHEN** total map data is 5.5 GB (3× the 1.8 GB limit)
- **THEN** tiles are sorted by latitude and split into at least 3 bands, each containing tiles from a contiguous latitude range

#### Scenario: Band size respects limit
- **WHEN** tiles are assigned to bands
- **THEN** each band's estimated size (JPEG data + headers + RGN2 + LBL28 + LBL29) is under MAX_GMP_SIZE

### Requirement: Unique FAT name per GMP subfile
Each GMP subfile SHALL have a unique 8-byte ASCII name in the FAT. Names SHALL be derived from the map ID to be deterministic and unique within the IMG file.

#### Scenario: FAT name generation
- **WHEN** a map with map_id `0x09C102B0` needs 3 GMP subfiles
- **THEN** the FAT names are distinct (e.g. `09C102B0`, `09C102B1`, `09C102B2`)

### Requirement: Full map bounds per GMP subfile
Each GMP subfile SHALL contain the full map bounds in its TRE header, not just the geographic band's range. This ensures GPXSee's zoom level filtering works correctly across all GMP subfiles.

#### Scenario: Bounds in all GMP subfiles
- **WHEN** Switzerland is split into 3 latitude bands
- **THEN** each of the 3 GMP subfiles has TRE bounds covering all of Switzerland (5.96°E–10.49°E, 45.82°N–47.81°N)

### Requirement: One MPS subfile shared across GMPs
The IMG file SHALL contain a single MPS subfile (not one per GMP). The MPS contains the mapset metadata and does not need to be duplicated.

#### Scenario: MPS section count
- **WHEN** an IMG file contains 3 GMP subfiles
- **THEN** it has exactly 1 MPS FAT entry (not 3)
