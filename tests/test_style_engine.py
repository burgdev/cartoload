"""Tests for the style engine: model, match expressions, parsers."""

from __future__ import annotations

import pytest

from cartoload.style.match import (
    AndExpr,
    Absent,
    ExactMatch,
    Exists,
    NotEqual,
    NotExpr,
    NumericCompare,
    OrExpr,
    Wildcard,
    evaluate,
    parse_match,
)
from cartoload.style.model import (
    LineStyle,
    StyleRule,
    parse_color,
    resolve_style_for_zoom,
)
from cartoload.style.yaml_parser import parse_yaml_rules


# ---- Color parsing ----


class TestParseColor:
    def test_hex_with_hash(self):
        assert parse_color("#FF8800") == (255, 136, 0)

    def test_hex_without_hash(self):
        assert parse_color("FF8800") == (255, 136, 0)

    def test_hex_short(self):
        assert parse_color("#F80") == (255, 136, 0)

    def test_qgis_rgba(self):
        assert parse_color("255,136,0,255") == (255, 136, 0)

    def test_qgis_rgb(self):
        assert parse_color("255,136,0") == (255, 136, 0)

    def test_named_white(self):
        assert parse_color("white") == (255, 255, 255)

    def test_named_black(self):
        assert parse_color("black") == (0, 0, 0)

    def test_named_blue(self):
        assert parse_color("blue") == (0, 0, 255)

    def test_tuple(self):
        assert parse_color((255, 136, 0)) == (255, 136, 0)

    def test_list(self):
        assert parse_color([255, 136, 0]) == (255, 136, 0)

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_color("not_a_color")


# ---- Match expression parsing ----


class TestParseMatch:
    def test_exact_match(self):
        expr = parse_match("difficulty=WS")
        assert isinstance(expr, ExactMatch)
        assert expr.tag == "difficulty"
        assert expr.value == "WS"

    def test_not_equal(self):
        expr = parse_match("type!=highway")
        assert isinstance(expr, NotEqual)
        assert expr.tag == "type"
        assert expr.value == "highway"

    def test_exists(self):
        expr = parse_match("name=*")
        assert isinstance(expr, Exists)
        assert expr.tag == "name"

    def test_absent(self):
        expr = parse_match("name!=*")
        assert isinstance(expr, Absent)
        assert expr.tag == "name"

    def test_wildcard(self):
        expr = parse_match("*")
        assert isinstance(expr, Wildcard)

    def test_empty_string(self):
        expr = parse_match("")
        assert isinstance(expr, Wildcard)

    def test_numeric_greater(self):
        expr = parse_match("elevation>2000")
        assert isinstance(expr, NumericCompare)
        assert expr.tag == "elevation"
        assert expr.op == ">"
        assert expr.value == 2000.0

    def test_numeric_gte(self):
        expr = parse_match("elevation>=2000")
        assert isinstance(expr, NumericCompare)
        assert expr.op == ">="

    def test_numeric_less(self):
        expr = parse_match("elevation<2000")
        assert isinstance(expr, NumericCompare)
        assert expr.op == "<"

    def test_numeric_lte(self):
        expr = parse_match("elevation<=2000")
        assert isinstance(expr, NumericCompare)
        assert expr.op == "<="

    def test_and(self):
        expr = parse_match("type=trail & difficulty=hard")
        assert isinstance(expr, AndExpr)
        assert isinstance(expr.left, ExactMatch)
        assert isinstance(expr.right, ExactMatch)

    def test_or(self):
        expr = parse_match("type=trail | type=path")
        assert isinstance(expr, OrExpr)

    def test_not_parenthesized(self):
        expr = parse_match("!(type=highway)")
        assert isinstance(expr, NotExpr)
        assert isinstance(expr.expr, ExactMatch)

    def test_quoted_value(self):
        expr = parse_match('name="hello world"')
        assert isinstance(expr, ExactMatch)
        assert expr.value == "hello world"

    def test_single_quoted_value(self):
        expr = parse_match("name='hello world'")
        assert isinstance(expr, ExactMatch)
        assert expr.value == "hello world"


# ---- Match evaluation ----


