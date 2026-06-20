## ADDED Requirements

### Requirement: Unified pipeline with single entry point
The system SHALL provide a single `build_target()` function that handles all layer types — single and composite. There SHALL NOT be separate `build_geotiff_layer`, `build_gpkg_layer`, or WMTS inline paths.

#### Scenario: Single-layer target
- **WHEN** a target has exactly one layer entry
- **THEN** the system SHALL process it through the unified pipeline without requiring a composite step

#### Scenario: Multi-layer target
- **WHEN** a target has multiple layer entries
- **THEN** the system SHALL download, prepare, and composite all layers through the same pipeline

### Requirement: Config split into layers and targets
The system SHALL support a `layers:` section for reusable layer definitions (no `output` field) and a `targets:` section for build instructions (with `output`, `layers` stack).

#### Scenario: Reusable layer definition
- **WHEN** a layer is defined in the `layers:` section
- **THEN** it SHALL have a `format`, `source`, and `zoom_levels` but no `output` field

#### Scenario: Target with referenced layers
- **WHEN** a target references a layer via `ref:`
- **THEN** the system SHALL use the layer's defaults with any target-level overrides

#### Scenario: Inline layer in target
- **WHEN** a target layer entry has no `ref:` key
- **THEN** the system SHALL treat it as a self-contained layer definition with its own `format` and `source`

#### Scenario: Target with name and description
- **WHEN** a target defines `name` and `description`
- **THEN** these SHALL be used for display in build summaries and progress output

### Requirement: Format field selects processor
The system SHALL use a `format` field on layer definitions to select the appropriate LayerProvider (`geotiff`, `gpkg`, `wmts`).

#### Scenario: Geotiff format
- **WHEN** a layer has `format: geotiff`
- **THEN** the system SHALL use `GeotiffProvider` for processing (pre-warp, VRT, tile reading)

#### Scenario: Gpkg format
- **WHEN** a layer has `format: gpkg`
- **THEN** the system SHALL use `GpkgProvider` for processing (rasterize vector features)

#### Scenario: Wmts format
- **WHEN** a layer has `format: wmts`
- **THEN** the system SHALL use `WmtsProvider` for processing (tile grid download, per-tile loading)

### Requirement: Provider download-prepare-render lifecycle
Each LayerProvider SHALL implement `download()`, `prepare()`, and `to_raster(x, y, z)` methods.

#### Scenario: Download stage
- **WHEN** the unified pipeline runs the download stage
- **THEN** each provider SHALL delegate to its source to fetch raw data to cache

#### Scenario: Prepare stage
- **WHEN** the unified pipeline runs the prepare stage
- **THEN** each provider SHALL pre-process its data (pre-warp for geotiff, rasterize for gpkg, nothing for wmts)

#### Scenario: Render a tile
- **WHEN** the export stage requests a tile at (x, y, z)
- **THEN** the provider SHALL return an RGBA Image or None if no data exists at that position

### Requirement: Single-provider fast path
The system SHALL detect when a target has a single provider with no opacity overrides and stream raw bytes without RGBA decode/re-encode.

#### Scenario: Single provider with no opacity
- **WHEN** a target has exactly one layer entry with opacity 1.0 (or unset) at all zoom levels
- **THEN** the system SHALL skip the composite step and stream tile bytes directly to the exporter

#### Scenario: Single provider with opacity override
- **WHEN** a target has one layer entry with opacity less than 1.0
- **THEN** the system SHALL use the composite pipeline (decode → apply opacity → re-encode)

### Requirement: Cache lifecycle with source-owned metadata
The system SHALL use a metadata sidecar file (`.json`) owned by the source for cache validation. The provider MAY delete original files after processing, leaving a marker so the source knows data is still valid.

#### Scenario: Source checks cache
- **WHEN** a source checks if data is cached
- **THEN** it SHALL look for the original file AND metadata sidecar, OR a processor marker file

#### Scenario: Provider deletes original after processing
- **WHEN** a provider replaces an original file with a processed version
- **THEN** it SHALL preserve the metadata sidecar and write a completion marker so the source's cache check succeeds on subsequent runs

### Requirement: CLI selects target instead of layer
The CLI `-l` flag SHALL select a target by ID from the `targets:` config section.

#### Scenario: Select a target
- **WHEN** the user runs `cartoload build -c config.yaml -l ch_topo`
- **THEN** the system SHALL look up `ch_topo` in the `targets:` section and build it

#### Scenario: Target not found
- **WHEN** the specified ID is not in the `targets:` section
- **THEN** the system SHALL list available targets and exit with an error

### Requirement: Compositing with opacity support
The unified pipeline SHALL support per-zoom opacity for each layer in the target's layer stack.

#### Scenario: Multiple layers with opacity
- **WHEN** a target has multiple layers with opacity settings
- **THEN** the system SHALL composite them bottom-to-top using alpha blending with the configured opacity values

#### Scenario: Per-zoom opacity
- **WHEN** a layer has a per-zoom opacity dict (e.g., `{13: 0.4, 14: 0.6}`)
- **THEN** the system SHALL apply the opacity value matching the current zoom level

### Requirement: Zoom level filtering per layer
Each layer SHALL only be rendered at its configured zoom levels.

#### Scenario: Zoom level outside configured range
- **WHEN** a layer does not include a zoom level in its `zoom_levels`
- **THEN** the system SHALL skip that layer for tiles at that zoom level

### Requirement: Tile fallback for missing tiles
When a tile is unavailable for a declared zoom level, the system SHALL attempt to use a lower-zoom tile from the same provider and upscale it.

#### Scenario: Missing tile with lower-zoom fallback
- **WHEN** a provider cannot produce a tile at (x, y, z) but has data at a lower zoom level
- **THEN** the system SHALL upscale the lower-zoom tile as a fallback

### Requirement: Documentation updated
The system documentation SHALL be updated to reflect the new config structure and pipeline architecture.

#### Scenario: Layer configuration docs
- **WHEN** a user reads the layer configuration documentation
- **THEN** it SHALL describe the `layers` + `targets` config structure with examples

#### Scenario: Source configuration docs
- **WHEN** a user reads the source configuration documentation
- **THEN** it SHALL describe source types as fetch methods (stac, wmts, path) with the format field on layers selecting the processor
