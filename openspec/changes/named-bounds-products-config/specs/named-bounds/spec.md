## ADDED Requirements

### Requirement: Named bounds section
The config loader SHALL accept a `bounds:` section as a dict of named bounding boxes, where each key is a slug and each value is a dict with `west`, `east`, `south`, `north` float fields.

#### Scenario: Named bounds section parsed
- **WHEN** a config file contains `bounds: {switzerland: {west: 5.96, east: 10.49, south: 45.82, north: 47.81}}`
- **THEN** the loader SHALL return `config.bounds` as `{"switzerland": BoundsConfig(id="switzerland", west=5.96, ...)}`

#### Scenario: Named bounds validated
- **WHEN** a named bounds entry has `west >= east` or `south >= north`
- **THEN** the loader SHALL raise a `ValueError` with the bounds slug and file path

### Requirement: Anonymous bounds backward compatibility
The config loader SHALL accept the existing anonymous `bounds: {west, east, south, north}` format and auto-convert it to a named bounds dict.

#### Scenario: Anonymous bounds auto-converted
- **WHEN** a config file contains `bounds: {west: 5.96, east: 10.49, south: 45.82, north: 47.81}`
- **THEN** the loader SHALL treat it as file-level anonymous bounds (existing behavior) and NOT as named bounds
- **AND** the anonymous bounds SHALL be inherited by layers/targets as before

#### Scenario: Detection of anonymous vs named
- **WHEN** the `bounds` key's value contains keys from `{west, east, south, north}` and no other keys
- **THEN** the loader SHALL treat it as anonymous bounds
- **WHEN** the `bounds` key's value contains any key NOT in `{west, east, south, north}`
- **THEN** the loader SHALL treat it as named bounds

### Requirement: Bounds slug references on targets
`TargetConfig.bounds` SHALL accept a string slug referencing a named bounds entry, inline coordinates, or `None`.

#### Scenario: Target references named bounds by slug
- **WHEN** a target config has `bounds: switzerland`
- **THEN** the loader SHALL resolve it to the named bounds with that slug after all bounds are loaded

#### Scenario: Target with inline bounds
- **WHEN** a target config has `bounds: {west: 5.96, east: 10.49, south: 45.82, north: 47.81}`
- **THEN** the loader SHALL parse it as inline coordinates (no resolution needed)

#### Scenario: Target with unresolved bounds slug
- **WHEN** a target config references `bounds: nonexistent`
- **AND** no named bounds with that slug exist
- **THEN** the loader SHALL raise a `ValueError`

### Requirement: Bounds slug references on layers
`LayerConfig.bounds` SHALL accept the same reference types as targets.

#### Scenario: Layer references named bounds
- **WHEN** a layer config has `bounds: switzerland`
- **THEN** the loader SHALL resolve it to the named bounds with that slug

### Requirement: Named bounds merge across includes
Named bounds from included files SHALL be merged with last-file-wins semantics, identical to sources and layers.

#### Scenario: Bounds merged from includes
- **WHEN** a main config includes a file with `bounds: {a: {...}}` and also defines `bounds: {b: {...}}`
- **THEN** the loader SHALL return both `a` and `b` in `config.bounds`

#### Scenario: Duplicate bounds slug
- **WHEN** two files define `bounds: {switzerland: ...}`
- **THEN** the loader SHALL use the later definition and log a warning
