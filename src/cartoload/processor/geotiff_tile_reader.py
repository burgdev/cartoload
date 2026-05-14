"""GeoTIFF tile reader — extracts tile-sized windows from GeoTIFF files on-the-fly.

For a given (x, y, zoom) tile coordinate, opens the GeoTIFF, computes the
pixel window covering that tile's geographic extent, warps to EPSG:4326,
and returns JPEG bytes compatible with the existing export pipeline.

Performance notes:
- Uses a per-thread LRU cache for rasterio dataset handles to avoid repeated
  open/close overhead while remaining safe for multi-threaded use.
  GDAL/rasterio DatasetReader handles are NOT thread-safe: concurrent reads
  on the same handle cause segfaults. Each thread maintains its own set of
  open handles.
- Palette expansion uses a vectorized LUT instead of per-entry masking.
- The destination transform is computed directly via from_bounds()
  instead of the expensive calculate_default_transform().
"""

from __future__ import annotations

import io
import logging
import math
import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np
import rasterio
import warnings
from PIL import Image
from rasterio.crs import CRS
from rasterio.enums import ColorInterp
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import rowcol
from rasterio.warp import reproject, Resampling

logger = logging.getLogger(__name__)

# Type alias: (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max))
ProcessedTile = tuple[bytes, tuple[float, float, float, float]]

# Standard web tile size
TILE_SIZE = 256

# Pixel buffer added around computed windows to avoid gaps from rounding
_WINDOW_BUFFER = 2

# Maximum number of GeoTIFF files to keep open per thread
_MAX_OPEN_DATASETS = 8


class _ThreadLocalDatasetCache:
    """Per-thread LRU cache for open rasterio datasets.

    GDAL/rasterio DatasetReader handles are NOT safe for concurrent use
    from multiple threads — concurrent reads on the same handle cause
    segfaults. This cache stores handles in thread-local storage so each
    thread gets its own independent set of open file handles.

    Colormaps are shared across threads since they are read-only dicts.
    """

    def __init__(self, maxsize: int = _MAX_OPEN_DATASETS) -> None:
        self._maxsize = maxsize
        self._local = threading.local()
        self._colormaps: dict[Path, dict[int, tuple[int, int, int, int]] | None] = {}
        self._colormap_lock = threading.Lock()

    def _get_cache(self) -> OrderedDict[Path, rasterio.DatasetReader]:
        """Get the thread-local cache OrderedDict."""
        if not hasattr(self._local, "cache"):
            self._local.cache: OrderedDict[Path, rasterio.DatasetReader] = OrderedDict()
        return self._local.cache

    def get(self, path: Path) -> rasterio.DatasetReader:
        """Get an open dataset for the given path (opens if not cached).

        Each thread maintains its own independent set of open handles.
        """
        cache = self._get_cache()
        if path in cache:
            cache.move_to_end(path)
            return cache[path]

        # Evict LRU entries if at capacity
        while len(cache) >= self._maxsize:
            oldest_path, oldest_ds = cache.popitem(last=False)
            try:
                oldest_ds.close()
            except Exception:
                pass

        ds = rasterio.open(path)
        cache[path] = ds
        return ds

    def get_colormap(
        self, path: Path, src: rasterio.DatasetReader
    ) -> dict[int, tuple[int, int, int, int]] | None:
        """Get the cached colormap for a file, reading it on first access.

        Colormaps are shared across threads (they are immutable once read).
        """
        with self._colormap_lock:
            if path in self._colormaps:
                return self._colormaps[path]
            try:
                cm = src.colormap(1)
                self._colormaps[path] = cm if cm else None
            except ValueError:
                self._colormaps[path] = None
            return self._colormaps[path]

    def close_all(self) -> None:
        """Close all cached datasets across all threads.

        Note: This can only close datasets in the calling thread's cache.
        Other threads' handles will be closed when they exit or when
        garbage collected. For clean shutdown, call this from each worker
        thread or after all threads have joined.
        """
        if hasattr(self._local, "cache"):
            for ds in self._local.cache.values():
                try:
                    ds.close()
                except Exception:
                    pass
            self._local.cache.clear()
        with self._colormap_lock:
            self._colormaps.clear()


# Module-level per-thread dataset cache
_dataset_cache = _ThreadLocalDatasetCache()


def close_dataset_cache() -> None:
    """Close all cached dataset handles. Call when processing is complete."""
    _dataset_cache.close_all()


def compute_bounds_4326(x: int, y: int, zoom: int) -> tuple[float, float, float, float]:
    """Compute WGS84 bounds from tile coordinates.

    Returns (lat_min, lon_min, lat_max, lon_max).
    """
    n = 2**zoom
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0

    lat_max_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_min_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))

    return (math.degrees(lat_min_rad), lon_min, math.degrees(lat_max_rad), lon_max)


