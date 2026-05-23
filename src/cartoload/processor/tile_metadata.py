"""Compute tile metadata for layout-only processing.

Produces TileMetadata objects from tile coordinates without loading JPEG data.
Bounds are computed deterministically from Web Mercator tile grid math;
JPEG sizes come from source file stat.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from ..exporters.garmin_img_model import TileMetadata
from cartoload.tile_math import compute_bounds_4326

logger = logging.getLogger(__name__)


def compute_tile_metadata(
    tile_coords: list[tuple[int, int]],
    zoom: int,
    source_crs: str | None,
    downloader,
) -> list[TileMetadata]:
    """Compute tile metadata for all tiles at a zoom level.

    For each (x, y) tile coordinate, computes geographic bounds from
    Web Mercator grid math and JPEG file size from the source cache.
    No JPEG data is loaded into memory.

    Args:
        tile_coords: List of (x, y) tile grid coordinates
        zoom: Zoom level (WMTS source zoom)
        source_crs: Source CRS string (e.g. "EPSG:3857", "EPSG:4326")
        downloader: Downloader instance for resolving cache paths

    Returns:
        List of TileMetadata objects
    """
    results: list[TileMetadata] = []
    for x, y in tile_coords:
        # Compute bounds deterministically from tile coordinates
        lat_min, lon_min, lat_max, lon_max = compute_bounds_4326(x, y, zoom)

        # Resolve source file path and get JPEG size
        source_path = _resolve_source_path(downloader, x, y, zoom)
        jpeg_size = 0
        if source_path is not None and source_path.exists():
            try:
                jpeg_size = os.path.getsize(source_path)
            except OSError:
                logger.warning(
                    "Cannot stat source tile %s: %s", source_path, exc_info=True
                )
                jpeg_size = 0

        results.append(
            TileMetadata(
                x=x,
                y=y,
                zoom=zoom,
                lat_min=lat_min,
                lon_min=lon_min,
                lat_max=lat_max,
                lon_max=lon_max,
                jpeg_size=jpeg_size,
                source_path=source_path,
            )
        )

    return results


def _resolve_source_path(downloader, x: int, y: int, zoom: int) -> Path | None:
    """Resolve the source tile cache path from the downloader.

    Uses the downloader's _cache_path method if available (duck typing),
    falling back to isinstance check for WmtsDownloader.
    """
    if hasattr(downloader, "_cache_path"):
        return downloader._cache_path(x, y, zoom)
    return None
