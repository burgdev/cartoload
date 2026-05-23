## ADDED Requirements

### Requirement: WmtsSource operates in template mode or Capabilities mode

`WmtsSource` SHALL support two modes of operation, auto-detected from the source config:
- **Template mode**: URL contains `${x}/${y}/${z}` placeholders → use hardcoded Web Mercator tile grid, build URLs from template (existing behavior, unchanged)
- **Capabilities mode**: Config provides `capabilities_url` or URL matches a Capabilities endpoint pattern → parse GetCapabilities XML, resolve layer+TileMatrixSet, build URL template from ResourceURL

Both modes produce a `WmtsDownloader` instance. No config migration needed.

#### Scenario: Template mode auto-detected from URL

- **WHEN** a source config has `type: wmts` and the first URL contains `${x}`, `${y}`, `${z}` placeholders
- **THEN** `WmtsSource` SHALL operate in template mode using hardcoded Web Mercator tile math

#### Scenario: Capabilities mode auto-detected from capabilities_url

- **WHEN** a source config has `type: wmts` and a `capabilities_url` field
- **THEN** `WmtsSource` SHALL operate in Capabilities mode — fetch and parse the Capabilities document

#### Scenario: Capabilities mode auto-detected from URL pattern

- **WHEN** a source config has `type: wmts` and the URL ends with `WMTSCapabilities.xml` or contains `GetCapabilities` and `WMTS`
- **THEN** `WmtsSource` SHALL operate in Capabilities mode

#### Scenario: type: xyz is alias for WmtsSource

- **WHEN** a source config specifies `type: xyz`
- **THEN** the source registry SHALL resolve it to `WmtsSource`
- **AND** `WmtsSource` SHALL auto-detect template mode if the URL contains tile coordinate placeholders

### Requirement: Parse WMTS GetCapabilities XML

The system SHALL parse a WMTS GetCapabilities XML document using Python's stdlib `xml.etree.ElementTree` and extract layer metadata, TileMatrixSet definitions, and ResourceURL templates.

#### Scenario: Parse swisstopo Capabilities

- **WHEN** a WMTS Capabilities URL is fetched (e.g., `https://wmts.geo.admin.ch/1.0.0/WMTSCapabilities.xml`)
- **THEN** the parser SHALL return a `WmtsCapabilities` dataclass containing all available layers, their TileMatrixSet links, and ResourceURL templates

#### Scenario: Layer discovery

- **WHEN** a Capabilities document contains a `<Layer>` with `Identifier` = `ch.swisstopo.pixelkarte-farbe`
- **THEN** the parser SHALL extract the layer identifier, title, bounding box, and associated TileMatrixSet links

#### Scenario: TileMatrixSet with GoogleMapsCompatible profile

- **WHEN** a Capabilities document defines a `TileMatrixSet` with `Identifier` = `GoogleMapsCompatible` (EPSG:3857)
- **THEN** the parser SHALL extract scale denominators, TopLeftCorner origins, tile dimensions, and matrix sizes for each zoom level
- **AND** the scale denominator for zoom level `z` SHALL equal `559082264.0287178 / 2^z`

#### Scenario: TileMatrixSet with WGS84 profile

- **WHEN** a Capabilities document defines a `TileMatrixSet` with `Identifier` containing `WGS84` or CRS `EPSG:4326`
- **THEN** the parser SHALL extract the tile matrix parameters for geographic (lon/lat) tile grids
- **AND** the origin SHALL be at `(-180, 90)` or similar geographic coordinates

#### Scenario: ResourceURL templates extracted

- **WHEN** a layer entry contains `<ResourceURL>` elements with `template` attributes
- **THEN** the parser SHALL extract the URL template for each layer+TileMatrixSet+format combination
- **AND** template variables like `{TileMatrix}/{TileCol}/{TileRow}` SHALL be mapped to internal `${z}/${x}/${y}` syntax

#### Scenario: Malformed Capabilities XML

- **WHEN** the fetched Capabilities document is not valid XML or is missing required elements
- **THEN** the system SHALL raise a clear error indicating the parse failure
- **AND** SHALL include the URL that was fetched in the error message

