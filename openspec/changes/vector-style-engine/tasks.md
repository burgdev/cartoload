## 1. Style model

- [ ] 1.1 Create `src/cartoload/style/__init__.py` with public API exports
- [ ] 1.2 Create `src/cartoload/style/model.py` with `LineStyle`, `StyleRule`, `GarminStyle` dataclasses
- [ ] 1.3 Implement color parsing utility (`parse_color`) supporting hex (`#RRGGBB`), QGIS RGBA (`R,G,B,A`), and basic named colors
- [ ] 1.4 Write tests for color parsing (hex, hex without hash, QGIS RGBA, named colors)

## 2. Match expression parser

- [ ] 2.1 Create `src/cartoload/style/match.py` with `MatchExpression` base and node types (`ExactMatch`, `NotEqual`, `Exists`, `Absent`, `RegexMatch`, `NumericCompare`, `AndExpr`, `OrExpr`, `NotExpr`, `Wildcard`)
- [ ] 2.2 Implement `parse_match(expression: str) -> MatchExpression` — tokenize and parse mkgmap-compatible syntax
- [ ] 2.3 Implement `evaluate(expr: MatchExpression, attributes: dict) -> bool`
- [ ] 2.4 Write tests for match parsing: exact, not-equal, exists, absent, regex, numeric comparisons
- [ ] 2.5 Write tests for compound expressions: AND, OR, NOT, wildcard, mixed nesting
- [ ] 2.6 Write tests for edge cases: missing attribute, non-numeric value in numeric comparison, empty expression

## 3. YAML style parser

- [ ] 3.1 Create `src/cartoload/style/yaml_parser.py` with `parse_yaml_rules(rules: list[dict]) -> list[StyleRule]`
- [ ] 3.2 Implement parsing of simple inline styles (match + style with color/width)
- [ ] 3.3 Implement parsing of dash patterns and border/casing properties
- [ ] 3.4 Implement parsing of zoom-dependent styles (zoom dict + default fallback)
- [ ] 3.5 Implement parsing of optional `garmin` block into `GarminStyle`
- [ ] 3.6 Write tests for YAML parsing: simple rules, zoom variants, garmin mapping, border/casing, dash patterns

## 4. QML parser

- [ ] 4.1 Create `src/cartoload/style/qml_parser.py` with `parse_qml(path: str | Path) -> list[StyleRule]`
- [ ] 4.2 Implement parsing of `categorizedSymbol` renderer: extract `attr`, categories, and symbols
- [ ] 4.3 Implement parsing of `SimpleLine` symbol layers: line_color, line_width, line_style, customdash, capstyle
- [ ] 4.4 Implement casing detection: when a symbol has multiple layers, identify wider layer as border
- [ ] 4.5 Implement parsing of `RuleRenderer` type: extract filter expressions and scale ranges
- [ ] 4.6 Implement QGIS filter expression to match expression conversion (e.g., `"difficulty" = 'WS'` → `difficulty=WS`)
- [ ] 4.7 Implement scale denominator to zoom level conversion (approximate lookup table)
- [ ] 4.8 Write tests for QML parsing: categorized renderer, multi-layer casing, dashed lines, null category, rule-based renderer, scale ranges

## 5. Style engine API

- [ ] 5.1 Create `StyleEngine` class in `src/cartoload/style/__init__.py` that loads rules from YAML inline or QML file
- [ ] 5.2 Implement `StyleEngine.resolve(feature_attrs: dict, zoom: int) -> LineStyle | None` — iterate rules, evaluate match, resolve zoom, return first matching style
- [ ] 5.3 Implement config integration: parse `rules` or `style` (QML path) from `LayerConfig`
- [ ] 5.4 Handle precedence: if both `rules` and `style` are present, `rules` takes precedence
- [ ] 5.5 Write tests for StyleEngine: inline rules, QML file, mixed config, zoom resolution, no-match returns None
