## 1. Template Resolution Engine (vendored expandvars)

- [ ] 1.1 Create `src/cartoload/template.py` — vendor a simplified version of [expandvars](https://github.com/sayanarijit/expandvars) (MIT license, ~150 LOC). Keep the peek-ahead parser but strip: env var lookup, indirect expansion (`${!VAR}`), length (`${#VAR}`), get-or-set (`:=`), substitute (`:+`), strict (`:?`), offset/substring, `nounset`, file input. Provide `expand(text: str, variables: dict[str, str]) -> str` that resolves `${VAR}`, `${VAR:-default}`, bare `$VAR`, and `$$` escape.
- [ ] 1.2 Add `check_unresolved(text: str) -> list[str]` that returns a list of unresolved `${VAR}` patterns (for warning logging)
- [ ] 1.3 Add `resolve_templates(fields: list[str], variables: dict[str, str]) -> list[str]` helper for batch-resolving multiple string fields
- [ ] 1.4 Add unit tests for template resolution: plain text passthrough, `${VAR}` substitution, bare `$VAR`, `${VAR:-default}` inline default, `$$` escape, nested defaults, multiple variables, unresolved variable detection, edge cases (empty string, dollar at end of string, dollar followed by non-var char)

## 2. Config Model Updates

- [ ] 2.1 Add `defaults: dict[str, str]` field to `SourceConfig` dataclass (default empty dict)
- [ ] 2.2 Update `load_sources_file()` to parse the `defaults` key from YAML
- [ ] 2.3 Update `LayerConfig.source` field to accept `str | dict` (source ID string or dict with `ref` key + args)
- [ ] 2.4 Add `source_args: dict[str, str]` field to `LayerConfig` (default empty dict)
- [ ] 2.5 Add `source_args: dict[str, str]` field to `CompositeSubLayer` (default empty dict)
- [ ] 2.6 Update `load_layers_file()` to handle `source` as string or dict; when dict, extract `ref` as source ID and remaining keys as `source_args`
- [ ] 2.7 Add backward-compat mapping: after parsing, merge `wmts_layer` into `source_args` as `{layer: <value>}` if `layer` not already in `source_args`
- [ ] 2.8 Update `resolve_sub_layer_refs()` to merge `source_args` from referenced layers
- [ ] 2.9 Add unit tests for config parsing: source with defaults, layer with string source, layer with dict source, wmts_layer mapped to source_args, source_args overrides wmts_layer, composite sub-layer with dict source

## 3. Pipeline Integration

- [ ] 3.1 Update `get_downloader()` signature to accept `source_args: dict[str, str] | None = None`
- [ ] 3.2 In `get_downloader()`, merge `source.defaults` with `source_args`, resolve templates on `url_template` and `urls` using the vendored expandvars, and pass resolved templates to the downloader
- [ ] 3.3 Update `build_layer()` to extract `source_args` from `effective_layer.source_args` and pass to `get_downloader()`
- [ ] 3.4 Update `build_composite_layer()` to extract `source_args` from each sub-layer and pass to `get_downloader()`
- [ ] 3.5 Update `resolve_source()` to handle `LayerConfig.source` as string or dict (extract source_id from either form)

## 4. WMTS Downloader Updates

- [ ] 4.1 Update `WMTSDownloader.__init__()` to accept pre-resolved URL templates (no `layer_name` parameter needed for template resolution)
- [ ] 4.2 Update `_build_tile_url()` to use only built-in tile variables (`{x}`, `{y}`, `{z}`, `{zoom}`, `{source_id}`) — custom variables are already resolved at construction time via the vendored template engine
- [ ] 4.3 Keep `layer_name` parameter for backward compat and cache path semantics, but it no longer drives `{layer}` template substitution (that's handled by source_args)

## 5. Documentation

- [ ] 5.1 Update `docs/configuration/sources.md` to document `defaults` field and `${var:-default}` syntax
- [ ] 5.2 Update `docs/configuration/layers.md` to document `source` as string or dict, and `source_args` usage
- [ ] 5.3 Add examples showing both old-style `wmts_layer` and new-style `source: {ref: ..., layer: ...}` configs

## 6. Example Config Updates

- [ ] 6.1 Update `examples/configs/sources/swisstopo.yaml` — add `defaults: {layer: ch.swisstopo.pixelkarte-farbe, extension: jpeg}` to `swisstopo_wmts`; change `{layer}` to `${layer}` in URLs
- [ ] 6.2 Update `examples/configs/sources/france_ign.yaml` — change `{layer}` to `${layer}` in URL template
- [ ] 6.3 Update `examples/configs/layers/switzerland.yaml` — add a new layer using dict-style `source: {ref: swisstopo_wmts, layer: ch.swisstopo.pixelkarte-farbe}` alongside existing `wmts_layer` layers
- [ ] 6.4 Update `examples/configs/layers/switzerland_composite.yaml` — add a sub-layer using dict-style `source`
- [ ] 6.5 Verify existing string-style `source` + `wmts_layer` configs still work (regression test)
- [ ] 6.6 Test build with new dict-style source config against a live WMTS server
