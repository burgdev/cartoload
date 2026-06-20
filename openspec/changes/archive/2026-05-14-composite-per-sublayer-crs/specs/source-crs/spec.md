## MODIFIED Requirements

### Requirement: CRS used to determine reprojection need

The pipeline SHALL compare the source CRS against the target CRS (EPSG:4326 for Garmin IMG) to decide whether reprojection is needed. For composite layers, this comparison SHALL happen independently per sub-layer — each sub-layer resolves its own source type and CRS from its `source.ref`.

#### Scenario: Composite layer with mixed source types

- **WHEN** a composite layer contains STAC sub-layers (EPSG:4326 mosaics) and WMTS sub-layers (EPSG:3857)
- **THEN** each sub-layer SHALL independently resolve its CRS from its own source config
- **AND** WMTS sub-layers SHALL be reprojected from EPSG:3857 to EPSG:4326
- **AND** STAC sub-layers SHALL use their pre-warped EPSG:4326 mosaics without additional reprojection

#### Scenario: Source CRS differs from target

- **WHEN** source CRS is EPSG:3857 and target CRS is EPSG:4326
- **THEN** the pipeline SHALL activate per-tile reprojection and use the reprojection cache

#### Scenario: Source CRS matches target

- **WHEN** source CRS is EPSG:4326 and target CRS is EPSG:4326
- **THEN** the pipeline SHALL skip reprojection and read tiles directly from the download cache
- **AND** no reprojection cache entries SHALL be created
