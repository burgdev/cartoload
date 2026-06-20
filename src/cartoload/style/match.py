"""Match expression parser and evaluator.

Supports mkgmap-compatible syntax for evaluating feature attributes:

    tag=value         Exact match
    tag!=value        Not equal (or absent)
    tag=*             Tag exists
    tag!=*            Tag absent
    tag~regex         Regex match
    tag>number        Numeric comparison (also >=, <, <=)
    *                 Match everything (wildcard)
    expr1 & expr2     AND
    expr1 | expr2     OR
    !(expr)           NOT
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# ---- AST node types ----


class MatchExpression:
    """Base class for match expression AST nodes."""


@dataclass(frozen=True)
class Wildcard(MatchExpression):
    """Match all features."""

    def __repr__(self) -> str:
        return "*"


@dataclass(frozen=True)
class ExactMatch(MatchExpression):
    """Match when attribute equals a value."""

    tag: str
    value: str

    def __repr__(self) -> str:
        return f"{self.tag}={self.value}"


@dataclass(frozen=True)
class NotEqual(MatchExpression):
    """Match when attribute does not equal a value (or is absent)."""

    tag: str
    value: str

    def __repr__(self) -> str:
        return f"{self.tag}!={self.value}"


@dataclass(frozen=True)
class Exists(MatchExpression):
    """Match when attribute exists (any value)."""

    tag: str

    def __repr__(self) -> str:
        return f"{self.tag}=*"


@dataclass(frozen=True)
class Absent(MatchExpression):
    """Match when attribute is absent."""

    tag: str

    def __repr__(self) -> str:
        return f"{self.tag}!=*"


@dataclass(frozen=True)
class RegexMatch(MatchExpression):
    """Match when attribute matches a regex pattern."""

    tag: str
    pattern: str

    def __repr__(self) -> str:
        return f"{self.tag}~{self.pattern}"


@dataclass(frozen=True)
class NumericCompare(MatchExpression):
    """Match when attribute compares numerically."""

    tag: str
    op: str  # '>', '>=', '<', '<='
    value: float

    def __repr__(self) -> str:
        return f"{self.tag}{self.op}{self.value}"


@dataclass(frozen=True)
class AndExpr(MatchExpression):
    """Match when both sub-expressions match."""

    left: MatchExpression
    right: MatchExpression

    def __repr__(self) -> str:
        return f"({self.left} & {self.right})"


@dataclass(frozen=True)
class OrExpr(MatchExpression):
    """Match when either sub-expression matches."""

    left: MatchExpression
    right: MatchExpression

    def __repr__(self) -> str:
        return f"({self.left} | {self.right})"


@dataclass(frozen=True)
class NotExpr(MatchExpression):
    """Match when sub-expression does not match."""

    expr: MatchExpression

    def __repr__(self) -> str:
        return f"!({self.expr})"


# ---- Tokenizer ----

_TOKEN_RE = re.compile(
    r"""
    \s*(
        [&|]           # operators
        | !=           # not-equal (before =)
        | [><]=?       # numeric comparison
        | ~            # regex
        | [()]         # parens
        | !            # not
        | =            # equal
        | \*           # wildcard
        | "[^"]*"      # double-quoted string
        | '[^']*'      # single-quoted string
        | [^\s&|()!=><~*]+  # bare word (tag name or value)
    )\s*
    """,
    re.VERBOSE,
)


def _tokenize(expr: str) -> list[str]:
    """Split a match expression string into tokens."""
    tokens = []
    pos = 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m:
            raise ValueError(f"Unexpected character at position {pos} in: {expr!r}")
        token = m.group(1).strip()
        if token:
            tokens.append(token)
        pos = m.end()
    return tokens


def _unquote(s: str) -> str:
    """Remove surrounding quotes from a string."""
    if (s.startswith('"') and s.endswith('"')) or (
        s.startswith("'") and s.endswith("'")
    ):
        return s[1:-1]
    return s


# ---- Recursive descent parser ----


class _Parser:
    """Recursive descent parser for match expressions.

    Precedence (low to high): OR, AND, NOT, comparison
    """

    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> str | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self, expected: str | None = None) -> str:
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        if expected is not None and tok != expected:
            raise ValueError(f"Expected {expected!r}, got {tok!r}")
        self.pos += 1
        return tok

    def parse_expr(self) -> MatchExpression:
        """Parse a full expression (OR precedence)."""
        left = self.parse_and()
        while self.peek() == "|":
            self.consume("|")
            right = self.parse_and()
            left = OrExpr(left, right)
        return left

    def parse_and(self) -> MatchExpression:
        """Parse AND expressions."""
        left = self.parse_not()
        while self.peek() == "&":
            self.consume("&")
            right = self.parse_not()
            left = AndExpr(left, right)
        return left

    def parse_not(self) -> MatchExpression:
        """Parse NOT expressions."""
        if self.peek() == "!":
            self.consume("!")
            if self.peek() == "(":
                self.consume("(")
                expr = self.parse_expr()
                self.consume(")")
                return NotExpr(expr)
            # Unary NOT on a simple comparison
            expr = self.parse_comparison()
            return NotExpr(expr)
        return self.parse_comparison()

    def parse_comparison(self) -> MatchExpression:
        """Parse a comparison or parenthesized expression."""
        tok = self.peek()

        # Parenthesized group
        if tok == "(":
            self.consume("(")
            expr = self.parse_expr()
            self.consume(")")
            return expr

        # Wildcard
        if tok == "*":
            self.consume("*")
            return Wildcard()

        # Must be tag <op> value
        tag = self.consume()
        op = self.peek()

        if op == "=":
            self.consume("=")
            val = self.peek()
            if val == "*":
                self.consume("*")
                return Exists(tag=tag)
            return ExactMatch(tag=tag, value=_unquote(self.consume()))

        if op == "!=":
            self.consume("!=")
            val = self.peek()
            if val == "*":
                self.consume("*")
                return Absent(tag=tag)
            return NotEqual(tag=tag, value=_unquote(self.consume()))

        if op == "~":
            self.consume("~")
            return RegexMatch(tag=tag, pattern=_unquote(self.consume()))

        if op in (">", ">=", "<", "<="):
            self.consume()
            val_str = _unquote(self.consume())
            try:
                val = float(val_str)
            except ValueError:
                raise ValueError(
                    f"Numeric comparison requires a number, got {val_str!r}"
                )
            return NumericCompare(tag=tag, op=op, value=val)

        # No operator — treat as existence check
        return Exists(tag=tag)


def parse_match(expression: str) -> MatchExpression:
    """Parse a match expression string into an AST.

    Args:
        expression: Match expression in mkgmap-compatible syntax.

    Returns:
        A MatchExpression AST node.

    Raises:
        ValueError: If the expression cannot be parsed.
    """
    expression = expression.strip()
    if not expression or expression == "*":
        return Wildcard()

    tokens = _tokenize(expression)
    if not tokens:
        return Wildcard()

    parser = _Parser(tokens)
    result = parser.parse_expr()

    if parser.pos < len(parser.tokens):
        raise ValueError(
            f"Unexpected token {parser.tokens[parser.pos]!r} "
            f"at position {parser.pos} in: {expression!r}"
        )

    return result


def evaluate(expr: MatchExpression, attributes: dict[str, Any]) -> bool:
    """Evaluate a match expression against a feature's attribute dict.

    Args:
        expr: The match expression AST to evaluate.
        attributes: Feature attributes as a dict.

    Returns:
        True if the expression matches, False otherwise.
    """
    if isinstance(expr, Wildcard):
        return True

    if isinstance(expr, ExactMatch):
        val = attributes.get(expr.tag)
        if val is None:
            return False
        return str(val) == expr.value

    if isinstance(expr, NotEqual):
        val = attributes.get(expr.tag)
        if val is None:
            return True  # absent → not equal
        return str(val) != expr.value

    if isinstance(expr, Exists):
        return expr.tag in attributes and attributes[expr.tag] is not None

    if isinstance(expr, Absent):
        return expr.tag not in attributes or attributes[expr.tag] is None

    if isinstance(expr, RegexMatch):
        val = attributes.get(expr.tag)
        if val is None:
            return False
        return bool(re.search(expr.pattern, str(val)))

    if isinstance(expr, NumericCompare):
        val = attributes.get(expr.tag)
        if val is None:
            return False
        try:
            num = float(val)
        except (ValueError, TypeError):
            return False
        ops = {
            ">": num > expr.value,
            ">=": num >= expr.value,
            "<": num < expr.value,
            "<=": num <= expr.value,
        }
        return ops[expr.op]

    if isinstance(expr, AndExpr):
        return evaluate(expr.left, attributes) and evaluate(expr.right, attributes)

    if isinstance(expr, OrExpr):
        return evaluate(expr.left, attributes) or evaluate(expr.right, attributes)

    if isinstance(expr, NotExpr):
        return not evaluate(expr.expr, attributes)

    raise ValueError(f"Unknown expression type: {type(expr).__name__}")
