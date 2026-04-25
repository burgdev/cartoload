## ADDED Requirements

### Requirement: LBL29 section descriptor in LBL sub-header

The LBL sub-header SHALL include LBL29 section descriptor fields (position and size) at byte offsets 45-52 (8 bytes total: uint32 position + uint32 size, both little-endian).

#### Scenario: LBL sub-header contains LBL29 section info

- **WHEN** an LBL sub-header is written for a raster GMP subfile
- **THEN** bytes 45-48 SHALL contain LBL29 section position (uint32 LE, relative to LBL sub-header start)
- **THEN** bytes 49-52 SHALL contain LBL29 section size in bytes (uint32 LE)

### Requirement: LBL29 section contains concatenated JPEG files

The LBL29 section SHALL contain JPEG image files concatenated sequentially with no padding or delimiters between files.

#### Scenario: LBL29 stores JFIF JPEG format tiles

- **WHEN** JPEG tiles are written to LBL29
- **THEN** each tile SHALL be a valid JFIF JPEG file starting with marker `FFD8FFE0` followed by `JFIF`
- **THEN** tiles SHALL be concatenated with no padding bytes between files

#### Scenario: LBL29 size equals sum of JPEG sizes

- **WHEN** N JPEG tiles with sizes [s0, s1, s2, ..., sN-1] are written
- **THEN** LBL29 section size SHALL equal sum(s0 + s1 + s2 + ... + sN-1)

### Requirement: LBL29 JPEG ordering matches tile traversal order

The LBL29 section SHALL store JPEGs in the same order as tiles are traversed: sequentially by zoom level, then sequentially within each zoom level.

#### Scenario: Multi-zoom JPEG ordering

- **WHEN** a GMP has zoom levels [20, 21, 22] with tile counts [5, 10, 15]
- **THEN** LBL29 SHALL contain JPEGs in order: [zoom20_tile0, zoom20_tile1, ..., zoom20_tile4, zoom21_tile0, ..., zoom21_tile9, zoom22_tile0, ..., zoom22_tile14]

#### Scenario: LBL29 index alignment with LBL28

- **WHEN** LBL28 entry[i] contains offset O
- **THEN** reading LBL29 from byte offset O SHALL yield the i-th JPEG file's start marker (FFD8)

### Requirement: LBL29 section written after LBL28

The LBL29 section data SHALL be written immediately after the LBL28 section.

#### Scenario: LBL29 position relative to LBL28

- **WHEN** LBL28 section has position P and size S
- **THEN** LBL29 section position SHALL equal P + S

### Requirement: JPEG data moved from end-of-GMP to LBL29

The JPEG tile data currently written at the end of the GMP subfile (after tile index table) SHALL be moved to the LBL29 section.

#### Scenario: No JPEG data after LBL data sections

- **WHEN** the GMP subfile is written
- **THEN** no JPEG data SHALL appear after the LBL29 section
- **THEN** all JPEG tile data SHALL reside within the LBL29 section boundaries
