## ADDED Requirements

### Requirement: GMP container header format

The GMP subfile must start with a 53-byte container header containing the "GARMIN GMP" signature and section offsets to embedded sub-file headers.

#### Scenario: GMP header signature and version

- **WHEN** a GMP subfile is written
- **THEN** bytes 0x02-0x0B contain "GARMIN GMP" in ASCII
- **AND** bytes 0x0C-0x0D contain version 1 (uint16 LE)
- **AND** byte 0x00 contains header size 0x35 (53)
- **AND** byte 0x01 contains flag 0x00

#### Scenario: GMP creation date

- **WHEN** a GMP subfile is written
- **THEN** bytes 0x0E-0x14 contain a 7-byte creation date (year_LE(2)+month+day+hour+minute+second)

#### Scenario: Section table offsets

- **WHEN** a GMP subfile is written
- **THEN** bytes 0x15-0x18 contain the section table offset (uint32 LE, value 0x19)
- **AND** bytes 0x19-0x34 contain 7 uint32 LE section offsets pointing to embedded sub-file headers
- **AND** section[0] points to TRE sub-header offset within GMP data
- **AND** section[1] points to RGN sub-header offset within GMP data
- **AND** section[2] points to LBL sub-header offset within GMP data
- **AND** section[3] points to NET sub-header offset within GMP data
- **AND** sections[4-6] are zero (absent)

### Requirement: Copyright strings in GMP

The GMP container must include null-terminated copyright strings between the container header and the first sub-file header.

#### Scenario: Copyright strings placement

- **WHEN** a GMP subfile is written
- **THEN** null-terminated copyright strings are written starting at offset 0x35 (after container header)
- **AND** the strings end before the TRE sub-header offset

### Requirement: TRE sub-header format

The TRE sub-header must use the standard Garmin common header format (21 bytes) followed by TRE-specific fields including bounds, map levels, subdivisions, and display priority.

#### Scenario: TRE common header

- **WHEN** a TRE sub-header is written
- **THEN** the first 2 bytes are the header length (uint16 LE)
- **AND** bytes 2-11 contain "GARMIN TRE" in ASCII
- **AND** byte 12 is 1 (version)
- **AND** byte 13 is 0 (not locked)
- **AND** bytes 14-20 contain the 7-byte creation date

#### Scenario: TRE bounds in 3-byte map units

- **WHEN** a TRE sub-header is written
- **THEN** after the common header, 12 bytes contain bounds as 4 × 3-byte signed LE values
- **AND** the order is: max_lat, max_lon, min_lat, min_lon
- **AND** map units = degrees × 2^24 / 360

#### Scenario: TRE display priority

- **WHEN** a TRE sub-header is written for a raster map
- **THEN** the display priority is set to 24 (0x18)

#### Scenario: TRE map info strings

- **WHEN** a TRE sub-header is written
- **THEN** after the header fields, null-terminated "Raster Map" and copyright strings are written

### Requirement: RGN sub-header format

The RGN sub-header must use the standard common header format followed by data section info.

#### Scenario: RGN common header

- **WHEN** an RGN sub-header is written
- **THEN** the header length is 125 bytes
- **AND** the type string is "GARMIN RGN"
- **AND** after the common header, data section position and size are written as uint32 LE values

#### Scenario: RGN data section contains JPEG tiles

- **WHEN** a raster map GMP is written
- **THEN** the RGN data section contains all JPEG-encoded bitmap tiles concatenated sequentially

### Requirement: LBL sub-header format

The LBL sub-header must use the standard common header format followed by label section info.

#### Scenario: LBL common header

- **WHEN** an LBL sub-header is written
- **THEN** the type string is "GARMIN LBL"
- **AND** after the common header, label section position and size, offset multiplier, and encoding type are written

### Requirement: NET sub-header format

The NET sub-header must use the standard common header format with zero-valued section data.

#### Scenario: NET minimal stub

- **WHEN** a NET sub-header is written for a raster map
- **THEN** the type string is "GARMIN NET"
- **AND** all section sizes are zero

### Requirement: GMT validation passes

The generated IMG file must pass GMT validation with exit code 0.

#### Scenario: Single-tile IMG passes GMT

- **WHEN** an IMG file with 1 tile at 1 zoom level is generated
- **THEN** `gmt -i -v file.img` exits with code 0
- **AND** output shows correct map bounds, zoom levels, and bitmap count

#### Scenario: Multi-tile IMG passes GMT

- **WHEN** an IMG file with multiple tiles at multiple zoom levels is generated
- **THEN** `gmt -i -v file.img` exits with code 0
- **AND** output shows correct zoom level range and total bitmap count
