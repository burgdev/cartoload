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

### Requirement: export_from_tiles accepts tile metadata, not accumulated JPEG data

The `GarminImgExporter.export_from_tiles()` method SHALL accept tile metadata per zoom level instead of requiring the full `compressed_tiles` dict with all JPEG data in memory. It SHALL perform a two-pass write: layout from metadata, then stream-write JPEG data in batches.

#### Scenario: Export from tile metadata

- **WHEN** the exporter receives tile metadata for all zoom levels
- **THEN** it SHALL compute the complete file layout from metadata alone (subdivisions, section sizes, byte offsets)
- **AND** it SHALL stream-write JPEG data from source cache files in batches during the write pass
- **AND** the full `compressed_tiles` dict SHALL NOT be required

#### Scenario: Backward compatibility with compressed_tiles

- **WHEN** the exporter receives a `compressed_tiles` dict (legacy API)
- **THEN** it SHALL extract metadata from the tiles and proceed with the two-pass write
- **AND** the legacy API SHALL continue to work but log a deprecation warning

### Requirement: 4GB file splitting works with streaming writer

The `_write_with_splitting()` method SHALL work with the two-pass streaming writer, splitting large builds across multiple IMG files when the estimated size exceeds 4 GB.

#### Scenario: Size estimation from metadata

- **WHEN** the exporter estimates output file size to decide on splitting
- **THEN** it SHALL compute the estimate from tile metadata (JPEG sizes) without loading JPEG data
- **AND** the estimate SHALL be accurate to within 1% of the actual written size

#### Scenario: Multi-file split with streaming

- **WHEN** the estimated size exceeds 4 GB
- **THEN** the exporter SHALL assign zoom levels to files and write each file using the two-pass streaming approach
- **AND** each output file SHALL be independently valid

### Requirement: File size limit enforcement
The export system SHALL validate that no individual GMP subfile exceeds MAX_GMP_SIZE (~1.8 GB). If the total map data exceeds this limit, the system SHALL write multiple GMP subfiles within a single IMG file.

#### Scenario: FAT part number overflow prevention
- **WHEN** writing a GMP subfile that would need more than 256 FAT entries
- **THEN** the system raises a clear error instead of producing corrupt output with part > 255

#### Scenario: Graceful handling of oversized maps
- **WHEN** total map data is 11 GB
- **THEN** the system writes ~7 GMP subfiles within a single `.img` file, each under 1.8 GB

### Requirement: Subdivision hierarchy uses true parent-child relationships
The system SHALL generate TRE subdivisions where each parent's `nextLevel` field points to the first of its own spatially-contained children at the next zoom level, not to a shared global first-child index.

#### Scenario: Parent links to its own children only
- **WHEN** a parent subdivision P at zoom level N has geographic bounds (N, S, E, W)
- **AND** child subdivisions are generated at zoom level N+1
- **THEN** P's `next_level_index` SHALL point to the first child subdivision whose geographic bounds intersect P's bounds
- **AND** child subdivisions whose bounds do NOT intersect P's bounds SHALL NOT be linked from P

#### Scenario: All children of a parent are contiguous in the subdivision list
- **WHEN** parent P has K children at the next zoom level
- **THEN** the K children SHALL occupy consecutive indices in the flat subdivision list
- **AND** the last child SHALL have the "end of chain" marker (bit15 in TRE2 width field) set

#### Scenario: Empty overview levels maintain single-subdivision structure
- **WHEN** a zoom level has no tiles (overview level)
- **THEN** the system SHALL create a single subdivision spanning the full map bounds
- **AND** its parent's `next_level_index` SHALL point to this single subdivision

### Requirement: Tiles are assigned to parent-bounded subdivisions
The system SHALL assign tiles to subdivisions based on geographic intersection with parent bounds, ensuring that child subdivisions at level N+1 only contain tiles that fall within their parent's geographic area at level N.

#### Scenario: Tile assigned to correct parent's child
- **WHEN** tile T at zoom level N+1 has bounds that intersect parent subdivision P at level N
- **THEN** T SHALL be assigned to one of P's child subdivisions
- **AND** T SHALL NOT be assigned to a child of a different parent

#### Scenario: Tile spanning parent boundary
- **WHEN** tile T's bounds intersect two adjacent parent subdivisions P1 and P2
- **THEN** T SHALL be assigned to the child subdivision of whichever parent's center is nearest
- **OR** T MAY be duplicated in both parents' children (acceptable for raster maps)
