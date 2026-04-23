## 1. YAML Parsing for Sources

- [x] 1.1 Add `load_sources_file(path: str) -> dict[str, SourceConfig]` to `config.py` that reads a YAML file, validates the top-level `sources` key exists, and returns a dict of `SourceConfig` instances keyed by source ID
- [x] 1.2 Validate that each source entry has a `type` field; raise `ValueError` with source ID and file path if missing
- [x] 1.3 Validate that each source entry has a `type` value in the allowed set (`wmts`, `geotiff` for Phase 1); raise `ValueError` with the invalid type and the list of valid types if not
- [x] 1.4 Validate type-specific required fields: `url_template` is required for `wmts` sources, `stac_url` is required for `geotiff` sources; raise `ValueError` with the field name and source ID if missing
- [x] 1.5 Validate optional fields (`attribution`, `rate_limit_ms`, `max_threads`) have correct types when present; provide sensible defaults when absent

## 2. YAML Parsing for Layers

- [x] 2.1 Add `load_layers_file(path: str) -> tuple[dict[str, LayerConfig], dict | None]` to `config.py` that reads a YAML file, validates the top-level `layers` key exists, and returns a dict of `LayerConfig` instances plus optional `bounds`
- [x] 2.2 Validate that each layer entry has required fields (`name`, `type`, `source`, `zoom_levels`, `exporter`, `output`); raise `ValueError` with layer ID and file path if any are missing
- [x] 2.3 Validate that `zoom_levels` is a non-empty list of integers within the range 0-22; raise `ValueError` with the layer ID and the problematic value if not
- [x] 2.4 Validate that `bounds` (if present) contains numeric `west`, `east`, `south`, `north` fields where west < east and south < north; raise `ValueError` if not

## 3. Multi-File Merging

- [x] 3.1 Add `merge_sources(*source_dicts: dict[str, SourceConfig]) -> dict[str, SourceConfig]` that merges multiple source dicts with last-file-wins semantics for duplicate keys
- [x] 3.2 Add `merge_layers(*layer_results: tuple[dict[str, LayerConfig], dict | None]) -> tuple[dict[str, LayerConfig], dict | None]` that merges multiple layer dicts with last-file-wins for both layers and bounds
- [x] 3.3 Log a warning (via `logging.warning`) when a key is overwritten during merge, including the key name and which file provided the overriding value

## 4. Source Reference Resolution

- [x] 4.1 Add `resolve_references(layers: dict[str, LayerConfig], sources: dict[str, SourceConfig]) -> None` that checks every layer's `source` field against the loaded sources dict
- [x] 4.2 Raise `ValueError` for each unresolved reference, including the layer ID, the referenced source ID, and the list of available source IDs
- [x] 4.3 Handle multiple unresolved references in a single error message so the user can fix all problems at once

## 5. Top-Level Loader and Config Container

- [x] 5.1 Add a `Config` dataclass to `config.py` holding `sources: dict[str, SourceConfig]`, `layers: dict[str, LayerConfig]`, and `bounds: dict | None`
- [x] 5.2 Add `load_config(source_paths: list[str], layer_paths: list[str]) -> Config` that orchestrates loading all files, merging, validating, and resolving references into a single `Config` object
- [x] 5.3 Handle `FileNotFoundError` with a clear message when a provided config file path does not exist

## 6. List CLI Command

- [x] 6.1 Update the `list` command in `cli.py` to accept `--sources` and `--layers` as repeatable path options
- [x] 6.2 Call `load_config` with the provided paths and handle `ValueError` by printing the error message and exiting with non-zero status
- [x] 6.3 Print each layer as a formatted line (or Rich table) showing layer ID, name, source, zoom levels, and exporter
- [x] 6.4 Print a helpful message when no `--sources` or `--layers` paths are provided

## 7. Tests

- [x] 7.1 Test loading a valid single source YAML file and verifying all `SourceConfig` fields
- [x] 7.2 Test loading a valid single layer YAML file and verifying all `LayerConfig` fields and bounds
- [x] 7.3 Test that loading a source file without the `sources` key raises `ValueError`
- [x] 7.4 Test that loading a layer file without the `layers` key raises `ValueError`
- [x] 7.5 Test that a source entry with an unknown `type` raises `ValueError`
- [x] 7.6 Test that a source entry missing a type-specific required field raises `ValueError`
- [x] 7.7 Test that a layer entry missing a required field raises `ValueError`
- [x] 7.8 Test that invalid zoom levels (empty list, out of range) raise `ValueError`
- [x] 7.9 Test merging two source files with disjoint keys produces a dict with all keys
- [x] 7.10 Test merging two source files with overlapping keys uses last-file-wins
- [x] 7.11 Test merging two layer files with overlapping keys and bounds uses last-file-wins
- [x] 7.12 Test that unresolved source references raise `ValueError` with layer ID and available source IDs
- [x] 7.13 Test that resolved source references produce a valid `Config` without errors
- [x] 7.14 Test `load_config` with a nonexistent file path raises `FileNotFoundError` with a clear message
- [x] 7.15 Test the `list` CLI command with valid config files produces expected output
- [x] 7.16 Test the `list` CLI command with no config files produces a "no files provided" message
- [x] 7.17 Test the `list` CLI command with invalid config files exits with non-zero status and prints the error
