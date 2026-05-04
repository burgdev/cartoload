"""In-process tile reprojection using rasterio.

Replaces the gdalwarp subprocess approach. Warps tiles from source CRS
to EPSG:4326 using rasterio's reproject() and outputs JPEG bytes via PIL.
"""

from __future__ import annotations

import io
import logging
import math
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import Affine
from rasterio.warp import calculate_default_transform, reproject, Resampling

logger = logging.getLogger(__name__)

# Type alias: (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max))
ProcessedTile = tuple[bytes, tuple[float, float, float, float]]


def compute_bounds_4326(x: int, y: int, zoom: int) -> tuple[float, float, float, float]:
    """Compute WGS84 bounds from tile coordinates using Web Mercator grid math.

    Args:
        x: Tile X coordinate
        y: Tile Y coordinate
        zoom: Zoom level

    Returns:
        (lat_min, lon_min, lat_max, lon_max) in WGS84 degrees
    """
    n = 2**zoom
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0

    lat_max_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_min_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))

    return (math.degrees(lat_min_rad), lon_min, math.degrees(lat_max_rad), lon_max)


def compute_transform_3857(
    x: int, y: int, zoom: int, tile_pixels: int = 256
) -> tuple[Affine, int, int]:
    """Compute EPSG:3857 affine transform from tile coordinates.

    Args:
        x: Tile X coordinate
        y: Tile Y coordinate
        zoom: Zoom level
        tile_pixels: Tile dimensions in pixels (default 256)

    Returns:
        (transform, width, height) where transform is the affine transform
        for the source tile in EPSG:3857 coordinates
    """
    origin = -20037508.342789244
    tile_size = 40075016.68557849 / 2**zoom

    left = origin + x * tile_size
    top = -origin - y * tile_size

    pixel_size = tile_size / tile_pixels
    transform = Affine(pixel_size, 0.0, left, 0.0, -pixel_size, top)

    return transform, tile_pixels, tile_pixels


def warp_tile_to_jpeg(
    source_path: Path,
    x: int,
    y: int,
    zoom: int,
    source_crs: str,
    target_crs: str = "EPSG:4326",
    quality: int = 85,
) -> ProcessedTile | None:
    """Warp a single tile and return JPEG bytes with geographic bounds.

    Handles two cases:
    - Source CRS matches target CRS: read raw JPEG, compute bounds from coords
    - Source CRS differs: warp in-process via rasterio, output JPEG via MemoryFile

    Args:
        source_path: Path to the source tile file
        x: Tile X coordinate
        y: Tile Y coordinate
        zoom: Zoom level
        source_crs: Source CRS string (e.g., "EPSG:3857")
        target_crs: Target CRS string (default "EPSG:4326")
        quality: JPEG output quality (1-100)

    Returns:
        (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max)) or None if failed
    """
    if not source_path.exists():
        return None

    src_crs = CRS.from_user_input(source_crs)
    dst_crs = CRS.from_user_input(target_crs)

    # Passthrough: no reprojection needed
    if src_crs == dst_crs:
        bounds = compute_bounds_4326(x, y, zoom)
        jpeg_bytes = source_path.read_bytes()
        return (jpeg_bytes, bounds)

    # Warp needed
    try:
        return _warp_to_jpeg(source_path, x, y, zoom, src_crs, dst_crs, quality)
    except Exception as e:
        logger.warning("Warp failed for (%d, %d, z=%d): %s", x, y, zoom, e)
        return None


def _warp_to_jpeg(
    source_path: Path,
    x: int,
    y: int,
    zoom: int,
    src_crs: CRS,
    dst_crs: CRS,
    quality: int,
) -> ProcessedTile:
    """Warp a tile from source CRS to target CRS, outputting JPEG bytes."""
    src_transform, src_width, src_height = compute_transform_3857(x, y, zoom)

    # Compute source bounds from transform
    left = src_transform.c
    top = src_transform.f
    right = left + src_transform.a * src_width
    bottom = top + src_transform.e * src_height  # e is negative

    with rasterio.open(source_path) as src:
        src_data = src.read()

        # Compute destination transform and dimensions
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src_crs,
            dst_crs,
            src.width,
            src.height,
            transform=src_transform,
            left=left,
            bottom=bottom,
            right=right,
            top=top,
        )

        # Warp source data into destination array
        # JPEG requires exactly 3 bands (RGB) — convert if needed
        if src.count == 1:
            src_data = np.repeat(src_data, 3, axis=0)
        elif src.count == 4:
            src_data = src_data[:3]
        elif src.count != 3:
            src_data = src_data[:3]

        dst_data = np.zeros((3, dst_height, dst_width), dtype="uint8")
        reproject(
            source=src_data,
            destination=dst_data,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.bilinear,
        )

    # Encode to JPEG via PIL (rasterio's MemoryFile ignores JPEG_QUALITY)
    dst_rgb = np.moveaxis(dst_data, 0, -1)  # (C, H, W) → (H, W, C)
    img = Image.fromarray(dst_rgb)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    jpeg_bytes = buf.getvalue()

    # Compute bounds from tile coordinates (WGS84)
    bounds = compute_bounds_4326(x, y, zoom)

    return (jpeg_bytes, bounds)
