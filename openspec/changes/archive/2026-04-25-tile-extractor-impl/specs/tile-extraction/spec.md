## ADDED Requirements

### Requirement: Tile extraction from GeoTIFF

The TileExtractor SHALL read the processed GeoTIFF and extract 256x256 pixel tiles for each configured zoom level. For each zoom level, the extractor SHALL compute the Web Mercator tile grid covering the configured bounds and extract one tile per grid cell.

#### Scenario: Extract tiles for a single zoom level

- **WHEN** `extract_tiles` is called with zoom level 10 and bounds covering Switzerland
- **THEN** the method SHALL return a dict mapping zoom level 10 to a list of numpy arrays, one per tile grid cell within the bounds

#### Scenario: Extract tiles for multiple zoom levels

- **WHEN** `extract_tiles` is called with zoom levels [10, 12, 14]
- **THEN** the method SHALL return a dict with keys 10, 12, and 14, each mapping to the correct number of tiles for that zoom level's grid

### Requirement: Tile grid computation

The TileExtractor SHALL compute the correct set of Web Mercator tile grid coordinates (x, y) for each zoom level that fall within the configured geographic bounds. Each grid cell SHALL correspond to exactly one extracted tile.

#### Scenario: Grid size varies with zoom level

- **WHEN** bounds are (5.96, 10.49, 45.82, 47.81) and zoom is 10
- **THEN** the grid SHALL contain more tile positions than at zoom 8 (higher zoom = more tiles)

#### Scenario: Tile grid covers full bounds

- **WHEN** tiles are extracted for given bounds and zoom
- **THEN** every geographic point within the bounds SHALL be covered by at least one extracted tile

### Requirement: Use GDAL CLI for extraction

The TileExtractor SHALL use `gdal_translate` CLI tool to extract tile regions from the GeoTIFF, consistent with the project's existing pattern of shelling out to GDAL CLI tools. No new Python geospatial dependencies SHALL be added.

#### Scenario: gdal_translate called per tile region

- **WHEN** a tile at geographic position (lon_min, lat_max, lon_max, lat_min) is needed
- **THEN** `gdal_translate` SHALL be called with `-projwin lon_min lat_max lon_max lat_min -outsize 256 256` to extract and resize the region

### Requirement: Non-empty tile data

The `extract_tiles` method SHALL NOT return empty lists for zoom levels that have tiles within the configured bounds. Each extracted tile SHALL be a numpy array of shape (256, 256, 3) containing RGB pixel data.

#### Scenario: Tiles contain actual pixel data

- **WHEN** tiles are extracted from a valid GeoTIFF
- **THEN** each tile array SHALL have shape (256, 256, 3) and dtype uint8, with non-zero pixel values in at least some tiles
