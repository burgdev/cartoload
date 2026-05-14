## ADDED Requirements

### Requirement: Composite layer config with sub-layers

The `LayerConfig` SHALL support an optional `layers` field containing an ordered list of sub-layer definitions. When present, the layer is treated as a composite layer. When absent, behavior is identical to the existing single-source pipeline.

#### Scenario: Composite layer with inline sub-layers

- **WHEN** a layer config contains a `layers` field with inline sub-layer definitions (each having `source`, `wmts_layer`, `zoom_levels`, `extension`, `opacity`)
- **THEN** the system SHALL validate each inline sub-layer has the required fields (`source` at minimum)
- **AND** the sub-layers SHALL be composited in list order (first = base, last = top)

#### Scenario: Composite layer with ref sub-layers

- **WHEN** a sub-layer entry has a `ref` field referencing an existing top-level layer ID
- **THEN** the system SHALL resolve the reference by looking up the referenced layer in the top-level layers dict
- **AND** the referenced layer's source, wmts_layer, and other fields SHALL be inherited
- **AND** any overrides on the ref entry (e.g., `zoom_levels`, `opacity`, `extension`) SHALL take precedence over the referenced layer's values

#### Scenario: Mixed inline and ref sub-layers

- **WHEN** a composite layer has both inline and ref sub-layers
- **THEN** the system SHALL resolve all sub-layers into a uniform representation
- **AND** the compositing order SHALL match the list order regardless of type

### Requirement: Sub-layer config validation

Each sub-layer SHALL be validated for consistency and completeness.

#### Scenario: Inline sub-layer missing source

- **WHEN** an inline sub-layer (no `ref`) does not have a `source` field
- **THEN** the config loader SHALL raise a `ValueError` with a message indicating the sub-layer index and missing field

#### Scenario: Ref sub-layer pointing to non-existent layer

- **WHEN** a sub-layer has `ref: "ch_basemap_25k"` but no top-level layer with that ID exists
- **THEN** the config loader SHALL raise a `ValueError` indicating the unresolved reference

#### Scenario: Ref sub-layer pointing to another composite layer

- **WHEN** a sub-layer has a `ref` pointing to a layer that itself has a `layers` field (i.e., another composite layer)
- **THEN** the config loader SHALL raise a `ValueError` indicating that composite-to-composite references are not supported

#### Scenario: Composite layer missing source field

- **WHEN** a composite layer (has `layers` field) does not have a top-level `source` field
- **THEN** the system SHALL NOT require a `source` field on the composite layer itself (sources come from sub-layers)

### Requirement: Sub-layer opacity configuration

Each sub-layer SHALL accept an optional `opacity` field.

#### Scenario: Float opacity value

- **WHEN** a sub-layer has `opacity: 0.6`
- **THEN** the value SHALL be validated as a float between 0.0 and 1.0
- **AND** the value SHALL be applied uniformly across all zoom levels for that sub-layer

#### Scenario: Per-zoom opacity mapping

- **WHEN** a sub-layer has `opacity: {12: 0.3, 14: 0.8}`
- **THEN** the value SHALL be validated as a dict of integer zoom levels to float opacity values
- **AND** each opacity value SHALL be between 0.0 and 1.0

#### Scenario: Invalid opacity value

- **WHEN** a sub-layer has `opacity: 1.5` or `opacity: -0.1`
- **THEN** the config loader SHALL raise a `ValueError`

### Requirement: Composite layer zoom levels

The composite layer's top-level `zoom_levels` field SHALL define the output zoom levels. Sub-layers contribute tiles at their own `zoom_levels`, which may be a subset of the composite layer's zoom levels.

#### Scenario: Sub-layer zoom levels are a subset

- **WHEN** a composite layer has `zoom_levels: [8, 9, 11, 12, 13, 14, 15]` and a sub-layer has `zoom_levels: [12, 13, 14]`
- **THEN** the sub-layer SHALL only contribute tiles at zoom levels 12, 13, and 14
- **AND** at other zoom levels, the sub-layer SHALL be absent (other sub-layers composited without it)

#### Scenario: Sub-layer zoom levels extend beyond composite

- **WHEN** a sub-layer has zoom levels not present in the composite layer's `zoom_levels`
- **THEN** those extra zoom levels SHALL be ignored (the composite output only includes the top-level zoom levels)

#### Scenario: Sub-layer without zoom_levels inherits from composite

- **WHEN** a sub-layer (inline or ref) does not specify `zoom_levels`
- **THEN** the sub-layer SHALL inherit the composite layer's `zoom_levels`

### Requirement: Sub-layer extension support

Sub-layers SHALL support different tile formats via an `extension` field (e.g., `png`, `jpeg`).

#### Scenario: PNG overlay sub-layer

- **WHEN** a sub-layer has `extension: png`
- **THEN** the downloader SHALL request/save tiles with `.png` extension
- **AND** the compositor SHALL decode the tile as RGBA PNG

#### Scenario: No extension specified

- **WHEN** a sub-layer does not specify `extension`
- **THEN** the system SHALL default to `jpeg` for the tile format
