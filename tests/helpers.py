"""Shared test utilities for cartoload test suite."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image


def make_jpeg(
    width: int = 256,
    height: int = 256,
    color: tuple[int, int, int] = (128, 128, 128),
    quality: int = 85,
) -> bytes:
    """Create a solid-color JPEG image.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        color: RGB color tuple
        quality: JPEG quality (1-100)

    Returns:
        JPEG bytes
    """
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def write_tile_with_world_file(
    tile_path: Path,
    pixel_size_x: float = 0.01,
    pixel_size_y: float = -0.01,
    top_left_x: float = 7.0,
    top_left_y: float = 47.0,
) -> Path:
    """Write a JPEG tile + world file to the given path.

    Args:
        tile_path: Path for the JPEG tile
        pixel_size_x: Horizontal pixel size (degrees per pixel)
        pixel_size_y: Vertical pixel size (degrees per pixel, typically negative)
        top_left_x: Longitude of the tile's top-left corner
        top_left_y: Latitude of the tile's top-left corner

    Returns:
        Path to the written JPEG tile
    """
    tile_path.parent.mkdir(parents=True, exist_ok=True)
    tile_path.write_bytes(make_jpeg())

    # Write world file
    wf_path = tile_path.with_suffix(".jgw")
    wf_path.write_text(
        f"{pixel_size_x:.10f}\n"
        f"0.0\n"
        f"0.0\n"
        f"{pixel_size_y:.10f}\n"
        f"{top_left_x}\n"
        f"{top_left_y}\n"
    )
    return tile_path
