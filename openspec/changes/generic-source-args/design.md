## Context

Cartoload uses a two-file config system: sources define where to get geodata, layers define what to build. Currently, WMTS URL templates support a hardcoded set of variables (`{x}`, `{y}`, `{z}`, `{layer}`, `{source_id}`) via simple `.replace()` calls in `WMTSDownloader._build_tile_url()`. The `{layer}` variable is populated through a dedicated `wmts_layer` field on `LayerConfig`, passed as `layer_name` through the pipeline to the downloader.

This approach has limitations:
- Each new template variable requires a dedicated config field, pipeline parameter, and downloader wiring
- `wmts_layer` is the only layer-specific parameter — no way to customize other URL parts (version, extension, style, etc.)
- The `source` field on layers is a plain string (source ID), not rich enough to carry parameters
- Composite sub-layers also carry `wmts_layer` as a one-off

The user wants a generic mechanism where any source string field can reference template variables, with defaults defined on the source and overrides provided by layers.

## Goals / Non-Goals

**Goals:**
- Generic `{var}` and `{var:default}` syntax in all source string fields (urls, attribution)
- `defaults` dict on `SourceConfig` for source-level default values
- `source_args` dict on layers for layer-specific variable overrides
- Backward compatibility: existing `wmts_layer` field maps to `source_args: {layer: <value>}`
- Central template resolution engine, reusable across source types
- Support built-in variables that are always available per source type (`{x}`, `{y}`, `{z}`, `{source_id}`)

**Non-Goals:**
- Complex template logic (conditionals, loops, expressions) — simple variable substitution only
- Validation of variable names — unknown variables are left as-is
- Per-tile variable resolution (variables are resolved once per source+layer, not per tile request)
- Changes to the IMG writer or compositing pipeline — this only affects config→downloader flow
- Removing `wmts_layer` from the config model — it remains as a convenience shorthand

## Decisions

### D1: Unix-style `${VAR:-default}` syntax via vendored expandvars

