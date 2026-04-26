## MODIFIED Requirements

### Requirement: Zoom codes computed dynamically from level count

The system SHALL compute Garmin TRE1 zoom codes dynamically based on the number and order of zoom levels, using the pattern: first level gets code `0x80 + (N-1)`, remaining levels count down from `N-2` to `0`. The TRE1 subdiv_count field SHALL reflect the actual number of spatial subdivisions at each level (not hard-coded 1).

#### Scenario: Three zoom levels [8, 10, 12]

- **WHEN** the exporter processes zoom levels [8, 10, 12]
- **THEN** the zoom codes SHALL be [0x82, 0x01, 0x00]
- **AND** each level's subdiv_count SHALL equal the number of spatial subdivisions generated for that level

#### Scenario: Five zoom levels matching SwissTopo [20, 21, 22, 23, 24]

- **WHEN** the exporter processes zoom levels [20, 21, 22, 23, 24]
- **THEN** the zoom codes SHALL be [0x84, 0x03, 0x02, 0x01, 0x00]

#### Scenario: Eight zoom levels matching IOM [17, 18, 19, 20, 21, 22, 23, 24]

- **WHEN** the exporter processes zoom levels [17, 18, 19, 20, 21, 22, 23, 24]
- **THEN** the zoom codes SHALL be [0x87, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01, 0x00]

#### Scenario: Single zoom level [12]

- **WHEN** the exporter processes a single zoom level [12]
- **THEN** the zoom code SHALL be [0x80]

### Requirement: Static zoom code mapping removed

The system SHALL NOT use a static dictionary mapping absolute zoom numbers to codes. The `_GARMIN_ZOOM_CODES` dictionary SHALL be removed.

#### Scenario: No static mapping dict exists

- **WHEN** the garmin_img module is loaded
- **THEN** there SHALL be no `_GARMIN_ZOOM_CODES` dictionary in the module scope

### Requirement: All Web Mercator zoom levels supported

The system SHALL support any valid Web Mercator zoom level (0-24) without requiring explicit registration in a lookup table.

#### Scenario: Zoom level 8 is included

- **WHEN** the user requests zoom levels [8, 10, 12]
- **THEN** zoom level 8 SHALL receive a valid computed zoom code (not default 0x00)
