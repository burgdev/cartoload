## ADDED Requirements

### Requirement: Auto-detect source method from URL
The system SHALL auto-detect the source method (how to fetch data) from the configured URL when no explicit `source` field is provided.

#### Scenario: STAC collection URL detected
- **WHEN** a source URL contains `/collections/` or `/stac/` in the path
- **THEN** the system SHALL set the source method to `stac`

#### Scenario: Local path detected
- **WHEN** a source URL starts with `./`, `../`, `/`, or has no URL scheme (not `http://` or `https://`)
- **THEN** the system SHALL set the source method to `path`

#### Scenario: Explicit source field overrides auto-detection
- **WHEN** a source config has an explicit `source` field (e.g., `source: stac`)
- **THEN** the system SHALL use that value regardless of what the URL looks like

#### Scenario: Cannot auto-detect source method
- **WHEN** a source URL is an HTTP URL that does not match STAC patterns and no explicit `source` is provided
- **THEN** the system SHALL raise a validation error asking the user to specify the `source` field

### Requirement: Pipeline dispatch by type, download by source method
The pipeline SHALL dispatch processing based on data type (`geotiff`, `gpkg`, `wmts`). Within each type, the source method determines how files are obtained.

#### Scenario: geotiff + stac source
- **WHEN** a layer uses a `type: geotiff` source with `source: stac`
- **THEN** the pipeline SHALL use `STACDownloader` to fetch GeoTIFF assets, then process via the GeoTIFF pipeline

#### Scenario: geotiff + path source
- **WHEN** a layer uses a `type: geotiff` source with `source: path`
- **THEN** the pipeline SHALL use `collect_geotiff_files` to resolve local paths, then process via the GeoTIFF pipeline

#### Scenario: gpkg + stac source
- **WHEN** a layer uses a `type: gpkg` source with `source: stac`
- **THEN** the pipeline SHALL use `GPKGDownloader` to fetch GPKG assets, then process via the GPKG rasterization pipeline

#### Scenario: gpkg + path source
- **WHEN** a layer uses a `type: gpkg` source with `source: path`
- **THEN** the pipeline SHALL load the GPKG file directly from the local path, then process via the GPKG rasterization pipeline
