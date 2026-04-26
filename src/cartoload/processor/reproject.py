"""Per-tile reprojection: warp individual tiles from source CRS to target CRS."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from cartoload.downloader.base import BaseDownloader

logger = logging.getLogger(__name__)


class ReprojectionError(Exception):
    """Raised when tile reprojection fails."""


def reproject_tile(
    source_path: Path,
    source_crs: str,
    target_crs: str,
    output_path: Path,
) -> Path:
    """Reproject a single tile from source CRS to target CRS using gdalwarp.

    Args:
        source_path: Path to the source tile (with world file)
        source_crs: Source CRS string (e.g., "EPSG:3857")
        target_crs: Target CRS string (e.g., "EPSG:4326")
        output_path: Path for the reprojected output tile

    Returns:
        Path to the reprojected tile

    Raises:
        ReprojectionError: If gdalwarp fails
        FileNotFoundError: If gdalwarp is not available
    """
    if not shutil.which("gdalwarp"):
        raise FileNotFoundError(
            "gdalwarp not found on PATH. Install GDAL: sudo apt install gdal-bin"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "gdalwarp",
        "-s_srs",
        source_crs,
        "-t_srs",
        target_crs,
        "-of",
        "GTiff",
        "-co",
        "COMPRESS=LZW",
        "-co",
        "TILED=NO",
        str(source_path),
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        # Clean up partial output
        if output_path.exists():
            output_path.unlink()
        raise ReprojectionError(
            f"gdalwarp failed for {source_path}: {result.stderr.strip()}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise ReprojectionError(f"gdalwarp produced no output for {source_path}")

    return output_path


def reproject_tile_cached(
    source_path: Path,
    x: int,
    y: int,
    zoom: int,
    source_crs: str,
    target_crs: str,
    tile_format: str,
    downloader: BaseDownloader,
) -> Path:
    """Reproject a tile with cache awareness.

    Checks the reprojection cache first. If a valid cached version exists
    (source tile not newer), returns the cached path. Otherwise, reprojects
    and writes to cache.

    Args:
        source_path: Path to the source tile
        x: Tile X coordinate
        y: Tile Y coordinate
        zoom: Zoom level
        source_crs: Source CRS string
        target_crs: Target CRS string
        tile_format: Output format extension (e.g., "tif")
        downloader: BaseDownloader instance for cache path computation

    Returns:
        Path to the reprojected (or cached) tile
    """
    # If source already in target CRS, no reprojection needed
    if not BaseDownloader.needs_reprojection(source_crs, target_crs):
        return source_path

    # Check reprojection cache
    reproj_path = downloader.reprojection_cache_path(
        x, y, zoom, target_crs, tile_format
    )

    if downloader.is_reprojection_valid(source_path, reproj_path):
        logger.debug("Reprojection cache hit: %s", reproj_path)
        return reproj_path

    # Reproject
    logger.debug(
        "Reprojecting tile (%d, %d, z=%d): %s → %s", x, y, zoom, source_crs, target_crs
    )
    return reproject_tile(source_path, source_crs, target_crs, reproj_path)