**Decision**: Use `${VAR}` and `${VAR:-default}` syntax, vendoring a stripped-down version of [expandvars](https://github.com/sayanarijit/expandvars) (MIT license) directly into `src/cartoload/template.py`. We keep the robust peek-ahead parser from expandvars but strip it down to only what we need:

- `${VAR}` — simple variable substitution
- `${VAR:-default}` — substitution with inline default
- Bare `$VAR` — also supported (alphanumeric/underscore names only)
- `$$` — escaped literal `$`

Removed from expandvars: env variable lookup (`os.environ`), indirect expansion (`${!VAR}`), length operator (`${#VAR}`), get-or-set default (`${VAR:=default}`), substitute-if-set (`${VAR:+value}`), strict error (`${VAR:?error}`), offset/substring (`${VAR:offset:length}`), `nounset` mode, file handle input.

The function signature is `expand(text: str, variables: dict[str, str]) -> str` — takes a mapping instead of `os.environ`. The variable symbol is `$` (Unix-style), not `{}` (Python format-style).

**Rationale**: expandvars is a well-known, battle-tested pattern (~350 LOC) with proper handling of edge cases (nested braces, escaping, peek-ahead parsing). Vendoring a simplified version (~150 LOC) avoids an external dependency and lets us tailor the API (dict-based lookup, no env vars). The `$` prefix clearly distinguishes template variables from literal text (unlike `{var}` which collides with JSON/YAML braces).

**Alternative**: A custom regex-based `{var:default}` engine is simpler to write but handles edge cases poorly (nested braces, escaping). Using `expandvars` as a pip dependency adds an external dep for ~150 lines of vendored code. Vendoring a simplified version gives us the best of both: robust parsing, no dependency.

### D2: `defaults` on source, `source_args` on layer

**Decision**: `SourceConfig` gets a `defaults: dict[str, str]` field. `LayerConfig` and `CompositeSubLayer` get `source_args: dict[str, str]`. Resolution order: built-in vars → source defaults → layer source_args → inline `{var:default}` values.

**Rationale**: Source defines the baseline, layer customizes per-use. This mirrors the existing pattern where `wmts_layer` is specified per layer. Using a dict is more extensible than adding dedicated fields for each variable.

### D3: `source` field accepts string or dict

**Decision**: The `source` field on `LayerConfig` can be either a string (source ID, backward compatible) or a dict with `ref` (source ID) and arbitrary key-value pairs that become `source_args`.

```yaml
# String (backward compatible)
source: swisstopo_wmts

# Dict (new, with args)
source:
  ref: swisstopo_wmts
  wmts_layer: ch.swisstopo.pixelkarte-farbe
  wmts_extension: jpeg
```

**Rationale**: Keeping the string form for simple cases avoids unnecessary nesting. The dict form is only needed when passing arguments. Keys in the dict become `source_args` entries.

**Alternative**: A separate `source_args` field alongside `source` would keep the schema cleaner but adds clutter for the common case.

### D4: `wmts_layer` remains as convenience shorthand

**Decision**: `wmts_layer` on `LayerConfig` and `CompositeSubLayer` continues to work. If both `wmts_layer` and `source_args` (or `source` dict) provide a `layer` value, the explicit `source_args`/dict value takes precedence. During config loading, `wmts_layer` is merged into `source_args` as `{layer: <value>}`.

**Rationale**: Breaking backward compatibility would require all existing configs to be updated. The mapping is straightforward: `wmts_layer: foo` → `source_args.layer = "foo"`. The `wmts_layer` field can be deprecated later.

### D5: Template resolution happens at downloader creation time

**Decision**: Variables are resolved once when the downloader is created (in `get_downloader()`), not per-tile. The resolved URL templates are stored in the downloader instance. Built-in tile variables (`{x}`, `{y}`, `{z}`) are still substituted per-tile in `_build_tile_url()`.

**Rationale**: Source defaults and layer args don't change between tiles — they're config-level values. Only tile coordinates vary per request. Resolving once avoids redundant work and keeps the per-tile path fast.

### D6: Built-in variables use the same `${VAR}` syntax

**Decision**: Per-tile variables (`${x}`, `${y}`, `${z}`, `${zoom}`, `${source_id}`, `${layer}`) use the same `${VAR}` syntax as config-level variables. The template engine resolves config-level variables first (at downloader construction time), leaving per-tile variables unresolved. The WMTS downloader resolves per-tile variables at download time via the same `expand()` function. Legacy `{x}`, `{y}`, `{z}` syntax is also supported for backward compat.

**Rationale**: Having two different syntaxes (`${VAR}` for config vars, `{VAR}` for tile vars) is confusing and "wired". Using one unified syntax is cleaner and more predictable. The template engine naturally handles this — it leaves unresolved `${VAR}` patterns as-is, which are then resolved at download time.

**Alternative**: Keep two separate syntaxes. This avoids ambiguity but creates a cognitive burden for config authors.

## Risks / Trade-offs

- **Config complexity**: The dict form of `source` adds nesting. → Mitigation: String form remains the default; dict is opt-in. Documentation shows both.
- **Breaking change if `source` type changes**: Code that assumes `source` is always a string must be updated. → Mitigation: Config loader normalizes to (source_id, source_args) tuple immediately. All downstream code sees a consistent interface.
- **Variable name collisions**: User could define a variable named `x` in defaults/args, colliding with built-in. → Mitigation: Built-ins are resolved first and cannot be overridden. Document this clearly.
- **Template errors are silent**: Unknown `{var}` patterns left as-is in URLs → 404 errors at download time. → Mitigation: Log a warning during config loading if any unresolved variables remain after resolution.
- **Migration**: Existing configs with `wmts_layer` work without changes. The `source` dict form is purely additive. No migration needed.
