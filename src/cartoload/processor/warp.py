"""In-process tile reprojection using rasterio.

Replaces the gdalwarp subprocess approach. Warps tiles from source CRS
to EPSG:4326 using rasterio's reproject() and outputs JPEG bytes via PIL.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import Affine
from rasterio.warp import calculate_default_transform, reproject, Resampling

from cartoload.tile_math import ProcessedTile, compute_bounds_4326
from ..utils import ensure_rgba

logger = logging.getLogger(__name__)


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
) -> ProcessedTile | None:
    """Warp a single tile and return JPEG bytes with geographic bounds.

    Handles two cases:
    - Source CRS matches target CRS: read raw JPEG, compute bounds from coords
    - Source CRS differs: warp in-process via rasterio, output JPEG via MemoryFile

    Always encodes at quality 95 (high quality intermediate step).
    The target quality is applied only during the final IMG write step.

    Args:
        source_path: Path to the source tile file
        x: Tile X coordinate
        y: Tile Y coordinate
        zoom: Zoom level
        source_crs: Source CRS string (e.g., "EPSG:3857")
        target_crs: Target CRS string (default "EPSG:4326")

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

    # Warp needed — always encode at high quality (95)
    try:
        return _warp_to_jpeg(source_path, x, y, zoom, src_crs, dst_crs)
    except Exception as e:
        logger.warning("Warp failed for (%d, %d, z=%d): %s", x, y, zoom, e)
        return None


def warp_tile_to_rgba(
    source_path: Path,
    x: int,
    y: int,
    zoom: int,
    source_crs: str,
    target_crs: str = "EPSG:4326",
) -> tuple[Image.Image, tuple[float, float, float, float]] | None:
    """Warp a single tile and return a PIL RGBA Image with geographic bounds.

    Like warp_tile_to_jpeg but returns an RGBA PIL Image instead of JPEG
    bytes. Used by the compositing pipeline where tiles need to be blended
    before final JPEG encoding.

    Args:
        source_path: Path to the source tile file (JPEG or PNG)
        x: Tile X coordinate
        y: Tile Y coordinate
        zoom: Zoom level
        source_crs: Source CRS string (e.g., "EPSG:3857")
        target_crs: Target CRS string (default "EPSG:4326")

    Returns:
        (PIL Image in RGBA mode, (lat_min, lon_min, lat_max, lon_max)) or None
    """
    if not source_path.exists():
        return None

    bounds = compute_bounds_4326(x, y, zoom)
    src_crs_obj = CRS.from_user_input(source_crs)
    dst_crs_obj = CRS.from_user_input(target_crs)

    # Passthrough: no reprojection needed
    if src_crs_obj == dst_crs_obj:
        img = _load_as_rgba(source_path)
        if img is None:
            return None
        return (img, bounds)

    # Warp needed
    try:
        return _warp_to_rgba(source_path, x, y, zoom, src_crs_obj, dst_crs_obj)
    except Exception as e:
        logger.warning("Warp to RGBA failed for (%d, %d, z=%d): %s", x, y, zoom, e)
        return None


def _load_as_rgba(source_path: Path) -> Image.Image | None:
    """Load a tile file as RGBA PIL Image, preserving alpha for PNG."""
    try:
        img = Image.open(source_path)
        return ensure_rgba(img)
    except Exception as e:
        logger.warning("Failed to load tile %s: %s", source_path, e)
        return None


def _warp_to_rgba(
    source_path: Path,
    x: int,
    y: int,
    zoom: int,
    src_crs: CRS,
    dst_crs: CRS,
) -> tuple[Image.Image, tuple[float, float, float, float]]:
    """Warp a tile from source CRS to target CRS, outputting RGBA PIL Image."""
    src_transform, src_width, src_height = compute_transform_3857(x, y, zoom)

    left = src_transform.c
    top = src_transform.f
    right = left + src_transform.a * src_width
    bottom = top + src_transform.e * src_height

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=NotGeoreferencedWarning)
        with rasterio.open(source_path) as src:
            src_data = src.read()

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

            # Determine number of bands for warp
            n_bands = src.count
            if n_bands == 1:
                src_data = np.repeat(src_data, 3, axis=0)
                n_bands = 3
            elif n_bands == 2:
                # 1 band + alpha → expand to RGBA
                src_data = np.concatenate(
                    [
                        np.repeat(src_data[:1], 3, axis=0),
                        src_data[1:2],
                    ],
                    axis=0,
                )
                n_bands = 4
            elif n_bands >= 4:
                # Keep all 4 bands (RGBA)
                src_data = src_data[:4]
                n_bands = 4
            # n_bands == 3: keep as is

            dst_data = np.zeros((n_bands, dst_height, dst_width), dtype="uint8")
            reproject(
                source=src_data,
                destination=dst_data,
                src_transform=src_transform,
                src_crs=src_crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=Resampling.cubic,
            )

    # Convert to PIL RGBA Image
    if n_bands == 3:
        # No alpha channel — add fully opaque alpha
        dst_rgb = np.moveaxis(dst_data, 0, -1)
        img = Image.fromarray(dst_rgb, mode="RGB").convert("RGBA")
    else:
        # 4 bands → RGBA
        dst_rgba = np.moveaxis(dst_data, 0, -1)
        img = Image.fromarray(dst_rgba, mode="RGBA")

    bounds = compute_bounds_4326(x, y, zoom)
    return (img, bounds)


def _warp_to_jpeg(
    source_path: Path,
    x: int,
    y: int,
    zoom: int,
    src_crs: CRS,
    dst_crs: CRS,
) -> ProcessedTile:
    """Warp a tile from source CRS to target CRS, outputting JPEG bytes."""
    src_transform, src_width, src_height = compute_transform_3857(x, y, zoom)

    # Compute source bounds from transform
    left = src_transform.c
    top = src_transform.f
    right = left + src_transform.a * src_width
    bottom = top + src_transform.e * src_height  # e is negative

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=NotGeoreferencedWarning)
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
                resampling=Resampling.cubic,
            )

    # Encode to JPEG at high quality (intermediate step)
    from ..utils import encode_jpeg

    dst_rgb = np.moveaxis(dst_data, 0, -1)  # (C, H, W) → (H, W, C)
    img = Image.fromarray(dst_rgb)
    jpeg_bytes = encode_jpeg(img, quality=95)

    # Compute bounds from tile coordinates (WGS84)
    bounds = compute_bounds_4326(x, y, zoom)

    return (jpeg_bytes, bounds)
