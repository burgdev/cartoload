"""Tests for the template variable expansion engine."""

from __future__ import annotations

from cartoload.template import check_unresolved, expand, resolve_templates


class TestExpand:
    """Tests for expand()."""

    # --- Plain text passthrough ---

    def test_empty_string(self):
        assert expand("", {}) == ""

    def test_plain_text_no_vars(self):
        assert expand("hello world", {}) == "hello world"

    def test_text_with_braces(self):
        assert expand("some {text}", {}) == "some {text}"

    # --- ${VAR} braced variables ---

    def test_braced_variable(self):
        assert expand("${name}", {"name": "world"}) == "world"

    def test_braced_variable_in_text(self):
        assert expand("hello ${name}!", {"name": "world"}) == "hello world!"

    def test_braced_variable_unresolved(self):
        assert expand("${unknown}", {}) == "${unknown}"

    def test_braced_variable_partial_match(self):
        """Variables that don't match are left as-is."""
        assert expand("${a}${b}", {"a": "X"}) == "X${b}"

    def test_multiple_braced_variables(self):
        assert expand("${a}-${b}-${c}", {"a": "1", "b": "2", "c": "3"}) == "1-2-3"

    # --- Bare $VAR ---

    def test_bare_variable(self):
        assert expand("$name", {"name": "world"}) == "world"

    def test_bare_variable_in_text(self):
        assert expand("prefix/$name/suffix", {"name": "value"}) == "prefix/value/suffix"

    def test_bare_variable_unresolved(self):
        assert expand("$unknown", {}) == "$unknown"

    def test_bare_variable_alphanumeric_only(self):
        """Bare variables stop at non-alphanumeric chars."""
        assert (
            expand("$host:$port", {"host": "localhost", "port": "8080"})
            == "localhost:8080"
        )

    def test_bare_variable_with_underscore(self):
        assert expand("$my_var", {"my_var": "val"}) == "val"

    # --- ${VAR:-default} ---

    def test_default_used_when_missing(self):
        assert expand("${name:-fallback}", {}) == "fallback"

    def test_default_not_used_when_present(self):
        assert expand("${name:-fallback}", {"name": "actual"}) == "actual"

    def test_default_empty_string(self):
        assert expand("${name:-}", {}) == ""

    def test_default_with_value(self):
        assert expand("${version:-1.0}", {}) == "1.0"

    def test_default_with_complex_text(self):
        assert (
            expand("${url:-https://example.com/path}", {}) == "https://example.com/path"
        )

    def test_default_variable_resolved(self):
        """Default values can reference other variables."""
        assert expand("${a:-$b}", {"b": "from_b"}) == "from_b"

    # --- $$ escape ---

    def test_dollar_escape(self):
        assert expand("$$5.00", {}) == "$5.00"

    def test_double_dollar_escape(self):
        assert expand("$$$$", {}) == "$$"

    def test_dollar_escape_before_var(self):
        assert expand("$$${name}", {"name": "val"}) == "$val"

    # --- Dollar at end / edge cases ---

    def test_trailing_dollar(self):
        assert expand("price$", {}) == "price$"

    def test_dollar_followed_by_non_var_char(self):
        assert expand("$!", {}) == "$!"

    def test_dollar_followed_by_space(self):
        assert expand("$ ", {}) == "$ "

    def test_dollar_followed_by_number(self):
        assert expand("$1", {}) == "$1"

    # --- Mixed scenarios ---

    def test_url_template_with_layer_and_coords(self):
        template = "https://tiles.example.com/${layer}/default/3857/{z}/{x}/{y}.${extension:-jpeg}"
        variables = {"layer": "ch.swisstopo.pixelkarte-farbe", "extension": "png"}
        result = expand(template, variables)
        assert (
            result
            == "https://tiles.example.com/ch.swisstopo.pixelkarte-farbe/default/3857/{z}/{x}/{y}.png"
        )

    def test_url_template_with_defaults(self):
        template = "https://wmts.example.com/${layer}/${version:-1.0.0}/${z}/${x}/${y}.${ext:-jpeg}"
        variables = {"layer": "basemap"}
        result = expand(template, variables)
        assert result == "https://wmts.example.com/basemap/1.0.0/${z}/${x}/${y}.jpeg"

    def test_empty_variables_dict(self):
        assert expand("${x}", {}) == "${x}"

    def test_none_variables_treated_as_empty(self):
        assert expand("${x}", None) == "${x}"


class TestCheckUnresolved:
    """Tests for check_unresolved()."""

    def test_no_unresolved(self):
        assert check_unresolved("hello world") == []

    def test_one_unresolved(self):
        assert check_unresolved("${layer}") == ["layer"]

    def test_multiple_unresolved(self):
        assert check_unresolved("${a}/${b}") == ["a", "b"]

    def test_mixed_resolved_and_unresolved(self):
        # check_unresolved doesn't know what's resolved — it just finds ${...} patterns
        assert check_unresolved("prefix/${a}/suffix") == ["a"]

    def test_bare_var_not_detected(self):
        """Bare $var is not detected by check_unresolved."""
        assert check_unresolved("$name") == []

    def test_empty_string(self):
        assert check_unresolved("") == []


class TestResolveTemplates:
    """Tests for resolve_templates()."""

    def test_batch_resolve(self):
        fields = ["${a}/path", "${b}/other"]
        variables = {"a": "val_a", "b": "val_b"}
        assert resolve_templates(fields, variables) == ["val_a/path", "val_b/other"]

    def test_empty_list(self):
        assert resolve_templates([], {}) == []

    def test_mixed_resolved(self):
        fields = ["${x}", "plain", "${y:-default}"]
        variables = {"x": "10"}
        assert resolve_templates(fields, variables) == ["10", "plain", "default"]
