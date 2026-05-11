"""Template variable expansion engine.

Simplified, vendored version of expandvars (MIT license, by Arijit Basu).
https://github.com/sayanarijit/expandvars

Supports:
  - ${VAR}          → value from variables dict
  - ${VAR:-default}  → value from variables dict, or inline default
  - $VAR             → bare variable (alphanumeric/underscore only)
  - $$               → escaped literal $

Stripped from upstream: os.environ, indirect expansion (${!VAR}),
length (${#VAR}), get-or-set (:=), substitute (:+), strict (:?),
offset/substring, nounset mode, file handle input.
"""

from __future__ import annotations

import re
from typing import Mapping

__all__ = ["expand", "check_unresolved", "resolve_templates"]

_ESCAPE_CHAR = "\\"
_VAR_SYMBOL = "$"

# Regex to find unresolved ${...} patterns after expansion
_UNRESOLVED_RE = re.compile(r"\$\{([^}]+)\}")


class _PeekableIterator:
    """Peekable iterator over a string."""

    NOTHING = object()

    def __init__(self, iterable: str) -> None:
        self._iter = iter(iterable)
        self._next: object = self.NOTHING

    def __iter__(self) -> _PeekableIterator:
        return self

    def __next__(self) -> str:
        if self._next is self.NOTHING:
            return next(self._iter)
        nxt: str = self._next  # type: ignore[assignment]
        self._next = self.NOTHING
        return nxt

    def peek(self) -> object:
        if self._next is self.NOTHING:
            self._next = next(self._iter, self.NOTHING)
        return self._next


def _valid_char(char: str) -> bool:
    return char.isalnum() or char == "_"


class _State:
    READING_VAR = 1
    READING_MODIFIER_VAR = 2
    READING_MODIFIER = 3
    FINISHED_READING = -1


class _ModifierType:
    GET_DEFAULT = 1


def _read_var(buff: _PeekableIterator) -> tuple[str, int | None, list[str]]:
    """Parse a variable reference starting after the '$' or after '${'.

    Returns (var_name, modifier_type, modifier_parts).
    modifier_type is None for bare variables, GET_DEFAULT for :- syntax.
    """
    name: list[str] = []
    state = _State.READING_VAR
    modifier: list[str] = []
    modifier_type: int | None = None
    brace_depth = 0

    while state != _State.FINISHED_READING:
        nxt = buff.peek()

        if nxt is _PeekableIterator.NOTHING:
            if state in (_State.READING_MODIFIER_VAR, _State.READING_MODIFIER):
                # Unterminated — treat as literal
                break
            state = _State.FINISHED_READING

        elif nxt == "{" and state == _State.READING_VAR:
            next(buff)
            state = _State.READING_MODIFIER_VAR

        elif nxt == "}" and state == _State.READING_MODIFIER_VAR:
            next(buff)
            state = _State.FINISHED_READING

        elif _valid_char(str(nxt)) and state in (
            _State.READING_VAR,
            _State.READING_MODIFIER_VAR,
        ):
            name.append(next(buff))

        elif nxt == ":" and state == _State.READING_MODIFIER_VAR:
            next(buff)
            nxt2 = buff.peek()
            if nxt2 == "-":
                next(buff)
                modifier_type = _ModifierType.GET_DEFAULT
                state = _State.READING_MODIFIER
            else:
                # Unknown modifier — treat as literal
                name.append(":")
                if nxt2 is not _PeekableIterator.NOTHING:
                    name.append(str(nxt2))
                    next(buff)
                state = _State.READING_MODIFIER_VAR

        elif state == _State.READING_MODIFIER:
            c = next(buff)
            if c == "{":
                brace_depth += 1
                modifier.append(c)
            elif c == "}":
                if brace_depth == 0:
                    state = _State.FINISHED_READING
                else:
                    modifier.append(c)
                    brace_depth -= 1
            else:
                modifier.append(c)

        elif state == _State.READING_VAR:
            # Bare variable ended — don't consume
            state = _State.FINISHED_READING

        else:
            state = _State.FINISHED_READING

    var = "".join(name)
    return var, modifier_type, modifier


def expand(text: str, variables: Mapping[str, str] | None = None) -> str:
    """Expand template variables in *text* using Unix-style $ syntax.

    Args:
        text: Template string with ${VAR}, ${VAR:-default}, $VAR, $$ patterns.
        variables: Mapping of variable names to values.

    Returns:
        The string with all known variables expanded.
    """
    if variables is None:
        variables = {}

    if not text:
        return ""

    result: list[str] = []
    it = _PeekableIterator(text)

    for c in it:
        if c == _ESCAPE_CHAR:
            nxt = it.peek()
            if nxt == _VAR_SYMBOL or nxt == _ESCAPE_CHAR:
                result.append(next(it))
            elif nxt is _PeekableIterator.NOTHING:
                result.append(c)
            else:
                result.append(c)
                result.append(next(it))

        elif c == _VAR_SYMBOL:
            nxt = it.peek()
            if nxt is _PeekableIterator.NOTHING:
                # Trailing $ — keep literal
                result.append(c)

            elif nxt == _VAR_SYMBOL:
                # $$ → literal $
                next(it)
                result.append("$")

            elif _valid_char(str(nxt)) or nxt == "{":
                var, mod_type, mod_parts = _read_var(it)
                if not var:
                    result.append("$")
                    continue

                val = variables.get(var)
                if mod_type == _ModifierType.GET_DEFAULT:
                    default_val = expand("".join(mod_parts), variables)
                    val = val if val is not None else default_val
                elif val is None:
                    # Unresolved — keep the original syntax
                    if mod_parts or nxt == "{":
                        result.append("${" + var + "}")
                    else:
                        result.append("$" + var)
                    continue

                result.append(val)

            else:
                # $ followed by non-var char — keep literal $
                result.append(c)

        else:
            result.append(c)

    return "".join(result)


def check_unresolved(text: str) -> list[str]:
    """Return a list of unresolved ${VAR} variable names in *text*.

    Only detects braced form ${VAR}. Bare $VAR is not detected because
    it's ambiguous with legitimate text.
    """
    return _UNRESOLVED_RE.findall(text)


def resolve_templates(fields: list[str], variables: Mapping[str, str]) -> list[str]:
    """Expand a list of template strings using the given variables."""
    return [expand(f, variables) for f in fields]
