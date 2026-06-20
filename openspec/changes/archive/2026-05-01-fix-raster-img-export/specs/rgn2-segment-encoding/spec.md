## ADDED Requirements

### Requirement: Per-subdivision RGN2 segment boundaries
The RGN2 data section SHALL be organized as per-subdivision segments. Each subdivision with tiles SHALL have its RGN2 data (polyline preamble + E0 records) stored in a contiguous segment. The segment boundaries SHALL be defined by TRE7 offsets: subdivision N's segment spans from TRE7[N].offset to TRE7[N+1].offset within the RGN2 section.

#### Scenario: Subdivision with tiles has non-empty segment
- **WHEN** a subdivision contains raster tiles
- **THEN** its TRE7 entry SHALL have flag=0x00 and an offset pointing to the start of its polyline preamble + E0 records within RGN2

#### Scenario: Empty overview subdivision
- **WHEN** a subdivision has no tiles (overview level)
- **THEN** its TRE7 entry SHALL have flag=0x01 and offset=0

### Requirement: Polyline preamble encoding for raster tiles
Each raster tile in RGN2 SHALL be preceded by a polyline preamble: `0x06 0xB3` (type=subtype) followed by lon/lat header deltas (int16 LE each), an 8-byte DeltaStream bitstream encoding the tile extent, and a 3-byte label pointer. The subtype 0xB3 encodes: bits 0-4 = 0x13 (raster subtype), bit 5 = 1 (has label pointer), bit 7 = 1 (has class fields → triggers raster info read).

#### Scenario: Preamble type and subtype bytes
- **WHEN** writing a polyline preamble for a raster tile
- **THEN** the first two bytes SHALL be `0x06 0xB3`

#### Scenario: Header deltas position tile bottom-left
- **WHEN** writing the lon_delta and lat_delta header fields
- **THEN** lon_delta SHALL be `(tile_left_mu - subdiv_center_lon_mu) >> shift` and lat_delta SHALL be `(tile_bottom_mu - subdiv_center_lat_mu) >> shift`, where shift = `24 - level_number`
- **AND** these are encoded as int16 LE (signed 16-bit little-endian)

#### Scenario: DeltaStream bitstream encodes tile extent
- **WHEN** writing the 8-byte bitstream for a tile at (lat_min, lon_min)-(lat_max, lon_max) at a given level_number
- **THEN** the bitstream SHALL encode exactly 1 delta pair (tile width, tile height) in level-shifted map units
- **AND** the info byte (byte 0) SHALL contain lon_baseSize in low nibble, lat_baseSize in high nibble
- **AND** bits 1-7 SHALL contain: lon_sign(1)=0, lat_sign(1)=0, extended(1)=0, lon_delta(N bits), lat_delta(N bits) packed LSB-first
- **AND** N = bitSize(baseSize) where bitSize follows GPXSee's formula: baseSize<=9 → 2+baseSize+1, baseSize>9 → 2+2*baseSize-9+1

### Requirement: E0 record format
Each raster tile SHALL have an E0 record following its polyline preamble. The format SHALL be: marker(1)=0xE0 + bits_field(1) + image_index(variable) + top(uint32) + right(uint32) + bottom(uint32) + left(uint32) + block_size(uint32). Coordinates SHALL be in Garmin 32-bit signed map units (degrees * 2^31 / 180).

#### Scenario: E0 record with 16-bit image index
- **WHEN** the total number of tiles requires 16-bit image indices
- **THEN** bits_field SHALL be 0x2D and image_index SHALL be encoded as uint16 LE, producing a 24-byte record

#### Scenario: Coordinate order in E0 record
- **WHEN** writing an E0 record for a tile with bounds (lat_max, lon_max, lat_min, lon_min)
- **THEN** the coordinate order SHALL be: top=lat_max, right=lon_max, bottom=lat_min, left=lon_min in Garmin 32-bit units
