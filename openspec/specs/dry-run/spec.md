## ADDED Requirements

### Requirement: Dry-run mode shows build plan without executing

The system SHALL support a `--dry-run` flag that computes and displays what a build would do — tile counts, zoom levels, estimated file size, cache status — without downloading, processing, or writing any files.

#### Scenario: Dry-run for a configured layer

- **WHEN** the user runs `cartoload build --dry-run --layer switzerland_25k`
- **THEN** the system SHALL compute the tile grid for all configured zoom levels within the configured bounds
- **AND** print a summary to stdout without performing any downloads, reprojection, or file writes
- **AND** exit with code 0

#### Scenario: Dry-run with bbox override

- **WHEN** the user runs `cartoload build --dry-run --bbox 7.0 46.5 8.0 47.0 --layer switzerland_25k`
- **THEN** the summary SHALL reflect the smaller bbox, with reduced tile counts

#### Scenario: Dry-run with cache status

- **WHEN** the user runs `cartoload build --dry-run --layer switzerland_25k` and some tiles are already cached
- **THEN** the summary SHALL show how many tiles are already cached vs. need downloading for each zoom level

### Requirement: Dry-run output format

The dry-run output SHALL include: layer name, source, geographic bounds, zoom levels with tile counts per level, cache status, and estimated output size.

#### Scenario: Complete dry-run output

- **WHEN** dry-run is executed for a layer
- **THEN** the output SHALL include:
  ```
  Layer: switzerland_25k
  Source: swisstopo_wmts (EPSG:3857)
  Bounds: 5.96°E – 10.49°E, 45.82°N – 47.81°N
  Zoom levels:
    20:       4 tiles (4 cached, 0 to download)
    21:      12 tiles (12 cached, 0 to download)
    22:   1,200 tiles (1,200 cached, 0 to download)
    23:   4,800 tiles (3,200 cached, 1,600 to download)
    24:  19,200 tiles (19,200 cached, 0 to download)
  Total: 25,216 tiles (23,616 cached, 1,600 to download)
  Estimated output: ~1.4 GB
  ```

#### Scenario: Estimated output size calculation

- **WHEN** dry-run computes estimated output size
- **THEN** it SHALL use the average JPEG tile size from cached tiles × total tile count
- **AND** if no tiles are cached yet, it SHALL estimate ~30 KB per tile as a rough default
