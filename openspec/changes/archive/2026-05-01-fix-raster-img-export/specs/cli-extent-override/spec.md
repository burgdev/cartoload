## ADDED Requirements

### Requirement: RGN2 per-subdivision segment parsing
The `cartoload analyze img info --rgn2` command SHALL parse RGN2 data per subdivision using TRE7 segment boundaries, displaying each subdivision's polyline preambles and E0 records separately.

#### Scenario: Display per-subdivision RGN2 records
- **WHEN** the user runs `cartoload analyze img info <file> --rgn2`
- **THEN** the output SHALL group RGN2 records by subdivision using TRE7 offsets as segment delimiters
- **AND** show which subdivision each polyline preamble and E0 record belongs to

### Requirement: TRE7/RGN2 consistency validation
The `cartoload analyze img info` command SHALL validate that TRE7 offsets form valid, non-overlapping RGN2 segments with no gaps between data subdivisions.

#### Scenario: Detect invalid TRE7 segment boundaries
- **WHEN** TRE7 offsets produce overlapping or gapped RGN2 segments
- **THEN** the analysis SHALL report a warning with the specific subdivisions involved

### Requirement: Section-level IMG comparison
The `cartoload analyze img compare` command SHALL support structured section comparison that normalizes for expected differences (map ID, dates, tile data) while highlighting structural differences in TRE, RGN, LBL headers and section layouts.

#### Scenario: Compare section structure between two IMG files
- **WHEN** the user runs `cartoload analyze img compare <ref.img> <our.img>`
- **THEN** the output SHALL show section-by-section structural comparison highlighting differences in header fields, section positions, record counts, and encoding parameters
