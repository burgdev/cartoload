## ADDED Requirements

### Requirement: Validate Web Mercator to WGS84 conversion
The system SHALL verify that Web Mercator tile bounds are correctly converted to WGS84 decimal degrees when computing tile geographic bounds.

#### Scenario: Web Mercator tile bounds converted correctly
- **WHEN** a tile at zoom 10, x=512, y=350 is extracted
- **THEN** its WGS84 bounds SHALL match the standard Web Mercator formula for that tile

#### Scenario: Polar region Web Mercator clipping
- **WHEN** a tile extends beyond ±85.0511° latitude
- **THEN** bounds SHALL be clipped to Web Mercator valid range

### Requirement: Validate Garmin 32-bit map unit encoding
The system SHALL validate that WGS84 decimal degrees are correctly encoded as Garmin 32-bit signed integers using the formula: `int(deg * 2^31 / 180)`.

#### Scenario: Positive latitude encoded correctly
- **WHEN** encoding latitude 47.5°
- **THEN** result SHALL be int(47.5 * 2147483648 / 180) = 566,231,040

#### Scenario: Negative longitude encoded correctly
- **WHEN** encoding longitude -122.5°
- **THEN** result SHALL be int(-122.5 * 2147483648 / 180) = -1,459,945,088

#### Scenario: Decoding matches encoding
- **WHEN** a coordinate is encoded and then decoded
- **THEN** decoded value SHALL match original within 0.000001° precision

### Requirement: Validate RGN2 E0 record coordinate layout
The system SHALL validate that tile bounds in RGN2 E0 records are written in the correct byte positions with little-endian byte order.

#### Scenario: E0 record has coordinates at correct offsets
- **WHEN** an E0 record is parsed
- **THEN** top (lat_max) SHALL be at bytes 22-25, right (lon_max) at 26-29, bottom (lat_min) at 30-33, left (lon_min) at 34-37

#### Scenario: Coordinates are little-endian
- **WHEN** top coordinate is 566231040 (0x21C20000)
- **THEN** bytes SHALL be [00, 00, C2, 21] in little-endian order

### Requirement: Validate subdivision center delta encoding
The system SHALL validate that lon_delta and lat_delta in RGN2 record bytes 2-5 correctly encode the tile center offset from subdivision center in 24-bit map units.

#### Scenario: Delta encoding for tile at subdivision center
- **WHEN** tile center equals subdivision center
- **THEN** lon_delta and lat_delta SHALL both be 0

#### Scenario: Delta encoding for offset tile
- **WHEN** tile center is 0.1° east of subdivision center
- **THEN** lon_delta SHALL be int(0.1 * 2^24 / 360) = 46,603

#### Scenario: Delta clamping to int16 range
- **WHEN** delta exceeds ±32767
- **THEN** value SHALL be clamped to [-32768, 32767] range

### Requirement: Validate coordinate consistency across sections
The system SHALL validate that tile bounds are consistent between RGN2 records, TRE2 subdivision bounds, and TRE header map bounds.

#### Scenario: All tile bounds within TRE header bounds
- **WHEN** validating an IMG file
- **THEN** every tile's bounds in RGN2 SHALL be within the TRE header map bounds

#### Scenario: Subdivision bounds encompass all its tiles
- **WHEN** a subdivision contains N tiles
- **THEN** subdivision bounds in TRE2 SHALL encompass the union of all N tile bounds

### Requirement: Report coordinate validation errors with context
The system SHALL report coordinate validation errors with tile index, expected vs actual values, and affected byte offsets.

#### Scenario: Map unit encoding error reported
- **WHEN** tile 42 has incorrect top coordinate encoding
- **THEN** error SHALL show "Tile 42: top coordinate at byte 22: expected 566231040 (0x21C20000), got 123456789 (0x075BCD15)"

#### Scenario: Delta encoding error reported
- **WHEN** tile has incorrect lon_delta
- **THEN** error SHALL show "Tile N at RGN2+offset: lon_delta expected X, got Y (bytes 2-3)"
