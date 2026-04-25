## ADDED Requirements

### Requirement: LBL28 section descriptor in LBL sub-header

The LBL sub-header SHALL include LBL28 section descriptor fields (position and size) at byte offsets 37-44 (8 bytes total: uint32 position + uint32 size, both little-endian).

#### Scenario: LBL sub-header contains LBL28 section info

- **WHEN** an LBL sub-header is written for a raster GMP subfile
- **THEN** bytes 37-40 SHALL contain LBL28 section position (uint32 LE, relative to LBL sub-header start)
- **THEN** bytes 41-44 SHALL contain LBL28 section size in bytes (uint32 LE)

### Requirement: LBL28 section contains uint32 offset array

The LBL28 section SHALL contain an array of uint32 little-endian offsets, one entry per JPEG tile, stored sequentially with no padding.

#### Scenario: LBL28 array size matches tile count

- **WHEN** a GMP subfile contains N raster tiles across all zoom levels
- **THEN** LBL28 section SHALL contain exactly N uint32 entries
- **THEN** LBL28 section size SHALL equal N × 4 bytes

#### Scenario: LBL28 offsets point to LBL29 JPEGs

- **WHEN** LBL28 contains offset values
- **THEN** each offset SHALL be a byte offset relative to the start of the LBL29 section
- **THEN** offset[0] SHALL equal 0 (first JPEG starts at LBL29 beginning)
- **THEN** offset[i] SHALL equal the cumulative size of all JPEGs before index i

### Requirement: LBL28 offsets are cumulative JPEG sizes

The LBL28 offset array SHALL be computed as cumulative sizes of JPEG files in LBL29, with the first entry always 0.

#### Scenario: Computing LBL28 offsets for 3 JPEGs

- **WHEN** LBL29 contains JPEGs of sizes [880, 920, 1024] bytes
- **THEN** LBL28 SHALL contain offsets [0, 880, 1800] (0, 0+880, 0+880+920)

#### Scenario: LBL28 entry ordering matches LBL29 JPEG ordering

- **WHEN** tiles are ordered by zoom level (zoom 20, 21, 22, etc.)
- **THEN** LBL28 offset[0] SHALL reference the first JPEG in LBL29 (first tile of first zoom level)
- **THEN** LBL28 entries SHALL follow the same ordering as LBL29 JPEG storage

### Requirement: LBL28 section written after LBL labels

The LBL28 section data SHALL be written immediately after the LBL labels section, before the LBL29 section.

#### Scenario: LBL data layout order

- **WHEN** LBL data sections are written
- **THEN** the order SHALL be: LBL labels → LBL28 (image index) → LBL29 (image storage)
- **THEN** LBL28 position SHALL equal (LBL labels position + LBL labels size)