### Requirement: Resolve layer to TileMatrixSet and URL template

In Capabilities mode, `WmtsSource` SHALL resolve a requested layer identifier to a specific TileMatrixSet and construct a URL template for the `WmtsDownloader`.

#### Scenario: Layer with single TileMatrixSet

- **WHEN** a WMTS source config specifies `layer: ch.swisstopo.pixelkarte-farbe` and the Capabilities document links this layer to one TileMatrixSet
- **THEN** the system SHALL use that TileMatrixSet for tile grid computation
- **AND** SHALL use the associated ResourceURL template for tile downloads

#### Scenario: Layer with multiple TileMatrixSets — explicit selection

- **WHEN** a WMTS source config specifies `tile_matrix_set: "3857"` and the layer supports multiple TileMatrixSets
- **THEN** the system SHALL select the TileMatrixSet whose identifier matches `3857`
- **AND** SHALL use the corresponding ResourceURL template

#### Scenario: Layer with multiple TileMatrixSets — default selection

- **WHEN** a WMTS source config does NOT specify `tile_matrix_set` and the layer supports multiple TileMatrixSets
- **THEN** the system SHALL prefer a GoogleMapsCompatible or EPSG:3857 TileMatrixSet
- **AND** SHALL log the selected TileMatrixSet identifier

#### Scenario: Layer not found in Capabilities

- **WHEN** a WMTS source config specifies a layer identifier not present in the Capabilities document
- **THEN** the system SHALL raise a clear error listing the available layer identifiers

### Requirement: Tile grid computation from TileMatrixSet

In Capabilities mode, `WmtsSource` SHALL compute tile coordinates from WGS84 bounding boxes using the TileMatrixSet definition, rather than hardcoded Web Mercator math. Template mode continues using the existing hardcoded math.

#### Scenario: GoogleMapsCompatible matches hardcoded math

- **WHEN** a TileMatrixSet uses the GoogleMapsCompatible profile (EPSG:3857, origin at `-20037508.3427892 20037508.3427892`, 256×256 tiles)
- **THEN** the computed tile indices SHALL match the existing hardcoded Web Mercator tile math for the same bounding box and zoom level

#### Scenario: WGS84 geographic tile grid

- **WHEN** a TileMatrixSet uses a WGS84 geographic tile grid (EPSG:4326, origin at `-180 90`)
- **THEN** the computed tile indices SHALL use geographic (degree-based) tile math
- **AND** tile bounds SHALL be in geographic coordinates, not meters

#### Scenario: Unsupported tile grid profile

- **WHEN** a TileMatrixSet uses a CRS or profile that is not GoogleMapsCompatible or WGS84
- **THEN** the system SHALL log a warning with the TileMatrixSet identifier and CRS
- **AND** SHALL attempt to compute tile indices using the generic formula from the TileMatrix parameters

### Requirement: WMTS source config schema for Capabilities mode

A WMTS source config SHALL accept the following fields for Capabilities mode:
- `capabilities_url` (required for Capabilities mode): URL to the WMTS GetCapabilities endpoint
- `layer` (optional): Layer identifier to use (can be overridden in layer `source_args`)
- `tile_matrix_set` (optional): TileMatrixSet identifier (defaults to GoogleMapsCompatible or first available)
- `tile_format` (optional): Output tile format — `image/jpeg`, `image/png`, etc. (defaults to first available)
- `crs` (optional): Override CRS from Capabilities (normally auto-detected from TileMatrixSet)
- `rate_limit_ms`, `max_threads`, `attribution`: Same as other source types

#### Scenario: Minimal Capabilities config

- **WHEN** a source config specifies only `type: wmts` and `capabilities_url`
- **THEN** the system SHALL use the first layer and default TileMatrixSet from the Capabilities document

#### Scenario: Full Capabilities config

- **WHEN** a source config specifies `type: wmts`, `capabilities_url`, `layer`, `tile_matrix_set`, and `tile_format`
- **THEN** the system SHALL resolve the exact layer+TileMatrixSet+format combination
- **AND** SHALL raise an error if the combination is not available in the Capabilities document
