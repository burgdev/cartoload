## ADDED Requirements

### Requirement: Convert GeoPackage to OSM XML
The system SHALL convert GeoPackage features to OSM XML format using ogr2ogr, preserving all attributes as OSM tags.

#### Scenario: Successful conversion
- **WHEN** a GPKG file with a `skitouren` layer containing features with attributes `schwierigkeit`, `name`, `hoehe` is converted
- **THEN** the output OSM XML SHALL contain `<way>` elements with `<tag k="schwierigkeit" v="WS"/>`, `<tag k="name" v="..."/>`, `<tag k="hoehe" v="..."/>` etc.

#### Scenario: CRS transformation
- **WHEN** the GPKG uses EPSG:2056
- **THEN** ogr2ogr SHALL reproject geometries to EPSG:4326 in the OSM output

#### Scenario: ogr2ogr not available
- **WHEN** ogr2ogr is not found on the system PATH
- **THEN** the system SHALL raise an error with a message indicating ogr2ogr is required

#### Scenario: Multiple GPKG layers
- **WHEN** the GPKG contains multiple layers
- **THEN** the system SHALL convert the specified layer name (from config) or all layers if none specified

### Requirement: Generate mkgmap style files
The system SHALL generate mkgmap-compatible style files from the style engine's match rules and Garmin type mappings.

#### Scenario: Generate lines file
- **WHEN** style rules contain match expressions with `garmin` type mappings for line features
- **THEN** the system SHALL generate a `lines` file with rules like `schwierigkeit=WS [0x16 resolution 16-24]`

#### Scenario: Compound match expression
- **WHEN** a rule has a compound match expression like `type=trail & difficulty=hard`
- **THEN** the generated rule SHALL preserve the compound syntax: `type=trail & difficulty=hard [0x16 resolution 20]`

#### Scenario: Catch-all rule
- **WHEN** a rule has match expression `*`
- **THEN** the generated rule SHALL use `* = *` or equivalent mkgmap syntax

#### Scenario: Generate options file
- **WHEN** a style is generated
- **THEN** the system SHALL produce an `options` file with default level-to-resolution mapping

#### Scenario: Generate version file
- **WHEN** a style is generated
- **THEN** the system SHALL produce a `version` file containing `1`

#### Scenario: Rule without Garmin mapping
- **WHEN** a style rule has no `garmin` block
- **THEN** the system SHALL skip that rule in the mkgmap style output (no Garmin type to assign)

### Requirement: Generate TYP file from visual properties
The system SHALL generate a Garmin TYP file with line visual definitions derived from `LineStyle` properties.

#### Scenario: Solid line with color and width
- **WHEN** a `LineStyle` has `color=(255,0,0)`, `width=2`, no dash, no border
- **THEN** the TYP file SHALL contain a `[_line]` section with `Type=0xNN`, `LineWidth=2`, and XPM with one solid color

#### Scenario: Solid line with border
- **WHEN** a `LineStyle` has `color=(0,102,255)`, `width=2`, `border_color=(255,255,255)`, `border_width=1`
- **THEN** the TYP file SHALL contain a line with `BorderWidth=1`, two XPM colours (fill + border), and `LineWidth=2`

#### Scenario: Dashed line
- **WHEN** a `LineStyle` has `dash=[8,4]`, `color=(255,0,0)`, `width=2`, no border
- **THEN** the TYP file SHALL contain a line with a 32-pixel-wide XPM bitmap encoding the dash pattern (8 pixels on, 4 pixels off, repeating across 32 pixels)

#### Scenario: Dashed line with border
- **WHEN** a `LineStyle` has `dash=[8,4]`, `color=(255,0,0)`, `width=2`, `border_color=(255,255,255)`, `border_width=1`
- **THEN** the TYP bitmap SHALL be 4 pixels tall (2 + 2*1), with border pixels on top/bottom rows and dashed fill pixels in the middle rows

#### Scenario: XPM bitmap dimensions
- **WHEN** any dashed line is generated
- **THEN** the XPM bitmap SHALL be exactly 32 pixels wide and `line_width + 2 * border_width` pixels tall

### Requirement: Run mkgmap subprocess
The system SHALL run mkgmap as a subprocess to generate the final `.img` file.

#### Scenario: Successful mkgmap run
- **WHEN** mkgmap is invoked with the generated OSM file, style directory, and TYP file
- **THEN** mkgmap SHALL produce a `.img` file in the output directory

#### Scenario: mkgmap not found
- **WHEN** mkgmap is not available (no `java` or no mkgmap jar)
- **THEN** the system SHALL raise an error with a clear message: "mkgmap is required for vector IMG output. Install mkgmap and ensure it is on PATH or set MKGMAP_JAR."

#### Scenario: mkgmap returns error
- **WHEN** mkgmap exits with a non-zero return code
- **THEN** the system SHALL raise an error including mkgmap's stderr output

### Requirement: Validate output IMG file
The system SHALL verify that the mkgmap output `.img` file exists and is non-empty.

#### Scenario: Output file exists and is valid
- **WHEN** mkgmap completes successfully
- **THEN** the system SHALL verify the output `.img` file exists and has size > 0

#### Scenario: Output file missing
- **WHEN** mkgmap completes but the expected `.img` file does not exist
- **THEN** the system SHALL raise an error indicating the expected output was not found

### Requirement: Separate IMG file output
The system SHALL produce a separate `.img` file for each vector layer, independent of raster output.

#### Scenario: Layer with exporter mkgmap
- **WHEN** a layer config has `exporter: mkgmap` and `output: skitouren.img`
- **THEN** the system SHALL run the mkgmap pipeline and place `skitouren.img` in the output directory

#### Scenario: Layer name in IMG
- **WHEN** a layer config has `name: "Swiss Skitours"`
- **THEN** the generated IMG SHALL use this name as the map name visible on Garmin devices