class TestEvaluate:
    def test_exact_match_true(self):
        expr = parse_match("difficulty=WS")
        assert evaluate(expr, {"difficulty": "WS"}) is True

    def test_exact_match_false(self):
        expr = parse_match("difficulty=WS")
        assert evaluate(expr, {"difficulty": "L"}) is False

    def test_exact_match_missing(self):
        expr = parse_match("difficulty=WS")
        assert evaluate(expr, {"name": "foo"}) is False

    def test_not_equal_present_different(self):
        expr = parse_match("type!=highway")
        assert evaluate(expr, {"type": "trail"}) is True

    def test_not_equal_present_same(self):
        expr = parse_match("type!=highway")
        assert evaluate(expr, {"type": "highway"}) is False

    def test_not_equal_absent(self):
        expr = parse_match("type!=highway")
        assert evaluate(expr, {"name": "foo"}) is True

    def test_exists_true(self):
        expr = parse_match("name=*")
        assert evaluate(expr, {"name": "foo"}) is True

    def test_exists_false(self):
        expr = parse_match("name=*")
        assert evaluate(expr, {"type": "foo"}) is False

    def test_absent_true(self):
        expr = parse_match("name!=*")
        assert evaluate(expr, {"type": "foo"}) is True

    def test_absent_false(self):
        expr = parse_match("name!=*")
        assert evaluate(expr, {"name": "foo"}) is False

    def test_wildcard(self):
        expr = parse_match("*")
        assert evaluate(expr, {}) is True
        assert evaluate(expr, {"a": "b"}) is True

    def test_numeric_int_attr(self):
        expr = parse_match("access=0")
        assert evaluate(expr, {"access": 0}) is True

    def test_numeric_comparison_string(self):
        expr = parse_match("elevation>2000")
        assert evaluate(expr, {"elevation": "3500"}) is True

    def test_numeric_comparison_int(self):
        expr = parse_match("elevation>2000")
        assert evaluate(expr, {"elevation": 3500}) is True

    def test_numeric_comparison_non_numeric(self):
        expr = parse_match("elevation>2000")
        assert evaluate(expr, {"elevation": "unknown"}) is False

    def test_numeric_comparison_missing(self):
        expr = parse_match("elevation>2000")
        assert evaluate(expr, {}) is False

    def test_and_true(self):
        expr = parse_match("type=trail & difficulty=hard")
        assert evaluate(expr, {"type": "trail", "difficulty": "hard"}) is True

    def test_and_false_one(self):
        expr = parse_match("type=trail & difficulty=hard")
        assert evaluate(expr, {"type": "trail", "difficulty": "easy"}) is False

    def test_or_true(self):
        expr = parse_match("type=trail | type=path")
        assert evaluate(expr, {"type": "trail"}) is True

    def test_or_false(self):
        expr = parse_match("type=trail | type=path")
        assert evaluate(expr, {"type": "road"}) is False

    def test_not(self):
        expr = parse_match("!(type=highway)")
        assert evaluate(expr, {"type": "trail"}) is True
        assert evaluate(expr, {"type": "highway"}) is False


# ---- YAML parser ----


class TestYamlParser:
    def test_simple_rule(self):
        rules = parse_yaml_rules(
            [
                {
                    "match": "difficulty=L",
                    "style": {"color": "#33A02C", "width": 1},
                }
            ]
        )
        assert len(rules) == 1
        assert isinstance(rules[0].match, ExactMatch)
        assert rules[0].default_style.color == (51, 160, 44)
        assert rules[0].default_style.width == 1.0

    def test_dash_pattern(self):
        rules = parse_yaml_rules(
            [
                {
                    "match": "*",
                    "style": {"color": "red", "width": 2, "dash": [8, 4]},
                }
            ]
        )
        assert rules[0].default_style.dash == [8.0, 4.0]

    def test_border(self):
        rules = parse_yaml_rules(
            [
                {
                    "match": "*",
                    "style": {
                        "color": "#0000FF",
                        "width": 2,
                        "border": {"color": "white", "width": 1},
                    },
                }
            ]
        )
        style = rules[0].default_style
        assert style.color == (0, 0, 255)
        assert style.border_color == (255, 255, 255)
        assert style.border_width == 1.0

    def test_zoom_keyed(self):
        rules = parse_yaml_rules(
            [
                {
                    "match": "*",
                    "style": {
                        "zoom": {
                            10: {"color": "red", "width": 0.5},
                            14: {"color": "blue", "width": 2},
                        },
                        "default": {"color": "green", "width": 1},
                    },
                }
            ]
        )
        assert 10 in rules[0].zoom_styles
        assert 14 in rules[0].zoom_styles
        assert rules[0].default_style.color == (0, 128, 0)

    def test_garmin_mapping(self):
        rules = parse_yaml_rules(
            [
                {
                    "match": "*",
                    "style": {"color": "red", "width": 1},
                    "garmin": {"type": "0x16", "resolution": [16, 24]},
                }
            ]
        )
        assert rules[0].garmin is not None
        assert rules[0].garmin.type_code == 0x16
        assert rules[0].garmin.resolution == (16, 24)

    def test_opacity(self):
        rules = parse_yaml_rules(
            [
                {
                    "match": "*",
                    "style": {"color": "red", "width": 1, "opacity": 0.7},
                }
            ]
        )
        assert rules[0].default_style.opacity == 0.7


