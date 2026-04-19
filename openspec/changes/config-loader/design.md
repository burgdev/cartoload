## Context

The project-scaffolding change created stub dataclasses (`SourceConfig`, `LayerConfig`) in `config.py` and a placeholder `list` command in `cli.py`. The YAML config schema is documented in SPEC.md and example config files exist in `examples/configs/`. However, there is no logic to parse YAML files into typed dataclass instances, merge multiple files, validate required fields, or resolve source references from layer definitions.

Every downstream feature -- the WMTS downloader, GeoTIFF downloader, raster processor, and Garmin IMG exporter -- consumes config objects. Until config loading works, nothing else can function.

## Goals / Non-Goals

**Goals:**

- Parse YAML source files into `dict[str, SourceConfig]` keyed by source ID
- Parse YAML layer files into `dict[str, LayerConfig]` keyed by layer ID, preserving file-level `bounds`
- Merge multiple source files and multiple layer files into unified dictionaries (later files win on key conflicts)
- Resolve source references: each `LayerConfig.source` string is matched against the loaded sources; raise a clear error if a layer references a source ID that was never loaded
- Validate required fields and value types on every parsed config entry, raising `ValueError` with a human-readable message that includes the file path, the config key, and what is wrong
- Make the `cartoload list` CLI command functional: load and merge all provided `--sources` and `--layers` files, then print each layer's ID, name, source, zoom levels, and exporter

**Non-Goals:**

- Downloading tiles or processing rasters -- that is the wmts-downloader and raster-processor changes
- Exporting `.img` files -- that is the garmin-img-exporter change
- Validating URL reachability or network connectivity
- Supporting config generation or writing YAML files back to disk

## Decisions

### 1. Plain dataclasses, not pydantic

**Choice**: Continue using `@dataclass` for `SourceConfig` and `LayerConfig`.

**Rationale**: The project-scaffolding decision is already settled. Plain dataclasses keep the dependency tree lean. Validation is done explicitly in loader functions rather than via a framework.

### 2. PyYAML for parsing

**Choice**: Use `yaml.safe_load()` from PyYAML (already a runtime dependency).

**Rationale**: PyYAML is listed in SPEC.md as a runtime dependency. `safe_load` is the standard safe deserializer. No need for advanced YAML features (anchors, custom tags) in user configs.

### 3. Raise ValueError on validation errors

**Choice**: Raise `ValueError` with a descriptive message for every validation failure (missing required field, unknown source type, unresolved source reference, invalid zoom levels).

**Rationale**: `ValueError` is the natural Python exception for bad input. Each message includes the file path, the config key (source ID or layer ID), the field name, and what was expected. This gives users actionable feedback without a custom exception hierarchy.

### 4. Merge strategy: last file wins

**Choice**: When multiple source or layer files define the same key, the entry from the later file overwrites the earlier one.

**Rationale**: This is the simplest deterministic merge strategy. It lets users override specific entries by appending an override file to the CLI arguments. No deep-merging of individual fields -- entire source/layer entries are replaced.

### 5. Eager validation at load time

**Choice**: All validation (required fields, type checks, source type enumeration, zoom level ranges) runs immediately when configs are loaded, not lazily at access time.

**Rationale**: Fail-fast gives users immediate feedback. Lazy validation would push errors into the downloader or exporter where the context is lost. Source reference resolution (layer -> source) is a separate step that runs after all files are loaded and merged, because references can cross file boundaries.

### 6. Loader returns typed dicts

**Choice**: The top-level loader function returns `Config` -- a typed container holding `dict[str, SourceConfig]` and `dict[str, LayerConfig]`.

**Rationale**: Downstream code (pipeline, list command) needs both sources and layers together. A single `Config` object is easier to pass around than loose dictionaries. The `Config` dataclass also carries the merged `bounds` from layer files.

## Risks / Trade-offs

- **Config schema evolution** -- New source types (gpkg, geojson, pbf) will be added in Phase 2. The validation logic uses an explicit allowlist of source types, so adding a new type requires updating the loader. This is acceptable because new source types also require a new downloader implementation.
- **No schema versioning yet** -- User configs have no `version` field. If the config format changes in a breaking way, users will get `ValueError` messages. A `version` field can be added later without changing the loader architecture.
- **Last-file-wins merge may surprise users** -- If a user accidentally defines the same source ID in two files, the second silently overrides the first. Mitigated by logging a warning when a key is overwritten (not blocking, just informational).
- **Bounds merging ambiguity** -- When multiple layer files each define `bounds`, there is no single correct merge strategy (union vs. intersection vs. last-wins). The loader uses last-file-wins for bounds as well, matching the source/layer merge strategy. Users who want a different bounding box can use `--bounds` on the CLI.
