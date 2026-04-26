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
Each raster tile in RGN2 SHALL be preceded by a polyline preamble: `0x06 0xB3` (type=subtype) followed by 16 bytes of bitstream encoding the tile's geographic extent as coordinate deltas from the subdivision center. The subtype 0xB3 encodes: bits 0-4 = 0x13 (raster subtype), bit 5 = 1 (has label pointer), bit 7 = 1 (has class fields → triggers raster info read).

#### Scenario: Preamble type and subtype bytes
- **WHEN** writing a polyline preamble for a raster tile
- **THEN** the first two bytes SHALL be `0x06 0xB3`

#### Scenario: Preamble bitstream encodes tile extent
- **WHEN** writing the 16-byte bitstream for a tile at (lat_min, lon_min)-(lat_max, lon_max) within a subdivision centered at (center_lat, center_lon)
- **THEN** the bitstream SHALL encode the tile corners as coordinate deltas from the center in Garmin 24-bit map units, matching the format that GPXSee's DeltaStream parser expects

### Requirement: E0 record format
Each raster tile SHALL have an E0 record following its polyline preamble. The format SHALL be: marker(1)=0xE0 + bits_field(1) + image_index(variable) + top(uint32) + right(uint32) + bottom(uint32) + left(uint32) + block_size(uint32). Coordinates SHALL be in Garmin 32-bit signed map units (degrees * 2^31 / 180).

#### Scenario: E0 record with 16-bit image index
- **WHEN** the total number of tiles requires 16-bit image indices
- **THEN** bits_field SHALL be 0x2D and image_index SHALL be encoded as uint16 LE, producing a 24-byte record

#### Scenario: Coordinate order in E0 record
- **WHEN** writing an E0 record for a tile with bounds (lat_max, lon_max, lat_min, lon_min)
- **THEN** the coordinate order SHALL be: top=lat_max, right=lon_max, bottom=lat_min, left=lon_min in Garmin 32-bit units
