## MODIFIED Requirements

### Requirement: Source config declares explicit CRS

The `SourceConfig` dataclass SHALL include an optional `crs` field that specifies the coordinate reference system of the source tiles. When set, this overrides any hardcoded assumptions about the source projection.

#### Scenario: WMTS source with explicit CRS

- **WHEN** a source config specifies `crs: "EPSG:3857"`
- **THEN** the system SHALL treat all downloaded tiles as being in EPSG:3857
- **AND** reprojection to EPSG:4326 SHALL be performed if needed for the target format

#### Scenario: WMTS source with CRS already matching target

- **WHEN** a source config specifies `crs: "EPSG:4326"`
- **THEN** the system SHALL skip reprojection entirely for tiles from this source
- **AND** tiles SHALL pass through directly from download cache to IMG writer

#### Scenario: No CRS specified — default by source type

- **WHEN** a source config does NOT specify a `crs` field
- **THEN** the system SHALL apply defaults: WMTS sources default to EPSG:3857, GeoTIFF sources read CRS from file metadata
- **AND** this preserves backward compatibility with existing configs

#### Scenario: Non-standard CRS

- **WHEN** a source config specifies a non-standard CRS (e.g., `EPSG:21781` for Swiss CH1903)
- **THEN** the system SHALL reproject tiles from that CRS to EPSG:4326
- **AND** the reprojection cache SHALL key on the source CRS to avoid mixing projections

#### Scenario: GeoTIFF source CRS detection

- **WHEN** a GeoTIFF source does not specify `crs` in config
- **THEN** the system SHALL read the CRS from the GeoTIFF file metadata using rasterio
- **AND** the detected CRS SHALL be used for the tiling reprojection step
