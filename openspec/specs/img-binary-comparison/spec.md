## ADDED Requirements

### Requirement: Compare IMG files structurally
The system SHALL compare two IMG files at the structural level, showing section positions, sizes, and counts with differences highlighted.

#### Scenario: Structural comparison shows section size difference
- **WHEN** comparing two IMG files where LBL29 size differs
- **THEN** output SHALL highlight the size difference with old vs new values

#### Scenario: Structural comparison shows matching files
- **WHEN** comparing two IMG files with identical structure
- **THEN** output SHALL indicate no structural differences found

### Requirement: Normalize temporal and random fields
The system SHALL normalize date stamps, map IDs, and random identifiers before comparison to reduce noise from non-structural differences.

#### Scenario: Dates are normalized before comparison
- **WHEN** comparing files with different creation dates
- **THEN** date fields SHALL be treated as equivalent

#### Scenario: Map IDs are normalized before comparison
- **WHEN** comparing files with different map IDs
- **THEN** map ID fields SHALL be treated as equivalent

### Requirement: Compare header fields byte-by-byte
The system SHALL compare TRE, RGN, and LBL sub-header bytes field-by-field, excluding normalized fields, and report differences with byte offsets.

#### Scenario: Header field difference is reported
- **WHEN** TRE headers differ in the display priority field
- **THEN** output SHALL show the field name, byte offset, and differing values

#### Scenario: Header fields match after normalization
- **WHEN** headers are identical except for dates
- **THEN** output SHALL indicate headers match after normalization

### Requirement: Sample data section comparison
The system SHALL compare sample records from RGN2 and LBL28 sections, showing first N records with byte-level differences.

#### Scenario: RGN2 record difference in coordinates
- **WHEN** first RGN2 record has different tile bounds
- **THEN** output SHALL show the record index and coordinate field differences

#### Scenario: LBL28 offset table matches
- **WHEN** first 10 LBL28 offset entries are identical
- **THEN** output SHALL indicate offset table sample matches

### Requirement: Configurable comparison depth
The system SHALL allow users to specify comparison depth via flags: --headers-only, --sample-size N, --full.

#### Scenario: Headers-only comparison skips data sections
- **WHEN** --headers-only flag is used
- **THEN** RGN2 and LBL28 data sections SHALL NOT be compared

#### Scenario: Custom sample size limits data comparison
- **WHEN** --sample-size 5 is specified
- **THEN** only first 5 records from each section SHALL be compared
