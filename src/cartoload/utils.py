"""Shared utility functions and type aliases.

Centralizes commonly duplicated patterns across the codebase:
- Registry[T]: generic name→type registry
- human_size: byte count formatting
- ensure_rgb / ensure_rgba: PIL image mode normalization
- encode_jpeg: PIL Image → JPEG bytes
- ProgressCallback / ExportProgressCallback: pipeline progress type aliases
"""

from __future__ import annotations

import io
import logging
from typing import Callable, Generic, TypeVar

from PIL import Image

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Generic registry
# ---------------------------------------------------------------------------


class Registry(Generic[T]):
    """A generic name → type registry.

    Provides ``register``, ``resolve``, and ``get_all`` methods.
    Used by both the source and processor registries.
    """

    def __init__(self, label: str) -> None:
        self._label = label
        self._types: dict[str, type[T]] = {}

    def register(self, name: str, cls: type[T]) -> None:
        """Register a type by name. Overwrites if already registered."""
        if name in self._types:
            logger.warning("%s '%s' already registered, overwriting", self._label, name)
        self._types[name] = cls

    def resolve(self, name: str) -> type[T]:
        """Look up a registered type by name.

        Raises:
            ValueError: If the name is not registered.
        """
        cls = self._types.get(name)
        if cls is None:
            available = ", ".join(sorted(self._types.keys()))
            raise ValueError(
                f"Unknown {self._label.lower()} '{name}'. "
                f"Available {self._label.lower()}s: {available}"
            )
        return cls

    def get_all(self) -> dict[str, type[T]]:
        """Return a copy of the registry (for inspection/testing)."""
        return dict(self._types)


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[str, str], None]
"""Called with (stage_id, description) at each pipeline stage."""

ExportProgressCallback = Callable[[str, int, int], None]
"""Called with (stage, current, total) for export progress."""


# ---------------------------------------------------------------------------
# Byte formatting
# ---------------------------------------------------------------------------


def human_size(size: int | float) -> str:
    """Format a byte count as a human-readable string.

    Uses clean formatting that strips trailing zeros:
        >>> human_size(500)
        '500 B'
        >>> human_size(1536000)
        '1.5 MB'
    """
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            formatted = f"{value:.2f}".rstrip("0").rstrip(".")
            return f"{formatted} {unit}"
        value /= 1024
    formatted = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{formatted} TB"


# ---------------------------------------------------------------------------
# Image utilities
# ---------------------------------------------------------------------------


def ensure_rgb(img: Image.Image) -> Image.Image:
    """Ensure a PIL Image is in RGB mode, compositing alpha over white.

    For RGBA images, composites over a white background.
    For other non-RGB modes, converts via PIL's convert().

    Returns:
        The same Image object if already RGB, or a new RGB Image.
    """
    if img.mode == "RGB":
        return img
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        return background
    return img.convert("RGB")


def ensure_rgba(img: Image.Image) -> Image.Image:
    """Ensure a PIL Image is in RGBA mode.

    Returns:
        The same Image object if already RGBA, or a new RGBA Image.
    """
    if img.mode == "RGBA":
        return img
    return img.convert("RGBA")


def encode_jpeg(
    img: Image.Image,
    quality: int = 95,
    *,
    optimize: bool = True,
) -> bytes:
    """Encode a PIL Image as JPEG bytes.

    Converts to RGB if necessary before encoding.

    Args:
        img: PIL Image to encode (any mode).
        quality: JPEG quality 1-100 (default 95 for high-quality intermediate).
        optimize: Whether to optimize the JPEG encoding (default True).

    Returns:
        JPEG bytes.
    """
    rgb = ensure_rgb(img)
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=quality, optimize=optimize)
    return buf.getvalue()
