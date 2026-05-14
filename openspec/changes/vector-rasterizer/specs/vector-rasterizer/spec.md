## ADDED Requirements

### Requirement: Read features from GeoPackage with spatial filtering
The system SHALL read vector features from a GeoPackage file, filtering by geographic bounding box.

#### Scenario: Read features within tile bounds
- **WHEN** a tile at (z=12, x=2140, y=1440) is being rendered and the GPKG has features in that area
- **THEN** the system SHALL read only features whose geometry intersects the tile's bounding box in EPSG:4326

#### Scenario: CRS reprojection at read time
- **WHEN** the GPKG source CRS is EPSG:2056 (Swiss LV95)
- **THEN** the system SHALL reproject features to EPSG:4326 during reading via Fiona's CRS transformation

#### Scenario: No features in tile bounds
- **WHEN** a tile's bounding box contains no features from the GPKG
- **THEN** the system SHALL produce a fully transparent tile

### Requirement: Render styled lines onto transparent tiles
The system SHALL draw line features onto 256x256 transparent RGBA tiles using visual properties from the style engine.

#### Scenario: Solid colored line
- **WHEN** a feature matches a style rule with color `(255, 0, 0)` and width `2`
- **THEN** the system SHALL draw a 2-pixel-wide red line on the transparent tile following the feature's geometry

#### Scenario: Line with border/casing
- **WHEN** a feature matches a style rule with color `(0, 102, 255)`, width `2`, border_color `(255, 255, 255)`, border_width `1`
- **THEN** the system SHALL draw a 4-pixel-wide white line first (2 + 2*1), then a 2-pixel-wide blue line on top

#### Scenario: Dashed line
- **WHEN** a feature matches a style rule with dash pattern `[8, 4]`
- **THEN** the system SHALL draw the line as alternating 8-pixel on segments and 4-pixel off segments

#### Scenario: Dashed line with border
- **WHEN** a feature matches a style rule with dash pattern `[8, 4]` and border properties
- **THEN** the system SHALL draw the border as a dashed line (same pattern) underneath the core dashed line

#### Scenario: Feature with no matching style rule
- **WHEN** a feature's attributes match no style rule and no catch-all exists
- **THEN** the system SHALL skip rendering that feature

### Requirement: Coordinate projection to tile pixel space
The system SHALL project geographic coordinates (EPSG:4326) to pixel coordinates within each 256x256 tile.

#### Scenario: Point within tile
- **WHEN** a feature has a vertex at `(lon=7.5, lat=46.9)` and the tile covers `(7.4, 46.8)` to `(7.6, 47.0)`
- **THEN** the system SHALL project the vertex to approximately `(128, 128)` in pixel space

#### Scenario: Feature crossing tile boundary
- **WHEN** a line feature extends beyond the tile's geographic bounds
- **THEN** the system SHALL render the visible portion clipped to the tile boundary (lines extending beyond 256x256 are naturally clipped by Pillow)

### Requirement: Per-zoom-level rendering
The system SHALL apply zoom-appropriate style variants when rendering tiles.

#### Scenario: Zoom with defined style
- **WHEN** rendering a tile at zoom 14 and the style engine returns a style with width `2` for that zoom
- **THEN** the system SHALL use width `2` for rendering

#### Scenario: Zoom falling back to default
- **WHEN** rendering a tile at zoom 8 and the style engine falls back to the default style
- **THEN** the system SHALL use the default style for rendering

### Requirement: Output transparent PNG tiles
The system SHALL write rendered tiles as RGBA PNG files to a cache directory.

#### Scenario: Tile output path
- **WHEN** a tile at (z=12, x=2140, y=1440) is rendered for layer `skitouren`
- **THEN** the system SHALL write the tile to `<cache_dir>/skitouren/<cache_key>/12/2140/1440.png`

#### Scenario: Empty tile (no features)
- **WHEN** no features intersect the tile bounds
- **THEN** the system SHALL either write a fully transparent PNG or skip writing the tile entirely

#### Scenario: Tile with rendered features
- **WHEN** features are rendered onto the tile
- **THEN** the output PNG SHALL be 256x256 pixels with RGBA channels and transparent background

### Requirement: Integration with composite pipeline
The rasterizer's output SHALL be consumable by the existing composite pipeline as an overlay sub-layer.

#### Scenario: Composite layer with GPKG overlay
- **WHEN** a composite layer includes a sub-layer referencing a GPKG source
- **THEN** the composite pipeline SHALL use the rasterizer to generate transparent PNG tiles and blend them with the base layer using the sub-layer's opacity setting

#### Scenario: Multiple overlay layers
- **WHEN** a composite layer has multiple GPKG overlay sub-layers
- **THEN** each overlay SHALL be rasterized independently and composited in order with its own opacity
