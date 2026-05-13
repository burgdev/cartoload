"""Preview image generation: tile mosaic assembler.

Generates preview mosaics from tile data produced by any source type
(WMTS, GeoTIFF/STAC, composite). Uses a tile_processor callable —
the same one used during export — to produce JPEG bytes, making the
preview source-agnostic.
"""

from __future__ import annotations

import io
import logging
import math
from pathlib import Path
from typing import Callable

from PIL import Image

from ..config import LayerConfig
from ..downloader.wmts import WMTSDownloader
from ..pipeline import _compute_tile_coords

logger = logging.getLogger(__name__)

TILE_SIZE = 256  # Standard tile size in pixels

# Type alias for the tile processor callable
TileProcessor = Callable[
    [Path | None, int, int, int, str, int | None],
    tuple[bytes, tuple[float, float, float, float]] | None,
]


def compute_preview_center(bounds: dict[str, float]) -> tuple[float, float]:
    """Compute the center point of geographic bounds.

    Args:
        bounds: Dict with west, east, south, north keys

    Returns:
        (longitude, latitude) of the center
    """
    lng = (bounds["west"] + bounds["east"]) / 2.0
    lat = (bounds["south"] + bounds["north"]) / 2.0
    return (lng, lat)


def _lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Convert lat/lon to tile coordinates at the given zoom level."""
    n = 2**zoom
    x = max(0, min(int((lon + 180.0) / 360.0 * n), n - 1))
    lat_rad = math.radians(lat)
    y = max(
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
    return x, y


def compute_preview_grid(
    layer: LayerConfig,
    zoom: int,
    max_tiles: int = 9,
    cached_coords: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    """Compute an adaptive grid of tile coords around the center for preview.

    Selects up to max_tiles tiles centered on the bounds midpoint,
    preferring cached tiles when available.

    Args:
        layer: Layer config with bounds
        zoom: Zoom level to preview
        max_tiles: Maximum number of tiles to include (default 9 = 3x3)
        cached_coords: Set of (x, y) coords that are already cached.
            If provided, selects tiles from this set preferentially.

    Returns:
        List of (x, y) tile coordinates for the preview
    """
    all_coords = _compute_tile_coords(layer, zoom)
    if not all_coords:
        return []

    all_set = set(all_coords)

    if len(all_coords) <= max_tiles:
        # Return only cached if we know what's cached, else return all
        if cached_coords is not None:
            return [c for c in all_coords if c in cached_coords]
        return all_coords

    # If we have cached coords info, pick a 3x3 grid from cached tiles
    if cached_coords:
        available = all_set & cached_coords
        if available:
            return _select_grid_from_available(available, layer, zoom, max_tiles)

    # Fallback: pick grid around geographic center from all coords
    return _select_grid_from_available(all_set, layer, zoom, max_tiles)


def _select_grid_from_available(
    available: set[tuple[int, int]],
    layer: LayerConfig,
    zoom: int,
    max_tiles: int,
) -> list[tuple[int, int]]:
    """Select up to max_tiles coords from available, centered on bounds."""
    if len(available) <= max_tiles:
        return sorted(available)

    bounds = layer.bounds
    if not bounds:
        return sorted(available)[:max_tiles]

    center_lng, center_lat = compute_preview_center(bounds)
    cx, cy = _lat_lon_to_tile(center_lat, center_lng, zoom)

    # Determine grid dimensions: try square grid that fits max_tiles
    grid_side = int(math.sqrt(max_tiles))
    if grid_side * grid_side < max_tiles:
        grid_side += 1

    half = grid_side // 2
    selected = []

    for dx in range(-half, half + 1):
        for dy in range(-half, half + 1):
            x, y = cx + dx, cy + dy
            if (x, y) in available and len(selected) < max_tiles:
                selected.append((x, y))

    if not selected:
        # Center tile not in available — pick closest available tiles
        return sorted(available, key=lambda c: abs(c[0] - cx) + abs(c[1] - cy))[
            :max_tiles
        ]

    return selected


def assemble_preview(
    downloader: WMTSDownloader,
    coords: list[tuple[int, int]],
    zoom: int,
    quality: int = 85,
) -> bytes | None:
    """Assemble a mosaic of cached tiles into a single JPEG image.

    Args:
        downloader: WMTS downloader for cache path resolution
        coords: List of (x, y) tile coordinates to include
        zoom: Zoom level
        quality: JPEG quality for the output mosaic (default 85)

    Returns:
        JPEG bytes of the mosaic, or None if no tiles available
    """
    if not coords:
        return None

    # Load all available tiles
    images: list[tuple[int, int, Image.Image]] = []
    for x, y in coords:
        path = downloader._cache_path(x, y, zoom)
        if path.exists():
            try:
                img = Image.open(path)
                img.load()  # Force load to avoid lazy loading issues
                images.append((x, y, img))
            except Exception:
                logger.debug("Failed to load tile %s for preview", path)
                continue

    if not images:
        return None

    return _assemble_mosaic(images, quality=quality)


def _assemble_mosaic(
    images: list[tuple[int, int, Image.Image]],
    quality: int = 85,
) -> bytes | None:
    """Assemble a list of (x, y, Image) tiles into a mosaic JPEG."""
    if not images:
        return None

    xs = [x for x, y, _ in images]
    ys = [y for x, y, _ in images]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    grid_w = max_x - min_x + 1
    grid_h = max_y - min_y + 1

    mosaic = Image.new("RGB", (grid_w * TILE_SIZE, grid_h * TILE_SIZE), (200, 200, 200))

    for x, y, img in images:
        col = x - min_x
        row = y - min_y
        mosaic.paste(img, (col * TILE_SIZE, row * TILE_SIZE))

    buf = io.BytesIO()
    mosaic.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def generate_previews(
    layer: LayerConfig,
    downloader: WMTSDownloader,
    output_dir: Path,
    max_tiles_per_zoom: int = 9,
    quality: int = 85,
) -> list[Path]:
    """Generate preview images for each zoom level with available tiles.

    Args:
        layer: Layer config
        downloader: WMTS downloader for cache access
        output_dir: Base output directory (previews go to output_dir/previews/)
        max_tiles_per_zoom: Max tiles per preview mosaic
        quality: JPEG quality for preview images (default 85)

    Returns:
        List of paths to generated preview files
    """
    preview_dir = output_dir / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []

    for zoom in layer.zoom_levels:
        # Scan for cached tiles at this zoom to guide selection
        all_coords = _compute_tile_coords(layer, zoom)
        cached_at_zoom: set[tuple[int, int]] = set()
        for x, y in all_coords:
            if downloader._cache_path(x, y, zoom).exists():
                cached_at_zoom.add((x, y))

        coords = compute_preview_grid(
            layer, zoom, max_tiles_per_zoom, cached_coords=cached_at_zoom
        )
        if not coords:
            logger.debug("No preview tiles for zoom %d, skipping", zoom)
            continue

        jpeg_bytes = assemble_preview(downloader, coords, zoom, quality=quality)
        if jpeg_bytes is None:
            logger.debug("No cached tiles for zoom %d preview, skipping", zoom)
            continue

        preview_path = preview_dir / f"{layer.id}_zoom{zoom}.jpg"
        preview_path.write_bytes(jpeg_bytes)
        generated.append(preview_path)
        logger.info("Preview generated: %s (%d tiles)", preview_path, len(coords))

    return generated


def generate_previews_from_processor(
    layer: LayerConfig,
    tile_metadata_by_zoom: dict[int, list],
    tile_processor: TileProcessor,
    source_crs: str,
    output_dir: Path,
    max_tiles_per_zoom: int = 9,
    quality: int = 85,
) -> list[Path]:
    """Generate preview images using the same tile processor used during export.

    This is source-agnostic: it works for WMTS, GeoTIFF/STAC, and composite
    layers by calling the tile_processor callable to produce JPEG bytes.

    Selects a 3x3 grid of tiles around the geographic center for each zoom
    level from the available tile_metadata, processes them through the
    tile_processor, and assembles a mosaic.

    Args:
        layer: Layer config with bounds and zoom levels
        tile_metadata_by_zoom: Dict mapping zoom level to list of TileMetadata
        tile_processor: Callable that produces (jpeg_bytes, bounds) from a tile
        source_crs: Source CRS string (passed to tile_processor)
        output_dir: Base output directory (previews go to output_dir/previews/)
        max_tiles_per_zoom: Max tiles per preview mosaic
        quality: JPEG quality for preview images (default 85)

    Returns:
        List of paths to generated preview files
    """
    preview_dir = output_dir / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []

    for zoom in layer.zoom_levels:
        tiles_at_zoom = tile_metadata_by_zoom.get(zoom, [])
        if not tiles_at_zoom:
            continue

        # Select tiles for preview: pick from available metadata
        available_coords = {(t.x, t.y) for t in tiles_at_zoom}
        if not available_coords:
            continue

        selected = _select_grid_from_available(
            available_coords, layer, zoom, max_tiles_per_zoom
        )
        if not selected:
            continue

        # Build lookup from (x, y) → TileMetadata
        meta_by_coord = {(t.x, t.y): t for t in tiles_at_zoom}

        # Process tiles through the tile processor
        images: list[tuple[int, int, Image.Image]] = []
        for x, y in selected:
            meta = meta_by_coord.get((x, y))
            if meta is None:
                continue

            result = tile_processor(meta.source_path, x, y, zoom, source_crs, quality)
            if result is None:
                logger.debug("Preview tile (%d, %d, z=%d) returned None", x, y, zoom)
                continue

            jpeg_bytes, _bounds = result
            try:
                img = Image.open(io.BytesIO(jpeg_bytes))
                img.load()
                images.append((x, y, img))
            except Exception:
                logger.debug("Failed to decode preview tile (%d, %d, z=%d)", x, y, zoom)
                continue

        if not images:
            logger.debug("No preview images for zoom %d, skipping", zoom)
            continue

        jpeg_bytes = _assemble_mosaic(images, quality=quality)
        if jpeg_bytes is None:
            continue

        preview_path = preview_dir / f"{layer.id}_zoom{zoom}.jpg"
        preview_path.write_bytes(jpeg_bytes)
        generated.append(preview_path)
        logger.info("Preview generated: %s (%d tiles)", preview_path, len(images))

    return generated
