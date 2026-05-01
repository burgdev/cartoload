## ADDED Requirements

### Requirement: Bitstream SHALL match SwissTopo 3-point L-shaped format

The bitstream in `_encode_tile_bitstream()` SHALL encode 2 delta pairs forming an L-shape: (+width_half, 0) and (0, +height_half), where width_half and height_half are approximately half the tile extent in shifted coordinates. This produces a boundingRect marker near the tile position, matching the proven SwissTopo reference format.

#### Scenario: L-shaped encoding at level_number 22
- **WHEN** a tile of 576x400 map units is encoded at level_number 22 (shift=2)
- **THEN** the bitstream SHALL contain 2 delta pairs: approximately (+144, 0) and (0, +100) in shifted coordinates
- **AND** the boundingRect after applying shift SHALL be near the tile position

#### Scenario: L-shaped encoding at level_number 24
- **WHEN** a tile is encoded at level_number 24 (shift=0)
- **THEN** the bitstream SHALL contain 2 delta pairs with exact half-extent values

#### Scenario: Bitstream fits in 8 bytes
- **WHEN** a large tile is encoded at any level_number
- **THEN** the 2 delta pairs plus sign bits and extended bit SHALL fit within 56 data bits (7 bytes)

### Requirement: Subdivision bounds SHALL cover all assigned tiles

The TRE2 width/height for each subdivision SHALL be computed from the actual geographic bounds of assigned tiles, ensuring all tiles' boundingRects fall within the subdivision's queryable extent.

#### Scenario: Grid cell with tiles near boundary
- **WHEN** tiles are assigned to a grid cell but their geographic positions extend beyond the cell's theoretical boundary
- **THEN** the subdivision's TRE2 bounds SHALL be expanded to include all assigned tiles' positions

### Requirement: Subdivision center SHALL minimize tile delta magnitudes

The subdivision center point SHALL be computed from the geographic midpoint of assigned tiles' bounds.

#### Scenario: Asymmetric tile distribution
- **WHEN** tiles in a grid cell are clustered on one side
- **THEN** the subdivision center SHALL be at the midpoint of the actual tile bounds, not the geometric center of the grid cell
