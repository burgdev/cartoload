## ADDED Requirements

### Requirement: Per-tile alpha compositing of multiple raster sub-layers

The system SHALL composite multiple raster sub-layers into a single output tile per (x, y, z) position. For each tile position, the compositor SHALL load all available sub-layer tiles, apply per-layer opacity, and alpha-blend them bottom-to-top using the painter's algorithm.

#### Scenario: Two sub-layers with opacity

- **WHEN** a composite layer has two sub-layers: a basemap at opacity 1.0 and an overlay at opacity 0.6
- **THEN** for each tile position, the system SHALL load both tiles, decode them as RGBA, apply opacity 0.6 to the overlay's alpha channel, and composite the overlay on top of the basemap
- **AND** the result SHALL be encoded as JPEG bytes

#### Scenario: Sub-layer tile not available at a zoom level

- **WHEN** a sub-layer declares zoom level 12 in its `zoom_levels` but a tile at position (x, y, 12) is unavailable (not in cache, download failed with 404)
- **THEN** the system SHALL fall back to the closest lower zoom level in the sub-layer's `zoom_levels` list (e.g., zoom 10) and upscale that tile to cover the requested position
- **AND** the upscaled tile SHALL be composited with the same opacity as the requested zoom level
- **AND** a debug-level log message SHALL be emitted noting the fallback

#### Scenario: Sub-layer zoom level not declared — no fallback

- **WHEN** a sub-layer's `zoom_levels` list does not include zoom level 12 (intentionally omitted)
- **THEN** no fallback SHALL occur — the sub-layer is simply absent at that zoom level
- **AND** this is not an error condition

#### Scenario: No lower zoom tile available for fallback

- **WHEN** a sub-layer tile is unavailable at zoom 12 and no lower zoom level in the sub-layer's `zoom_levels` list has a tile covering that position
- **THEN** the sub-layer SHALL be absent for that tile position
- **AND** the compositor SHALL proceed with the remaining available sub-layers

#### Scenario: All sub-layers absent at a position

- **WHEN** no sub-layer can produce a tile at tile position (x, y, z) (neither directly nor via fallback)
- **THEN** that tile position SHALL be skipped entirely
- **AND** no entry SHALL be written to the tile metadata for that position

### Requirement: PNG tile input with transparency support

The compositor SHALL accept PNG tiles as input and preserve their alpha channel during compositing. PNG tiles SHALL be decoded as RGBA (4 channels).

#### Scenario: PNG overlay with transparent regions

- **WHEN** a sub-layer provides a PNG tile with partially transparent pixels (alpha < 255)
- **THEN** the compositor SHALL use the PNG's native alpha channel for blending
- **AND** transparent regions SHALL show the underlying sub-layer(s) through

#### Scenario: JPEG tile treated as fully opaque

- **WHEN** a sub-layer provides a JPEG tile (no alpha channel)
- **THEN** the compositor SHALL decode it as RGB and treat it as fully opaque (alpha = 255)
- **AND** the tile SHALL fully cover any underlying content at its opacity level

### Requirement: Per-layer opacity control

Each sub-layer SHALL support an `opacity` parameter that controls its transparency during compositing. Opacity SHALL be either a uniform float (0.0–1.0) or a per-zoom-level mapping.

#### Scenario: Uniform opacity

- **WHEN** a sub-layer has `opacity: 0.6`
- **THEN** all tiles from that sub-layer SHALL be composited at 60% opacity at every zoom level
- **AND** the sub-layer's alpha channel SHALL be multiplied by 0.6 before compositing

#### Scenario: Per-zoom opacity mapping

- **WHEN** a sub-layer has `opacity: {12: 0.3, 13: 0.6, 14: 0.8}`
- **THEN** tiles at zoom 12 SHALL be composited at 30% opacity, zoom 13 at 60%, zoom 14 at 80%
- **AND** zoom levels not present in the mapping SHALL use opacity 1.0 (fully opaque)

#### Scenario: No opacity specified

- **WHEN** a sub-layer does not specify an `opacity` field
- **THEN** the sub-layer SHALL be composited at opacity 1.0 (fully opaque)

### Requirement: Composite output is standard JPEG bytes

The compositor SHALL produce JPEG bytes as its output, identical in format to the existing single-source tile pipeline. The composited RGBA image SHALL be converted to RGB (discarding alpha) before JPEG encoding.

#### Scenario: Composite tile encoded as JPEG

- **WHEN** the compositor produces a blended tile
- **THEN** the output SHALL be JPEG bytes encoded at the configured quality level
- **AND** the output SHALL be indistinguishable from a single-source JPEG tile from the perspective of the IMG writer

### Requirement: Compositing for tiles requiring reprojection

When sub-layer tiles are in a different CRS than the target EPSG:4326, the system SHALL reproject each sub-layer tile individually before compositing. Reprojected tiles SHALL then be composited in EPSG:4326 space.

#### Scenario: Sub-layer in EPSG:3857

- **WHEN** a sub-layer's source uses EPSG:3857 (Web Mercator)
- **THEN** each tile from that sub-layer SHALL be reprojected to EPSG:4326 before compositing
- **AND** the reprojection SHALL use the same rasterio warp process as the single-source pipeline

#### Scenario: Mixed CRS sub-layers

- **WHEN** one sub-layer uses EPSG:3857 and another uses EPSG:4326
- **THEN** the EPSG:3857 tiles SHALL be reprojected to EPSG:4326 before compositing
- **AND** the EPSG:4326 tiles SHALL be used directly without reprojection
- **AND** both sets of tiles SHALL be composited in EPSG:4326 space
