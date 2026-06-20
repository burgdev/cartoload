## MODIFIED Requirements

### Requirement: Unified config file format
A config file SHALL be a YAML document that may contain any combination of the following top-level keys: `includes`, `sources`, `layers`, `bounds`, `settings`. All sections are optional. A file containing only `sources:` is valid. Source type `gpkg` SHALL be accepted as a valid source type alongside `wmts`, `stac`, and `geotiff`.

#### Scenario: Config file with all sections
- **WHEN** a config file contains `includes`, `sources`, `layers`, and `bounds` keys
- **THEN** the loader SHALL parse all sections and return them as a unified result

#### Scenario: Config file with only sources
- **WHEN** a config file contains only a `sources` key (no `layers` or `bounds`)
- **THEN** the loader SHALL return the sources with no layers and no bounds

#### Scenario: Config file with only layers
- **WHEN** a config file contains only a `layers` key (no `sources`)
- **THEN** the loader SHALL return the layers with no sources

#### Scenario: Empty config file
- **WHEN** a config file contains no recognized top-level keys
- **THEN** the loader SHALL return empty sources, empty layers, and no bounds

#### Scenario: GPKG source type accepted
- **WHEN** a source config defines `type: gpkg` with a `url_template`
- **THEN** the loader SHALL accept it as a valid source configuration
