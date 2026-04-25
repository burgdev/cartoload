## ADDED Requirements

### Requirement: RGN data section contains Type E0 records

The RGN data section SHALL contain Type E0 records for each raster tile, replacing the current 1582 bytes of zeros.

#### Scenario: One Type E0 record per tile

- **WHEN** a GMP subfile contains N raster tiles across all zoom levels
- **THEN** the RGN data section SHALL contain exactly N Type E0 records

#### Scenario: Type E0 records replace zero-filled RGN data

- **WHEN** RGN data section is written
- **THEN** the section SHALL NOT contain zero-padding
- **THEN** the section SHALL contain sequential Type E0 records with no padding between records

### Requirement: Type E0 record binary format

Each Type E0 record SHALL follow the format: marker (1 byte) + bits_field (1 byte) + coordinates (4× uint32 LE) + block_size (uint32 LE) + image_index (variable).

#### Scenario: Type E0 record structure for tile with <256 total tiles

- **WHEN** a Type E0 record is written for a tile in a GMP with <256 total tiles
- **THEN** byte 0 SHALL be `0xE0` (Type E0 marker)
- **THEN** byte 1 SHALL be `0x2B` (bits_field for 8-bit index)
- **THEN** bytes 2-5 SHALL be lat_min (uint32 LE in Garmin map units)
- **THEN** bytes 6-9 SHALL be lon_min (uint32 LE in Garmin map units)
- **THEN** bytes 10-13 SHALL be lat_max (uint32 LE in Garmin map units)
- **THEN** bytes 14-17 SHALL be lon_max (uint32 LE in Garmin map units)
- **THEN** bytes 18-21 SHALL be block_size (uint32 LE, JPEG file size in bytes)
- **THEN** byte 22 SHALL be image_index (uint8, index into LBL28 array)
- **THEN** total record size SHALL be 23 bytes

#### Scenario: Type E0 record structure for tile with 256-65536 total tiles

- **WHEN** a Type E0 record is written for a tile in a GMP with ≥256 total tiles
- **THEN** byte 0 SHALL be `0xE0` (Type E0 marker)
- **THEN** byte 1 SHALL be `0x25` (bits_field for 16-bit index)
- **THEN** bytes 2-21 SHALL be coordinates and block_size (same as <256 case)
- **THEN** bytes 22-23 SHALL be image_index (uint16 LE, index into LBL28 array)
- **THEN** total record size SHALL be 24 bytes

### Requirement: bits_field encoding based on total tile count

The bits_field byte SHALL be set to `0x2B` for <256 tiles or `0x25` for 256-65536 tiles, determining the image_index field width.

#### Scenario: bits_field for small tile count

- **WHEN** total tiles across all zoom levels is less than 256
- **THEN** all Type E0 records SHALL use bits_field = `0x2B`
- **THEN** all Type E0 records SHALL use 1-byte (uint8) image_index

#### Scenario: bits_field for large tile count

- **WHEN** total tiles across all zoom levels is 256 or greater
- **THEN** all Type E0 records SHALL use bits_field = `0x25`
- **THEN** all Type E0 records SHALL use 2-byte (uint16 LE) image_index

### Requirement: Coordinate encoding uses 32-bit Garmin map units

Tile bounds in Type E0 records SHALL be encoded as 32-bit signed integers in Garmin map units (degrees × 2^31 / 180).

#### Scenario: Converting decimal degree bounds to Type E0 coordinates

- **WHEN** a tile has bounds lat_min=46.0°, lon_min=8.0°, lat_max=47.0°, lon_max=9.0°
- **THEN** lat_min SHALL be encoded as int(46.0 × 2^31 / 180) = 548,308,309 = `0x20AAAAAA` → bytes `AA AA AA 20`
- **THEN** coordinate values SHALL be written as uint32 little-endian

### Requirement: block_size field equals JPEG file size

The block_size field in each Type E0 record SHALL equal the size in bytes of the corresponding JPEG tile in LBL29.

#### Scenario: block_size matches LBL29 JPEG size

- **WHEN** JPEG tile i in LBL29 has size S bytes
- **THEN** Type E0 record for tile i SHALL have block_size = S (uint32 LE)

### Requirement: image_index references LBL28 entry

The image_index field in each Type E0 record SHALL be the zero-based index into the LBL28 offset array, pointing to the corresponding JPEG in LBL29.

#### Scenario: Sequential image indices for sequential tiles

- **WHEN** Type E0 records are written in tile order (zoom 20 tiles, then zoom 21 tiles, etc.)
- **THEN** Type E0 record 0 SHALL have image_index = 0 (references LBL28[0] → first JPEG in LBL29)
- **THEN** Type E0 record i SHALL have image_index = i (references LBL28[i])

#### Scenario: image_index alignment with LBL28/LBL29

- **WHEN** Type E0 record has image_index = i
- **THEN** LBL28[i] SHALL contain the byte offset to the corresponding JPEG in LBL29
- **THEN** reading LBL29 from offset LBL28[i] SHALL yield the JPEG file referenced by this Type E0 record

### Requirement: Type E0 records written in tile order

Type E0 records SHALL be written sequentially in the same order as tiles appear in LBL29: by zoom level, then by tile within each zoom level.

#### Scenario: Type E0 ordering matches JPEG ordering

- **WHEN** LBL29 contains JPEGs in order [zoom20_tile0, zoom20_tile1, zoom21_tile0]
- **THEN** RGN data SHALL contain Type E0 records in the same order: [E0_zoom20_tile0, E0_zoom20_tile1, E0_zoom21_tile0]
