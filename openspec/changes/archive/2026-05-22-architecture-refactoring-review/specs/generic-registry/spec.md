## ADDED Requirements

### Requirement: Generic Registry class
The system SHALL provide a `Registry[T]` generic class with `register(key, cls)`, `resolve(key)`, and `get_all()` methods. Both the source registry and processor registry SHALL be instances of this class.

#### Scenario: Register and resolve a type
- **WHEN** a registry is created, a class is registered with a key, and `resolve(key)` is called
- **THEN** the registered class is returned

#### Scenario: Resolve unknown key raises error
- **WHEN** `resolve("unknown")` is called on a registry with no entry for "unknown"
- **THEN** a descriptive error is raised listing available keys

#### Scenario: Source and processor registries use generic class
- **WHEN** the source and processor base modules create their registries
- **THEN** they are instances of `Registry[T]` with the same API as before

### Requirement: Pipeline resolve_source renamed
The pipeline's `resolve_source()` function (which maps layers to SourceConfig) SHALL be renamed to `resolve_source_config()` to avoid name collision with `source.resolve_source()` (which maps type strings to Source classes).

#### Scenario: No name collision
- **WHEN** both `source.resolve_source()` and `pipeline.resolve_source_config()` are used in the same file
- **THEN** they work correctly without ambiguity
