## ADDED Requirements

### Requirement: Spatial subdivision grid generation

The system SHALL divide the map area into a grid of geographic subdivisions at each zoom level. The number of subdivisions SHALL increase with zoom level detail (fewer for overview zooms, more for detailed zooms), matching the SwissTopo reference pattern.

#### Scenario: Single zoom level with few tiles

- **WHEN** the exporter processes a map with zoom level 15 and 625 tiles
- **THEN** the system SHALL generate multiple spatial subdivisions at that zoom level, each covering a subset of the tiles

#### Scenario: Multiple zoom levels

- **WHEN** the exporter processes zoom levels [6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
- **THEN** zoom level 6 SHALL have fewer subdivisions than zoom level 15
- **AND** the total subdivision count across all levels SHALL be greater than the number of zoom levels

### Requirement: Tile-to-subdivision assignment

The system SHALL assign each tile to exactly one subdivision based on its geographic extent. Tiles within a subdivision's geographic region SHALL be grouped together in the RGN2 data section.

#### Scenario: Tile falls within subdivision bounds

- **WHEN** a tile at position (lat=46.93, lon=7.51) is processed
- **THEN** the tile SHALL be assigned to the subdivision whose geographic region contains that position

#### Scenario: All tiles assigned

- **WHEN** 871 tiles are extracted across 10 zoom levels
- **THEN** every tile SHALL be assigned to exactly one subdivision
- **AND** the sum of tiles across all subdivisions SHALL equal 871

### Requirement: Per-subdivision TRE2 records

The system SHALL write one 16-byte TRE2 subdivision record per spatial subdivision. Each record SHALL contain the subdivision's center latitude and longitude (3-byte signed map units), the RGN2 byte offset for that subdivision's tile data, and the correct subdivision count and next-level index.

#### Scenario: Multiple subdivisions at one zoom level

- **WHEN** zoom level 15 has 100 subdivisions
- **THEN** 100 TRE2 records SHALL be written, each with its own center coordinates
- **AND** each record's RGN offset SHALL point to the correct position in the RGN2 data for that subdivision's tiles

#### Scenario: TRE2 center coordinates

- **WHEN** a subdivision covers the area from (lat=46.90, lon=7.40) to (lat=47.00, lon=7.60)
- **THEN** the TRE2 center latitude SHALL be approximately 46.95 degrees
- **AND** the TRE2 center longitude SHALL be approximately 7.50 degrees

### Requirement: Per-subdivision TRE7 entries

The system SHALL write one TRE7 entry per spatial subdivision. TRE7 rec_size SHALL be 5 (uint32 RGN2 offset + 1 flag byte) matching the SwissTopo reference format.

#### Scenario: TRE7 entry count matches subdivisions

- **WHEN** 100 spatial subdivisions are generated across all zoom levels
- **THEN** TRE7 SHALL contain exactly 100 entries

#### Scenario: TRE7 rec_size is 5

- **WHEN** the TRE7 descriptor is written
- **THEN** rec_size SHALL be 5 (uint32 offset + 1 flag byte)

### Requirement: Polyline preamble with coordinate data

The system SHALL encode actual geographic coordinate deltas in the polyline preamble bitstream (16 bytes after the `0x06 0xB3` marker) instead of all zeros. The preamble SHALL describe the subdivision's geographic extent using Garmin polyline coordinate encoding.

#### Scenario: Non-zero preamble data

- **WHEN** a subdivision covers a non-zero geographic area
- **THEN** the 16-byte preamble bitstream SHALL contain non-zero coordinate data representing the subdivision extent

#### Scenario: Preamble matches subdivision

- **WHEN** a subdivision has center at (lat=46.95, lon=7.50) and covers a 5km area
- **THEN** the preamble coordinate deltas SHALL reflect the subdivision's geographic extent relative to its center

### Requirement: RGN2 data grouped by subdivision

The system SHALL write RGN2 data grouped by spatial subdivision rather than by zoom level. Within each subdivision group, tiles SHALL be written as polyline preamble + Type E0 record pairs.

#### Scenario: Multiple subdivisions at one zoom level

- **WHEN** zoom level 15 has 3 subdivisions with [20, 30, 50] tiles respectively
- **THEN** the RGN2 data SHALL contain 3 groups of preamble+E0 pairs, one group per subdivision
- **AND** each group's byte offset SHALL match the corresponding TRE2 and TRE7 entry

### Requirement: TRE1 subdivision count reflects actual counts

The system SHALL write the actual number of spatial subdivisions per zoom level in the TRE1 map_levels data, not the hard-coded value 1.

#### Scenario: SwissTopo-like subdivision counts

- **WHEN** zoom level 14 has 156 spatial subdivisions
- **THEN** the TRE1 record for that level SHALL report subdiv_count=156
