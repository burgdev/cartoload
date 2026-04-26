## ADDED Requirements

### Requirement: Tile Y coordinates start from positive northing

The `_compute_tile_bounds()` method SHALL compute tile Y coordinates starting from positive northing (+20,037,508.34 meters at y=0) and decreasing southward, matching the standard Web Mercator tile grid where y=0 represents the northernmost row.

#### Scenario: Tile at y=0 has positive northing

- **WHEN** `_compute_tile_bounds(x=0, y=0, zoom=0)` is called
- **THEN** the returned `top` value SHALL be positive (~20,037,508 meters)

#### Scenario: Swiss tiles have correct northing

- **WHEN** `_compute_tile_bounds(x=528, y=356, zoom=10)` is called
- **THEN** the returned `top` value SHALL correspond to latitude ~48° N (positive northing ~6,105,178 meters)

### Requirement: World files use correct Y northing

The `_write_world_file()` method SHALL produce world files with Y coordinates that place tiles at their correct geographic location in the northern hemisphere for northern latitudes.

#### Scenario: World file for Swiss tile

- **WHEN** a world file is written for tile (528, 356) at zoom 10
- **THEN** the Y origin (line 6 of the world file) SHALL be a positive value corresponding to ~48° N
