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
    Subdivision,
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

# Garmin zoom code computation (position-based, not absolute)
# The TRE1 level records store a zoom_code byte at offset 0.
# Pattern (confirmed from SwissTopo_West.img reference files):
#   For N levels: first two levels get 0x80 + (N-1) and 0x80 + (N-2),
#   remaining levels count down from N-3 to 0.
# Examples:
#   SwissTopo 5 levels [20-24]: codes 0x84, 0x83, 0x02, 0x01, 0x00
#   IOM 8 levels [17-24]:       codes 0x87, 0x86, 0x05, 0x04, 0x03, 0x02, 0x01, 0x00


def _compute_zoom_codes(sorted_level_numbers: list[int]) -> list[tuple[int, int]]:
    """Compute Garmin zoom codes for a set of zoom levels.

    Args:
        sorted_level_numbers: Zoom level numbers in ascending order.

    Returns:
        List of (level_number, zoom_code) tuples in the same order.
    """
    n = len(sorted_level_numbers)
    codes = []
    for i, level_num in enumerate(sorted_level_numbers):
        if i <= 1:
            code = 0x80 + (n - 1 - i)
        else:
            code = n - 1 - i
        codes.append((level_num, code))
    return codes


def generate_subdivisions(
    compressed_tiles: CompressedTiles,
    sorted_zoom_levels: list[int],
    bounds: dict[str, float],
) -> list[Subdivision]:
    """Generate spatial subdivisions for all zoom levels.

    Divides the map area into a geographic grid at each zoom level.
    The grid size increases with zoom level detail (fewer for overview
    zooms, more for detailed zooms), matching the SwissTopo pattern.

    Each tile is assigned to a subdivision based on its geographic position.

    Args:
        compressed_tiles: Dict mapping zoom level number to list of
            (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max)) tuples.
        sorted_zoom_levels: Zoom level numbers in ascending order.
        bounds: Geographic bounds dict with north, south, west, east keys.

    Returns:
        Flat list of Subdivision objects across all zoom levels, ordered
        by zoom level (overview first). Each subdivision contains its
        assigned tiles.
    """
    if not sorted_zoom_levels:
        return []

    n_zoom = len(sorted_zoom_levels)
    subdivisions: list[Subdivision] = []

    for z_idx, zoom_level in enumerate(sorted_zoom_levels):
        tiles = compressed_tiles.get(zoom_level, [])
        if not tiles:
            # No tiles at this zoom level — create one empty subdivision
            sub = Subdivision(
                center_lat=(bounds.get("north", 0) + bounds.get("south", 0)) / 2,
                center_lon=(bounds.get("west", 0) + bounds.get("east", 0)) / 2,
                zoom_level_index=z_idx,
            )
            subdivisions.append(sub)
            continue

        # Compute grid dimensions for this zoom level.
        # SwissTopo pattern: subdiv_counts=[1, 3, 138, 156, 300] for 5 levels.
        # For overview levels (z_idx=0,1): 1 subdivision
        # For detail levels: subdivide proportionally to tile count.
        if z_idx <= 1 or len(tiles) <= 4:
            # Few tiles or overview level: one subdivision for all tiles
            _assign_tiles_to_single_subdivision(tiles, z_idx, subdivisions)
        else:
            # Subdivide into a regular grid
            n_tiles = len(tiles)
            # Target roughly sqrt(n_tiles) subdivisions, but at least 4
            grid_side = max(2, int(n_tiles**0.25))
            _assign_tiles_to_grid(tiles, z_idx, grid_side, grid_side, subdivisions)

    # Set TRE2 links and bounds
    _set_subdivision_links(subdivisions, n_zoom, bounds)

    return subdivisions


def _assign_tiles_to_single_subdivision(
    tiles: list, z_idx: int, subdivisions: list[Subdivision]
) -> None:
    """Assign all tiles to a single subdivision."""
    # Compute center and bounds from tiles
    lats: list[float] = []
    lons: list[float] = []
    for tile_entry in tiles:
        if isinstance(tile_entry, tuple):
            _, tile_bounds = tile_entry
            lat_min, lon_min, lat_max, lon_max = tile_bounds
            lats.extend([lat_min, lat_max])
            lons.extend([lon_min, lon_max])

    center_lat = (min(lats) + max(lats)) / 2 if lats else 0.0
    center_lon = (min(lons) + max(lons)) / 2 if lons else 0.0

    sub = Subdivision(
        center_lat=center_lat,
        center_lon=center_lon,
        zoom_level_index=z_idx,
        tile_entries=list(tiles),
        bounds_west=min(lons) if lons else 0.0,
        bounds_east=max(lons) if lons else 0.0,
        bounds_north=max(lats) if lats else 0.0,
        bounds_south=min(lats) if lats else 0.0,
    )
    subdivisions.append(sub)


