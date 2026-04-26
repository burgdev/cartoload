## ADDED Requirements

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

### Requirement: CRS used to determine reprojection need

The pipeline SHALL compare the source CRS against the target CRS (EPSG:4326 for Garmin IMG) to decide whether reprojection is needed. This comparison SHALL happen once per source, not per tile.

#### Scenario: Source CRS differs from target

- **WHEN** source CRS is EPSG:3857 and target CRS is EPSG:4326
- **THEN** the pipeline SHALL activate per-tile reprojection and use the reprojection cache

#### Scenario: Source CRS matches target

- **WHEN** source CRS is EPSG:4326 and target CRS is EPSG:4326
- **THEN** the pipeline SHALL skip reprojection and read tiles directly from the download cache
- **AND** no reprojection cache entries SHALL be created

### Requirement: CRS stored in cache metadata

The source CRS SHALL be recorded in a metadata file within the download cache directory so that the fast path can determine the projection without re-reading the source config.

#### Scenario: Cache metadata file

- **WHEN** tiles are downloaded from a source with `crs: "EPSG:3857"`
- **THEN** the system SHALL write a `metadata.json` file in `cache/{source_id}/` containing `{"crs": "EPSG:3857"}`
- **AND** the fast path SHALL read this metadata to determine if reprojection is needed
