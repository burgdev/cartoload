from __future__ import annotations

import hashlib
import logging
import shutil
import struct
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .base import BaseExporter
from .garmin_img_model import (
    DrawOrderEntry,
    IMGFile,
    IMGHeader,
    ZoomLevel,
)
from .garmin_img_writer import (
    IMGWriter,
    LayoutComputer,
    MAX_FILE_SIZE,
    CompressedTiles,
    TileEncoder,
    TileExtractor,
)

if TYPE_CHECKING:
    from cartoload.config import LayerConfig

# Type alias for the export progress callback
ExportProgressCallback = Callable[[str, int, int], None]

logger = logging.getLogger(__name__)

# Garmin zoom level mapping (Web Mercator zoom -> Garmin zoom codes)
# These are the byte values stored in the TRE level record at byte offset 0.
# GMT displays them as hex notation (e.g., 0x84 shows as "84").
# Reference SwissTopo: levels [20,21,22,23,24], zoom [84,83,2,1,0]
#   level 20 → byte 0x84 (132), level 21 → byte 0x83 (131),
#   levels 22-24 → bytes 0x02, 0x01, 0x00
_GARMIN_ZOOM_CODES = {
    10: 0x94,
    11: 0x93,
    12: 0x92,
    13: 0x91,
    14: 0x90,
    15: 0x8F,
    16: 0x88,
    17: 0x87,
    18: 0x86,
    19: 0x85,
    20: 0x84,
    21: 0x83,
    22: 0x02,
    23: 0x01,
    24: 0x00,
}

MAP_NAME_MAX_LEN = 32


def _generate_map_id(layer_config: "LayerConfig") -> int:
    """Generate a deterministic map ID from layer configuration.

    Uses bounds and layer name to produce a 32-bit unsigned integer
    that serves as the unique map identifier in the IMG file.

    The algorithm matches Garmin conventions: the map_id is displayed
    as an 8-character uppercase hex string (e.g., 0x09C102B0).
    """
    bounds = layer_config.bounds or {}
    seed = (
        f"{layer_config.id}:"
        f"{bounds.get('north', 0):.6f},"
        f"{bounds.get('south', 0):.6f},"
        f"{bounds.get('west', 0):.6f},"
        f"{bounds.get('east', 0):.6f}"
    )
    digest = hashlib.md5(seed.encode()).digest()
    # Take first 4 bytes as uint32, mask to positive range
    map_id = struct.unpack("<I", digest[:4])[0] & 0x7FFFFFFF
    return map_id