def read_tile_from_geotiff(
    geotiff_path: Path,
    x: int,
    y: int,
    zoom: int,
    quality: int = 85,
) -> ProcessedTile | None:
    """Read a tile-sized window from a GeoTIFF and return JPEG bytes.

    Uses a shared dataset cache to avoid repeated file open/close
    overhead when reading many tiles from the same GeoTIFF.

    Args:
        geotiff_path: Path to the GeoTIFF file
        x, y, zoom: Web Mercator tile coordinates
        quality: JPEG output quality (1-100)

    Returns:
        (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max)) or None
    """
    if not geotiff_path.exists():
        return None

    bounds = compute_bounds_4326(x, y, zoom)
    lat_min, lon_min, lat_max, lon_max = bounds

    try:
        src = _dataset_cache.get(geotiff_path)
        src_crs = src.crs
        if src_crs is None:
            logger.warning("No CRS in %s", geotiff_path)
            return None

        # Transform tile bounds from WGS84 to source CRS
        dst_crs = CRS.from_epsg(4326)
        src_left, src_bottom, src_right, src_top = _transform_bounds_to_src(
            lon_min, lat_min, lon_max, lat_max, dst_crs, src_crs
        )

        # Compute pixel window in source CRS (with buffer)
        col_off, row_off, width, height = _compute_window(
            src, src_left, src_bottom, src_right, src_top
        )

        if width <= 0 or height <= 0:
            return None

        # Read the window
        window = rasterio.windows.Window(col_off, row_off, width, height)
        src_data = src.read(window=window)

        if src_data.size == 0:
            return None

        # Build source transform for the actual window
        src_transform = rasterio.windows.transform(window, src.transform)

        # Detect and expand palette/colormapped images to RGB
        n_bands = src_data.shape[0]
        if (
            n_bands == 1
            and len(src.colorinterp) > 0
            and src.colorinterp[0] == ColorInterp.palette
        ):
            colormap = _dataset_cache.get_colormap(geotiff_path, src)
            if colormap:
                src_data = _expand_palette(src_data, colormap)

        # Normalize to 3 bands (RGB)
        n_bands = src_data.shape[0]
        if n_bands == 1:
            src_data = np.repeat(src_data, 3, axis=0)
        elif n_bands == 2:
            src_data = src_data[:1].repeat(3, axis=0)
        elif n_bands >= 4:
            src_data = src_data[:3]

        # Warp to EPSG:4326 at exactly TILE_SIZE x TILE_SIZE.
        # Compute destination transform directly from tile bounds — no
        # need for the expensive calculate_default_transform().
        dst_transform = rasterio.transform.from_bounds(
            lon_min, lat_min, lon_max, lat_max, TILE_SIZE, TILE_SIZE
        )

        nodata = src.nodata

        dst_data = np.zeros((3, TILE_SIZE, TILE_SIZE), dtype="uint8")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=NotGeoreferencedWarning)
            reproject(
                source=src_data,
                destination=dst_data,
                src_transform=src_transform,
                src_crs=src_crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=Resampling.cubic,
                src_nodata=nodata,
                dst_nodata=0,
                init_dest_nodata=True,
            )

        # Free source data promptly — no longer needed after warp
        del src_data

        # Encode to JPEG
        dst_rgb = np.moveaxis(dst_data, 0, -1)  # (C, H, W) → (H, W, C)
        img = Image.fromarray(dst_rgb, mode="RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        jpeg_bytes = buf.getvalue()

        return (jpeg_bytes, bounds)

    except Exception as e:
        logger.warning(
            "Failed to read tile (%d, %d, z=%d) from %s: %s",
            x,
            y,
            zoom,
            geotiff_path,
            e,
        )
        return None


def read_tile_from_warped_geotiff(
    geotiff_path: Path,
    x: int,
    y: int,
    zoom: int,
    quality: int = 85,
) -> ProcessedTile | None:
    """Read a tile from a pre-warped (EPSG:4326, RGB) GeoTIFF.

    Uses reproject to correctly map the mosaic data into the tile's
    geographic extent. This handles the case where the mosaic extent
    is smaller than the tile — data is placed at the correct position
    in the 256x256 output instead of being stretched to fill it.

    Args:
        geotiff_path: Path to pre-warped GeoTIFF (must be EPSG:4326, 3-band RGB)
        x, y, zoom: Web Mercator tile coordinates
        quality: JPEG output quality (1-100)

    Returns:
        (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max)) or None
    """
    if not geotiff_path.exists():
        return None

    bounds = compute_bounds_4326(x, y, zoom)
    lat_min, lon_min, lat_max, lon_max = bounds

    try:
        src = _dataset_cache.get(geotiff_path)

        # Compute the intersection of tile bounds and mosaic extent.
        # If no overlap, skip this tile.
        src_left = max(lon_min, src.bounds.left)
        src_right = min(lon_max, src.bounds.right)
        src_bottom = max(lat_min, src.bounds.bottom)
        src_top = min(lat_max, src.bounds.top)

        if src_left >= src_right or src_bottom >= src_top:
            return None

        # Compute source pixel window for the intersection (with buffer).
        col_off, row_off, width, height = _compute_window(
            src, src_left, src_bottom, src_right, src_top
        )

        if width <= 0 or height <= 0:
            return None

        # Read the source window at native resolution.
        window = rasterio.windows.Window(col_off, row_off, width, height)
        src_data = src.read(window=window)

        if src_data.size == 0:
            return None

        # Build source transform for the read window.
        src_transform = rasterio.windows.transform(window, src.transform)

        # Destination: the tile's full geographic extent mapped to TILE_SIZE x TILE_SIZE.
        dst_transform = rasterio.transform.from_bounds(
            lon_min, lat_min, lon_max, lat_max, TILE_SIZE, TILE_SIZE
        )

        dst_data = np.zeros((3, TILE_SIZE, TILE_SIZE), dtype="uint8")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=NotGeoreferencedWarning)
            reproject(
                source=src_data,
                destination=dst_data,
                src_transform=src_transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=src.crs,  # Same CRS, but reproject handles the spatial mapping
                resampling=Resampling.cubic,
                init_dest_nodata=True,
            )

        del src_data

        # Skip tiles that are entirely nodata (all zeros).
        if not np.any(dst_data):
            return None

        # Encode to JPEG
        dst_rgb = np.moveaxis(dst_data, 0, -1)  # (C, H, W) -> (H, W, C)
        img = Image.fromarray(dst_rgb, mode="RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        jpeg_bytes = buf.getvalue()

        return (jpeg_bytes, bounds)

    except Exception as e:
        logger.warning(
            "Failed to read tile (%d, %d, z=%d) from pre-warped %s: %s",
            x,
            y,
            zoom,
            geotiff_path,
            e,
        )
        return None


def _expand_palette(
    src_data: np.ndarray,
    colormap: dict[int, tuple[int, int, int, int]],
) -> np.ndarray:
    """Expand a 1-band palette image to 3-band RGB using vectorized LUT.

    Uses a flat 256-entry lookup table and numpy fancy indexing instead
    of iterating over colormap entries with boolean masks.

    Args:
        src_data: Array of shape (1, H, W) with uint8 palette index values
        colormap: Dict mapping index -> (R, G, B, A) tuples

    Returns:
        Array of shape (3, H, W) with uint8 RGB values
    """
    # Build a flat 256-entry RGB lookup table
    lut = np.zeros((256, 3), dtype=np.uint8)
    for idx, rgba in colormap.items():
        if 0 <= idx < 256:
            lut[idx] = [rgba[0], rgba[1], rgba[2]]

    indices = src_data[0]  # (H, W), dtype uint8
    rgb = lut[indices]  # (H, W, 3) — single vectorized lookup
    return rgb.transpose(2, 0, 1)  # (3, H, W)


def _transform_bounds_to_src(
    west: float,
    south: float,
    east: float,
    north: float,
    from_crs: CRS,
    to_crs: CRS,
) -> tuple[float, float, float, float]:
    """Transform bounds from one CRS to another.

    Returns (left, bottom, right, top) in the target CRS.
    """
    from rasterio.warp import transform_bounds as _transform_bounds

    return _transform_bounds(from_crs, to_crs, west, south, east, north)


def _compute_window(
    src: rasterio.DatasetReader,
    left: float,
    bottom: float,
    right: float,
    top: float,
) -> tuple[int, int, int, int]:
    """Compute pixel window (col_off, row_off, width, height) for geographic bounds.

    Adds a small pixel buffer to avoid gaps from rounding at tile boundaries.

    Args:
        src: Open rasterio dataset
        left, bottom, right, top: Bounds in the source CRS

    Returns:
        (col_off, row_off, width, height) — all integers, clamped to dataset
    """
    # Convert geographic corners to pixel coordinates
    row_min, col_min = rowcol(src.transform, left, top, op=math.floor)
    row_max, col_max = rowcol(src.transform, right, bottom, op=math.ceil)

    # Add buffer to avoid gaps from rounding
    col_min -= _WINDOW_BUFFER
    row_min -= _WINDOW_BUFFER
    col_max += _WINDOW_BUFFER
    row_max += _WINDOW_BUFFER

    # Clamp to dataset bounds
    col_off = max(0, col_min)
    row_off = max(0, row_min)
    col_end = min(src.width, col_max)
    row_end = min(src.height, row_max)

    width = col_end - col_off
    height = row_end - row_off

    return (col_off, row_off, width, height)
