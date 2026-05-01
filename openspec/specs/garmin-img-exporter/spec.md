## ADDED Requirements

### Requirement: Validate coordinate encoding matches reference files
The system SHALL validate that tile coordinate encoding in RGN2 E0 records produces byte-identical results to reference files for the same geographic tiles.

#### Scenario: Coordinate encoding matches SwissTopo for same tile
- **WHEN** generating a tile at the same lat/lon bounds as a SwissTopo tile
- **THEN** the RGN2 E0 record coordinate bytes SHALL match SwissTopo's encoding

### Requirement: Validate Web Mercator to WGS84 conversion
The system SHALL validate that Web Mercator tile bounds are correctly converted to WGS84 before encoding as Garmin coordinates.

#### Scenario: Web Mercator tile bounds converted correctly
- **WHEN** extracting a tile at Web Mercator zoom 10, x=512, y=350
- **THEN** WGS84 bounds SHALL use the standard Web Mercator inverse projection formula

#### Scenario: Tile bounds match WMTS specification
- **WHEN** downloading tiles from WMTS source
- **THEN** computed WGS84 bounds SHALL match the WMTS TileMatrixSet definition for that zoom/x/y

### Requirement: Validate zoom level encoding
The system SHALL investigate and potentially fix zoom level encoding to match reference files (which use level_number 16+ instead of 6-17).

#### Scenario: Zoom level encoding investigation
- **WHEN** comparing zoom level encoding with SwissTopo
- **THEN** determine if level_number affects coordinate scaling or display

#### Scenario: Zoom code computation validated
- **WHEN** generating zoom codes
- **THEN** codes SHALL match the pattern used by working reference files

### Requirement: Validate JPEG-coordinate linkage
The system SHALL validate that JPEG images in LBL29 are correctly linked to their RGN2 coordinate records via LBL28 indices.

#### Scenario: LBL28 index points to correct JPEG
- **WHEN** RGN2 record N references image_id M
- **THEN** LBL28 entry M SHALL point to the JPEG data for tile N in LBL29

#### Scenario: JPEG boundaries in LBL29 are correct
- **WHEN** LBL28 has offsets [0, 5230, 10450, ...]
- **THEN** JPEG N spans bytes LBL28[N] to LBL28[N+1] in LBL29

### Requirement: Fix coordinate bugs identified by comparison
Based on comparison findings, the system SHALL fix any coordinate encoding bugs in:
- WGS84 to Garmin 32-bit map unit conversion
- Subdivision center delta encoding (lon_delta, lat_delta)
- E0 record coordinate byte order or field positions
- Zoom level to coordinate scaling factor

#### Scenario: Fix applied and validated
- **WHEN** a coordinate bug is identified and fixed
- **THEN** regenerated IMG file SHALL pass coordinate validation against reference
