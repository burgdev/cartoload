"""Parse QGIS QML style files into StyleRule objects.

Supports:
- ``RuleRenderer``: Filter expressions, scale ranges, nested rules
- ``categorizedSymbol``: Attribute-based categories
- ``SimpleLine`` symbol layers: color, width, dash, border/casing
- Multi-layer symbols (casing detection)

Skips:
- MarkerLine, ArrowLine, effects
- Data-defined properties
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from cartoload.style.match import (
    AndExpr,
    ExactMatch,
    MatchExpression,
    OrExpr,
    Wildcard,
)
from cartoload.style.model import (
    LineStyle,
    StyleRule,
    parse_color,
)

logger = logging.getLogger(__name__)

# Approximate scale denominator → zoom level mapping for Web Mercator
# Based on DPI=96, tile size=256
_SCALE_TO_ZOOM = [
    (500000000, 0),
    (200000000, 1),
    (100000000, 2),
    (50000000, 3),
    (20000000, 4),
    (10000000, 5),
    (5000000, 6),
    (2000000, 7),
    (1000000, 8),
    (500000, 9),
    (200000, 10),
    (100000, 11),
    (50000, 12),
    (20000, 13),
    (10000, 14),
    (5000, 15),
    (2000, 16),
    (1000, 17),
    (500, 18),
    (200, 19),
    (100, 20),
]


def scale_to_zoom(scale_denom: float) -> int:
    """Convert a QGIS scale denominator to an approximate zoom level.

    Returns the zoom level whose scale denominator is closest to but
    not exceeding the given scale.
    """
    for threshold, zoom in _SCALE_TO_ZOOM:
        if scale_denom >= threshold:
            return zoom
    return 21  # Very detailed


def parse_qml(path: str | Path) -> list[StyleRule]:
    """Parse a QGIS QML file into a list of StyleRule objects.

    Args:
        path: Path to the .qml file.

    Returns:
        List of StyleRule objects.

    Raises:
        ValueError: If the renderer type is unsupported.
    """
    tree = ET.parse(path)
    root = tree.getroot()

    renderer = root.find("renderer-v2")
    if renderer is None:
        raise ValueError("No renderer-v2 found in QML file")

    renderer_type = renderer.get("type", "")

    # Load symbols from the <symbols> section inside the renderer
    # (QGIS puts symbols as a child of renderer-v2)
    symbols_elem = renderer.find("symbols")
    if symbols_elem is None:
        # Fallback: check top-level
        symbols_elem = root.find("symbols")
    symbols: dict[str, list[_SymbolLayer]] = {}
    if symbols_elem is not None:
        for sym in symbols_elem.findall("symbol"):
            name = sym.get("name", "")
            sym_type = sym.get("type", "")
            if sym_type != "line":
                continue
            layers = _parse_symbol(sym)
            symbols[name] = layers

    if renderer_type == "RuleRenderer":
        return _parse_rule_renderer(renderer, symbols)
    elif renderer_type == "categorizedSymbol":
        return _parse_categorized_renderer(renderer, symbols)
    elif renderer_type == "singleSymbol":
        # Single symbol: one catch-all rule
        symbol_elem = renderer.find("symbol")
        if symbol_elem is not None:
            name = symbol_elem.get("name", "")
            layers = _parse_symbol(symbol_elem)
            if layers:
                style = _layers_to_style(layers)
                return [StyleRule(match=Wildcard(), default_style=style)]
        return []
    else:
        raise ValueError(
            f"Unsupported QML renderer type: '{renderer_type}'. "
            f"Supported: RuleRenderer, categorizedSymbol, singleSymbol"
        )


# ---- Internal data types ----


class _SymbolLayer:
    """Parsed SimpleLine symbol layer."""

    color: tuple[int, int, int]
    width: float
    width_unit: str  # "MM", "RenderMetersInMapUnits", "Pixel"
    line_style: str  # "solid", "dash", "dot", "dash dot", "no"
    custom_dash: list[float]
    use_custom_dash: bool
    pass_value: int  # rendering order (lower = drawn first = border)

    def __init__(self) -> None:
        self.color = (0, 0, 0)
        self.width = 1.0
        self.width_unit = "MM"
        self.line_style = "solid"
        self.custom_dash = []
        self.use_custom_dash = False
        self.pass_value = 0


def _parse_symbol(sym_elem: ET.Element) -> list[_SymbolLayer]:
    """Parse symbol layers from a <symbol> element."""
    layers = []
    for layer_elem in sym_elem.findall("layer"):
        layer_class = layer_elem.get("class", "")
        if layer_class != "SimpleLine":
            # Skip MarkerLine, ArrowLine, etc.
            continue

        sl = _SymbolLayer()
        sl.pass_value = int(layer_elem.get("pass", "0"))

        for prop in layer_elem.findall("prop"):
            key = prop.get("k", "")
            value = prop.get("v", "")

            if key == "line_color":
                sl.color = parse_color(value)
            elif key == "line_width":
                sl.width = float(value)
            elif key == "line_width_unit":
                sl.width_unit = value
            elif key == "line_style":
                sl.line_style = value
            elif key == "customdash":
                sl.custom_dash = [float(x) for x in value.split(";") if x.strip()]
            elif key == "use_custom_dash":
                sl.use_custom_dash = value == "1"

        layers.append(sl)

    return layers


def _layers_to_style(layers: list[_SymbolLayer]) -> LineStyle:
    """Convert parsed symbol layers into a LineStyle.

    Detects casing: when multiple SimpleLine layers are present,
    the wider one at lower pass is treated as border.
    """
    if not layers:
        return LineStyle()

    if len(layers) == 1:
        return _single_layer_to_style(layers[0])

    # Multiple layers: detect casing
    # Sort by pass value (lower pass = drawn first = border)
    sorted_layers = sorted(layers, key=lambda layer: layer.pass_value)

    border_layer = sorted_layers[0]
    core_layer = sorted_layers[-1]

    core_style = _single_layer_to_style(core_layer)

    border_color = border_layer.color
    border_width = border_layer.width - core_layer.width
    if border_width < 0:
        border_width = 0.5  # fallback

    return LineStyle(
        color=core_style.color,
        width=core_style.width,
        dash=core_style.dash,
        border_color=border_color,
        border_width=border_width / 2,  # border_width is per side
        opacity=core_style.opacity,
    )


def _single_layer_to_style(layer: _SymbolLayer) -> LineStyle:
    """Convert a single symbol layer to a LineStyle."""
    dash = None
    if layer.line_style == "no":
        # Invisible line
        return LineStyle(color=layer.color, width=0.0, opacity=0.0)
    elif layer.use_custom_dash and layer.custom_dash:
        dash = layer.custom_dash
    elif layer.line_style == "dash":
        dash = [5.0, 2.0]  # default dash
    elif layer.line_style == "dot":
        dash = [1.0, 2.0]
    elif layer.line_style == "dash dot":
        dash = [5.0, 2.0, 1.0, 2.0]

    return LineStyle(
        color=layer.color,
        width=layer.width,
        dash=dash,
    )


# ---- QML filter expression → match expression ----


def _parse_qml_filter(filter_str: str) -> MatchExpression:
    """Convert a QGIS filter expression to a match expression.

    Handles:
    - "tag" = value  → tag=value
    - "tag" = 'value'  → tag=value
    - AND, OR
    - $length > N  →  skip (we can't evaluate geometry functions)
    - ELSE → wildcard
    """
    if not filter_str or filter_str.strip().upper() == "ELSE":
        return Wildcard()

    # Tokenize QGIS filter: handle quoted strings, operators, AND/OR
    # Pattern: "tag" op value [AND/OR "tag" op value ...]
    tokens = _tokenize_qml_filter(filter_str)
    return _parse_qml_tokens(tokens)


def _tokenize_qml_filter(expr: str) -> list[str]:
    """Tokenize a QGIS filter expression."""
    tokens = []
    i = 0
    expr = expr.strip()
    while i < len(expr):
        # Skip whitespace
        if expr[i].isspace():
            i += 1
            continue

        # Quoted string: "tag" or 'value'
        if expr[i] in ('"', "'"):
            quote = expr[i]
            j = i + 1
            while j < len(expr) and expr[j] != quote:
                j += 1
            tokens.append(expr[i + 1 : j])  # content without quotes
            i = j + 1
            continue

        # Operators: =, !=, >, >=, <, <=
        if expr[i : i + 2] in ("!=", ">=", "<="):
            tokens.append(expr[i : i + 2])
            i += 2
            continue
        if expr[i] in ("=", ">", "<"):
            tokens.append(expr[i])
            i += 1
            continue

        # Keywords: AND, OR
        upper = expr[i:].upper()
        if upper.startswith("AND") and (
            i + 3 >= len(expr) or not expr[i + 3].isalnum()
        ):
            tokens.append("AND")
            i += 3
            continue
        if upper.startswith("OR") and (i + 2 >= len(expr) or not expr[i + 2].isalnum()):
            tokens.append("OR")
            i += 2
            continue

        # Bare word/number (including $length etc.)
        j = i
        while (
            j < len(expr)
            and not expr[j].isspace()
            and expr[j] not in ('"', "'", "=", "!", ">", "<")
        ):
            j += 1
        tokens.append(expr[i:j])
        i = j

    return tokens


def _parse_qml_tokens(tokens: list[str]) -> MatchExpression:
    """Parse tokenized QML filter into a MatchExpression."""
    if not tokens:
        return Wildcard()

    # Split by OR first (lower precedence)
    or_groups: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        if tok == "OR":
            or_groups.append(current)
            current = []
        else:
            current.append(tok)
    or_groups.append(current)

    if len(or_groups) > 1:
        parts = [_parse_qml_tokens(g) for g in or_groups]
        result = parts[0]
        for p in parts[1:]:
            result = OrExpr(result, p)
        return result

    # Split by AND
    and_groups: list[list[str]] = []
    current = []
    for tok in tokens:
        if tok == "AND":
            and_groups.append(current)
            current = []
        else:
            current.append(tok)
    and_groups.append(current)

    if len(and_groups) > 1:
        parts = [_parse_qml_tokens(g) for g in and_groups]
        result = parts[0]
        for p in parts[1:]:
            result = AndExpr(result, p)
        return result

    # Single comparison: tag op value
    if len(tokens) >= 3:
        tag = tokens[0]
        op = tokens[1]
        value = tokens[2]

        # Skip geometry functions ($length etc.)
        if tag.startswith("$"):
            return Wildcard()  # can't evaluate, match all

        # Normalize: for numeric values, use numeric comparison
        if op == "=":
            # Try to build match expression
            return ExactMatch(tag=tag, value=value)
        elif op == "!=":
            return ExactMatch(tag=tag, value=value)  # We'll handle negation at eval
        elif op in (">", ">=", "<", "<="):
            try:
                num = float(value)
                from cartoload.style.match import NumericCompare

                return NumericCompare(tag=tag, op=op, value=num)
            except ValueError:
                return Wildcard()

    # Bare tag name → existence check
    if len(tokens) == 1:
        from cartoload.style.match import Exists

        return Exists(tag=tokens[0])

    return Wildcard()


# ---- Renderer-specific parsers ----


def _parse_rule_renderer(
    renderer: ET.Element, symbols: dict[str, list[_SymbolLayer]]
) -> list[StyleRule]:
    """Parse a RuleRenderer into StyleRule objects."""
    rules_elem = renderer.find("rules")
    if rules_elem is None:
        return []

    rules: list[StyleRule] = []
    _collect_rules_recursive(rules_elem, symbols, rules)
    return rules


def _collect_rules_recursive(
    parent: ET.Element,
    symbols: dict[str, list[_SymbolLayer]],
    result: list[StyleRule],
) -> None:
    """Recursively collect rules from a RuleRenderer."""
    for rule_elem in parent.findall("rule"):
        symbol_idx = rule_elem.get("symbol")
        filter_str = rule_elem.get("filter", "")
        scale_min = rule_elem.get("scalemindenom")
        scale_max = rule_elem.get("scalemaxdenom")

        # Check for child rules (nested groups)
        child_rules = rule_elem.findall("rule")

        if child_rules:
            # This is a group rule — recurse into children
            _collect_rules_recursive(rule_elem, symbols, result)
            continue

        # Leaf rule: has a symbol and optional filter
        if symbol_idx is None:
            continue

        layers = symbols.get(symbol_idx, [])
        if not layers:
            continue

        style = _layers_to_style(layers)
        match_expr = _parse_qml_filter(filter_str)

        # Convert scale range to zoom range
        zoom_styles: dict[int, LineStyle] = {}
        if scale_min is not None or scale_max is not None:
            # scalemindenom = most detailed scale (small number)
            # scalemaxdenom = least detailed scale (large number)
            # The rule applies between scalemaxdenom (zoomed out) and
            # scalemindenom (zoomed in).
            # Convert to zoom: low scale → high zoom, high scale → low zoom
            min_scale = int(scale_min) if scale_min else 1
            max_scale = int(scale_max) if scale_max else 500000000

            # Map to zoom range
            zoom_high = scale_to_zoom(min_scale)  # detailed end
            zoom_low = scale_to_zoom(max_scale)  # overview end

            # Store the style at the zoom level where it becomes active
            # (the high-zoom/detailed end)
            for z in range(zoom_low, zoom_high + 1):
                zoom_styles[z] = style

        rule = StyleRule(
            match=match_expr,
            zoom_styles=zoom_styles,
            default_style=style if not zoom_styles else LineStyle(),
        )
        result.append(rule)


def _parse_categorized_renderer(
    renderer: ET.Element, symbols: dict[str, list[_SymbolLayer]]
) -> list[StyleRule]:
    """Parse a categorizedSymbol renderer into StyleRule objects."""
    attr = renderer.get("attr", "")
    categories_elem = renderer.find("categories")
    if categories_elem is None:
        return []

    rules: list[StyleRule] = []
    for cat in categories_elem.findall("category"):
        value = cat.get("value", "")
        cat_type = cat.get("type", "")
        symbol_idx = cat.get("symbol")

        if symbol_idx is None:
            continue

        layers = symbols.get(symbol_idx, [])
        if not layers:
            continue

        style = _layers_to_style(layers)

        if cat_type == "NULL" or value == "":
            match_expr = Wildcard()
        else:
            match_expr = ExactMatch(tag=attr, value=value)

        rules.append(
            StyleRule(
                match=match_expr,
                default_style=style,
            )
        )

    return rules
