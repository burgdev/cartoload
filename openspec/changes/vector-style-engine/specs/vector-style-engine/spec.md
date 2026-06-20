## ADDED Requirements

### Requirement: Parse inline YAML style rules
The system SHALL parse inline YAML style definitions from layer config, converting them into an internal style model.

#### Scenario: Simple inline rule
- **WHEN** a layer config contains `rules` with a `match` expression and a `style` dict containing `color` and `width`
- **THEN** the system SHALL create a `StyleRule` with the parsed match expression and a `LineStyle` with the given color and width

#### Scenario: Multiple rules
- **WHEN** a layer config contains multiple rules in the `rules` list
- **THEN** the system SHALL preserve rule order (first match wins at evaluation time)

#### Scenario: Rule with dash pattern
- **WHEN** a style rule defines `dash: [8, 4]`
- **THEN** the system SHALL store the dash pattern as a list of on/off lengths

#### Scenario: Rule with border/casing
- **WHEN** a style rule defines `border: {color: "#FFFFFF", width: 1}`
- **THEN** the system SHALL store the border color and width in the `LineStyle`

#### Scenario: Rule with opacity
- **WHEN** a style rule defines `opacity: 0.7`
- **THEN** the system SHALL store the opacity value in the `LineStyle`

### Requirement: Parse zoom-dependent style variants
The system SHALL support per-zoom-level style definitions within a single rule.

#### Scenario: Zoom-keyed styles
- **WHEN** a rule's `style` contains a `zoom` dict mapping zoom integers to style dicts
- **THEN** the system SHALL store each zoom-level variant in the `StyleRule.zoom_styles` dict

#### Scenario: Default style for zoom fallback
- **WHEN** a rule's `style` contains a `default` key alongside `zoom`
- **THEN** the system SHALL store it as the `StyleRule.default_style`

#### Scenario: Missing default style
- **WHEN** a rule has zoom-keyed styles but no `default` key
- **THEN** the system SHALL use the lowest-zoom style as the default

### Requirement: Resolve style for a specific zoom level
The system SHALL select the correct style variant for a given zoom level using nearest-zoom-below fallback.

#### Scenario: Exact zoom match
- **WHEN** a rule defines style at zoom 14 and zoom 14 is requested
- **THEN** the system SHALL return the zoom 14 style

#### Scenario: Nearest zoom below
- **WHEN** a rule defines styles at zoom 10 and zoom 14, and zoom 12 is requested
- **THEN** the system SHALL return the zoom 10 style (nearest at or below 12)

#### Scenario: Zoom above all definitions
- **WHEN** a rule defines styles at zoom 10 and zoom 14, and zoom 16 is requested
- **THEN** the system SHALL return the zoom 14 style (nearest at or below 16)

#### Scenario: Zoom below all definitions
- **WHEN** a rule defines styles at zoom 10 and zoom 14, and zoom 8 is requested
- **THEN** the system SHALL return the `default_style`

### Requirement: Parse match expressions
The system SHALL parse match expression strings into an evaluatable AST supporting mkgmap-compatible syntax.

#### Scenario: Exact match
- **WHEN** a match expression is `difficulty=WS`
- **THEN** the system SHALL match features where attribute `difficulty` equals `WS`

#### Scenario: Not equal
- **WHEN** a match expression is `type!=highway`
- **THEN** the system SHALL match features where attribute `type` does not equal `highway` or is absent

#### Scenario: Exists wildcard
- **WHEN** a match expression is `name=*`
- **THEN** the system SHALL match features that have a `name` attribute (any value)

#### Scenario: Absent check
- **WHEN** a match expression is `name!=*`
- **THEN** the system SHALL match features that do not have a `name` attribute

#### Scenario: Regex match
- **WHEN** a match expression is `type~'alpine.*'`
- **THEN** the system SHALL match features where attribute `type` matches the regex `alpine.*`

#### Scenario: Numeric comparison
- **WHEN** a match expression is `elevation>2000`
- **THEN** the system SHALL match features where attribute `elevation` is numerically greater than 2000

#### Scenario: AND combination
- **WHEN** a match expression is `type=trail & difficulty=hard`
- **THEN** the system SHALL match features where both conditions are true

#### Scenario: OR combination
- **WHEN** a match expression is `type=trail | type=path`
- **THEN** the system SHALL match features where either condition is true

#### Scenario: NOT negation
- **WHEN** a match expression is `!(type=highway)`
- **THEN** the system SHALL match features where `type` is not `highway`

#### Scenario: Catch-all wildcard
- **WHEN** a match expression is `*`
- **THEN** the system SHALL match all features

### Requirement: Evaluate match against feature attributes
The system SHALL evaluate a match expression against a feature's attribute dict and return True or False.

#### Scenario: Feature with matching attribute
- **WHEN** evaluating `difficulty=WS` against a feature with attributes `{difficulty: "WS", name: "Route 1"}`
- **THEN** the system SHALL return True

#### Scenario: Feature without matching attribute
- **WHEN** evaluating `difficulty=WS` against a feature with attributes `{name: "Route 1"}`
- **THEN** the system SHALL return False

