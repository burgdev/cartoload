"""Pre-warp GeoTIFF files to a target CRS with palette expansion.

Converts source GeoTIFFs (any CRS, possibly paletted) to 3-band RGB
GeoTIFFs in EPSG:4326, cached alongside the originals. This eliminates
per-tile CRS transforms and palette expansion during export, dramatically
improving performance at low zoom levels where large pixel windows would
otherwise be read, expanded, and then downsampled.

After pre-warping, individual files are merged into a single mosaic so
that tiles spanning multiple source GeoTIFFs can read all data at once.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import ColorInterp
from rasterio.warp import calculate_default_transform, reproject, Resampling

logger = logging.getLogger(__name__)


def prewarp_geotiff(
    source_path: Path,
    target_crs: str = "EPSG:4326",
    force: bool = False,
) -> Path:
    """Pre-warp a GeoTIFF to target_crs with palette expansion.

    Produces a 3-band uint8 RGB GeoTIFF alongside the original.
    Cache file: {stem}_4326.tif in same directory.

    Skips if cache exists and mtime >= source mtime (or force=True).
    Returns source_path unchanged if already in target CRS and not paletted.

    Args:
        source_path: Path to original GeoTIFF (any CRS, may be paletted)
        target_crs: Target CRS string (default "EPSG:4326")
        force: If True, re-warp even if cache exists

    Returns:
        Path to the pre-warped GeoTIFF (or source_path if no warp needed)
    """
    dst_crs = CRS.from_user_input(target_crs)

    # Check if source is already in target CRS and not paletted
    with rasterio.open(source_path) as src:
        already_ok = (
            src.crs is not None
            and src.crs == dst_crs
            and (len(src.colorinterp) == 0 or src.colorinterp[0] != ColorInterp.palette)
            and src.count >= 3
        )

    if already_ok:
        return source_path

    cache_path = source_path.parent / f"{source_path.stem}_4326.tif"

    # Check cache freshness
    if not force and cache_path.exists():
        if cache_path.stat().st_mtime >= source_path.stat().st_mtime:
            logger.debug("Using cached pre-warp: %s", cache_path)
            return cache_path

    logger.info("Pre-warping %s -> %s", source_path.name, cache_path.name)

    with rasterio.open(source_path) as src:
        src_crs = src.crs
        if src_crs is None:
            logger.warning("No CRS in %s, skipping pre-warp", source_path)
            return source_path

        # Compute output dimensions and transform
        transform, width, height = calculate_default_transform(
            src_crs, dst_crs, src.width, src.height, *src.bounds
        )

        if width <= 0 or height <= 0:
            logger.warning("Invalid output dimensions for %s, skipping", source_path)
            return source_path

        # Detect palette
        is_paletted = (
            src.count == 1
            and len(src.colorinterp) > 0
            and src.colorinterp[0] == ColorInterp.palette
        )

        # Build colormap LUT if paletted
        lut: np.ndarray | None = None
        if is_paletted:
            try:
                cm = src.colormap(1)
                lut = np.zeros((256, 3), dtype=np.uint8)
                for idx, rgba in cm.items():
                    if 0 <= idx < 256:
                        lut[idx] = [rgba[0], rgba[1], rgba[2]]
            except ValueError:
                lut = None

        # Write pre-warped file
        profile = {
            "driver": "GTiff",
            "width": width,
            "height": height,
            "count": 3,
            "dtype": "uint8",
            "crs": dst_crs,
            "transform": transform,
            "compress": "lzw",
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256,
        }

        with rasterio.open(cache_path, "w", **profile) as dst:
            if is_paletted and lut is not None:
                # Warp palette indices first (preserving exact pixel identity),
                # then expand to RGB. This avoids color fringing that occurs
                # when warping RGB bands independently — nearest-neighbor on
                # each band can pick from different source pixels due to
                # sub-pixel rounding in the CRS transform.
                indices = src.read(1)  # (H, W) uint8
                warped_indices = np.zeros((height, width), dtype="uint8")
                reproject(
                    source=indices,
                    destination=warped_indices,
                    src_transform=src.transform,
                    src_crs=src_crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.nearest,
                    dst_nodata=0,
                )

                # Now expand the warped indices to RGB
                rgb = lut[warped_indices]  # (H, W, 3)
                src_rgb = rgb.transpose(2, 0, 1)  # (3, H, W)
                for band_idx in range(3):
                    dst.write(src_rgb[band_idx], band_idx + 1)
            else:
                # Non-paletted: warp existing bands to RGB
                src_bands = min(src.count, 3)
                for band_idx in range(3):
                    src_band_idx = min(band_idx, src_bands - 1) + 1
                    band_out = np.zeros((height, width), dtype="uint8")
                    reproject(
                        source=rasterio.band(src, src_band_idx),
                        destination=band_out,
                        src_transform=src.transform,
                        src_crs=src_crs,
                        dst_transform=transform,
                        dst_crs=dst_crs,
                        resampling=Resampling.bilinear,
                        src_nodata=src.nodata,
                        dst_nodata=0,
                    )
                    dst.write(band_out, band_idx + 1)

    logger.info("Pre-warp complete: %s (%dx%d)", cache_path.name, width, height)
    return cache_path


def _needs_warp(source_path: Path, target_crs: str = "EPSG:4326") -> bool:
    """Check whether a GeoTIFF needs pre-warping (no fresh cache exists)."""
    dst_crs = CRS.from_user_input(target_crs)

    with rasterio.open(source_path) as src:
        # Already in target CRS and not paletted — no warp needed
        if (
            src.crs is not None
            and src.crs == dst_crs
            and (len(src.colorinterp) == 0 or src.colorinterp[0] != ColorInterp.palette)
            and src.count >= 3
        ):
            return False

    cache_path = source_path.parent / f"{source_path.stem}_4326.tif"
    if (
        cache_path.exists()
        and cache_path.stat().st_mtime >= source_path.stat().st_mtime
    ):
        return False

    return True


def prewarp_all_geotiffs(
    geotiff_paths: list[Path],
    target_crs: str = "EPSG:4326",
    force: bool = False,
    progress_callback: Callable[[str, str], None] | None = None,
) -> dict[Path, Path]:
    """Pre-warp all GeoTIFFs, returning mapping from original to pre-warped paths.

    Args:
        geotiff_paths: List of original GeoTIFF file paths
        target_crs: Target CRS for pre-warping
        force: Force re-warp even if cache exists
        progress_callback: Called with (stage, description) for progress

    Returns:
        Dict mapping original_path -> prewarped_path
        (identity mapping for files that didn't need warping)
    """
    mapping: dict[Path, Path] = {}

    # Check which files actually need warping
    to_warp = [p for p in geotiff_paths if force or _needs_warp(p, target_crs)]

    if to_warp and progress_callback:
        progress_callback(
            "prewarp", f"Pre-warping {len(to_warp)} GeoTIFF(s) to EPSG:4326..."
        )

    for i, path in enumerate(to_warp, 1):
        if progress_callback and len(to_warp) > 1:
            progress_callback("prewarp", f"Pre-warping GeoTIFF {i}/{len(to_warp)}...")

        mapping[path] = prewarp_geotiff(path, target_crs=target_crs, force=force)

    # Fill in the rest (cached or already in target CRS)
    for path in geotiff_paths:
        if path not in mapping:
            mapping[path] = prewarp_geotiff(path, target_crs=target_crs, force=force)

    return mapping


def merge_prewarped_geotiffs(
    prewarped_paths: list[Path],
    cache_dir: Path,
    mosaic_name: str = "mosaic_4326.tif",
    force: bool = False,
    progress_callback: Callable[[str, str], None] | None = None,
) -> Path:
    """Merge all pre-warped GeoTIFFs into a single mosaic file.

    This is essential for low-zoom tiles that span multiple source GeoTIFFs.
    Without merging, each tile only reads from one GeoTIFF and misses data
    from others.

    The mosaic is cached in cache_dir. It is re-created only when any source
    file has a newer mtime than the existing mosaic (or force=True).

    Args:
        prewarped_paths: List of pre-warped GeoTIFF paths (EPSG:4326, 3-band RGB)
        cache_dir: Directory to store the mosaic file
        mosaic_name: Filename for the mosaic (default "mosaic_4326.tif")
        force: Force re-merge even if cached mosaic exists
        progress_callback: Called with (stage, description) for progress

    Returns:
        Path to the merged mosaic GeoTIFF
    """
    if not prewarped_paths:
        raise ValueError("No pre-warped GeoTIFFs to merge")

    mosaic_path = cache_dir / mosaic_name

    # Check if we can skip merging (all source files older than mosaic)
    if not force and mosaic_path.exists():
        mosaic_mtime = mosaic_path.stat().st_mtime
        if all(p.stat().st_mtime <= mosaic_mtime for p in prewarped_paths):
            logger.debug("Using cached mosaic: %s", mosaic_path)
            return mosaic_path

    if progress_callback:
        progress_callback("merge", "Merging GeoTIFFs into mosaic...")

    # Open all datasets for merging
    datasets = [rasterio.open(p) for p in prewarped_paths]

    try:
        # Compute a shared pixel grid that encompasses all datasets.
        # Pre-warped files share the same CRS but may have slightly different
        # pixel resolutions after the CRS warp (e.g., 1.494e-5 vs 1.499e-5).
        # We use reproject with nearest-neighbor instead of direct pixel copy
        # to correctly handle sub-pixel misalignment and avoid seam gaps.
        dst_crs = datasets[0].crs

        # Use the median resolution as the target pixel size
        resolutions = [abs(ds.res[0]) for ds in datasets]
        res = sorted(resolutions)[len(resolutions) // 2]

        # Find bounding box across all datasets
        all_left = min(ds.bounds.left for ds in datasets)
        all_bottom = min(ds.bounds.bottom for ds in datasets)
        all_right = max(ds.bounds.right for ds in datasets)
        all_top = max(ds.bounds.top for ds in datasets)

        # Compute output dimensions
        dst_width = int(math.ceil((all_right - all_left) / res))
        dst_height = int(math.ceil((all_top - all_bottom) / res))

        dst_transform = rasterio.transform.from_bounds(
            all_left,
            all_bottom,
            all_right,
            all_top,
            dst_width,
            dst_height,
        )

        # Allocate output (3 bands, initialized to nodata=0)
        mosaic_arr = np.zeros((3, dst_height, dst_width), dtype="uint8")

        for ds in datasets:
            # Use reproject with nearest-neighbor to handle sub-pixel offsets.
            # This correctly fills every destination pixel from the closest
            # source pixel, avoiding 1-pixel seam gaps that occur with direct
            # integer-offset pixel copying when source files have slightly
            # different resolutions.
            band_out = np.zeros((3, dst_height, dst_width), dtype="uint8")
            for band_idx in range(3):
                reproject(
                    source=rasterio.band(ds, band_idx + 1),
                    destination=band_out[band_idx],
                    src_transform=ds.transform,
                    src_crs=ds.crs,
                    dst_transform=dst_transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.nearest,
                    src_nodata=0,
                    dst_nodata=0,
                )

            # Only overwrite where the source has data (any band nonzero)
            valid = np.any(band_out != 0, axis=0)
            for b in range(3):
                mosaic_arr[b][valid] = band_out[b][valid]

        profile = {
            "driver": "GTiff",
            "width": dst_width,
            "height": dst_height,
            "count": 3,
            "dtype": "uint8",
            "crs": dst_crs,
            "transform": dst_transform,
            "compress": "lzw",
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256,
            "nodata": 0,
        }

        with rasterio.open(mosaic_path, "w", **profile) as dst:
            dst.write(mosaic_arr)

    finally:
        for ds in datasets:
            try:
                ds.close()
            except Exception:
                pass

    logger.info("Mosaic complete: %s (%dx%d)", mosaic_path.name, dst_width, dst_height)
    return mosaic_path