def _assign_tiles_to_grid(
    tiles: list,
    z_idx: int,
    grid_cols: int,
    grid_rows: int,
    subdivisions: list[Subdivision],
) -> None:
    """Assign tiles to a grid of subdivisions based on geographic position."""
    # Find overall tile extent
    lat_min_all = float("inf")
    lat_max_all = float("-inf")
    lon_min_all = float("inf")
    lon_max_all = float("-inf")

    for tile_entry in tiles:
        if isinstance(tile_entry, tuple):
            _, tile_bounds = tile_entry
            t_lat_min, t_lon_min, t_lat_max, t_lon_max = tile_bounds
            lat_min_all = min(lat_min_all, t_lat_min)
            lat_max_all = max(lat_max_all, t_lat_max)
            lon_min_all = min(lon_min_all, t_lon_min)
            lon_max_all = max(lon_max_all, t_lon_max)

    lat_range = lat_max_all - lat_min_all
    lon_range = lon_max_all - lon_min_all

    if lat_range <= 0:
        lat_range = 1.0
    if lon_range <= 0:
        lon_range = 1.0

    # Create grid cells
    cell_lat = lat_range / grid_rows
    cell_lon = lon_range / grid_cols

    # Initialize grid cells
    grid: dict[tuple[int, int], list] = {
        (r, c): [] for r in range(grid_rows) for c in range(grid_cols)
    }

    # Assign tiles to grid cells
    for tile_entry in tiles:
        if isinstance(tile_entry, tuple):
            _, tile_bounds = tile_entry
            t_lat_min, t_lon_min, t_lat_max, t_lon_max = tile_bounds
        else:
            continue

        tile_center_lat = (t_lat_min + t_lat_max) / 2
        tile_center_lon = (t_lon_min + t_lon_max) / 2

        row = min(int((tile_center_lat - lat_min_all) / cell_lat), grid_rows - 1)
        col = min(int((tile_center_lon - lon_min_all) / cell_lon), grid_cols - 1)
        row = max(0, row)
        col = max(0, col)

        grid[(row, col)].append(tile_entry)

    # Create subdivisions for non-empty cells
    for r in range(grid_rows):
        for c in range(grid_cols):
            cell_tiles = grid[(r, c)]
            if not cell_tiles:
                continue

            cell_lat_min = lat_min_all + r * cell_lat
            cell_lat_max = cell_lat_min + cell_lat
            cell_lon_min = lon_min_all + c * cell_lon
            cell_lon_max = cell_lon_min + cell_lon

            center_lat = (cell_lat_min + cell_lat_max) / 2
            center_lon = (cell_lon_min + cell_lon_max) / 2

            sub = Subdivision(
                center_lat=center_lat,
                center_lon=center_lon,
                zoom_level_index=z_idx,
                tile_entries=cell_tiles,
                bounds_west=cell_lon_min,
                bounds_east=cell_lon_max,
                bounds_north=cell_lat_max,
                bounds_south=cell_lat_min,
            )
            subdivisions.append(sub)


