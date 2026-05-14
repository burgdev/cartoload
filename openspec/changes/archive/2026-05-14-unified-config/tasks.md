## 1. Config Loading Core

- [x] 1.1 Refactor `load_sources_file()` into `_parse_sources_section(data, path)` that extracts `sources:` from a unified YAML dict, reusing existing validation logic
- [x] 1.2 Refactor `load_layers_file()` into `_parse_layers_section(data, path)` that extracts `layers:` and `bounds:` from a unified YAML dict, reusing existing validation logic
- [x] 1.3 Implement `_load_unified_file(path, seen)` with depth-first include resolution, circular detection via `seen: set[Path]`, and merge of included results
- [x] 1.4 Implement new `load_config(config_paths: list[str]) -> Config` that calls `_load_unified_file` for each path and merges results, then runs `resolve_sub_layer_refs()` and `resolve_references()`

## 2. Settings Support

- [x] 2.1 Add `SettingsConfig` dataclass with fields: `cache_dir`, `output_dir`, `executor`, `quality`, `rate_limit_ms` (all optional with None defaults)
- [x] 2.2 Add `settings` field to `Config` dataclass
- [x] 2.3 Implement `_parse_settings_section(data, path)` to extract and validate `settings:` from a unified YAML dict
- [x] 2.4 Implement `resolve_settings(settings)` that merges config settings with env vars (`CARTOLOAD_<KEY>`) — env vars override config, CLI flags override env vars
- [x] 2.5 Integrate settings resolution into the CLI commands: use resolved settings as defaults, let explicit CLI flags override

## 3. CLI Changes

- [x] 3.1 Replace `-S`/`--sources` and `-L`/`--layers` flags with `-c`/`--config` (repeatable) in the `build` command
- [x] 3.2 Change `--cache-dir` short flag from `-c` to `-C` in `build` and `cache` commands
- [x] 3.3 Update `build` command to call new `load_config(list(config_paths))` and apply resolved settings
- [x] 3.4 Apply same CLI changes to `download` command
- [x] 3.5 Apply same CLI changes to `list` command

## 4. Example Configs

- [x] 4.1 Restructure `examples/configs/sources/swisstopo.yaml` to unified format (add `sources:` as only section, keep content)
- [x] 4.2 Restructure `examples/configs/layers/switzerland.yaml` to unified format
- [x] 4.3 Restructure `examples/configs/layers/test.yaml` to unified format
- [x] 4.4 Create a top-level `examples/configs/cartoload.yaml` that uses `includes:` to compose swisstopo sources and switzerland layers
- [x] 4.5 Verify the test command from AGENTS.md still works with new `-c` flag

## 5. Tests

- [ ] 5.1 Update existing config loading tests to use new `load_config(paths)` signature
- [ ] 5.2 Add tests for unified format: file with all sections, sources-only, layers-only, empty
- [ ] 5.3 Add tests for includes: single, multiple, nested, missing file
- [ ] 5.4 Add tests for circular include detection: direct and indirect
- [ ] 5.5 Add tests for merge semantics: duplicate sources, duplicate layers, duplicate bounds
- [ ] 5.6 Add tests for settings: config-only, merge across includes, absent settings
- [ ] 5.7 Add tests for env var override: env overrides config, CLI overrides env, env with no config
- [ ] 5.8 Update CLI tests (`tests/test_cli.py`) to use `-c` flag instead of `-S`/`-L`

## 6. Documentation

- [ ] 6.1 Update docs to reflect new unified config format, `-c` flag, and `settings` section with env var support
- [ ] 6.2 Run `just check` and `just check types` to verify formatting and types
- [ ] 6.3 Run `just test` and ensure all tests pass
