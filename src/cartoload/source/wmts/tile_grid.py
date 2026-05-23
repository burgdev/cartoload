"""Tile grid computation from WMTS TileMatrixSet parameters.

Computes tile coordinates from bounding boxes using the generic WMTS
tile grid formula. Works with any TileMatrixSet (EPSG:3857, EPSG:4326, etc.).
"""

from __future__ import annotations

import math

from .capabilities import TileMatrix, TileMatrixSet


def bbox_to_tile_indices(
    bbox: tuple[float, float, float, float],
    tile_matrix_set: TileMatrixSet,
    zoom: int,
) -> list[tuple[int, int]]:
    """Convert a WGS84 bounding box to tile (x, y) indices at the given zoom.

    Uses the generic WMTS tile grid formula from the TileMatrixSet parameters.
    For EPSG:3857 TileMatrixSets, the bbox must be in meters (Web Mercator).
    For EPSG:4326 TileMatrixSets, the bbox is in degrees.

    The zoom level selects the corresponding TileMatrix from the TileMatrixSet.

    Args:
        bbox: (min_x, min_y, max_x, max_y) in the TMS CRS.
        tile_matrix_set: The TileMatrixSet defining the grid.
        zoom: Zoom level (index into the TileMatrixSet's sorted tile matrices).

    Returns:
        Sorted list of (x, y) tile coordinate tuples covering the bbox.
    """
    tm = _get_tile_matrix(tile_matrix_set, zoom)
    if tm is None:
        return []

    pixel_span = (
        tm.scale_denominator * 0.00028
    )  # meters per pixel (0.28mm = standard pixel)
    tile_span_x = pixel_span * tm.tile_width
    tile_span_y = pixel_span * tm.tile_height

    min_x, min_y, max_x, max_y = bbox

    # Compute tile indices
    x_min = max(0, int(math.floor((min_x - tm.top_left_x) / tile_span_x)))
    x_max = min(
        tm.matrix_width - 1,
        int(math.floor((max_x - tm.top_left_x) / tile_span_x)),
    )
    # Y increases downward from top_left_y
    y_min = max(0, int(math.floor((tm.top_left_y - max_y) / tile_span_y)))
    y_max = min(
        tm.matrix_height - 1,
        int(math.floor((tm.top_left_y - min_y) / tile_span_y)),
    )

    tiles = []
    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            tiles.append((x, y))

    return tiles


def compute_tile_bounds(
    x: int,
    y: int,
    tile_matrix: TileMatrix,
) -> tuple[float, float, float, float]:
    """Compute the bounding box of a tile in the TMS CRS.

    Args:
        x: Tile column index.
        y: Tile row index.
        tile_matrix: The TileMatrix defining the grid at this zoom level.

    Returns:
        (left, bottom, right, top) in the TMS CRS coordinates.
    """
    pixel_span = tile_matrix.scale_denominator * 0.00028
    tile_span_x = pixel_span * tile_matrix.tile_width
    tile_span_y = pixel_span * tile_matrix.tile_height

    left = tile_matrix.top_left_x + x * tile_span_x
    top = tile_matrix.top_left_y - y * tile_span_y
    right = left + tile_span_x
    bottom = top - tile_span_y

    return (left, bottom, right, top)


def wgs84_to_tms_bbox(
    bbox_wgs84: tuple[float, float, float, float],
    tile_matrix_set: TileMatrixSet,
) -> tuple[float, float, float, float]:
    """Convert a WGS84 bbox to the TileMatrixSet's CRS.

    For EPSG:3857, transforms lon/lat to Web Mercator meters.
    For EPSG:4326, returns as-is (already in degrees).

    Args:
        bbox_wgs84: (min_lon, min_lat, max_lon, max_lat) in WGS84 degrees.
        tile_matrix_set: The TileMatrixSet whose CRS to transform to.

    Returns:
        (min_x, min_y, max_x, max_y) in the TMS CRS.
    """
    epsg = tile_matrix_set.epsg_code

    if epsg == "4326":
        # Already in degrees — return as-is
        return bbox_wgs84
    elif epsg == "3857":
        # Transform WGS84 to Web Mercator
        min_lon, min_lat, max_lon, max_lat = bbox_wgs84
        return (
            _lon_to_mercator_x(min_lon),
            _lat_to_mercator_y(min_lat),
            _lon_to_mercator_x(max_lon),
            _lat_to_mercator_y(max_lat),
        )
    else:
        # Unknown CRS — log warning, assume CRS matches WGS84
        import logging

        logging.getLogger(__name__).warning(
            "Unknown TMS CRS '%s', using WGS84 coordinates directly",
            tile_matrix_set.supported_crs,
        )
        return bbox_wgs84


def _lon_to_mercator_x(lon: float) -> float:
    """Convert longitude (degrees) to Web Mercator X (meters)."""
    return lon * 20037508.342789244 / 180.0


def _lat_to_mercator_y(lat: float) -> float:
    """Convert latitude (degrees) to Web Mercator Y (meters)."""
    lat_rad = math.radians(lat)
    return (
        math.log(math.tan(math.pi / 4.0 + lat_rad / 2.0)) * 20037508.342789244 / math.pi
    )


def _get_tile_matrix(
    tile_matrix_set: TileMatrixSet,
    zoom: int,
) -> TileMatrix | None:
    """Get the TileMatrix for a given zoom level.

    TileMatrixSets are sorted by scale denominator (largest first = zoom 0).
    """
    if 0 <= zoom < len(tile_matrix_set.tile_matrices):
        return tile_matrix_set.tile_matrices[zoom]
    return None
