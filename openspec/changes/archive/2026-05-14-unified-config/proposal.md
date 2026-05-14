## Why

Running cartoload requires two separate config files (`-S` for sources, `-L` for layers), forcing an artificial split between conceptually related configuration. There is no way to compose reusable config pieces or to bundle source and layer definitions in a single self-contained file.

## What Changes

- **BREAKING**: Replace `-S/--sources` and `-L/--layers` CLI flags with a single repeatable `-c/--config` flag
- Introduce a unified YAML config format where a single file can contain `sources:`, `layers:`, and `bounds:` sections
- Add an `includes:` key that allows a config file to include other config files (paths relative to the declaring file)
- Includes are resolved depth-first; the current file's sections merge on top (later wins for duplicate keys)
- Circular includes are detected and raise an error
- Multiple `-c` flags on the CLI are merged in order (last wins)

## Capabilities

### New Capabilities
- `unified-config`: Unified YAML config format with `sources:`, `layers:`, `bounds:` sections and `includes:` mechanism for composing configs from multiple files

### Modified Capabilities
<!-- No existing specs need requirement changes -->

## Impact

- **`src/cartoload/config.py`**: Rewrite config loading to handle unified format, includes, and merge logic
- **`src/cartoload/cli.py`**: Replace `-S`/`-L` flags with `-c/--config`, update build command
- **`examples/configs/`**: Restructure example configs to unified format
- **`tests/`**: Update all config-related tests
- **`docs/`**: Update user-facing documentation for new config format
