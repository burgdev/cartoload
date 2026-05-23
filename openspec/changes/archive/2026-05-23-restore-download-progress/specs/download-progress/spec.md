## ADDED Requirements

### Requirement: WMTS tile pre-fetch during unified pipeline download stage
When building a target with WMTS source layers, the unified pipeline SHALL pre-fetch all tiles via `download_grid()` during the download stage, before the export stage begins.

#### Scenario: WMTS layer with uncached tiles
- **WHEN** a target contains a WMTS layer and tiles are not yet cached
- **THEN** the pipeline SHALL call `download_grid()` for each zoom level in the layer's bounds
- **AND** a Rich progress bar SHALL show download progress per zoom level

#### Scenario: WMTS layer with all tiles cached
- **WHEN** a target contains a WMTS layer and all tiles are already cached
- **THEN** the pipeline SHALL call `download_grid()` which will detect cached tiles and skip downloading
- **AND** the download stage SHALL complete quickly

#### Scenario: Multiple WMTS layers
- **WHEN** a target contains multiple WMTS layers
- **THEN** each layer SHALL be downloaded sequentially with its own progress bar
- **AND** the "Layer N/M: downloading..." message SHALL remain visible above the progress bar

### Requirement: Download progress visibility
The download stage SHALL show a Rich progress bar with tile count, percentage, and elapsed time for each zoom level being downloaded.

#### Scenario: Large download area
- **WHEN** downloading tiles for a large area (e.g., Switzerland at zoom 12, ~10k tiles)
- **THEN** the progress bar SHALL show: spinner, layer name + zoom, progress bar, percentage, completed/total, elapsed time
- **AND** the user SHALL see continuous progress feedback during the download

### Requirement: Non-WMTS providers unchanged
GeoTIFF and other non-WMTS providers SHALL NOT be affected by this change.

#### Scenario: GeoTIFF layer download
- **WHEN** a target contains a GeoTIFF layer
- **THEN** the download behavior SHALL remain unchanged (STAC fetch, no tile grid)
