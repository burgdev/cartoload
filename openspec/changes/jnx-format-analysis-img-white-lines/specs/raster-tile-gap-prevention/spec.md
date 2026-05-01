## ADDED Requirements

### Requirement: Bitstream boundingRect SHALL extend beyond tile edges

The bitstream delta encoding in `_encode_tile_bitstream()` SHALL produce a boundingRect that extends at least 1 quantization step beyond the tile's actual right and top edges. This ensures adjacent tiles' boundingRects always overlap, preventing GPXSee's `copyPolys()` from filtering out tiles at boundaries.

#### Scenario: Adjacent tiles at level_number 20
- **WHEN** two horizontally adjacent tiles share a vertical edge at level_number 20 (shift=4)
- **THEN** the right tile's boundingRect left edge SHALL be at or left of the shared edge, and the left tile's boundingRect right edge SHALL be at or right of the shared edge

#### Scenario: Adjacent tiles at level_number 24
- **WHEN** two vertically adjacent tiles share a horizontal edge at level_number 24 (shift=0)
- **THEN** both tiles' boundingRects SHALL overlap by at least 1 unit in the shifted coordinate space

#### Scenario: Tile at subdivision boundary
- **WHEN** a tile is positioned near the edge of its subdivision at any level_number
- **THEN** the tile's boundingRect SHALL remain within the subdivision's TRE2 extent (so the R-tree query finds the subdivision)

### Requirement: Subdivision bounds SHALL cover all assigned tiles

The TRE2 width/height for each subdivision SHALL be computed from the actual geographic bounds of assigned tiles, ensuring all tiles' boundingRect points fall within the subdivision's queryable extent.

#### Scenario: Grid cell with tiles near boundary
- **WHEN** tiles are assigned to a grid cell but their geographic positions extend beyond the cell's theoretical boundary
- **THEN** the subdivision's TRE2 bounds SHALL be expanded to include all assigned tiles' positions (with quantization margin)

#### Scenario: Subdivision with single tile
- **WHEN** a subdivision contains a single tile far from the grid cell center
- **THEN** the subdivision bounds SHALL cover that tile's position, not just the grid cell area

### Requirement: Subdivision center SHALL minimize tile delta magnitudes

The subdivision center point SHALL be computed from the geographic midpoint of assigned tiles' bounds, minimizing the magnitude of lon_delta/lat_delta and thus reducing quantization error impact.

#### Scenario: Asymmetric tile distribution
- **WHEN** tiles in a grid cell are clustered on one side (e.g., coastal map with tiles only in the eastern half)
- **THEN** the subdivision center SHALL be at the midpoint of the actual tile bounds, not the geometric center of the grid cell
