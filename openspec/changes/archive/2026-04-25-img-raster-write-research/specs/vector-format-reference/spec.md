## ADDED Requirements

### Requirement: Vector IMG format overview documented

The specification SHALL document the Garmin vector IMG format structure from the Willink/Pinns PDF, providing a reference for potential future hybrid raster+vector maps.

#### Scenario: Vector TRE subdivision format documented

- **WHEN** the Willink/Pinns PDF TRE subdivision section is summarized
- **THEN** the documentation SHALL describe: 14-byte (lowest level) and 16-byte (other levels) subdivision records, RGN data pointer, object type bit flags (0x10=points, 0x20=indexed, 0x40=polylines, 0x80=polygons), geographic center (3-byte coordinates), width/height with terminating flag, and next-level linkage

#### Scenario: Vector RGN bitstream encoding documented

- **WHEN** the Willink/Pinns PDF RGN section is summarized
- **THEN** the documentation SHALL describe: element group layout (points, indexed points, polylines, polygons), bitstream coordinate encoding with variable bits-per-coordinate, and the pointer structure within each RGN data segment

#### Scenario: Vector LBL label encoding documented

- **WHEN** the Willink/Pinns PDF LBL section is summarized
- **THEN** the documentation SHALL describe: 6-bit/8-bit/10-bit character encoding modes, bit-packing (MSB-first), special character codes (0x1B prefix for symbols, 0x1C for lowercase), and highway shield encoding

#### Scenario: Vector NET/NOD overview documented

- **WHEN** the Willink/Pinns PDF NET and NOD sections are summarized
- **THEN** the documentation SHALL provide a high-level overview of: road network graph structure, routing node format, and why these sections are absent in raster maps

### Requirement: Hybrid raster+vector considerations documented

The specification SHALL document considerations for potential future hybrid maps that combine raster tiles with vector overlays.

#### Scenario: Coexistence requirements noted

- **WHEN** raster and vector format structures are compared
- **THEN** the documentation SHALL note: which sections are shared (TRE, GMP container), which are raster-specific (TRE7, TRE8, LBL28, LBL29, RGN Type E0), which are vector-specific (RGN bitstreams, NET, NOD), and how they might coexist in a single GMP subfile

#### Scenario: Existing vector IMG tools referenced

- **WHEN** tools for writing vector IMG files are surveyed
- **THEN** the documentation SHALL list: mkgmap (Java, open-source), sendmap, and other tools that can already produce vector IMG files, noting that hybrid maps might be created by combining raster tiles written by cartoload with vector data written by mkgmap
