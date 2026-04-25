## ADDED Requirements

### Requirement: IMG header heads field matches SwissTopo reference

The system SHALL write the `heads` field at IMG header offset 0x1A-0x1B as 256 (0x0100) for 32KB-block raster maps, matching the SwissTopo reference format.

#### Scenario: Building IMG with 32KB blocks

- **WHEN** the exporter writes an IMG file with block size 32768 (E1=9, E2=6)
- **THEN** the heads field at offset 0x1A-0x1B SHALL be 0x0100 (256)

### Requirement: IMG header MapSource flag is zero

The system SHALL write the MapSource flag at IMG header offset 0x0E as 0x00, matching the SwissTopo reference format.

#### Scenario: Writing IMG header

- **WHEN** the exporter writes an IMG header
- **THEN** byte at offset 0x0E SHALL be 0x00

### Requirement: TRE header flag byte matches SwissTopo reference

The system SHALL write the TRE header flag byte at offset 0x42 as 0x00, matching the SwissTopo reference format.

#### Scenario: Writing TRE sub-header

- **WHEN** the exporter writes the TRE sub-header
- **THEN** byte at TRE offset 0x42 SHALL be 0x00

### Requirement: RGN2 section starts directly with tile records

The system SHALL NOT write `0x0D` raster outline records at the start of each zoom level in RGN2 data. The RGN2 section SHALL start directly with `0x06` preamble + `0xE0` tile record pairs, matching the SwissTopo reference format.

#### Scenario: RGN2 data for a zoom level with 3 tiles

- **WHEN** the exporter writes RGN2 data for a zoom level containing 3 tiles
- **THEN** the data SHALL consist of 3 pairs of `0x06` preamble (18 bytes) + `0xE0` tile record (23-24 bytes), with no `0x0D` outline records

#### Scenario: RGN2 data across multiple zoom levels

- **WHEN** the exporter writes RGN2 data for multiple zoom levels
- **THEN** each zoom level SHALL consist of only `0x06`+`0xE0` pairs, concatenated directly without outline records or level separators

### Requirement: Polyline preambles contain coordinate data

The system SHALL populate the `0x06` polyline preamble bitstream with actual geographic coordinate data derived from the tile bounds, instead of all-zero bytes.

#### Scenario: Writing polyline preamble for a tile

- **WHEN** the exporter writes a polyline preamble for a tile at known coordinates
- **THEN** the preamble bitstream SHALL contain coordinate data representing the tile's geographic location
