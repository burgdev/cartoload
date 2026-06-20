"""Shared tile math utilities for Web Mercator (EPSG:3857 / EPSG:4326).

Canonical implementations of:
- ``lon_to_tile_x`` / ``lat_to_tile_y`` — convert WGS84 coords to tile indices
- ``tile_x_to_lon`` / ``tile_y_to_lat`` — convert tile indices to WGS84 coords
- ``compute_bounds_4326`` — compute WGS84 bounding box for a tile
- ``bounds_to_tile_coords`` — compute tile grid covering a bounding box
- ``ProcessedTile`` — type alias for (jpeg_bytes, bounds) tuples
"""

from __future__ import annotations

import math
from typing import TypeAlias

# Type alias for processed tile data: (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max))
ProcessedTile: TypeAlias = tuple[bytes, tuple[float, float, float, float]]


def lon_to_tile_x(lon: float, zoom: int) -> int:
    """Convert longitude (degrees) to tile X index at the given zoom level."""
    n = 2**zoom
    return max(0, min(int((lon + 180.0) / 360.0 * n), n - 1))


def lat_to_tile_y(lat: float, zoom: int) -> int:
    """Convert latitude (degrees) to tile Y index at the given zoom level.

    Uses the standard Web Mercator projection formula.
    """
    n = 2**zoom
    lat_rad = math.radians(lat)
    return max(
        0,
        min(
            int(
                (
                    1.0
                    - math.log(
                        max(math.tan(lat_rad), 1e-10)
                        + 1.0 / max(math.cos(lat_rad), 1e-10)
                    )
                    / math.pi
                )
                / 2.0
                * n
            ),
            n - 1,
        ),
    )


def tile_x_to_lon(x: int, zoom: int) -> float:
    """Convert tile X index to longitude (degrees) at the western edge."""
    n = 2**zoom
    return x / n * 360.0 - 180.0


def tile_y_to_lat(y: int, zoom: int) -> float:
    """Convert tile Y index to latitude (degrees) at the northern edge."""
    n = 2**zoom
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    return math.degrees(lat_rad)


def compute_bounds_4326(x: int, y: int, zoom: int) -> tuple[float, float, float, float]:
    """Compute WGS84 bounding box for a Web Mercator tile.

    Args:
        x: Tile X coordinate
        y: Tile Y coordinate
        zoom: Zoom level

    Returns:
        ``(lat_min, lon_min, lat_max, lon_max)`` in WGS84 degrees
    """
    n = 2**zoom
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0

    lat_max_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_min_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))

    return (math.degrees(lat_min_rad), lon_min, math.degrees(lat_max_rad), lon_max)


def bounds_to_tile_coords(
    west: float,
    south: float,
    east: float,
    north: float,
    zoom: int,
) -> list[tuple[int, int]]:
    """Compute tile grid coordinates covering the given WGS84 bounding box.

    Args:
        west: Western longitude (degrees)
        south: Southern latitude (degrees)
        east: Eastern longitude (degrees)
        north: Northern latitude (degrees)
        zoom: Zoom level

    Returns:
        List of ``(x, y)`` tile coordinates covering the bbox
    """
    x_min = lon_to_tile_x(west, zoom)
    x_max = lon_to_tile_x(east, zoom)
    y_min = lat_to_tile_y(north, zoom)
    y_max = lat_to_tile_y(south, zoom)

    coords = []
    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            coords.append((x, y))
    return coords
