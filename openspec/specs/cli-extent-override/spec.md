## ADDED Requirements

### Requirement: Export command extracts raster tiles as GeoTIFF
The `cartoload analyze img export` command SHALL extract JPEG tiles from an IMG file and export them as a georeferenced GeoTIFF.

#### Scenario: Export IMG file to GeoTIFF
- **WHEN** user runs `cartoload analyze img export input.img -o output.tif`
- **THEN** system SHALL create a GeoTIFF containing all tiles from input.img

#### Scenario: Export requires output path
- **WHEN** user runs `cartoload analyze img export input.img` without -o flag
- **THEN** CLI SHALL exit with error "Output path required: use -o/--output"

### Requirement: Export command accepts bbox filtering
The export command SHALL accept `--bbox W S E N` to filter tiles by bounding box.

#### Scenario: Export with bbox filter
- **WHEN** user runs `cartoload analyze img export input.img -o output.tif --bbox 7.0 46.5 7.5 47.0`
- **THEN** only tiles intersecting the specified bounds SHALL be exported

### Requirement: Export command accepts zoom filtering
The export command SHALL accept `--zoom` to filter tiles by zoom level or range.

#### Scenario: Export single zoom level
- **WHEN** user runs `cartoload analyze img export input.img -o output.tif --zoom 10`
- **THEN** only tiles from zoom level 10 SHALL be exported

#### Scenario: Export zoom range
- **WHEN** user runs `cartoload analyze img export input.img -o output.tif --zoom 10-12`
- **THEN** tiles from zoom levels 10, 11, and 12 SHALL be exported

### Requirement: Info command shows per-tile coordinate details
The `cartoload analyze img info --rgn2` command SHALL optionally display detailed coordinate information for each tile when `--tile-details` flag is used.

#### Scenario: Tile details show decoded coordinates
- **WHEN** user runs `cartoload analyze img info input.img --rgn2 --tile-details --limit 5`
- **THEN** output SHALL show tile index, RGN2 offset, decoded WGS84 bounds, and subdivision delta for first 5 tiles

### Requirement: Compare command normalizes temporal fields
The `cartoload analyze img compare` command SHALL normalize date stamps and map IDs before comparison to reduce noise.

#### Scenario: Comparison with normalized dates
- **WHEN** comparing files with different creation dates
- **THEN** dates SHALL be normalized and not shown as differences

#### Scenario: Comparison flag to disable normalization
- **WHEN** user runs `cartoload analyze img compare file1.img file2.img --no-normalize`
- **THEN** dates and map IDs SHALL be compared as-is

### Requirement: Compare command accepts comparison depth flags
The compare command SHALL accept `--headers-only`, `--sample-size N`, and `--full` flags to control comparison depth.

#### Scenario: Headers-only comparison
- **WHEN** user runs `cartoload analyze img compare file1.img file2.img --headers-only`
- **THEN** only TRE/RGN/LBL headers SHALL be compared, data sections skipped

#### Scenario: Custom sample size
- **WHEN** user runs `cartoload analyze img compare file1.img file2.img --sample-size 10`
- **THEN** first 10 records from each data section SHALL be compared
