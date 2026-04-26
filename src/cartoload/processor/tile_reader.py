"""Direct tile reader: read tiles from cache without gdal_translate subprocess."""

from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class WorldFileParams:
    """Parsed world file parameters."""

    pixel_size_x: float
    rotation_y: float
    rotation_x: float
    pixel_size_y: float
    top_left_x: float
    top_left_y: float


def parse_world_file(path: Path) -> WorldFileParams:
    """Parse an ESRI world file (.jgw, .pgw, .tfw, etc.).

    World files contain 6 lines:
      1. pixel size in X direction (map units/pixel)
      2. rotation about Y axis
      3. rotation about X axis
      4. pixel size in Y direction (map units/pixel, usually negative)
      5. X coordinate of upper-left pixel center
      6. Y coordinate of upper-left pixel center

    Args:
        path: Path to the world file

    Returns:
        WorldFileParams with the 6 parameters

    Raises:
        ValueError: If the world file cannot be parsed
        FileNotFoundError: If the file does not exist
    """
    if not path.exists():
        raise FileNotFoundError(f"World file not found: {path}")

    text = path.read_text().strip()
    lines = text.split("\n")
    if len(lines) < 6:
        raise ValueError(
            f"World file must have at least 6 lines, got {len(lines)}: {path}"
        )

    try:
        return WorldFileParams(
            pixel_size_x=float(lines[0]),
            rotation_y=float(lines[1]),
            rotation_x=float(lines[2]),
            pixel_size_y=float(lines[3]),
            top_left_x=float(lines[4]),
            top_left_y=float(lines[5]),
        )
    except (ValueError, IndexError) as e:
        raise ValueError(f"Cannot parse world file {path}: {e}") from e


def compute_bounds_from_world_file(
    wf: WorldFileParams, width: int, height: int
) -> tuple[float, float, float, float]:
    """Compute geographic bounds from world file parameters and image dimensions.

    Args:
        wf: Parsed world file parameters
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        (lat_min, lon_min, lat_max, lon_max) in EPSG:4326 degrees
    """
    lon_min = wf.top_left_x
    lat_max = wf.top_left_y
    lon_max = lon_min + wf.pixel_size_x * width
    lat_min = lat_max - abs(wf.pixel_size_y) * height
    return (lat_min, lon_min, lat_max, lon_max)


def compute_bounds_from_tile_coords(
    x: int, y: int, zoom: int
) -> tuple[float, float, float, float]:
    """Compute WGS84 bounds from tile coordinates (for fallback when no world file).

    Uses the standard Web Mercator tile grid math.

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

    lat_max = math.degrees(lat_max_rad)
    lat_min = math.degrees(lat_min_rad)

    return (lat_min, lon_min, lat_max, lon_max)


class TileCacheReader:
    """Read tiles directly from the download/reprojection cache.

    Returns (jpeg_bytes, bounds) tuples for consumption by the IMG writer,
    without spawning gdal_translate subprocesses.
    """

    def __init__(
        self,
        source_crs: str | None = None,
        target_quality: int | None = None,
        default_tile_size: int = 256,
    ) -> None:
        self._source_crs = source_crs
        self._target_quality = target_quality
        self._default_tile_size = default_tile_size

    def read_tile(
        self,
        tile_path: Path,
        x: int | None = None,
        y: int | None = None,
        zoom: int | None = None,
    ) -> tuple[bytes, tuple[float, float, float, float]]:
        """Read a tile from cache and return (jpeg_bytes, bounds).

        Args:
            tile_path: Path to the cached tile file
            x: Tile X coordinate (for fallback bounds)
            y: Tile Y coordinate (for fallback bounds)
            zoom: Zoom level (for fallback bounds)

        Returns:
            Tuple of (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max))

        Raises:
            FileNotFoundError: If the tile does not exist
        """
        if not tile_path.exists():
            raise FileNotFoundError(f"Tile not found: {tile_path}")

        suffix = tile_path.suffix.lower()
        raw_bytes = tile_path.read_bytes()

        # Determine bounds
        bounds = self._compute_bounds(tile_path, x, y, zoom)

        # JPEG passthrough: if source is JPEG and no quality change needed
        if suffix in (".jpeg", ".jpg") and self._target_quality is None:
            return (raw_bytes, bounds)

        # For TIFF files from reprojection cache, read as image
        if suffix in (".tif", ".tiff"):
            return self._read_tiff(tile_path, bounds)

        # PNG or quality change: convert to JPEG
        return self._convert_to_jpeg(raw_bytes, suffix, bounds)

    def _compute_bounds(
        self,
        tile_path: Path,
        x: int | None,
        y: int | None,
        zoom: int | None,
    ) -> tuple[float, float, float, float]:
        """Compute tile bounds from world file or fallback to tile grid math."""
        world_file = self._find_world_file(tile_path)

        if world_file and world_file.exists():
            try:
                wf = parse_world_file(world_file)
                width, height = self._get_image_dimensions(tile_path)
                return compute_bounds_from_world_file(wf, width, height)
            except (ValueError, FileNotFoundError) as e:
                logger.warning("Failed to parse world file %s: %s", world_file, e)

        # Fallback: compute from tile coordinates
        if x is not None and y is not None and zoom is not None:
            logger.debug(
                "Computing fallback bounds for tile (%d, %d, z=%d)", x, y, zoom
            )
            return compute_bounds_from_tile_coords(x, y, zoom)

        raise ValueError(
            f"Cannot compute bounds for {tile_path}: "
            "no world file and no tile coordinates provided"
        )

    def _find_world_file(self, tile_path: Path) -> Path | None:
        """Find the world file for a tile based on its extension."""
        suffix = tile_path.suffix.lower()
        if suffix in (".jpeg", ".jpg"):
            return tile_path.with_suffix(".jgw")
        elif suffix == ".png":
            return tile_path.with_suffix(".pgw")
        elif suffix in (".tif", ".tiff"):
            return tile_path.with_suffix(".tfw")
        return None

    def _get_image_dimensions(self, tile_path: Path) -> tuple[int, int]:
        """Get image dimensions using PIL, or fall back to default tile size."""
        try:
            from PIL import Image

            with Image.open(tile_path) as img:
                return img.size
        except ImportError:
            return (self._default_tile_size, self._default_tile_size)
        except Exception:
            return (self._default_tile_size, self._default_tile_size)

    def _convert_to_jpeg(
        self,
        raw_bytes: bytes,
        source_suffix: str,
        bounds: tuple[float, float, float, float],
    ) -> tuple[bytes, tuple[float, float, float, float]]:
        """Convert image bytes (PNG or JPEG with quality change) to JPEG."""
        from PIL import Image

        img = Image.open(io.BytesIO(raw_bytes))
        if img.mode == "RGBA":
            img = img.convert("RGB")

        buf = io.BytesIO()
        quality = self._target_quality or 85
        img.save(buf, format="JPEG", quality=quality)
        return (buf.getvalue(), bounds)

    def _read_tiff(
        self,
        tile_path: Path,
        bounds: tuple[float, float, float, float],
    ) -> tuple[bytes, tuple[float, float, float, float]]:
        """Read a GeoTIFF tile and convert to JPEG for the IMG writer."""
        from PIL import Image

        img = Image.open(tile_path)
        if img.mode != "RGB":
            img = img.convert("RGB")

        buf = io.BytesIO()
        quality = self._target_quality or 85
        img.save(buf, format="JPEG", quality=quality)
        return (buf.getvalue(), bounds)
