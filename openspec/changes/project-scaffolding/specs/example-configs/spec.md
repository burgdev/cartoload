## ADDED Requirements

### Requirement: Example source configs

The project SHALL have `examples/configs/sources/` with three YAML files:

- `swisstopo.yaml` — defining `swisstopo_wmts` (WMTS) and `swisstopo_stac` (GeoTIFF/STAC) sources
- `basemap_at.yaml` — defining `basemap_at_wmts` (WMTS) source
- `france_ign.yaml` — defining `ign_wmts` (WMTS) source

Each source SHALL include `type`, `url_template` or `stac_url`, `attribution`, `rate_limit_ms`, and `max_threads` fields as documented in SPEC.md.

#### Scenario: Load swisstopo source config

- **WHEN** `swisstopo.yaml` is parsed as YAML
- **THEN** it contains `sources.swisstopo_wmts` with `type: wmts` and `sources.swisstopo_stac` with `type: geotiff`

#### Scenario: Load basemap.at source config

- **WHEN** `basemap_at.yaml` is parsed as YAML
- **THEN** it contains `sources.basemap_at_wmts` with `type: wmts` and the correct basemap.at URL template

#### Scenario: Load IGN France source config

- **WHEN** `france_ign.yaml` is parsed as YAML
- **THEN** it contains `sources.ign_wmts` with `type: wmts` and the correct IGN Geoportail WMTS URL

### Requirement: Example layer configs

The project SHALL have `examples/configs/layers/` with three YAML files:

- `switzerland.yaml` — with `bounds` and layers: `ch_basemap_25k`, `ch_basemap_10k`, `ch_steepness` (and Phase 2 vector template commented out)
- `austria.yaml` — with `bounds` and at least one layer referencing `basemap_at_wmts`
- `france.yaml` — with `bounds` and at least one layer referencing `ign_wmts`

Each layer config SHALL include the fields documented in SPEC.md: `name`, `description`, `type`, `source`, `zoom_levels`, `exporter`, `output`.

#### Scenario: Load Switzerland layer config

- **WHEN** `switzerland.yaml` is parsed as YAML
- **THEN** it contains `bounds` (west/east/south/north) and `layers.ch_basemap_25k` with `source: swisstopo_stac`, `zoom_levels: [10, 12, 14]`, `exporter: garmin_img`

#### Scenario: Load Austria layer config

- **WHEN** `austria.yaml` is parsed as YAML
- **THEN** it contains at least one layer referencing `source: basemap_at_wmts`

#### Scenario: Load France layer config

- **WHEN** `france.yaml` is parsed as YAML
- **THEN** it contains at least one layer referencing `source: ign_wmts`
