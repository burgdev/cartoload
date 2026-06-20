## Context

Cartoload's `config.py` currently treats `bounds` as a single anonymous `dict[str, float]` at file level, inherited by all layers/targets. The `products` concept is server-specific and parsed outside `load_config()`. Both need to become first-class config sections with proper dataclasses, parsing, merging, and validation.

The current `Config` dataclass has:
- `sources: dict[str, SourceConfig]`
- `layers: dict[str, LayerConfig]`
- `targets: dict[str, TargetConfig]`
- `bounds: dict[str, float] | None` (anonymous, single)
- `settings: SettingsConfig`

The `bounds` field on `TargetConfig` and `LayerConfig` is `dict[str, float] | None` (inline coordinates only).

## Goals / Non-Goals

**Goals:**
- Named bounds section with slug-based references from targets/layers
- Products section with target reference validation
- Full backward compatibility with anonymous bounds format
- Include merging for both new sections

**Non-Goals:**
- CLI integration for bounds or products (CLI ignores these)
- Geometry support beyond axis-aligned bounding boxes
- Server-side model changes (that's a separate change in cartoload-server)

## Decisions

### Decision 1: Named bounds as a top-level section

**Choice**: Add `bounds` as a named dict section alongside `sources`, `layers`, `targets`.

```yaml
bounds:
  switzerland:
    west: 5.96
    east: 10.49
    south: 45.82
    north: 47.81
```

**Alternative considered**: Keep bounds inline only. Rejected because it prevents reuse across targets and loses identity.

**Backward compat**: When `bounds` is a dict with `west`/`east`/`south`/`north` keys (not containing named sub-dicts), treat it as anonymous file-level bounds (existing behavior). When it's a dict of dicts, treat it as named bounds section.

Detection: If any top-level key in `bounds` is not in `{west, east, south, north}`, it's named bounds. If all keys are in `{west, east, south, north}`, it's anonymous bounds.

### Decision 2: Bounds references on targets/layers as string slugs

**Choice**: `TargetConfig.bounds` and `LayerConfig.bounds` accept `str | dict[str, float] | None`.

```yaml
targets:
  my_target:
    bounds: switzerland    # slug reference
    # OR
    bounds: {west: 5.96, east: 10.49, south: 45.82, north: 47.81}  # inline
```

**Rationale**: String references are resolved during validation. Inline coordinates are parsed directly. `None` means inherit from file-level bounds.

### Decision 3: Products as a declarative section

**Choice**: `ProductConfig` with `targets: list[str]` referencing target slugs.

```yaml
products:
  outdoor-winter:
    name: "Outdoor Winter"
    price: 25.0
    currency: CHF
    targets: [ch_outdoor_winter]
```

Validation checks that all target refs exist. Not used by CLI pipeline.

### Decision 4: New dataclasses

```python
@dataclass
class BoundsConfig:
    id: str
    west: float
    east: float
    south: float
    north: float

@dataclass
class ProductConfig:
    id: str
    name: str = ""
    price: float = 0.0
    currency: str = "CHF"
    token_max_downloads: int = 5
    token_expiry_days: int = 30
    sort_order: int = 0
    targets: list[str] = field(default_factory=list)
```

`Config` changes:
- `bounds: dict[str, BoundsConfig]` (was `dict[str, float] | None`)
- `products: dict[str, ProductConfig]` (new)

## Risks / Trade-offs

- **[Backward compat for `bounds` key]** → Detect anonymous vs named format based on key names. All existing configs use `{west, east, south, north}` keys, which won't collide with named bounds keys like `switzerland`.
- **[Config type change]** → `Config.bounds` changes from `dict[str, float] | None` to `dict[str, BoundsConfig]`. This is a **BREAKING** change for consumers that read `config.bounds` directly. The cartoload-server import command will need updating in a coordinated change.
- **[Target bounds resolution]** → String refs need resolution after all bounds are loaded. Add a `resolve_bounds_refs()` step.
