## ADDED Requirements

### Requirement: Generate preview images per zoom level

The system SHALL generate preview images during the build process, one per zoom level. Each preview SHALL be a mosaic of tiles centered on the map area, saved as a JPEG file.

#### Scenario: Preview for each zoom level

- **WHEN** a build produces an IMG file with zoom levels [20, 21, 22, 23, 24]
- **THEN** the system SHALL generate 5 preview images, one for each zoom level
- **AND** each preview SHALL be saved at `previews/{layer_name}_zoom{Z}.jpg` relative to the output directory

#### Scenario: Preview disabled by default

- **WHEN** the user runs `cartoload build` without `--preview` flag
- **THEN** no preview images SHALL be generated
- **AND** build performance SHALL not be affected by preview logic

#### Scenario: Preview enabled via flag

- **WHEN** the user runs `cartoload build --preview`
- **THEN** preview images SHALL be generated for all zoom levels after the IMG file is written

### Requirement: Preview center defaults to bbox center

The preview SHALL be centered on the geographic center of the bounding box unless a custom center is specified. The system SHALL select the tiles closest to the center point.

#### Scenario: Default center from bbox

- **WHEN** the bbox is (7.0, 46.5, 8.5, 47.5) and no `--preview-center` is specified
- **THEN** the preview SHALL be centered at approximately (7.75, 47.0)
- **AND** the X×X tile grid SHALL be selected around that center point

#### Scenario: Custom preview center

- **WHEN** the user specifies `--preview-center 7.45,46.9`
- **THEN** the preview SHALL be centered at (7.45, 46.9) instead of the bbox center
- **AND** tiles SHALL be selected around this custom center

#### Scenario: Center near edge of coverage

- **WHEN** the preview center is near the edge of the downloaded area and the requested tile count would extend beyond available tiles
- **THEN** the system SHALL reduce the tile count to fit within available tiles (see adaptive tile count requirement)

### Requirement: Preview tile count configurable via -P/--preview-tiles

The number of tiles to mosaic in each dimension SHALL be configurable. The flag SHALL accept a single integer representing both width and height of the tile grid.

#### Scenario: Default tile count

- **WHEN** `--preview` is specified without `--preview-tiles`
- **THEN** the preview SHALL be 8×8 tiles (64 tiles total per zoom level)
- **AND** the resulting image SHALL be 2048×2048 pixels (8 × 256)

#### Scenario: Custom tile count

- **WHEN** the user specifies `--preview-tiles 4`
- **THEN** the preview SHALL be 4×4 tiles (16 tiles total per zoom level)
- **AND** the resulting image SHALL be 1024×1024 pixels

#### Scenario: Odd tile count

- **WHEN** the user specifies `--preview-tiles 5`
- **THEN** the preview SHALL be 5×5 tiles centered on the center point
- **AND** the center tile SHALL contain the center point

### Requirement: Adaptive tile count — shrink to available tiles

The system SHALL adapt the preview tile grid to the number of tiles actually available around the center. If fewer tiles exist than requested, the preview SHALL use a smaller grid rather than filling gaps with placeholders.

#### Scenario: Full tile grid available

- **WHEN** `--preview-tiles 8` is specified and at least 8×8 tiles exist around the center
- **THEN** the preview SHALL be 8×8 tiles as requested

#### Scenario: Partial tile grid — edge of coverage

- **WHEN** `--preview-tiles 8` is specified but only 5×3 tiles exist around the center (e.g., near a map edge)
- **THEN** the preview SHALL be 5×3 tiles
- **AND** a info message SHALL be logged: "Preview for zoom 20: requested 8×8, using 5×3 (available tiles)"

#### Scenario: Very few tiles at high zoom

- **WHEN** `--preview-tiles 8` is specified at a high overview zoom level that only has 2×2 tiles total
- **THEN** the preview SHALL be 2×2 tiles
- **AND** the resulting image SHALL be 512×512 pixels

#### Scenario: No tiles at zoom level

- **WHEN** a zoom level has zero tiles in the cache
- **THEN** no preview SHALL be generated for that zoom level
- **AND** a warning SHALL be logged: "Skipping preview for zoom Z: no tiles available"

### Requirement: Preview assembled from cached tiles

Preview images SHALL be assembled from the tile data already in cache (download or reprojection cache). The preview generation SHALL NOT download additional tiles.

#### Scenario: Tiles available in cache

- **WHEN** all preview tiles are available in the cache
- **THEN** the preview SHALL be assembled by reading cached JPEG/PNG files, stitching them into a mosaic, and writing a single JPEG

### Requirement: Preview output location

Preview images SHALL be stored in a `previews/` subdirectory next to the IMG output file.

#### Scenario: Output directory structure

- **WHEN** the IMG is written to `output/switzerland_25k.img` and previews are enabled
- **THEN** preview files SHALL be written to:
  - `output/previews/switzerland_25k_zoom20.jpg`
  - `output/previews/switzerland_25k_zoom21.jpg`
  - ... etc.
- **AND** the `previews/` directory SHALL be created if it does not exist
