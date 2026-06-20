## Tasks

- [x] Add `BoundsConfig` dataclass with `id`, `west`, `east`, `south`, `north` fields
- [x] Add `ProductConfig` dataclass with `id`, `name`, `price`, `currency`, `token_max_downloads`, `token_expiry_days`, `sort_order`, `targets` fields
- [x] Update `Config` dataclass: change `bounds` from `dict[str, float] | None` to `dict[str, BoundsConfig]`, add `products: dict[str, ProductConfig]`
- [x] Update `TargetConfig.bounds` and `LayerConfig.bounds` type to `str | dict[str, float] | None`
- [x] Add `_parse_bounds_section()` to detect anonymous vs named bounds format and parse accordingly
- [x] Add `_parse_products_section()` to parse the products section with validation
- [x] Update `_parse_layers_section()` to return named bounds alongside layers (replace anonymous bounds return)
- [x] Update `_parse_targets_section()` to handle string bounds references
- [x] Add `merge_bounds()` helper with last-file-wins semantics (like `merge_sources()`)
- [x] Add `merge_products()` helper with last-file-wins semantics
- [x] Add `resolve_bounds_refs()` to resolve string bounds references on targets/layers to concrete `BoundsConfig` objects
- [x] Update `resolve_references()` to validate product target references
- [x] Update `_load_unified_file()` to parse and merge named bounds and products sections
- [x] Update `load_config()` to return `Config` with new bounds and products fields, and call `resolve_bounds_refs()`
- [x] Add tests for named bounds parsing, anonymous compat, slug references, merge, and validation
- [x] Add tests for products section parsing, target validation, merge, and defaults
