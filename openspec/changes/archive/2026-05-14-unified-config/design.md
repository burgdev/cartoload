## Context

cartoload currently uses two separate config file types loaded via `-S/--sources` and `-L/--layers` CLI flags. Sources and layers are defined in different YAML files with different top-level keys (`sources:` vs `layers:` + `bounds:`). The `load_config()` function in `config.py` handles separate loading and merging pipelines for each.

The existing merge logic (`merge_sources()`, `merge_layers()`) already supports multiple files with last-wins semantics. Source references from layers are resolved after merge. Sub-layer refs within composite layers are also resolved post-merge.

## Goals / Non-Goals

**Goals:**
- Single unified YAML config format where any file can contain `sources:`, `layers:`, `bounds:`, and `includes:`
- Include mechanism for composing configs from reusable pieces
- Replace `-S`/`-L` with single repeatable `-c/--config` flag
- Keep existing merge, validation, and reference resolution logic intact

**Non-Goals:**
- Glob patterns in includes (e.g., `sources/*.yaml`) — can be added later
- Conditional includes — overcomplicated for now
- Config file auto-discovery (e.g., looking for `cartoload.yaml` in CWD) — nice-to-have, not in scope
- Backward compatibility with `-S`/`-L` flags — clean break, users adapt existing files

## Decisions

### 1. Unified file format with optional sections

A config file can contain any combination of `sources:`, `layers:`, `bounds:`, and `includes:`. All sections are optional. A file with only `sources:` is a valid sources-only config. A file with only `layers:` is a valid layers-only config.

**Rationale:** This is the simplest approach. No file type detection needed. No mode flags. The parser treats every file the same way.

### 2. `includes:` as flat list, relative to declaring file

```yaml
includes:
  - ../sources/swisstopo.yaml
  - ./overlays.yaml
```

Paths are resolved relative to the directory containing the file that declares the include. Included files use the same unified format.

**Rationale:** This is what Docker Compose, kustomize, and most YAML-based tools do. Relative-to-file is intuitive and works regardless of CWD.

### 3. Depth-first include resolution with cycle detection

Loading order:
1. Open file, parse YAML
2. Process `includes:` list in order
3. For each include, recursively load (depth-first)
4. Merge included results in order
5. Merge current file's sections on top

Cycle detection: maintain a `set[Path]` of resolved file paths being loaded. If a path is already in the set, raise `ValueError`.

**Rationale:** Depth-first matches mental model — includes are "pulled in" before the current file adds its own definitions. Cycle detection is essential for safety.

### 4. Merge strategy: later-wins at key level

For `sources:` and `layers:` dicts: if the same key appears in multiple files, the last definition wins (with a warning log, matching current behavior).

For `bounds:`: if multiple files define file-level bounds, the last definition wins (with a warning log, matching current behavior).

**Rationale:** This matches the existing merge behavior in `merge_sources()` and `merge_layers()`. No new merge semantics needed.

### 5. CLI: `-c/--config` for config, `-C` for cache-dir

```
cartoload build -c cartoload.yaml -l ch_basemap
cartoload build -c base.yaml -c overrides.yaml -l ch_basemap
```

Remove `-S`/`--sources` and `-L`/`--layers` from all commands (`build`, `download`, `list`). Change `-c` short flag for `--cache-dir` to `-C` (uppercase). Config is used far more frequently than cache-dir, so `-c` goes to config.

### 6. `settings` section for runtime defaults

A new top-level `settings:` section in config files holds runtime defaults that can otherwise be set via CLI flags. This lets users pin common settings in their config:

```yaml
settings:
  cache_dir: ./cache
  output_dir: ./output
  executor: thread
  quality: 85
  rate_limit_ms: 150
```

**Resolution order** (highest priority wins):
1. CLI flag (e.g., `--quality 90`)
2. Environment variable (e.g., `CARTOLOAD_CACHE_DIR=/tmp/cache`)
3. Config file `settings:` section
4. Built-in default

**Environment variable mapping:** `CARTOLOAD_<UPPER_SNAKE_KEY>`. Examples:
- `settings.cache_dir` ← `CARTOLOAD_CACHE_DIR`
- `settings.output_dir` ← `CARTOLOAD_OUTPUT_DIR`
- `settings.executor` ← `CARTOLOAD_EXECUTOR`
- `settings.quality` ← `CARTOLOAD_QUALITY`

This follows the established `CARTOLOAD_EXECUTOR` pattern already in use in `cli.py`.

**Merge:** `settings` sections merge at the key level across includes — same later-wins semantics as sources/layers.

### 7. Internal architecture

Replace `load_config(source_paths, layer_paths)` with `load_config(config_paths)`.

The new loading pipeline:

```
load_config(paths)
  → for each path: load_unified_file(path, seen=set)
      → parse YAML
      → resolve and load includes (recursive, with cycle check)
      → merge included results
      → parse current file's sources/layers/bounds/settings
      → merge current file on top
  → merge all top-level results (for multiple -c flags)
  → resolve_sub_layer_refs()
  → resolve_references()
  → resolve_settings(settings) — apply env vars over config defaults
  → return Config(sources, layers, bounds, settings)
```

The existing `load_sources_file()` and `load_layers_file()` functions will be refactored into internal helpers that extract `sources:` and `layers:` sections from a unified dict, rather than being entry points. The validation logic stays the same.

## Risks / Trade-offs

- **Breaking change for all users** → Clean break is acceptable per user decision. Migration is straightforward: combine source and layer files, or add `includes:` to reference existing files.
- **Deep include chains** → Could make debugging harder. Mitigate by logging the include chain when warnings occur (e.g., "Source 'x' overridden by file at foo.yaml, included from bar.yaml").
- **Settings precedence confusion** → Users might not know whether their CLI flag, env var, or config setting won. Mitigate by logging the resolved value at startup when `-v` is used.
