## ADDED Requirements

### Requirement: Canonical tile math functions
The system SHALL provide a `tile_math` module at `src/cartoload/tile_math.py` with canonical Web Mercator tile coordinate functions: `lon_to_tile_x`, `lat_to_tile_y`, `tile_x_to_lon`, `tile_y_to_lat`, `compute_bounds_4326`, and `bounds_to_tile_coords`. These functions SHALL replace all existing inline implementations.

#### Scenario: Convert longitude to tile X
- **WHEN** `lon_to_tile_x(7.5, 12)` is called
- **THEN** it returns the correct Web Mercator tile X index for zoom level 12

#### Scenario: Convert latitude to tile Y
- **WHEN** `lat_to_tile_y(46.95, 12)` is called
- **THEN** it returns the correct Web Mercator tile Y index for zoom level 12

#### Scenario: Compute tile bounds in WGS84
- **WHEN** `compute_bounds_4326(x, y, zoom)` is called
- **THEN** it returns `(lat_min, lon_min, lat_max, lon_max)` matching the standard Web Mercator tile grid

#### Scenario: Compute tile coordinates for bounds
- **WHEN** `bounds_to_tile_coords({"west": 7.0, "south": 46.0, "east": 8.0, "north": 47.0}, 12)` is called
- **THEN** it returns a list of `(x, y)` tuples covering the entire bounds at the given zoom level

### Requirement: Existing tile math implementations replaced
All existing inline tile math implementations in `pipeline.py`, `processor/pipeline.py` (formerly `unified_pipeline.py`), `vector_rasterizer.py`, `wmts/download.py`, `garmin_img_writer.py`, and `preview.py` SHALL import from `tile_math.py` instead of reimplementing the math.

#### Scenario: No inline tile math after refactoring
- **WHEN** the codebase is searched for `lat_to_y` or `lon_to_x` function definitions
- **THEN** they only appear in `tile_math.py`

### Requirement: ProcessedTile type alias defined once
The `ProcessedTile` type alias SHALL be defined once in `tile_math.py` and imported by all modules that use it.

#### Scenario: Single ProcessedTile definition
- **WHEN** the codebase is searched for `ProcessedTile =` type alias definitions
- **THEN** it appears exactly once
