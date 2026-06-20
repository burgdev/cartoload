## ADDED Requirements

### Requirement: Most-zoomed-out level with tiles is visible on devices
The system SHALL ensure that the most-zoomed-out zoom level containing actual tile data does NOT have the inherited flag (0x80) in its TRE1 zoom code, so that GPXSee and Garmin devices render tiles at that zoom scale.

#### Scenario: Map visible when zoomed out to overview scale
- **WHEN** a map is generated with zoom levels [8, 9, 11, 12, 13, 14, 15, 16]
- **AND** level 11 is the most-zoomed-out level with tiles (levels 8, 9 are empty)
- **THEN** the TRE1 record for level 11 SHALL NOT have the 0x80 bit set
- **AND** the map SHALL be visible on a Garmin device when zoomed out to the scale corresponding to level 11

#### Scenario: Map visible at most zoomed-out scale when all levels have tiles
- **WHEN** a map is generated with zoom levels [10, 12, 14]
- **AND** all levels have tiles
- **THEN** no TRE1 record SHALL have the 0x80 bit set
- **AND** the map SHALL be visible on a Garmin device at all zoom scales
