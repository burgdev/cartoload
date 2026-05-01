## MODIFIED Requirements

### Requirement: TRE7 extended section encoding
The TRE7 extended section SHALL use rec_size=5 with entries formatted as `[uint32_LE extPolygonsOffset][uint8 flag]`. The offsets SHALL represent per-subdivision RGN2 segment start positions. A sentinel entry (all zeros) SHALL follow the last subdivision's entry. Flag=0x01 for empty (overview) subdivisions, flag=0x00 for data subdivisions. Adjacent entries' offsets SHALL form segment boundaries: subdivision N's RGN2 data spans from offset[N] to offset[N+1].

#### Scenario: TRE7 offsets form valid segment boundaries
- **WHEN** a GMP subfile with subdivisions is written
- **THEN** each TRE7 entry's uint32 offset points to the start of that subdivision's polyline preamble within RGN2
- **AND** the next entry's offset marks the end of this subdivision's RGN2 data
- **AND** the sentinel entry terminates the offset chain

#### Scenario: SwissTopo rec_size=5 format
- **WHEN** raster tiles are present
- **THEN** TRE7 rec_size is 5 (uint32 offset + uint8 flag per entry)
- **AND** a sentinel entry of 5 zero bytes follows the last real entry

### Requirement: RGN sub-header polygon section
The RGN sub-header at offset 0x1D SHALL store the RGN2 section position and size as uint32 LE values. The extended polygon section fields (offsets 0x25-0x2C and surrounding non-zero fields visible in reference files) SHALL be populated to match the format that Garmin devices expect for extended polygon object parsing.

#### Scenario: RGN sub-header matches reference binary
- **WHEN** a GMP subfile is written for a raster map
- **THEN** the RGN sub-header non-zero bytes at offsets 0x25, 0x2D-0x33, 0x39-0x3B, 0x49, 0x4C-0x4E, 0x55-0x57, 0x65-0x66, 0x68-0x6C, 0x71-0x72, 0x79 SHALL match the patterns found in the SwissTopo reference RGN header

### Requirement: TRE2 subdivision records for raster maps
TRE2 subdivision records SHALL encode correct RGN2 segment offsets, center coordinates, width/height extents, and next-level links. The RGN offset field (3 bytes) SHALL point to the subdivision's first byte within RGN2 (matching the TRE7 offset for this subdivision).

#### Scenario: TRE2 rgn_offset matches TRE7 offset
- **WHEN** subdivisions are written for a raster map
- **THEN** each subdivision's TRE2 rgn_offset (3-byte LE) SHALL equal its TRE7 extPolygonsOffset value
