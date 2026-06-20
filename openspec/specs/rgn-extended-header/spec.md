## ADDED Requirements

### Requirement: RGN sub-header contains polygon section offset and size
The RGN sub-header SHALL store the polygon section offset at byte 0x1D and size at byte 0x21, matching the existing RGN2 position and size. These fields already exist in the current implementation.

#### Scenario: Polygon section matches RGN2
- **WHEN** the RGN sub-header is written with RGN2 at position P and size S
- **THEN** `_polygons.offset` (0x1D) SHALL be P and `_polygons.size` (0x21) SHALL be S

### Requirement: RGN sub-header contains polygon local flag bitmasks
The RGN sub-header SHALL store polygon local flag bitmasks at offsets 0x29 (global flags), 0x2D (local flags [0]), 0x31 (local flags [1]), and 0x35 (local flags [2]). These bitmasks tell the Garmin device which object types have local fields in the polygon section.

#### Scenario: Polygon local flags match reference pattern
- **WHEN** the RGN sub-header is written
- **THEN** the field at 0x29 SHALL be 0x00000000 (global flags)
- **AND** the field at 0x2D SHALL be 0x200000FF (local flags [0])
- **AND** the field at 0x31 SHALL be 0x0003FCFD (local flags [1])
- **AND** the field at 0x35 SHALL be 0x00000000 (local flags [2])

### Requirement: RGN sub-header contains lines section with offset, size, and flags
The RGN sub-header SHALL store the lines section offset at byte 0x39 and size at byte 0x3D, plus line local flag bitmasks at 0x45, 0x49, 0x4D, and 0x51.

#### Scenario: Lines section offset points past polygon data
- **WHEN** the RGN sub-header is written with polygon data ending at position END
- **THEN** `_lines.offset` (0x39) SHALL be END and `_lines.size` (0x3D) SHALL be 0

#### Scenario: Lines local flags match reference pattern
- **WHEN** the RGN sub-header is written
- **THEN** the field at 0x45 SHALL be 0x00000000
- **AND** the field at 0x49 SHALL be 0x2000003F
- **AND** the field at 0x4D SHALL be 0x00000FFD
- **AND** the field at 0x51 SHALL be 0x00000000

### Requirement: RGN sub-header contains points section with offset, size, and flags
The RGN sub-header SHALL store the points section offset at byte 0x55 and size at byte 0x59, plus point local flag bitmasks at 0x61, 0x65, 0x69, and 0x6D.

#### Scenario: Points section offset matches lines offset
- **WHEN** the RGN sub-header is written with lines offset L
- **THEN** `_points.offset` (0x55) SHALL be L and `_points.size` (0x59) SHALL be 0

#### Scenario: Points local flags match reference pattern
- **WHEN** the RGN sub-header is written
- **THEN** the field at 0x61 SHALL be 0x00000000
- **AND** the field at 0x65 SHALL be 0x200007FF
- **AND** the field at 0x69 SHALL be 0x003FF73F
- **AND** the field at 0x6D SHALL be 0x00000000

### Requirement: RGN sub-header contains dictionary section offset, size, and info
The RGN sub-header SHALL store the dictionary offset at byte 0x71 and size at byte 0x75, plus an info field at byte 0x79.

#### Scenario: Dictionary section is empty
- **WHEN** the RGN sub-header is written with lines offset L
- **THEN** `_dict.offset` (0x71) SHALL be L and `_dict.size` (0x75) SHALL be 0
- **AND** the info field at 0x79 SHALL be 0

### Requirement: RGN sub-header byte at 0x25 set to 2
The byte at offset 0x25 in the RGN sub-header SHALL be set to the value 2, matching both IOM and SwissTopo reference files.

#### Scenario: Byte 0x25 value
- **WHEN** the RGN sub-header is written
- **THEN** the byte at offset 0x25 SHALL be 0x02

### Requirement: RGN sub-header local flags stored as 4-byte little-endian uint32
All local flag fields in the RGN sub-header SHALL be encoded as 4-byte little-endian unsigned 32-bit integers.

#### Scenario: Flag field encoding
- **WHEN** writing a local flag value 0x200000FF at offset 0x2D
- **THEN** the bytes SHALL be FF 00 00 20
