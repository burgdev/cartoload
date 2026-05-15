"""Style model: dataclasses for line styles, rules, and Garmin type mappings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cartoload.style.match import MatchExpression


@dataclass(frozen=True)
class LineStyle:
    """Visual properties for rendering a line feature."""

    color: tuple[int, int, int] = (0, 0, 0)
    width: float = 1.0
    dash: list[float] | None = None
    border_color: tuple[int, int, int] | None = None
    border_width: float | None = None
    opacity: float = 1.0


@dataclass(frozen=True)
class GarminStyle:
    """Garmin type code and resolution range for mkgmap integration."""

    type_code: int  # Garmin type code (e.g., 0x16 = 22)
    resolution: tuple[int, int]  # (min, max) Garmin resolution range


@dataclass
class StyleRule:
    """A single style rule: match expression + zoom-keyed line styles."""

    match: "MatchExpression"
    zoom_styles: dict[int, LineStyle] = field(default_factory=dict)
    default_style: LineStyle = field(
        default_factory=lambda: LineStyle(color=(0, 0, 0), width=1.0)
    )
    garmin: GarminStyle | None = None


# ---- Color parsing utilities ----

_NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "orange": (255, 165, 0),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "transparent": (0, 0, 0),
}


def parse_color(value: str | tuple | list) -> tuple[int, int, int]:
    """Parse a color value to an (R, G, B) tuple.

    Supported formats:
    - Hex: "#RRGGBB" or "RRGGBB"
    - QGIS RGBA: "R,G,B,A" or "R,G,B"
    - Named: "white", "black", etc.
    - Tuple/list: (R, G, B)
    """
    if isinstance(value, (tuple, list)):
        return (int(value[0]), int(value[1]), int(value[2]))

    if not isinstance(value, str):
        raise ValueError(f"Cannot parse color from {type(value).__name__}: {value}")

    value = value.strip()

    # Named color
    lower = value.lower()
    if lower in _NAMED_COLORS:
        return _NAMED_COLORS[lower]

    # Hex with hash
    if value.startswith("#"):
        hex_str = value[1:]
        if len(hex_str) == 6:
            return (
                int(hex_str[0:2], 16),
                int(hex_str[2:4], 16),
                int(hex_str[4:6], 16),
            )
        if len(hex_str) == 3:
            return (
                int(hex_str[0] * 2, 16),
                int(hex_str[1] * 2, 16),
                int(hex_str[2] * 2, 16),
            )

    # Hex without hash (6 chars)
    if len(value) == 6 and all(c in "0123456789abcdefABCDEF" for c in value):
        return (
            int(value[0:2], 16),
            int(value[2:4], 16),
            int(value[4:6], 16),
        )

    # QGIS RGBA format: "R,G,B,A" or "R,G,B"
    parts = value.split(",")
    if len(parts) in (3, 4):
        try:
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            return (
                max(0, min(255, r)),
                max(0, min(255, g)),
                max(0, min(255, b)),
            )
        except (ValueError, IndexError):
            pass

    raise ValueError(f"Cannot parse color: '{value}'")


def resolve_style_for_zoom(rule: StyleRule, zoom: int) -> LineStyle:
    """Select the appropriate LineStyle for a given zoom level.

    Uses nearest-zoom-below fallback: finds the highest defined zoom
    at or below the requested zoom. Falls back to default_style if
    no zoom is defined at or below.
    """
    candidates = [z for z in rule.zoom_styles if z <= zoom]
    if candidates:
        return rule.zoom_styles[max(candidates)]
    return rule.default_style
