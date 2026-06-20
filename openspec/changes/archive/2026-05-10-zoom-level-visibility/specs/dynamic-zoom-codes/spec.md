## MODIFIED Requirements

### Requirement: Zoom codes computed dynamically from level count
The system SHALL compute Garmin TRE1 zoom codes dynamically based on the number and order of zoom levels. The 0x80 inherited flag SHALL be set only on levels at the top of the hierarchy that have no tiles (empty overview levels). The first level with actual tile data SHALL NOT have the inherited flag.

The numeric part of zoom codes SHALL descend from N-1 to 0. Inherited levels get `0x80 | (N-1-i)`, non-inherited levels get `N-1-i`.

#### Scenario: Three zoom levels [8, 10, 12] with tiles at all levels

- **WHEN** the exporter processes zoom levels [8, 10, 12] and all levels have tiles
- **THEN** the zoom codes SHALL be [0x02, 0x01, 0x00] (no inherited flag on any level)

#### Scenario: Eight zoom levels [8, 9, 11, 12, 13, 14, 15, 16] with empty levels 8 and 9

- **WHEN** the exporter processes zoom levels [8, 9, 11, 12, 13, 14, 15, 16]
- **AND** levels 8 and 9 have no tiles
- **THEN** the zoom codes SHALL be [0x87, 0x86, 0x05, 0x04, 0x03, 0x02, 0x01, 0x00]
- **AND** levels 0 and 1 (zoom 8, 9) SHALL have the 0x80 inherited flag
- **AND** level 2 (zoom 11, first with tiles) SHALL NOT have the 0x80 flag

#### Scenario: Five zoom levels [10, 12, 14, 16, 18] with tiles at all levels

- **WHEN** the exporter processes zoom levels [10, 12, 14, 16, 18] and all have tiles
- **THEN** the zoom codes SHALL be [0x04, 0x03, 0x02, 0x01, 0x00] (no inherited flag)

#### Scenario: Eight zoom levels with first level having tiles

- **WHEN** the exporter processes zoom levels [8, 9, 11, 12, 13, 14, 15, 16]
- **AND** level 8 HAS tiles
- **THEN** the zoom codes SHALL be [0x07, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01, 0x00]
- **AND** no level SHALL have the 0x80 inherited flag

#### Scenario: Single zoom level [12] with tiles

- **WHEN** the exporter processes a single zoom level [12] with tiles
- **THEN** the zoom code SHALL be [0x00] (no inherited flag)

#### Scenario: Mixed empty and non-empty levels with gap

- **WHEN** the exporter processes zoom levels [8, 10, 12, 14]
- **AND** levels 8 and 10 have no tiles but level 12 has tiles
- **THEN** the zoom codes SHALL be [0x83, 0x82, 0x01, 0x00]
- **AND** levels 0 and 1 (zoom 8, 10) SHALL have the 0x80 inherited flag
- **AND** level 2 (zoom 12, first with tiles) SHALL NOT have the 0x80 flag
