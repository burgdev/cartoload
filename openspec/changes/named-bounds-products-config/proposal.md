## Why

Bounds are currently a single anonymous `dict[str, float]` at file level — all layers and targets in a file inherit the same bounding box. The server's `MapBounds` model has a slug and name, making bounds reusable across targets. On import, bounds get a generated slug like `5.96_45.82_10.49_47.81` which is not human-readable. On export, bounds are dropped entirely. Products are parsed outside of `load_config()` in the server, losing validation and include merging.

## What Changes

- Add a `bounds` section as a named dict (`bounds: {slug: {west, east, south, north}}`) alongside backward-compatible anonymous file-level bounds
- Add a `products` section with `ProductConfig` dataclass for server-side product definitions (targets, price, etc.) — not used by the CLI but part of the schema
- Update `Config` to hold `bounds: dict[str, BoundsConfig]` and `products: dict[str, ProductConfig]`
- Update `TargetConfig.bounds` and `LayerConfig.bounds` to accept a string slug reference or inline coordinates
- Add `merge_bounds()` and `merge_products()` helpers
- Validate product target references in `resolve_references()`

## Capabilities

### New Capabilities
- `named-bounds`: Named bounds section with slug references and backward-compatible anonymous bounds
- `products-section`: Products section for server-side product definitions with target reference validation

### Modified Capabilities
- `unified-config`: Config file format gains `bounds` and `products` top-level sections

## Impact

- `src/cartoload/config.py` — new dataclasses, parsing, merging, validation
- Backward compatible: anonymous `bounds: {west: ...}` still works, auto-converts to a single unnamed entry
- Products section is optional with safe defaults
- No CLI changes needed — CLI ignores bounds slug refs and products