class GarminImgExporter(BaseExporter):
    """
    Exports processed raster data to Garmin .img format.

    Creates raster IMG files with multi-resolution tile pyramids suitable
    for Garmin GPS devices (Fenix watches, handheld units, etc.).
    """

    @property
    def name(self) -> str:
        return "garmin-img"

    def export(
        self,
        raster_path: Path,
        layer_config: LayerConfig,
        output_path: Path,
        *,
        progress_callback: ExportProgressCallback | None = None,
    ) -> list[Path]:
        """
        Export processed raster to Garmin .img format.

        Orchestrates the full pipeline:
          1. Resolve attribution
          2. Build IMG data structure
          3. Extract and encode tiles
          4. Compute layout and handle size limits
          5. Write binary IMG file(s)

        Args:
            raster_path: Path to processed GeoTIFF
            layer_config: Layer configuration
            output_path: Path to output .img file
            progress_callback: Called with (stage, current, total) to report progress

        Returns:
            List of created .img files (may be multiple if >4GB)
        """
        logger.info(f"Exporting {raster_path} to Garmin IMG: {output_path}")

        # 1. Resolve attribution
        attribution = self._resolve_attribution(layer_config)

        # 2. Build IMG data structure
        img_file = self._build_img_structure(layer_config, attribution)

        # 3. Extract and encode tiles
        compressed_tiles = self._encode_tiles(
            raster_path, layer_config, progress_callback=progress_callback
        )

        # 4. Check if we need to split across files
        output_files = self._write_with_splitting(
            img_file, compressed_tiles, output_path
        )

        logger.info(f"IMG export complete: {len(output_files)} file(s)")
        return output_files

    def validate(self, output_path: Path) -> bool:
        """
        Validate IMG file using gmt (GMapTool).

        Args:
            output_path: Path to .img file

        Returns:
            True if file passes gmt validation, False otherwise
        """
        if not output_path.exists():
            logger.error(f"Output file does not exist: {output_path}")
            return False

        if not shutil.which("gmt"):
            logger.warning("gmt (GMapTool) not found, skipping validation")
            return True

        try:
            result = subprocess.run(
                ["gmt", "-i", "-v", str(output_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.error(f"gmt validation failed: {result.stderr}")
                return False

            logger.info(f"IMG file validated successfully: {output_path}")
            return True

        except subprocess.TimeoutExpired:
            logger.error("gmt validation timed out")
            return False
        except Exception as e:
            logger.error(f"gmt validation error: {e}")
            return False

    def _resolve_attribution(self, layer_config: LayerConfig) -> str:
        """Resolve attribution from layer config or source."""
        name = layer_config.name
        if len(name) > MAP_NAME_MAX_LEN:
            logger.warning(
                f"Map name truncated from {len(name)} to {MAP_NAME_MAX_LEN} characters"
            )
        return name[:MAP_NAME_MAX_LEN]

    def _build_img_structure(
        self, layer_config: LayerConfig, attribution: str
    ) -> IMGFile:
        """Build the IMGFile data structure from configuration."""
        bounds = layer_config.bounds or {}

        header = IMGHeader(
            magic="DSKIMG",
            format_version=2,
            creation_date=datetime.now(),
            creator="GARMIN",
            map_name=attribution,
        )

        draw_order = DrawOrderEntry(
            priority=24,
            layer_type="Raster Map",
        )

        # Build zoom levels
        zoom_levels = []
        for zl in sorted(layer_config.zoom_levels):
            zoom_code = _GARMIN_ZOOM_CODES.get(zl, 0)
            zoom_levels.append(
                ZoomLevel(
                    level_number=zl,
                    zoom_code=zoom_code,
                    lat_north=bounds.get("north"),
                    lat_south=bounds.get("south"),
                    lon_west=bounds.get("west"),
                    lon_east=bounds.get("east"),
                )
            )

        img_file = IMGFile(
            header=header,
            draw_order=draw_order,
            map_id=_generate_map_id(layer_config),
            bounds_north=bounds.get("north", 0.0),
            bounds_south=bounds.get("south", 0.0),
            bounds_west=bounds.get("west", 0.0),
            bounds_east=bounds.get("east", 0.0),
            description=layer_config.description or "Raster Map",
            copyright_string=f"© {datetime.now().year} cartoload",
            zoom_levels=zoom_levels,
        )

        return img_file

    def _encode_tiles(
        self,
        raster_path: Path,
        layer_config: LayerConfig,
        *,
        progress_callback: ExportProgressCallback | None = None,
    ) -> dict[int, list[tuple[bytes, tuple[float, float, float, float]]]]:
        """Extract and compress tiles from the raster at each zoom level.

        Returns:
            Dictionary mapping zoom level to list of (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max)) tuples.
        """
        bounds = layer_config.bounds or {}

        if raster_path and raster_path.exists():
            extractor = TileExtractor(raster_path)
            raw_tiles = extractor.extract_tiles(
                layer_config.zoom_levels,
                bounds,
                progress_callback=progress_callback,
            )
        else:
            # No raster file: produce empty tile sets
            raw_tiles = {z: [] for z in layer_config.zoom_levels}
            logger.warning("No raster path provided, producing empty tile sets")

        # Report encoding stage
        total_tiles = sum(len(t) for t in raw_tiles.values())
        if progress_callback:
            progress_callback("encoding", 0, total_tiles)

        compressed: dict[
            int, list[tuple[bytes, tuple[float, float, float, float]]]
        ] = {}
        encoded_count = 0
        for zoom, tiles in raw_tiles.items():
            if tiles:
                compressed[zoom] = []
                for tile_array, tile_bounds in tiles:
                    jpeg_data = TileEncoder.encode_tile(tile_array)
                    compressed[zoom].append((jpeg_data, tile_bounds))
                    encoded_count += 1
                    if progress_callback:
                        progress_callback("encoding", encoded_count, total_tiles)
            else:
                compressed[zoom] = []
                logger.debug(f"No tiles for zoom level {zoom}")

        total = sum(len(t) for t in compressed.values())
        logger.info(f"Encoded {total} tiles across {len(compressed)} zoom levels")
        return compressed

    def _write_with_splitting(
        self,
        img_file: IMGFile,
        compressed_tiles: CompressedTiles,
        output_path: Path,
    ) -> list[Path]:
        """
        Write IMG file(s), splitting into multiple files if needed.

        Handles the 4 GB file size limit by splitting along zoom level
        boundaries when the output would exceed the limit.
        """
        # Compute total estimated size
        computer = LayoutComputer(img_file, compressed_tiles)
        layouts = computer.compute()
        total_size = max(lay.end_offset for lay in layouts)

        if total_size <= MAX_FILE_SIZE:
            # Single file
            writer = IMGWriter(output_path)
            writer.write(img_file, compressed_tiles)
            return [output_path]

        # Need to split
        logger.info(
            f"Output would be {total_size:,} bytes, splitting into multiple files"
        )
        return self._split_write(img_file, compressed_tiles, output_path)

    def _split_write(
        self,
        img_file: IMGFile,
        compressed_tiles: CompressedTiles,
        output_path: Path,
    ) -> list[Path]:
        """
        Split output across multiple IMG files.

        Strategy: assign zoom levels to files, ensuring each stays under 4 GB.
        """
        stem = output_path.stem
        suffix = output_path.suffix
        parent = output_path.parent

        # Group zoom levels into files
        zoom_groups = self._compute_zoom_splits(img_file, compressed_tiles)

        output_files = []
        for i, (zooms, tiles_for_group) in enumerate(zoom_groups, start=1):
            if len(zoom_groups) == 1:
                file_path = output_path
            else:
                file_path = parent / f"{stem}_{i}{suffix}"

            # Build a per-file IMG structure
            file_img = IMGFile(
                header=IMGHeader(
                    magic="DSKIMG",
                    format_version=2,
                    creation_date=datetime.now(),
                    creator="GARMIN",
                    map_name=img_file.header.map_name,
                ),
                draw_order=img_file.draw_order,
                bounds_north=img_file.bounds_north,
                bounds_south=img_file.bounds_south,
                bounds_west=img_file.bounds_west,
                bounds_east=img_file.bounds_east,
                description=img_file.description,
                copyright_string=img_file.copyright_string,
                zoom_levels=[
                    z for z in img_file.zoom_levels if z.level_number in zooms
                ],
            )

            writer = IMGWriter(file_path)
            writer.write(file_img, tiles_for_group)
            output_files.append(file_path)

            logger.info(f"Wrote split file {i}: {file_path}")

        return output_files

    def _compute_zoom_splits(
        self,
        img_file: IMGFile,
        compressed_tiles: CompressedTiles,
    ) -> list[tuple[list[int], CompressedTiles]]:
        """
        Compute how to split zoom levels across files.

        Returns list of (zoom_levels, tiles_dict) tuples, one per output file.
        """
        groups: list[tuple[list[int], CompressedTiles]] = []
        current_zooms: list[int] = []
        current_tiles: CompressedTiles = {}

        for zoom in sorted(compressed_tiles.keys()):
            # Estimate size if we add this zoom level
            trial_tiles = {**current_tiles, zoom: compressed_tiles[zoom]}
            trial_img = IMGFile(
                header=img_file.header,
                zoom_levels=[
                    z
                    for z in img_file.zoom_levels
                    if z.level_number in list(current_zooms) + [zoom]
                ],
            )
            computer = LayoutComputer(trial_img, trial_tiles)
            layouts = computer.compute()
            trial_size = max(lay.end_offset for lay in layouts)

            if trial_size > MAX_FILE_SIZE and current_zooms:
                # Current group is full, start a new one
                groups.append((list(current_zooms), dict(current_tiles)))
                current_zooms = [zoom]
                current_tiles = {zoom: compressed_tiles[zoom]}
            else:
                current_zooms.append(zoom)
                current_tiles = dict(trial_tiles)

        if current_zooms:
            groups.append((list(current_zooms), dict(current_tiles)))

        return groups