# ---- Zoom resolution ----


class TestResolveStyleForZoom:
    def test_exact_zoom(self):
        rule = StyleRule(
            match=Wildcard(),
            zoom_styles={
                10: LineStyle(color=(255, 0, 0), width=1),
                14: LineStyle(color=(0, 0, 255), width=2),
            },
            default_style=LineStyle(color=(0, 128, 0), width=1),
        )
        assert resolve_style_for_zoom(rule, 14).color == (0, 0, 255)

    def test_nearest_below(self):
        rule = StyleRule(
            match=Wildcard(),
            zoom_styles={
                10: LineStyle(color=(255, 0, 0), width=1),
                14: LineStyle(color=(0, 0, 255), width=2),
            },
            default_style=LineStyle(color=(0, 128, 0), width=1),
        )
        # Zoom 12 → nearest at or below is 10
        assert resolve_style_for_zoom(rule, 12).color == (255, 0, 0)

    def test_above_all(self):
        rule = StyleRule(
            match=Wildcard(),
            zoom_styles={
                10: LineStyle(color=(255, 0, 0), width=1),
                14: LineStyle(color=(0, 0, 255), width=2),
            },
            default_style=LineStyle(color=(0, 128, 0), width=1),
        )
        # Zoom 16 → nearest at or below is 14
        assert resolve_style_for_zoom(rule, 16).color == (0, 0, 255)

    def test_below_all(self):
        rule = StyleRule(
            match=Wildcard(),
            zoom_styles={
                10: LineStyle(color=(255, 0, 0), width=1),
                14: LineStyle(color=(0, 0, 255), width=2),
            },
            default_style=LineStyle(color=(0, 128, 0), width=1),
        )
        # Zoom 8 → below all definitions → default
        assert resolve_style_for_zoom(rule, 8).color == (0, 128, 0)


# ---- StyleEngine resolve ----


class TestStyleEngine:
    def test_first_match_wins(self):
        from cartoload.style import StyleEngine

        engine = StyleEngine(
            rules=[
                StyleRule(
                    match=ExactMatch(tag="difficulty", value="WS"),
                    default_style=LineStyle(color=(255, 0, 0), width=2),
                ),
                StyleRule(
                    match=Wildcard(),
                    default_style=LineStyle(color=(0, 0, 255), width=1),
                ),
            ]
        )
        style = engine.resolve({"difficulty": "WS"}, 12)
        assert style is not None
        assert style.color == (255, 0, 0)

    def test_fallback_to_wildcard(self):
        from cartoload.style import StyleEngine

        engine = StyleEngine(
            rules=[
                StyleRule(
                    match=ExactMatch(tag="difficulty", value="WS"),
                    default_style=LineStyle(color=(255, 0, 0), width=2),
                ),
                StyleRule(
                    match=Wildcard(),
                    default_style=LineStyle(color=(0, 0, 255), width=1),
                ),
            ]
        )
        style = engine.resolve({"difficulty": "L"}, 12)
        assert style is not None
        assert style.color == (0, 0, 255)

    def test_no_match(self):
        from cartoload.style import StyleEngine

        engine = StyleEngine(
            rules=[
                StyleRule(
                    match=ExactMatch(tag="difficulty", value="WS"),
                    default_style=LineStyle(color=(255, 0, 0), width=2),
                ),
            ]
        )
        style = engine.resolve({"difficulty": "L"}, 12)
        assert style is None

    def test_zoom_resolution(self):
        from cartoload.style import StyleEngine

        engine = StyleEngine(
            rules=[
                StyleRule(
                    match=Wildcard(),
                    zoom_styles={
                        10: LineStyle(color=(255, 0, 0), width=1),
                        14: LineStyle(color=(0, 0, 255), width=2),
                    },
                    default_style=LineStyle(color=(0, 128, 0), width=1),
                ),
            ]
        )
        style_10 = engine.resolve({}, 10)
        assert style_10 is not None
        assert style_10.color == (255, 0, 0)

        style_14 = engine.resolve({}, 14)
        assert style_14 is not None
        assert style_14.color == (0, 0, 255)

        style_8 = engine.resolve({}, 8)
        assert style_8 is not None
        assert style_8.color == (0, 128, 0)
