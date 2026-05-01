## MODIFIED Requirements

### Requirement: Polyline preamble encoding for raster tiles

The RGN2 raster record preamble SHALL position the tile's bottom-left corner via lon_delta/lat_delta. The bitstream SHALL encode 2 delta pairs forming an L-shaped boundingRect marker: (+width_half, 0) and (0, +height_half), where each half is the ceiling of half the tile extent in shifted coordinates.

Width and height halves SHALL be computed as:
- `width_half = ((right_mu - left_mu + mask) >> shift) // 2 + 1`
- `height_half = ((top_mu - bottom_mu + mask) >> shift) // 2 + 1`

This matches the SwissTopo reference format which uses small L-shaped markers for copyPolys() filtering while the absolute 32-bit bounds handle rendering.

#### Scenario: L-shaped bitstream at shift=2
- **WHEN** a tile is encoded at level_number=22 (shift=2)
- **THEN** the bitstream SHALL contain 2 delta pairs with the first moving right and the second moving up (or down), forming an L

#### Scenario: Bitstream fits in 8 bytes for all tile sizes
- **WHEN** a tile of any size is encoded at any level_number
- **THEN** the 2 delta pairs SHALL fit within the 56-bit data budget with appropriate baseSize values