def _set_subdivision_links(
    subdivisions: list[Subdivision], n_zoom: int, bounds: dict[str, float]
) -> None:
    """Set next_level_index links and bounds on subdivisions.

    Links the subdivision hierarchy across zoom levels.
    Sets bounds from the map bounds for empty subdivisions (overview levels).
    """
    if not subdivisions:
        return

    # Group subdivisions by zoom level index
    by_level: dict[int, list[int]] = {}
    for i, sub in enumerate(subdivisions):
        by_level.setdefault(sub.zoom_level_index, []).append(i)

    for i, sub in enumerate(subdivisions):
        z_idx = sub.zoom_level_index

        # Set bounds for empty subdivisions (overview levels with no tiles)
        if not sub.tile_entries and sub.bounds_west == 0.0:
            sub.bounds_west = bounds.get("west", 0.0)
            sub.bounds_east = bounds.get("east", 0.0)
            sub.bounds_north = bounds.get("north", 0.0)
            sub.bounds_south = bounds.get("south", 0.0)

        # next_level_index: index of first subdivision at next zoom level
        has_children = z_idx < n_zoom - 1
        if has_children:
            next_z = z_idx + 1
            if next_z in by_level and by_level[next_z]:
                sub.next_level_index = by_level[next_z][0]
            else:
                sub.next_level_index = 0
        else:
            sub.next_level_index = 0


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

    def export_from_tiles(
        self,
        compressed_tiles: CompressedTiles,
        layer_config: "LayerConfig",
        output_path: Path,
        *,
        progress_callback: ExportProgressCallback | None = None,
    ) -> list[Path]:
        """Export pre-encoded tiles directly to Garmin .img format.

        Skips the TileExtractor + TileEncoder pipeline entirely, accepting
        tiles that have already been read, reprojected, and encoded to JPEG
        (e.g. from BatchTileProcessor).

        Args:
            compressed_tiles: Dict mapping zoom level to list of
                (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max)) tuples
                or plain jpeg_bytes.
            layer_config: Layer configuration
            output_path: Path to output .img file
            progress_callback: Called with (stage, current, total) for progress

        Returns:
            List of created .img files (may be multiple if >4GB)
        """
        logger.info("Exporting pre-encoded tiles to Garmin IMG: %s", output_path)

        # 1. Resolve attribution and build IMG structure
        attribution = self._resolve_attribution(layer_config)
        img_file = self._build_img_structure(layer_config, attribution)

        # 2. Report tile counts
        total_tiles = sum(len(t) for t in compressed_tiles.values())
        if progress_callback:
            progress_callback("writing", 0, total_tiles)
        logger.info(
            "Writing %d pre-encoded tiles across %d zoom levels",
            total_tiles,
            len(compressed_tiles),
        )

        # 3. Write IMG file(s)
        output_files = self._write_with_splitting(
            img_file, compressed_tiles, output_path
        )

        logger.info("IMG export complete: %d file(s)", len(output_files))
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

        # Build zoom levels with dynamically computed codes
        sorted_zooms = sorted(layer_config.zoom_levels)
        zoom_code_map = dict(_compute_zoom_codes(sorted_zooms))
        zoom_levels = []
        for zl in sorted_zooms:
            zoom_levels.append(
                ZoomLevel(
                    level_number=zl,
                    zoom_code=zoom_code_map[zl],
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
        # Generate spatial subdivisions
        bounds = {
            "north": img_file.bounds_north,
            "south": img_file.bounds_south,
            "west": img_file.bounds_west,
            "east": img_file.bounds_east,
        }
        sorted_zooms = [z.level_number for z in img_file.zoom_levels]
        subdivisions = generate_subdivisions(compressed_tiles, sorted_zooms, bounds)

        # Compute total estimated size
        computer = LayoutComputer(img_file, compressed_tiles, subdivisions=subdivisions)
        layouts = computer.compute()
        total_size = max(lay.end_offset for lay in layouts)

        if total_size <= MAX_FILE_SIZE:
            # Single file
            writer = IMGWriter(output_path)
            writer.write(img_file, compressed_tiles, subdivisions=subdivisions)
            return [output_path]

        # Need to split
        logger.info(
            f"Output would be {total_size:,} bytes, splitting into multiple files"
        )
        return self._split_write(
            img_file, compressed_tiles, output_path, subdivisions=subdivisions
        )

    def _split_write(
        self,
        img_file: IMGFile,
        compressed_tiles: CompressedTiles,
        output_path: Path,
        subdivisions: list[Subdivision] | None = None,
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

        bounds = {
            "north": img_file.bounds_north,
            "south": img_file.bounds_south,
            "west": img_file.bounds_west,
            "east": img_file.bounds_east,
        }

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

            # Generate subdivisions for this zoom subset
            group_subdivs = generate_subdivisions(tiles_for_group, zooms, bounds)

            writer = IMGWriter(file_path)
            writer.write(file_img, tiles_for_group, subdivisions=group_subdivs)
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