#### Scenario: Numeric comparison with string attribute
- **WHEN** evaluating `elevation>2000` against a feature with attributes `{elevation: "3500"}`
- **THEN** the system SHALL parse the attribute as a number and return True

#### Scenario: Numeric comparison with non-numeric attribute
- **WHEN** evaluating `elevation>2000` against a feature with attributes `{elevation: "unknown"}`
- **THEN** the system SHALL return False (cannot parse as number)

### Requirement: Parse QGIS QML categorized renderer
The system SHALL parse QGIS `.qml` files with `categorizedSymbol` renderer type, extracting categories and their line symbols.

#### Scenario: Categorized renderer with single attribute
- **WHEN** a QML file has `renderer-v2 type="categorizedSymbol" attr="schwierigkeit"` with categories for values `L`, `WS`, `ZS`
- **THEN** the system SHALL create one `StyleRule` per category with match expressions `schwierigkeit=L`, `schwierigkeit=WS`, `schwierigkeit=ZS`

#### Scenario: QML with casing (multi-layer symbol)
- **WHEN** a QML symbol has two `SimpleLine` layers (wider white at pass=0, thinner colored at pass=1)
- **THEN** the system SHALL detect the wider layer as a border and store it in `LineStyle.border_color` and `LineStyle.border_width`

#### Scenario: QML with dashed line
- **WHEN** a QML SimpleLine layer has `line_style` = `dash` and `customdash` = `"5;2"`
- **THEN** the system SHALL store the dash pattern `[5, 2]` in `LineStyle.dash`

#### Scenario: QML with default/null category
- **WHEN** a QML categorized renderer has a category with `type="NULL"` (catch-all)
- **THEN** the system SHALL create a rule with match expression `*`

#### Scenario: QML with unknown renderer type
- **WHEN** a QML file has `renderer-v2 type="singleSymbol"` or another unsupported type
- **THEN** the system SHALL raise an error indicating the renderer type is not supported

### Requirement: Parse QGIS QML rule-based renderer
The system SHALL parse QGIS `.qml` files with `RuleRenderer` type, extracting filter expressions and symbols.

#### Scenario: Rule-based renderer with filter expressions
- **WHEN** a QML file has `renderer-v2 type="RuleRenderer"` with rules containing `filter` attributes
- **THEN** the system SHALL convert each QGIS filter expression to a match expression

#### Scenario: QGIS filter with scale range
- **WHEN** a QGIS rule has `scalemindenom="50000"` and `scalemaxdenom="5000"`
- **THEN** the system SHALL store the corresponding zoom range in the `StyleRule`

#### Scenario: ELSE rule in QGIS
- **WHEN** a QGIS rule has `filter="ELSE"`
- **THEN** the system SHALL create a rule with match expression `*`

### Requirement: Parse Garmin type mapping from config
The system SHALL parse optional `garmin` blocks from inline rules and `garmin_types` from QML-based configs.

#### Scenario: Inline Garmin type mapping
- **WHEN** a YAML rule defines `garmin: {type: 0x16, resolution: [16, 24]}`
- **THEN** the system SHALL store a `GarminStyle` with type `0x16` and resolution range `(16, 24)` on the `StyleRule`

#### Scenario: QML config with garmin_types
- **WHEN** a layer config references a QML file and provides `garmin_types: {L: {type: 0x16, resolution: [18, 24]}}`
- **THEN** the system SHALL attach the `GarminStyle` to the matching QML-derived `StyleRule` by category value

#### Scenario: Rule without Garmin mapping
- **WHEN** a style rule has no `garmin` block and no `garmin_types` entry
- **THEN** the system SHALL set `StyleRule.garmin` to `None`

### Requirement: Color parsing
The system SHALL accept colors in multiple formats and normalize to RGB tuples.

#### Scenario: Hex color with hash
- **WHEN** a color value is `"#FF8800"`
- **THEN** the system SHALL parse it as `(255, 136, 0)`

#### Scenario: Hex color without hash
- **WHEN** a color value is `"FF8800"`
- **THEN** the system SHALL parse it as `(255, 136, 0)`

#### Scenario: QGIS RGBA color
- **WHEN** a color value is `"255,136,0,255"` (QGIS format)
- **THEN** the system SHALL parse it as `(255, 136, 0)` ignoring the alpha channel (opacity is handled separately)

#### Scenario: Named color
- **WHEN** a color value is `"white"`
- **THEN** the system SHALL parse it as `(255, 255, 255)` from a basic named-color lookup

### Requirement: Find first matching style for a feature
The system SHALL iterate rules in order and return the style for the first rule that matches a feature's attributes.

#### Scenario: First matching rule wins
- **WHEN** rules are defined for `difficulty=WS` then `difficulty=*` and a feature has `{difficulty: "WS"}`
- **THEN** the system SHALL return the style from the `difficulty=WS` rule

#### Scenario: Fallback to catch-all
- **WHEN** no specific rule matches and a `*` catch-all rule exists
- **THEN** the system SHALL return the catch-all rule's style

#### Scenario: No matching rule
- **WHEN** no rule matches a feature and no catch-all exists
- **THEN** the system SHALL return `None`
