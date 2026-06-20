"""Parse inline YAML style definitions from layer config into StyleRule objects."""

from __future__ import annotations

from cartoload.style.match import parse_match
from cartoload.style.model import (
    GarminStyle,
    LineStyle,
    StyleRule,
    parse_color,
)


def parse_yaml_rules(rules: list[dict]) -> list[StyleRule]:
    """Parse a list of inline YAML style rule dicts into StyleRule objects.

    Each rule dict should have:
    - ``match``: A match expression string (mkgmap-compatible syntax)
    - ``style``: Either a simple style dict or a zoom-keyed style dict

    Simple style:
        {color: "#FF0000", width: 2, dash: [8, 4], border: {color: white, width: 1}}

    Zoom-keyed style:
        zoom:
          10: {color: "#FF0000", width: 0.5}
          14: {color: "#FF0000", width: 2, dash: [8, 4]}
        default: {color: "#FF0000", width: 1}

    Optional ``garmin`` block:
        garmin: {type: "0x16", resolution: [16, 24]}
    """
    result: list[StyleRule] = []

    for rule_dict in rules:
        match_str = rule_dict.get("match", "*")
        match_expr = parse_match(match_str)

        style_dict = rule_dict.get("style", {})
        garmin_dict = rule_dict.get("garmin")

        # Check for zoom-keyed style
        if "zoom" in style_dict:
            zoom_styles = {}
            zoom_dict = style_dict["zoom"]
            for zoom_key, zoom_style in zoom_dict.items():
                zoom = int(zoom_key)
                zoom_styles[zoom] = _parse_line_style(zoom_style)

            default_dict = style_dict.get("default")
            if default_dict:
                default_style = _parse_line_style(default_dict)
            else:
                # Use lowest zoom as default
                if zoom_styles:
                    min_zoom = min(zoom_styles.keys())
                    default_style = zoom_styles[min_zoom]
                else:
                    default_style = LineStyle()

            rule = StyleRule(
                match=match_expr,
                zoom_styles=zoom_styles,
                default_style=default_style,
            )
        else:
            # Simple single style
            line_style = _parse_line_style(style_dict)
            rule = StyleRule(
                match=match_expr,
                default_style=line_style,
            )

        # Parse optional Garmin mapping
        if garmin_dict:
            type_str = str(garmin_dict.get("type", "0x00"))
            if type_str.startswith("0x") or type_str.startswith("0X"):
                type_code = int(type_str, 16)
            else:
                type_code = int(type_str)

            res = garmin_dict.get("resolution", [16, 24])
            rule.garmin = GarminStyle(
                type_code=type_code,
                resolution=(int(res[0]), int(res[1])),
            )

        result.append(rule)

    return result


def _parse_line_style(style_dict: dict) -> LineStyle:
    """Parse a single style dict into a LineStyle."""
    if not style_dict:
        return LineStyle()

    color = parse_color(style_dict["color"]) if "color" in style_dict else (0, 0, 0)
    width = float(style_dict.get("width", 1.0))

    dash = None
    if "dash" in style_dict:
        d = style_dict["dash"]
        if isinstance(d, list):
            dash = [float(x) for x in d]

    border_color = None
    border_width = None
    if "border" in style_dict:
        border = style_dict["border"]
        border_color = parse_color(border.get("color", "white"))
        border_width = float(border.get("width", 1.0))

    opacity = float(style_dict.get("opacity", 1.0))

    return LineStyle(
        color=color,
        width=width,
        dash=dash,
        border_color=border_color,
        border_width=border_width,
        opacity=opacity,
    )
