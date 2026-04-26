## ADDED Requirements

### Requirement: Cache-only build mode via --cache-warmup

The system SHALL support a `--cache-warmup` flag (or `cache-warmup` subcommand) that downloads and caches all tiles for the configured layer without producing any output files (no IMG). This allows users to pre-populate the cache for subsequent fast builds.

#### Scenario: Cache warmup with existing config

- **WHEN** the user runs `cartoload build --cache-warmup --layer switzerland_25k`
- **THEN** the system SHALL download all tiles for the layer's zoom levels and bounds
- **AND** tiles SHALL be stored in the download cache as normal
- **AND** NO IMG export SHALL run
- **AND** the command SHALL exit successfully after all tiles are cached

#### Scenario: Cache warmup with bbox override

- **WHEN** the user runs `cartoload build --cache-warmup --bbox 7.0 46.5 8.0 47.0 --layer switzerland_25k`
- **THEN** only tiles within the specified bbox SHALL be downloaded
- **AND** the bbox override SHALL work identically to the normal build mode

#### Scenario: Cache already warm

- **WHEN** the user runs cache warmup and all tiles are already in the download cache
- **THEN** the command SHALL complete quickly (no downloads needed)
- **AND** a summary SHALL be printed: "All N tiles already cached"

### Requirement: Cache warmup reports progress

The cache warmup mode SHALL report progress showing how many tiles are already cached vs. need downloading, and track download progress.

#### Scenario: Partial cache

- **WHEN** the user runs cache warmup for 30,000 tiles and 20,000 are already cached
- **THEN** the progress output SHALL show: "20,000 cached, 10,000 to download"
- **AND** download progress SHALL be tracked for the remaining 10,000 tiles

#### Scenario: Progress summary on completion

- **WHEN** cache warmup completes
- **THEN** the system SHALL print a summary: total tiles, already cached, newly downloaded, download errors

### Requirement: Cache warmup does not create output directory artifacts

The cache warmup mode SHALL NOT create any files outside the cache directory. No temporary files, no output directory structure, no empty IMG files.

#### Scenario: Clean cache warmup

- **WHEN** cache warmup runs for a layer
- **THEN** the only files created SHALL be within the configured cache directory
- **AND** the output directory SHALL NOT be created or modified

### Requirement: Reprojection cache warmup

When `--cache-warmup` is used and the source CRS differs from EPSG:4326, the system SHALL also populate the reprojection cache during warmup. This ensures subsequent fast builds require zero processing.

#### Scenario: Warmup with reprojection

- **WHEN** the source CRS is EPSG:3857 and the user runs `--cache-warmup`
- **THEN** the system SHALL download tiles AND reproject them to EPSG:4326
- **AND** both the download cache and reprojection cache SHALL be populated
- **AND** subsequent `cartoload build --layer ...` SHALL use the fast path with zero tile processing

#### Scenario: Warmup without reprojection (matching CRS)

- **WHEN** the source CRS is EPSG:4326 and the user runs `--cache-warmup`
- **THEN** only the download cache SHALL be populated
- **AND** no reprojection cache SHALL be created (not needed)
