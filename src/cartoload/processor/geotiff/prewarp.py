"""Pre-warp GeoTIFF files to a target CRS with palette expansion.

Converts source GeoTIFFs (any CRS, possibly paletted) to 3-band RGB
GeoTIFFs in EPSG:4326 using the ``gdalwarp`` CLI for multi-threaded,
block-streamed processing. Results are cached alongside the originals.

After pre-warping, individual files are assembled into a VRT (Virtual
Raster Table) so that tiles spanning multiple source GeoTIFFs can read
all data at once — without allocating a full mosaic in memory.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import rasterio
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rasterio.crs import CRS  # ty: ignore
from rasterio.enums import ColorInterp

logger = logging.getLogger(__name__)

# Maximum number of concurrent gdalwarp processes
MAX_WARP_WORKERS = 4


def _geo_overlaps_bbox(
    path: Path,
    bbox: tuple[float, float, float, float] | None,
) -> bool:
    """Check whether a GeoTIFF's bounds overlap the given bbox.

    Args:
        path: Path to the GeoTIFF file
        bbox: (west, south, east, north) in EPSG:4326, or None to accept all

    Returns:
        True if the file overlaps the bbox (or bbox is None)
    """
    if bbox is None:
        return True
    try:
        with rasterio.open(path) as src:
            if src.crs is None:
                return True
            from rasterio.warp import transform_bounds

            file_bounds = transform_bounds(src.crs, CRS.from_epsg(4326), *src.bounds)
            # file_bounds: (left, bottom, right, top)
            return not (
                file_bounds[2] < bbox[0]
                or file_bounds[0] > bbox[2]
                or file_bounds[3] < bbox[1]
                or file_bounds[1] > bbox[3]
            )
    except Exception:
        return True


def _run_gdal_translate_expand(
    source_path: Path,
    dest_path: Path,
) -> None:
    """Run gdal_translate to expand a paletted GeoTIFF to RGB.

    Args:
        source_path: Input paletted GeoTIFF path
        dest_path: Output 3-band RGB GeoTIFF path
    """
    cmd = [
        shutil.which("gdal_translate") or "gdal_translate",
        "-expand",
        "rgb",
        "-of",
        "GTiff",
        "-co",
        "COMPRESS=LZW",
        "-co",
        "TILED=YES",
        "-co",
        "BLOCKXSIZE=256",
        "-co",
        "BLOCKYSIZE=256",
        str(source_path),
        str(dest_path),
    ]

    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"gdal_translate failed (exit {result.returncode}): {result.stderr.strip()}"
        )


def _run_gdalwarp(
    source_path: Path,
    dest_path: Path,
    target_crs: str = "EPSG:4326",
) -> None:
    """Run gdalwarp CLI to warp a GeoTIFF to the target CRS.

    Uses multi-threaded warping and LZW-compressed tiled output.

    Args:
        source_path: Input GeoTIFF path (must be RGB if originally paletted)
        dest_path: Output GeoTIFF path
        target_crs: Target CRS string
    """
    cmd = [
        shutil.which("gdalwarp") or "gdalwarp",
        "-overwrite",
        "-r",
        "cubic",
        "-t_srs",
        target_crs,
        "-of",
        "GTiff",
        "-co",
        "COMPRESS=LZW",
        "-co",
        "TILED=YES",
        "-co",
        "BLOCKXSIZE=256",
        "-co",
        "BLOCKYSIZE=256",
        "-wo",
        "NUM_THREADS=2",
        "-wm",
        "512",
        "-multi",
        str(source_path),
        str(dest_path),
    ]

    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"gdalwarp failed (exit {result.returncode}): {result.stderr.strip()}"
        )


def _run_gdalbuildvrt(vrt_path: Path, source_paths: list[Path]) -> None:
    """Run gdalbuildvrt CLI to create a VRT from multiple GeoTIFFs.

    Args:
        vrt_path: Output VRT file path
        source_paths: Input GeoTIFF paths to mosaic
    """
    cmd = [
        shutil.which("gdalbuildvrt") or "gdalbuildvrt",
        str(vrt_path),
        *[str(p) for p in source_paths],
    ]

    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"gdalbuildvrt failed (exit {result.returncode}): {result.stderr.strip()}"
        )


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

    # If the source was cleaned up after a previous successful warp,
    # return the warped file directly.
    if not source_path.exists():
        cache_path = source_path.parent / f"{source_path.stem}_4326.tif"
        cache_meta_path = source_path.parent / f"{source_path.stem}_4326.json"
        if cache_path.exists() and cache_meta_path.exists():
            logger.debug("Source deleted, using warped cache: %s", cache_path)
            return cache_path
        logger.warning("Source file missing: %s", source_path)
        return source_path

    # Check if source is already in target CRS and not paletted
    with rasterio.open(source_path) as src:
        if src.crs is None:
            logger.warning("No CRS in %s, skipping pre-warp", source_path)
            return source_path

        already_ok = (
            src.crs == dst_crs
            and (len(src.colorinterp) == 0 or src.colorinterp[0] != ColorInterp.palette)
            and src.count >= 3
        )
        is_paletted = (
            src.count == 1
            and len(src.colorinterp) > 0
            and src.colorinterp[0] == ColorInterp.palette
        )

    if already_ok:
        return source_path

    cache_path = source_path.parent / f"{source_path.stem}_4326.tif"

    # Check cache freshness: _4326.tif must exist AND have a completion
    # marker ({stem}_4326.json).  Without the marker the warp was aborted.
    cache_meta_path = source_path.parent / f"{source_path.stem}_4326.json"
    if not force and cache_path.exists() and cache_meta_path.exists():
        if cache_path.stat().st_mtime >= source_path.stat().st_mtime:
            logger.debug("Using cached pre-warp: %s", cache_path)
            return cache_path

    logger.info("Pre-warping %s -> %s", source_path.name, cache_path.name)

    warp_input = source_path
    intermediate_path: Path | None = None
    if is_paletted:
        # Palette expansion must be done via gdal_translate (-expand is not
        # a valid gdalwarp option).  Create an intermediate RGB file first.
        intermediate_path = source_path.parent / f"{source_path.stem}_rgb.tif"
        _run_gdal_translate_expand(source_path, intermediate_path)
        warp_input = intermediate_path

    _run_gdalwarp(warp_input, cache_path, target_crs=target_crs)

    # Clean up intermediate file
    if intermediate_path and intermediate_path.exists():
        intermediate_path.unlink()

    # Write completion marker so we can detect aborted warps
    cache_meta_path.write_text(json.dumps({"warped": True}))
    logger.debug("Wrote warp completion marker: %s", cache_meta_path.name)

    logger.info("Pre-warp complete: %s", cache_path.name)
    return cache_path


def cleanup_after_warp(
    source_path: Path,
    warped_path: Path,
    metadata: dict | None = None,
) -> None:
    """Delete the original GeoTIFF after successful warp and write metadata JSON.

    Preserves existing metadata (etag, url, etc.) from the download sidecar
    and adds warp completion info.

    Args:
        source_path: Path to the original GeoTIFF (will be deleted)
        warped_path: Path to the pre-warped GeoTIFF (kept)
        metadata: Optional dict with cache metadata (etag, url, etc.)
    """
    if warped_path == source_path or not source_path.exists():
        return

    # Read existing download metadata (written by _write_metadata) so we
    # don't lose etag/url/last_modified when overwriting.
    meta_path = source_path.parent / f"{source_path.stem}.json"
    existing: dict = {}
    if meta_path.exists():
        try:
            existing = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    from datetime import datetime, timezone

    meta = {
        **existing,
        "item_id": source_path.stem,
        "original_size": source_path.stat().st_size,
        "warp_date": datetime.now(timezone.utc).isoformat(),
        **(metadata or {}),
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    logger.debug("Wrote metadata: %s", meta_path.name)

    # Delete original
    source_path.unlink()
    logger.debug("Deleted original: %s", source_path.name)


def _needs_warp(source_path: Path, target_crs: str = "EPSG:4326") -> bool:
    """Check whether a GeoTIFF needs pre-warping (no fresh cache exists)."""
    # Source was cleaned up after a previous warp — no warp needed.
    if not source_path.exists():
        return False

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
    cache_meta_path = source_path.parent / f"{source_path.stem}_4326.json"
    if (
        cache_path.exists()
        and cache_meta_path.exists()
        and cache_path.stat().st_mtime >= source_path.stat().st_mtime
    ):
        return False

    return True


def prewarp_all_geotiffs(
    geotiff_paths: list[Path],
    target_crs: str = "EPSG:4326",
    force: bool = False,
    progress_callback: Callable[[str, str], None] | None = None,
    cleanup: bool = False,
    item_metadata: dict[str, dict] | None = None,
    max_workers: int = MAX_WARP_WORKERS,
    bbox: tuple[float, float, float, float] | None = None,
    label: str | None = None,
) -> dict[Path, Path]:
    """Pre-warp all GeoTIFFs, returning mapping from original to pre-warped paths.

    Runs up to ``max_workers`` gdalwarp processes in parallel with a Rich
    progress bar.  Cached files (already in target CRS or fresh _4326.tif)
    are resolved sequentially before the parallel warp starts.

    Files whose spatial extent does not overlap ``bbox`` are skipped
    entirely (mapped to themselves, no warp).

    Args:
        geotiff_paths: List of original GeoTIFF file paths
        target_crs: Target CRS for pre-warping
        force: Force re-warp even if cache exists
        progress_callback: Called with (stage, description) for progress
        cleanup: If True, delete originals after successful warp and write
            metadata JSON sidecar files
        item_metadata: Optional dict mapping item_id (file stem) to metadata
            dict (etag, url, etc.) to include in the JSON sidecar. Only
            used when cleanup=True.
        max_workers: Maximum concurrent gdalwarp processes (default 4)
        bbox: Optional (west, south, east, north) in EPSG:4326 to filter
            files — only GeoTIFFs overlapping this bbox are warped.

    Returns:
        Dict mapping original_path -> prewarped_path
        (identity mapping for files that didn't need warping)
    """
    mapping: dict[Path, Path] = {}

    # Resolve cached/already-correct files first (no warp needed).
    # Also skip files outside the bbox.
    to_warp: list[Path] = []
    for path in geotiff_paths:
        if bbox is not None and not _geo_overlaps_bbox(path, bbox):
            logger.debug("Skipping %s — outside bbox", path.name)
            mapping[path] = path
            continue
        if not force and not _needs_warp(path, target_crs):
            warped = prewarp_geotiff(path, target_crs=target_crs, force=force)
            mapping[path] = warped
            if cleanup and warped != path and path.exists():
                meta = (item_metadata or {}).get(path.stem)
                cleanup_after_warp(path, warped, metadata=meta)
        else:
            to_warp.append(path)

    if not to_warp:
        return mapping

    logger.info(
        "Pre-warping %d GeoTIFF(s) to %s (%d workers)",
        len(to_warp),
        target_crs,
        max_workers,
    )

    with Progress(
        TextColumn(
            f"[bold blue]Pre-warping {label}" if label else "[bold blue]Pre-warping"
        ),
        BarColumn(bar_width=None),
        TextColumn("{task.completed}/{task.total}"),
        "•",
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task_id = progress.add_task("warp", total=len(to_warp))

        def _warp_one(path: Path) -> tuple[Path, Path]:
            warped = prewarp_geotiff(path, target_crs=target_crs, force=force)
            if cleanup and warped != path:
                meta = (item_metadata or {}).get(path.stem)
                cleanup_after_warp(path, warped, metadata=meta)
            return (path, warped)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {
                executor.submit(_warp_one, path): path for path in to_warp
            }
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    orig, warped = future.result()
                    mapping[orig] = warped
                except Exception as e:
                    logger.error("Pre-warp failed for %s: %s", path.name, e)
                    mapping[path] = path
                progress.advance(task_id)

    return mapping


def merge_prewarped_geotiffs(
    prewarped_paths: list[Path],
    cache_dir: Path,
    mosaic_name: str = "mosaic.vrt",
    force: bool = False,
    progress_callback: Callable[[str, str], None] | None = None,
) -> Path:
    """Create a VRT mosaicking all pre-warped GeoTIFFs.

    This is essential for low-zoom tiles that span multiple source GeoTIFFs.
    The VRT is a tiny XML file that virtually references the underlying
    GeoTIFFs — no pixel data is copied and memory usage is minimal.

    The VRT is cached in cache_dir. It is re-created only when any source
    file has a newer mtime than the existing VRT (or force=True).

    Args:
        prewarped_paths: List of pre-warped GeoTIFF paths (EPSG:4326, 3-band RGB)
        cache_dir: Directory to store the VRT file
        mosaic_name: Filename for the VRT (default "mosaic.vrt")
        force: Force re-merge even if cached VRT exists
        progress_callback: Called with (stage, description) for progress

    Returns:
        Path to the VRT file
    """
    if not prewarped_paths:
        raise ValueError("No pre-warped GeoTIFFs to merge")

    vrt_path = cache_dir / mosaic_name

    # Check if we can skip VRT creation (all source files older than VRT)
    if not force and vrt_path.exists():
        vrt_mtime = vrt_path.stat().st_mtime
        if all(p.stat().st_mtime <= vrt_mtime for p in prewarped_paths):
            logger.debug("Using cached VRT: %s", vrt_path)
            return vrt_path

    if progress_callback:
        progress_callback("merge", "Building VRT mosaic...")

    _run_gdalbuildvrt(vrt_path, prewarped_paths)

    logger.info("VRT mosaic complete: %s", vrt_path.name)
    return vrt_path
