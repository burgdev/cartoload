## ADDED Requirements

### Requirement: World file generation for downloaded tiles

The WMTSDownloader SHALL compute and write a GDAL-compatible world file (`.jgw` for JPEG, `.pgw` for PNG) alongside each downloaded tile. The world file SHALL contain the correct affine transformation parameters derived from the tile's z/x/y coordinates and the Web Mercator (EPSG:3857) tile grid.

#### Scenario: Downloading a new JPEG tile

- **WHEN** a JPEG tile at coordinates (x, y, z) is downloaded and written to cache
- **THEN** a `.jgw` world file SHALL be created in the same directory with affine transform parameters computed from the tile grid

#### Scenario: Downloading a new PNG tile

- **WHEN** a PNG tile at coordinates (x, y, z) is downloaded and written to cache
- **THEN** a `.pgw` world file SHALL be created in the same directory with affine transform parameters computed from the tile grid

### Requirement: World file affine transform correctness

The world file SHALL encode the standard Web Mercator tile grid mapping. Given tile coordinates (x, y, z) and a tile size of 256x256 pixels, the world file SHALL contain: pixel width (tile*size_m / 256), 0, 0, negative pixel height (-tile_size_m / 256), upper-left X coordinate, and upper-left Y coordinate, where tile_size_m = 2 * pi \_ 6378137 / 2^z and origin = -20037508.3427892.

#### Scenario: World file values for a specific tile

- **WHEN** tile (541, 362, z=10) is downloaded
- **THEN** the world file SHALL contain 6 lines with correct affine transform values placing the tile at its correct Web Mercator position

### Requirement: World file generation for cached tiles

The WMTSDownloader SHALL regenerate world files for previously cached tiles that lack them. When a tile is found in cache but has no corresponding world file, the world file SHALL be generated without re-downloading the tile.

#### Scenario: Cached tile missing world file

- **WHEN** a tile is found in cache but no corresponding world file exists
- **THEN** the world file SHALL be generated from the tile's z/x/y coordinates and the tile SHALL be returned as valid

#### Scenario: Cached tile with existing world file

- **WHEN** a tile is found in cache and a corresponding world file already exists
- **THEN** the world file SHALL NOT be regenerated

### Requirement: CRS specification in gdalbuildvrt

The RasterProcessor SHALL pass the `-a_srs EPSG:3857` flag to `gdalbuildvrt` when building a VRT from WMTS tiles, declaring the coordinate reference system that matches the tile grid used to compute the world files.

#### Scenario: Building VRT from WMTS tiles

- **WHEN** `gdalbuildvrt` is called with a list of georeferenced WMTS tiles
- **THEN** the command SHALL include `-a_srs EPSG:3857` to declare the source CRS
