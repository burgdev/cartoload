## Why

The CLI and pipeline need to load and merge user-provided YAML config files (sources + layers) at runtime. The scaffolding created stub dataclasses in `config.py`, but there's no logic to parse YAML, validate field types, merge multiple files, or resolve cross-references between source IDs and layer definitions. This is a prerequisite for every downstream feature — the downloader, processor, and exporter all consume config objects.

## What Changes

- Implement YAML parsing in `config.py` to load source and layer config files from disk
- Implement config merging: multiple `--sources` and `--layers` files are merged into a unified config at runtime
- Implement source reference resolution: layers reference sources by ID, and the loader resolves these references
- Add validation: missing required fields, unknown source types, unresolved source references, invalid zoom levels
- Implement the `list` CLI command using the config loader

## Capabilities

### New Capabilities

- `config-loader`: Parse, merge, validate, and resolve user-provided YAML source and layer config files into typed Python dataclass objects

### Modified Capabilities

- `package-skeleton`: The stub `config.py` dataclasses gain parsing, merging, and validation logic; the `cli.py` `list` command becomes functional

## Impact

- **Code**: `src/cartoload/config.py` grows from stub dataclasses to a full loader; `src/cartoload/cli.py` `list` command becomes functional
- **Dependencies**: PyYAML (already in deps) — no new dependencies
- **Tests**: New `tests/test_config.py` with coverage for parsing, merging, validation, and error cases
