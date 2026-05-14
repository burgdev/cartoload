## ADDED Requirements

### Requirement: Source config defaults field
The `SourceConfig` dataclass SHALL accept an optional `defaults` field of type `dict[str, str]`. These defaults provide fallback values for template variables used in source string fields.

#### Scenario: Source with defaults
- **WHEN** a source config defines `defaults: {wmts_version: "1.0.0", wmts_extension: jpeg}`
- **THEN** these values SHALL be available for template substitution in all source string fields

#### Scenario: Empty defaults
- **WHEN** a source config does not define `defaults`
- **THEN** the defaults dict SHALL be empty, not None

### Requirement: Template variable syntax
Source string fields (urls, attribution) SHALL support `${VAR}` and `${VAR:-default}` syntax for variable substitution. Bare `$VAR` is also supported for alphanumeric/underscore names. `$$` produces a literal `$`.

#### Scenario: Variable with inline default
- **WHEN** a URL template contains `${wmts_version:-1.0.0}`
- **THEN** the variable SHALL resolve to the value `1.0.0` if no override is provided

#### Scenario: Variable without default
- **WHEN** a URL template contains `${layer}` and no value is provided for `layer`
- **THEN** the `${layer}` placeholder SHALL remain unresolved in the string and a warning SHALL be logged

#### Scenario: Variable with override
- **WHEN** a URL template contains `${wmts_extension:-jpeg}` and `source_args` provides `wmts_extension: png`
- **THEN** the variable SHALL resolve to `png`

#### Scenario: Bare variable
- **WHEN** a URL template contains `$layer`
- **THEN** the variable SHALL resolve to the value of `layer` from the merged variables

#### Scenario: Escaped dollar sign
- **WHEN** a URL template contains `$$5.00`
- **THEN** the output SHALL be `$5.00`

### Requirement: Template resolution order
Template variables SHALL be resolved in this order (later overrides earlier): inline `${VAR:-default}` values → source `defaults` → layer `source_args`.

#### Scenario: Layer args override source defaults
- **WHEN** source defaults define `attribution: "© swisstopo"` and layer args provide `attribution: "Custom"`
- **THEN** the resolved value SHALL be `"Custom"`

#### Scenario: Source defaults override inline defaults
- **WHEN** a URL template uses `${version:-2.0}` and source defaults define `version: "1.0.0"`
- **THEN** the resolved value SHALL be `"1.0.0"`

### Requirement: Source field as string or dict
The `source` field on `LayerConfig` SHALL accept either a string (source ID) or a dict with a `ref` key (source ID) and arbitrary key-value pairs that become `source_args`.

#### Scenario: String source reference
- **WHEN** a layer defines `source: swisstopo_wmts`
- **THEN** the layer SHALL reference source ID `swisstopo_wmts` with empty `source_args`

#### Scenario: Dict source reference with args
- **WHEN** a layer defines `source: {ref: swisstopo_wmts, wmts_layer: ch.swisstopo.pixelkarte-farbe}`
- **THEN** the layer SHALL reference source ID `swisstopo_wmts` with `source_args: {wmts_layer: ch.swisstopo.pixelkarte-farbe}`

### Requirement: wmts_layer backward compatibility
The `wmts_layer` field on `LayerConfig` and `CompositeSubLayer` SHALL remain functional. If both `wmts_layer` and `source_args.layer` are provided, `source_args.layer` SHALL take precedence.

#### Scenario: wmts_layer mapped to source_args
- **WHEN** a layer defines `wmts_layer: ch.swisstopo.pixelkarte-farbe` without source_args
- **THEN** the system SHALL behave as if `source_args: {layer: ch.swisstopo.pixelkarte-farbe}` was specified

#### Scenario: source_args overrides wmts_layer
- **WHEN** a layer defines both `wmts_layer: foo` and `source: {ref: src, layer: bar}`
- **THEN** the `layer` variable SHALL resolve to `"bar"`

### Requirement: Built-in template variables
Built-in per-tile variables SHALL use the same `${VAR}` syntax as config-level variables. They are resolved at download time (not at pipeline start). WMTS sources provide `${x}`, `${y}`, `${z}`, `${zoom}`, `${source_id}`, `${layer}`. These cannot be overridden by defaults or source_args.

#### Scenario: WMTS built-in variables
- **WHEN** processing a WMTS source
- **THEN** the variables `${x}`, `${y}`, `${z}`, `${zoom}`, `${source_id}`, `${layer}` SHALL be available for per-tile substitution in URLs

#### Scenario: Built-in variables not overridable
- **WHEN** source_args defines `x: "custom"` for a WMTS source
- **THEN** the `${x}` placeholder in URLs SHALL resolve to the actual tile X coordinate, ignoring the override

#### Scenario: Legacy syntax also supported
- **WHEN** a URL template uses `{x}`, `{y}`, `{z}` (without `$`)
- **THEN** the variables SHALL still be resolved correctly for backward compatibility

### Requirement: Composite sub-layer source_args
`CompositeSubLayer` SHALL support the same `source` field forms (string or dict) as `LayerConfig`.

#### Scenario: Inline sub-layer with source dict
- **WHEN** a composite sub-layer defines `source: {ref: swisstopo_wmts, wmts_layer: ch.swisstopo.skiroutes}`
- **THEN** the sub-layer SHALL pass these args to the downloader

### Requirement: Unresolved variable warning
When template resolution completes but unresolved `${VAR}` patterns remain in any source string field, a warning SHALL be logged listing the unresolved variables.

#### Scenario: Unresolved variable in URL
- **WHEN** a URL template contains `${unknown_var}` and no default or arg provides a value
- **THEN** the URL SHALL contain the literal `${unknown_var}` and a warning SHALL be logged
