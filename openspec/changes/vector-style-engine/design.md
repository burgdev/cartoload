## Context

The gpkg-download change provides GeoPackage files with vector features and attributes. To render these features visually, we need a style system that maps feature attributes to visual properties. This style system must serve two downstream consumers:

1. **Path B (Pillow rasterizer)** — needs color, width, dash, border, opacity for drawing on transparent PNG tiles
2. **Path C (mkgmap pipeline)** — needs Garmin type codes, resolution ranges, and visual properties for TYP file generation

The key constraint: both consumers should use the **same style definition**, so the visual output is consistent whether the user rasterizes the overlay or generates a vector IMG.

## Goals / Non-Goals

**Goals:**
- Parse three style tiers into a unified internal model
- Evaluate match expressions against feature attributes
- Support zoom-dependent styling with nearest-zoom fallback
- Provide a clean API for downstream consumers (rasterizer, mkgmap generator)
- No external dependencies beyond stdlib

**Non-Goals:**
- Actual rendering (Path B rasterizer change)
- mkgmap style/TYP file generation (Path C change)
- Point/polygon symbols (start with lines only, extend later)
- Label styling (deferred)
- Creating or editing QML files (read-only)

## Decisions

### 1. Internal style model: flat list of rules

**Decision:** The internal model is a flat list of `StyleRule` objects, each containing a match expression and a list of zoom-keyed `LineStyle` objects.

```python
@dataclass
class LineStyle:
    color: tuple[int, int, int]     # RGB
    width: float                    # pixels at tile resolution
    dash: list[float] | None        # dash pattern [on, off, ...]
    border_color: tuple[int, int, int] | None
    border_width: float | None
    opacity: float = 1.0

@dataclass
class StyleRule:
    match: MatchExpression
    zoom_styles: dict[int, LineStyle]  # zoom → style
    default_style: LineStyle
    garmin: GarminStyle | None      # optional Garmin type mapping

@dataclass
class GarminStyle:
    type: int                       # Garmin type code (e.g., 0x16)
    resolution: tuple[int, int]     # (min, max) Garmin resolution range
```

**Rationale:** Flat rules are simple to evaluate (iterate, first match wins). Zoom-keyed styles avoid nested conditions. The `garmin` field is optional — Path B ignores it, Path C uses it.

### 2. Match expression AST

**Decision:** Parse match strings into a small AST that supports mkgmap-compatible syntax.

Supported expressions:
- `tag=value` → exact match
- `tag!=value` → not equal
- `tag=*` → tag exists
- `tag!=*` → tag absent
- `tag~regex` → regex match
- `tag>number`, `tag>=number`, `tag<number`, `tag<=number` → numeric comparison
- `*` → match everything (fallback)
- `expr1 & expr2` → AND
- `expr1 | expr2` → OR
- `!(expr)` → NOT

**Rationale:** This is a strict subset of mkgmap's rule syntax. By matching mkgmap's expression language, the same `match` string can be used both for evaluating features in Python (Path B) and for generating mkgmap style rules (Path C) with zero translation. The parser is simple (~100 lines) since we don't need mkgmap's full function support (`length()`, `area_size()`, etc.).

### 3. QML parsing: reduced feature set

**Decision:** Parse only `categorizedSymbol` and `RuleRenderer` renderer types. Only `SimpleLine` symbol layer class. Skip `ArrowLine`, `MarkerLine`, effects, data-defined properties.

**Rationale:** These cover the vast majority of line styling use cases (color, width, dash, casing via multi-layer). ArrowLine and complex effects have no Garmin equivalent anyway. The reduced set keeps parsing tractable.

**QML → internal model mapping:**
- Each category/rule → one `StyleRule` with the filter expression as the match
- Each symbol with multiple `<layer>` elements → detect casing (wider layer = border)
- `scalemindenom`/`scalemaxdenom` → zoom levels (using an approximate scale-to-zoom table)

### 4. Zoom level handling

**Decision:** Zoom styles are stored as a dict keyed by integer zoom level. When resolving a style for a given zoom, use the nearest defined zoom level at or below the requested zoom. If no such zoom exists, use `default_style`.

```python
def resolve_style(rule: StyleRule, zoom: int) -> LineStyle:
    # Find the nearest zoom at or below the requested zoom
    candidates = [z for z in rule.zoom_styles if z <= zoom]
    if candidates:
        return rule.zoom_styles[max(candidates)]
    return rule.default_style
```

**Rationale:** This matches the cartoload pipeline model where zoom levels are integers. "At or below" means a style defined at zoom 12 applies to zoomes 12, 13, 14, etc. unless a more specific zoom is defined. This is intuitive — you define styles at the zoom where they first appear.

### 5. Module structure

**Decision:** Place style code in `src/cartoload/style/` as a sub-package.

```
src/cartoload/style/
├── __init__.py          # public API: StyleEngine, resolve_style
├── model.py             # LineStyle, StyleRule, GarminStyle dataclasses
├── match.py             # MatchExpression parser and evaluator
├── yaml_parser.py       # Parse inline YAML style definitions
└── qml_parser.py        # Parse QGIS QML files
```

**Rationale:** Separate concerns, each file is small and testable. The `match.py` parser is reused by both YAML and QML parsing.

### 6. Config integration

**Decision:** Layer config gets two optional fields for styling:

```yaml
layers:
  skitouren:
    source: {type: gpkg, url: "..."}
    zoom_levels: [10, 11, 12, 13, 14]

    # Option A: inline rules (Tier 1/2)
    rules:
      - match: "difficulty=L"
        style: {color: "#33A02C", width: 1}
      - match: "difficulty=WS"
        style:
          zoom:
            10: {color: "#FF8800", width: 0.5}
            14: {color: "#FF8800", width: 2, dash: [4,4], border: {color: white, width: 1}}
          default: {color: "#FF8800", width: 1}
        garmin: {type: 0x16, resolution: [16, 24]}

    # Option B: QGIS QML file (Tier 3)
    style: "styles/skitouren.qml"
    garmin_types:          # needed only for Path C with QML
      L: {type: 0x16, resolution: [18, 24]}
      WS: {type: 0x16, resolution: [16, 24]}
```

If both `rules` and `style` are present, `rules` takes precedence (allows overriding QGIS styles inline).

## Risks / Trade-offs

- **[QML format drift]** QGIS may change QML format in future versions. → QML has been stable since QGIS 2.x. We parse a reduced feature set which is less likely to break.
- **[Match expression subset]** Not all mkgmap expressions are supported (no functions like `length()`, `area_size()`). → Can be extended when needed. Basic tag matching covers 95% of use cases.
- **[Scale-to-zoom approximation]** Converting QGIS scale denominators to zoom levels is approximate. → Use a lookup table with reasonable defaults. Users can override with inline `rules` if the mapping is wrong.
