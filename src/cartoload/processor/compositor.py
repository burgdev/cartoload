"""Tile compositing: alpha-blend multiple raster sub-layers into one tile.

Implements the painter's algorithm — sub-layers are composited bottom-to-top
with per-layer opacity control. PNG tiles preserve transparency; JPEG tiles
are treated as fully opaque. Output is always RGB JPEG bytes.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image

from ..config import CompositeSubLayer

logger = logging.getLogger(__name__)


def composite_tiles(
    images: list[tuple[Image.Image, float]],
) -> Image.Image:
    """Composite multiple PIL Images using painter's algorithm.

    Args:
        images: List of (PIL Image, opacity) tuples, ordered bottom-to-top.
            Each image is RGBA. Opacity is applied by multiplying the alpha
            channel.

    Returns:
        A composited RGBA PIL Image. If no images are provided, returns None.
    """
    if not images:
        raise ValueError("No images to composite")

    # Use the first image as the canvas
    canvas = images[0][0].convert("RGBA").copy()

    # Apply opacity to first layer too
    first_opacity = images[0][1]
    if first_opacity < 1.0:
        alpha = canvas.split()[3]
        alpha = alpha.point(lambda p: int(p * first_opacity))
        canvas.putalpha(alpha)

    # Composite remaining layers on top
    for img, opacity in images[1:]:
        layer = img.convert("RGBA").copy()

        # Apply per-layer opacity by multiplying alpha channel
        if opacity < 1.0:
            alpha = layer.split()[3]
            alpha = alpha.point(lambda p: int(p * opacity))
            layer.putalpha(alpha)

        # Alpha composite onto canvas
        canvas = Image.alpha_composite(canvas, layer)

    return canvas


def resolve_opacity(sub_layer: CompositeSubLayer, zoom: int) -> float:
    """Return the opacity value for a sub-layer at a given zoom level.

    Args:
        sub_layer: The sub-layer configuration.
        zoom: The zoom level.

    Returns:
        Float opacity value between 0.0 and 1.0.
    """
    opacity = sub_layer.opacity
    if isinstance(opacity, dict):
        return opacity.get(zoom, 1.0)
    return float(opacity)


def encode_composite_to_jpeg(image: Image.Image, quality: int = 85) -> bytes:
    """Convert an RGBA composited image to JPEG bytes.

    Discards the alpha channel (converts to RGB) before JPEG encoding.
    Always encodes at quality 95 (high quality intermediate step).
    The target quality is applied during the final IMG write step.

    Args:
        image: RGBA PIL Image to encode.
        quality: Ignored (always encodes at 95). Kept for API compatibility.

    Returns:
        JPEG bytes.
    """
    rgb = image.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=95, optimize=True)
    return buf.getvalue()


def load_tile_as_rgba(path: Path) -> Image.Image | None:
    """Load a tile file as a PIL RGBA Image.

    JPEG files (no alpha) are converted to RGBA with full opacity.
    PNG files preserve their alpha channel.

    Args:
        path: Path to the tile file (JPEG or PNG).

    Returns:
        PIL Image in RGBA mode, or None if the file doesn't exist.
    """
    if not path.exists():
        return None

    try:
        img = Image.open(path)
        if img.mode == "RGBA":
            return img
        elif img.mode == "RGB":
            return img.convert("RGBA")
        elif img.mode == "P":
            # Palette mode — convert through RGBA to preserve transparency
            return img.convert("RGBA")
        else:
            return img.convert("RGBA")
    except Exception as e:
        logger.warning("Failed to load tile %s: %s", path, e)
        return None


def find_fallback_tile(
    sub_layer: CompositeSubLayer,
    x: int,
    y: int,
    zoom: int,
    cache_dir: Path,
    source_id: str,
    cache_key: str = "",
) -> Image.Image | None:
    """Find a fallback tile from a lower zoom level and upscale it.

    When a tile is unavailable at (x, y, zoom), this function searches
    the sub-layer's declared zoom_levels for the closest lower zoom that
    has a cached tile covering the same geographic area. The found tile
    is cropped to cover only the requested area and upscaled.

    Args:
        sub_layer: The sub-layer configuration (zoom_levels used for search).
        x: Requested tile X coordinate.
        y: Requested tile Y coordinate.
        zoom: Requested zoom level.
        cache_dir: Cache directory root.
        source_id: Source ID for cache path resolution.
        cache_key: URL-based cache key for path resolution.

    Returns:
        Upscaled RGBA PIL Image, or None if no fallback tile found.
    """
    # Get declared zoom levels sorted descending, only those below the requested zoom
    candidate_zooms = sorted(
        [z for z in sub_layer.zoom_levels if z < zoom], reverse=True
    )

    if not candidate_zooms:
        return None

    for fallback_zoom in candidate_zooms:
        # Compute which tile at the fallback zoom covers this position
        scale = 2 ** (zoom - fallback_zoom)
        fb_x = x // scale
        fb_y = y // scale

        # Build the cache path for the fallback tile
        fb_path = _cache_path(
            cache_dir,
            source_id,
            fb_x,
            fb_y,
            fallback_zoom,
            sub_layer.extension,
            cache_key=cache_key,
        )

        fb_img = load_tile_as_rgba(fb_path)
        if fb_img is None:
            continue

        # Crop the fallback tile to the region covering the requested tile
        # At fallback_zoom, each pixel covers 'scale' pixels at the target zoom.
        # The requested tile (x, y) maps to pixel region within the fallback tile.
        px_left = (x % scale) * (fb_img.width // scale)
        py_top = (y % scale) * (fb_img.height // scale)
        px_right = px_left + (fb_img.width // scale)
        py_bottom = py_top + (fb_img.height // scale)

        # Clamp to image bounds
        px_right = min(px_right, fb_img.width)
        py_bottom = min(py_bottom, fb_img.height)

        if px_right <= px_left or py_bottom <= py_top:
            continue

        cropped = fb_img.crop((px_left, py_top, px_right, py_bottom))

        # Upscale to standard tile size (256x256)
        target_size = 256
        upscaled = cropped.resize((target_size, target_size), Image.BILINEAR)

        logger.debug(
            "Fallback tile for (%d, %d, z=%d): using z=%d tile (%d, %d)",
            x,
            y,
            zoom,
            fallback_zoom,
            fb_x,
            fb_y,
        )
        return upscaled

    return None


def _cache_path(
    cache_dir: Path,
    source_id: str,
    x: int,
    y: int,
    zoom: int,
    extension: str,
    cache_key: str = "",
) -> Path:
    """Resolve a tile cache path.

    Matches the WMTSDownloader cache structure:
    - With cache_key: cache_dir / source_id / cache_key / zoom / x / y.<ext>
    - Without cache_key: cache_dir / source_id / zoom / x / y.<ext>
    """
    base = cache_dir / source_id
    if cache_key:
        base = base / cache_key
    return base / str(zoom) / str(x) / f"{y}.{extension}"
