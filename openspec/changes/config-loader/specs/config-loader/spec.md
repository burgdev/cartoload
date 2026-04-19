## ADDED Requirements

### Requirement: Load single source YAML file

The loader SHALL parse a YAML file containing a `sources` top-level key and return a `dict[str, SourceConfig]` keyed by source ID.

#### Scenario: Valid source file with one WMTS source
- **WHEN** a YAML file containing `sources.swisstopo_wmts` with `type: wmts`, `url_template`, `attribution`, `rate_limit_ms`, and `max_threads` is loaded
- **THEN** the loader returns a dict with key `swisstopo_wmts` mapped to a `SourceConfig` whose fields match the YAML values

#### Scenario: Valid source file with multiple sources
- **WHEN** a YAML file containing `sources.swisstopo_wmts` (WMTS) and `sources.swisstopo_stac` (GeoTIFF) is loaded
- **THEN** the loader returns a dict with two keys, each mapped to a correctly typed `SourceConfig`

#### Scenario: Source file missing top-level sources key
- **WHEN** a YAML file with no `sources` key is loaded
- **THEN** the loader raises `ValueError` with a message indicating the file path and the missing `sources` key

#### Scenario: Source entry missing required field type
- **WHEN** a source entry exists but has no `type` field
- **THEN** the loader raises `ValueError` with a message including the source ID, the missing field name, and the file path

#### Scenario: Source entry missing required field url_template for WMTS
- **WHEN** a source entry has `type: wmts` but no `url_template` field
- **THEN** the loader raises `ValueError` with a message indicating that `url_template` is required for WMTS sources

#### Scenario: Source entry missing required field stac_url for GeoTIFF
- **WHEN** a source entry has `type: geotiff` but no `stac_url` field
- **THEN** the loader raises `ValueError` with a message indicating that `stac_url` is required for GeoTIFF sources

### Requirement: Load single layer YAML file

The loader SHALL parse a YAML file containing a `layers` top-level key and return a `dict[str, LayerConfig]` keyed by layer ID, along with an optional `bounds` dict.

#### Scenario: Valid layer file with one layer
- **WHEN** a YAML file containing `layers.ch_basemap_25k` with `name`, `description`, `type`, `source`, `zoom_levels`, `exporter`, and `output` is loaded
- **THEN** the loader returns a dict with key `ch_basemap_25k` mapped to a `LayerConfig` whose fields match the YAML values

#### Scenario: Valid layer file with multiple layers
- **WHEN** a YAML file containing `layers.ch_basemap_25k`, `layers.ch_basemap_10k`, and `layers.ch_steepness` is loaded
- **THEN** the loader returns a dict with three keys, each mapped to a correctly typed `LayerConfig`

#### Scenario: Layer file with bounds
- **WHEN** a YAML file containing `bounds` with `west`, `east`, `south`, `north` and one or more layers is loaded
- **THEN** the loader returns the bounds alongside the layer dict

#### Scenario: Layer file missing top-level layers key
- **WHEN** a YAML file with no `layers` key is loaded
- **THEN** the loader raises `ValueError` with a message indicating the file path and the missing `layers` key

#### Scenario: Layer entry missing required field source
- **WHEN** a layer entry exists but has no `source` field
- **THEN** the loader raises `ValueError` with a message including the layer ID, the missing field name, and the file path

#### Scenario: Layer entry missing required field zoom_levels
- **WHEN** a layer entry exists but has no `zoom_levels` field
- **THEN** the loader raises `ValueError` with a message including the layer ID, the missing field name, and the file path

### Requirement: Merge multiple source files

The loader SHALL accept multiple source file paths and merge their contents into a single `dict[str, SourceConfig]`.

#### Scenario: Merge two source files with disjoint keys
- **WHEN** source file A defines `swisstopo_wmts` and source file B defines `basemap_at_wmts`
- **THEN** the merged dict contains both keys

#### Scenario: Merge two source files with overlapping keys
- **WHEN** source file A defines `swisstopo_wmts` with one `url_template` and source file B also defines `swisstopo_wmts` with a different `url_template`
- **THEN** the merged dict contains `swisstopo_wmts` with the values from file B (last file wins)

### Requirement: Merge multiple layer files

The loader SHALL accept multiple layer file paths and merge their contents into a single `dict[str, LayerConfig]`.

#### Scenario: Merge two layer files with disjoint keys
- **WHEN** layer file A defines `ch_basemap_25k` and layer file B defines `at_basemap`
- **THEN** the merged dict contains both keys

#### Scenario: Merge two layer files with overlapping keys
- **WHEN** layer file A defines `ch_basemap_25k` and layer file B also defines `ch_basemap_25k`
- **THEN** the merged dict contains `ch_basemap_25k` with the values from file B (last file wins)

#### Scenario: Merge bounds from multiple layer files
- **WHEN** layer file A defines `bounds` with one region and layer file B defines `bounds` with a different region
- **THEN** the merged bounds come from file B (last file wins)

### Requirement: Resolve source references in layers

After loading and merging all source and layer files, the loader SHALL verify that every `LayerConfig.source` value matches a loaded source ID.

#### Scenario: All layer sources resolve
- **WHEN** a layer references `source: swisstopo_stac` and `swisstopo_stac` exists in the merged sources dict
- **THEN** the layer is considered valid and no error is raised

#### Scenario: Layer references unknown source
- **WHEN** a layer references `source: nonexistent_source` and `nonexistent_source` is not in the merged sources dict
- **THEN** the loader raises `ValueError` with a message including the layer ID, the unresolved source reference, and the list of available source IDs

### Requirement: Validate source type values

The loader SHALL reject source entries with `type` values outside the supported set.

#### Scenario: Valid source type wmts
- **WHEN** a source entry has `type: wmts`
- **THEN** the source is accepted without error

#### Scenario: Valid source type geotiff
- **WHEN** a source entry has `type: geotiff`
- **THEN** the source is accepted without error

#### Scenario: Unknown source type
- **WHEN** a source entry has `type: made_up_type`
- **THEN** the loader raises `ValueError` with a message including the source ID, the invalid type value, and the list of valid types

### Requirement: Validate zoom levels

The loader SHALL validate that `zoom_levels` in layer configs is a non-empty list of integers within a reasonable range.

#### Scenario: Valid zoom levels
- **WHEN** a layer defines `zoom_levels: [10, 12, 14]`
- **THEN** the layer is accepted without error

#### Scenario: Empty zoom levels list
- **WHEN** a layer defines `zoom_levels: []`
- **THEN** the loader raises `ValueError` with a message including the layer ID and indicating that zoom_levels must not be empty

#### Scenario: Zoom level out of range
- **WHEN** a layer defines `zoom_levels: [10, 25]`
- **THEN** the loader raises `ValueError` with a message including the layer ID, the invalid zoom level, and the valid range

### Requirement: Implement list CLI command

The `cartoload list` command SHALL load and merge all provided `--sources` and `--layers` files and print a summary of each layer.

#### Scenario: List command with valid configs
- **WHEN** `cartoload list --sources sources.yaml --layers layers.yaml` is run with valid config files
- **THEN** the command prints each layer's ID, name, source, zoom levels, and exporter to stdout

#### Scenario: List command with no config files
- **WHEN** `cartoload list` is run without `--sources` or `--layers` flags
- **THEN** the command prints a message indicating that no config files were provided

#### Scenario: List command with invalid config
- **WHEN** `cartoload list --sources bad.yaml --layers layers.yaml` is run and `bad.yaml` has a validation error
- **THEN** the command exits with a non-zero status code and prints the validation error message
