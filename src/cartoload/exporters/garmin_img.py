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
    GMPGroup,
    IMGFile,
    IMGHeader,
    Subdivision,
    TileMetadata,
    ZoomLevel,
)
from .garmin_img_writer import (
    IMGWriter,
    LayoutComputer,
    MAX_FILE_SIZE,
    MAX_GMP_SIZE,
    CompressedTiles,
    StreamingIMGWriter,
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
# Only the top level (most zoomed-out, first entry) gets the inherited flag (0x80).
# This matches mkgmap behavior: Map.topLevelSubdivision() calls zoom.setInherited(true)
# only once, on the root level. GPXSee skips all levels with 0x80 and starts rendering
# from the first non-inherited level.
# Pattern: first level gets 0x80 + (N-1), remaining levels count down from N-2 to 0.
# Example (8 levels): 0x87, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01, 0x00


def _compute_zoom_codes(
    sorted_level_numbers: list[int],
    has_tiles: list[bool] | None = None,
) -> list[tuple[int, int]]:
    """Compute Garmin zoom codes for a set of zoom levels.

    The 0x80 inherited flag is set only on consecutive empty levels at the
    top of the hierarchy (before the first level with tiles). This ensures
    that the most-zoomed-out level with actual tile data is visible on
    Garmin devices and in GPXSee, which skip all levels with the inherited
    flag.

    Args:
        sorted_level_numbers: Zoom level numbers in ascending order.
        has_tiles: Optional list of booleans (same length as
            sorted_level_numbers). True means that level has tile data.
            If None, defaults to all True (no levels get inherited flag).

    Returns:
        List of (level_number, zoom_code) tuples in the same order.
    """
    n = len(sorted_level_numbers)
    if has_tiles is None:
        has_tiles = [True] * n

    # Find the first level with tiles; only levels before it get inherited.
    first_with_tiles = 0
    for i, has in enumerate(has_tiles):
        if has:
            first_with_tiles = i
            break
    else:
        # No level has tiles — only the first gets inherited (map boundary).
        first_with_tiles = 1

    codes = []
    for i, level_num in enumerate(sorted_level_numbers):
        code = n - 1 - i
        if i < first_with_tiles:
            code |= 0x80
        codes.append((level_num, code))
    return codes


def _filter_tiles_by_bounds(
    tiles: list, parent_bounds: tuple[float, float, float, float]
) -> list:
    """Filter tiles whose center falls within parent bounds.

    Args:
        tiles: List of (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max)) tuples.
        parent_bounds: (north, south, west, east) of the parent subdivision.

    Returns:
        List of tiles whose center is within the parent bounds.
    """
    p_north, p_south, p_west, p_east = parent_bounds
    result = []
    for tile_entry in tiles:
        if not isinstance(tile_entry, tuple):
            continue
        _, tile_bounds = tile_entry
        lat_min, lon_min, lat_max, lon_max = tile_bounds
        center_lat = (lat_min + lat_max) / 2
        center_lon = (lon_min + lon_max) / 2
        if p_south <= center_lat <= p_north and p_west <= center_lon <= p_east:
            result.append(tile_entry)
    return result


def _filter_metadata_by_bounds(
    tiles: list[TileMetadata], parent_bounds: tuple[float, float, float, float]
) -> list[TileMetadata]:
    """Filter TileMetadata entries whose center falls within parent bounds."""
    p_north, p_south, p_west, p_east = parent_bounds
    result = []
    for tm in tiles:
        center_lat = (tm.lat_min + tm.lat_max) / 2
        center_lon = (tm.lon_min + tm.lon_max) / 2
        if p_south <= center_lat <= p_north and p_west <= center_lon <= p_east:
            result.append(tm)
    return result


def _generate_child_subdivisions(
    tiles: list,
    z_idx: int,
    parent_bounds: tuple[float, float, float, float],
) -> list[Subdivision]:
    """Generate child subdivisions within parent bounds from (bytes, bounds) tiles.

    Args:
        tiles: Tiles at zoom level z_idx whose centers fall within parent_bounds.
        z_idx: Zoom level index for the children.
        parent_bounds: (north, south, west, east) constraining the grid.

    Returns:
        List of child Subdivision objects, with bounds derived from tiles.
    """
    if not tiles:
        # No tiles in this parent — create one empty child spanning parent bounds
        p_n, p_s, p_w, p_e = parent_bounds
        return [
            Subdivision(
                center_lat=(p_n + p_s) / 2,
                center_lon=(p_w + p_e) / 2,
                zoom_level_index=z_idx,
                bounds_west=p_w,
                bounds_east=p_e,
                bounds_north=p_n,
                bounds_south=p_s,
            )
        ]

    if len(tiles) <= 4:
        # Few tiles: single subdivision
        children: list[Subdivision] = []
        _assign_tiles_to_single_subdivision(tiles, z_idx, children)
        return children

    n_tiles = len(tiles)
    grid_side = max(2, int(n_tiles**0.25))
    children = []
    _assign_tiles_to_grid(tiles, z_idx, grid_side, grid_side, children)
    return children


def _generate_child_subdivisions_from_metadata(
    tiles: list[TileMetadata],
    z_idx: int,
    parent_bounds: tuple[float, float, float, float],
) -> list[Subdivision]:
    """Generate child subdivisions within parent bounds from TileMetadata.

    Same logic as _generate_child_subdivisions but for metadata-based tiles.
    """
    if not tiles:
        p_n, p_s, p_w, p_e = parent_bounds
        return [
            Subdivision(
                center_lat=(p_n + p_s) / 2,
                center_lon=(p_w + p_e) / 2,
                zoom_level_index=z_idx,
                bounds_west=p_w,
                bounds_east=p_e,
                bounds_north=p_n,
                bounds_south=p_s,
            )
        ]

    if len(tiles) <= 4:
        children: list[Subdivision] = []
        _assign_metadata_to_single_subdivision(tiles, z_idx, children)
        return children

    n_tiles = len(tiles)
    grid_side = max(2, int(n_tiles**0.25))
    children = []
    _assign_metadata_to_grid(tiles, z_idx, grid_side, grid_side, children)
    return children


def generate_subdivisions(
    compressed_tiles: CompressedTiles,
    sorted_zoom_levels: list[int],
    bounds: dict[str, float],
) -> list[Subdivision]:
    """Generate spatial subdivisions for all zoom levels in a hierarchical tree.

    Builds a true parent-child hierarchy where each parent's children are
    spatially contained within the parent's bounds. At each level, for each
    parent, tiles whose centers fall within the parent's bounds are assigned
    to child subdivisions. This enables efficient spatial pruning on Garmin
    devices.

    Args:
        compressed_tiles: Dict mapping zoom level number to list of
            (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max)) tuples.
        sorted_zoom_levels: Zoom level numbers in ascending order.
        bounds: Geographic bounds dict with north, south, west, east keys.

    Returns:
        Flat list of Subdivision objects across all zoom levels, ordered
        by zoom level then by parent group. Each parent's children are
        contiguous. Each subdivision contains its assigned tiles and
        next_level_index pointing to its first child.
    """
    if not sorted_zoom_levels:
        return []

    n_zoom = len(sorted_zoom_levels)
    subdivisions: list[Subdivision] = []

    map_n = bounds.get("north", 0.0)
    map_s = bounds.get("south", 0.0)
    map_w = bounds.get("west", 0.0)
    map_e = bounds.get("east", 0.0)

    # Level 0: create top-level subdivisions from all tiles at zoom 0
    first_zoom = sorted_zoom_levels[0]
    first_tiles = compressed_tiles.get(first_zoom, [])

    if not first_tiles:
        # Empty overview level — single full-bounds subdivision
        subdivisions.append(
            Subdivision(
                center_lat=(map_n + map_s) / 2,
                center_lon=(map_w + map_e) / 2,
                zoom_level_index=0,
                bounds_west=map_w,
                bounds_east=map_e,
                bounds_north=map_n,
                bounds_south=map_s,
            )
        )
    elif len(first_tiles) <= 4:
        _assign_tiles_to_single_subdivision(first_tiles, 0, subdivisions)
    else:
        grid_side = max(2, int(len(first_tiles) ** 0.25))
        _assign_tiles_to_grid(first_tiles, 0, grid_side, grid_side, subdivisions)

    # Levels 1..N-1: for each parent, generate children within its bounds
    for z_idx in range(1, n_zoom):
        zoom_level = sorted_zoom_levels[z_idx]
        all_tiles_at_level = compressed_tiles.get(zoom_level, [])

        # Get parents at previous level
        parents = [s for s in subdivisions if s.zoom_level_index == z_idx - 1]

        for parent in parents:
            parent_bounds = (
                parent.bounds_north,
                parent.bounds_south,
                parent.bounds_west,
                parent.bounds_east,
            )

            # Filter tiles to those within this parent's bounds
            parent_tiles = _filter_tiles_by_bounds(all_tiles_at_level, parent_bounds)

            # Generate children within parent bounds
            children = _generate_child_subdivisions(parent_tiles, z_idx, parent_bounds)

            # Link parent to first child
            parent.next_level_index = len(subdivisions)

            # Append children contiguously
            subdivisions.extend(children)

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

            # Compute bounds from actual tile positions (not grid cell)
            tile_lat_min = float("inf")
            tile_lat_max = float("-inf")
            tile_lon_min = float("inf")
            tile_lon_max = float("-inf")
            for te in cell_tiles:
                if isinstance(te, tuple):
                    _, tb = te
                    tl_min, tn_min, tl_max, tn_max = tb
                    tile_lat_min = min(tile_lat_min, tl_min)
                    tile_lat_max = max(tile_lat_max, tl_max)
                    tile_lon_min = min(tile_lon_min, tn_min)
                    tile_lon_max = max(tile_lon_max, tn_max)

            # Center on actual tile midpoint to minimize delta magnitudes
            center_lat = (tile_lat_min + tile_lat_max) / 2
            center_lon = (tile_lon_min + tile_lon_max) / 2

            sub = Subdivision(
                center_lat=center_lat,
                center_lon=center_lon,
                zoom_level_index=z_idx,
                tile_entries=cell_tiles,
                bounds_west=tile_lon_min,
                bounds_east=tile_lon_max,
                bounds_north=tile_lat_max,
                bounds_south=tile_lat_min,
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


def _reorder_subdivisions_in_place(
    subdivisions: list[Subdivision],
    old_indices: list[int],
    new_order: list[int],
    by_level: dict[int, list[int]],
    level: int,
) -> None:
    """Reorder subdivisions at a given level in-place.

    Given old_indices (current positions of level's subdivisions) and
    new_order (desired order of those same subdivisions), rearranges the
    main subdivisions list and updates by_level.

    The trick: we extract the subdivision objects at old_indices, reorder
    them according to new_order, and put them back at the same positions.
    """
    if old_indices == new_order:
        return  # Already in correct order

    # Build index mapping: old position -> object
    old_to_obj: dict[int, Subdivision] = {}
    for idx in old_indices:
        old_to_obj[idx] = subdivisions[idx]

    # Create ordered list of objects in the new order
    ordered_objs = [old_to_obj[oi] for oi in new_order]

    # Place back at the same positions (which are sorted)
    sorted_positions = sorted(old_indices)
    for i, obj in enumerate(ordered_objs):
        subdivisions[sorted_positions[i]] = obj

    # Update by_level to reflect new ordering
    by_level[level] = sorted_positions


MAP_NAME_MAX_LEN = 32


def generate_subdivisions_from_metadata(
    tile_metadata_by_zoom: dict[int, list[TileMetadata]],
    sorted_zoom_levels: list[int],
    bounds: dict[str, float],
) -> list[Subdivision]:
    """Generate spatial subdivisions from TileMetadata in a hierarchical tree.

    Same hierarchical approach as generate_subdivisions() but reads bounds
    directly from TileMetadata fields instead of unpacking (bytes, bounds)
    tuples. Produces Subdivision objects with tile_entries populated from
    metadata.

    Args:
        tile_metadata_by_zoom: Dict mapping zoom level to list of TileMetadata
        sorted_zoom_levels: Zoom level numbers in ascending order.
        bounds: Geographic bounds dict with north, south, west, east keys.

    Returns:
        Flat list of Subdivision objects in hierarchical order.
    """
    if not sorted_zoom_levels:
        return []

    n_zoom = len(sorted_zoom_levels)
    subdivisions: list[Subdivision] = []

    map_n = bounds.get("north", 0.0)
    map_s = bounds.get("south", 0.0)
    map_w = bounds.get("west", 0.0)
    map_e = bounds.get("east", 0.0)

    # Level 0: create top-level subdivisions
    first_zoom = sorted_zoom_levels[0]
    first_tiles = tile_metadata_by_zoom.get(first_zoom, [])

    if not first_tiles:
        subdivisions.append(
            Subdivision(
                center_lat=(map_n + map_s) / 2,
                center_lon=(map_w + map_e) / 2,
                zoom_level_index=0,
                bounds_west=map_w,
                bounds_east=map_e,
                bounds_north=map_n,
                bounds_south=map_s,
            )
        )
    elif len(first_tiles) <= 4:
        _assign_metadata_to_single_subdivision(first_tiles, 0, subdivisions)
    else:
        grid_side = max(2, int(len(first_tiles) ** 0.25))
        _assign_metadata_to_grid(first_tiles, 0, grid_side, grid_side, subdivisions)

    # Levels 1..N-1: for each parent, generate children within its bounds
    for z_idx in range(1, n_zoom):
        zoom_level = sorted_zoom_levels[z_idx]
        all_tiles_at_level = tile_metadata_by_zoom.get(zoom_level, [])

        parents = [s for s in subdivisions if s.zoom_level_index == z_idx - 1]

        for parent in parents:
            parent_bounds = (
                parent.bounds_north,
                parent.bounds_south,
                parent.bounds_west,
                parent.bounds_east,
            )

            parent_tiles = _filter_metadata_by_bounds(all_tiles_at_level, parent_bounds)

            children = _generate_child_subdivisions_from_metadata(
                parent_tiles, z_idx, parent_bounds
            )

            parent.next_level_index = len(subdivisions)
            subdivisions.extend(children)

    return subdivisions


def _assign_metadata_to_single_subdivision(
    tiles: list[TileMetadata], z_idx: int, subdivisions: list[Subdivision]
) -> None:
    """Assign all TileMetadata entries to a single subdivision."""
    lats = [t.lat_min for t in tiles] + [t.lat_max for t in tiles]
    lons = [t.lon_min for t in tiles] + [t.lon_max for t in tiles]

    center_lat = (min(lats) + max(lats)) / 2
    center_lon = (min(lons) + max(lons)) / 2

    sub = Subdivision(
        center_lat=center_lat,
        center_lon=center_lon,
        zoom_level_index=z_idx,
        tile_entries=list(tiles),
        bounds_west=min(lons),
        bounds_east=max(lons),
        bounds_north=max(lats),
        bounds_south=min(lats),
    )
    subdivisions.append(sub)


def _assign_metadata_to_grid(
    tiles: list[TileMetadata],
    z_idx: int,
    grid_cols: int,
    grid_rows: int,
    subdivisions: list[Subdivision],
) -> None:
    """Assign TileMetadata entries to a grid of subdivisions."""
    lat_min_all = min(t.lat_min for t in tiles)
    lat_max_all = max(t.lat_max for t in tiles)
    lon_min_all = min(t.lon_min for t in tiles)
    lon_max_all = max(t.lon_max for t in tiles)

    lat_range = lat_max_all - lat_min_all or 1.0
    lon_range = lon_max_all - lon_min_all or 1.0

    cell_lat = lat_range / grid_rows
    cell_lon = lon_range / grid_cols

    grid: dict[tuple[int, int], list[TileMetadata]] = {
        (r, c): [] for r in range(grid_rows) for c in range(grid_cols)
    }

    for tm in tiles:
        tile_center_lat = (tm.lat_min + tm.lat_max) / 2
        tile_center_lon = (tm.lon_min + tm.lon_max) / 2

        row = min(int((tile_center_lat - lat_min_all) / cell_lat), grid_rows - 1)
        col = min(int((tile_center_lon - lon_min_all) / cell_lon), grid_cols - 1)
        row = max(0, row)
        col = max(0, col)

        grid[(row, col)].append(tm)

    for r in range(grid_rows):
        for c in range(grid_cols):
            cell_tiles = grid[(r, c)]
            if not cell_tiles:
                continue

            cell_lat_min = min(t.lat_min for t in cell_tiles)
            cell_lat_max = max(t.lat_max for t in cell_tiles)
            cell_lon_min = min(t.lon_min for t in cell_tiles)
            cell_lon_max = max(t.lon_max for t in cell_tiles)

            center_lat = (cell_lat_min + cell_lat_max) / 2
            center_lon = (cell_lon_min + cell_lon_max) / 2

            sub = Subdivision(
                center_lat=center_lat,
                center_lon=center_lon,
                zoom_level_index=z_idx,
                tile_entries=list(cell_tiles),
                bounds_west=cell_lon_min,
                bounds_east=cell_lon_max,
                bounds_north=cell_lat_max,
                bounds_south=cell_lat_min,
            )
            subdivisions.append(sub)


def _split_into_gmp_groups(
    tile_metadata: dict[int, list[TileMetadata]],
    img_file: IMGFile,
    bounds: dict[str, float],
) -> list[GMPGroup]:
    """Split tiles into GMP groups, handling both multi-zoom and within-zoom splits.

    Each group's estimated JPEG data stays under MAX_GMP_SIZE * 0.85.
    Zoom levels are grouped contiguously. When a single zoom level exceeds the
    target, its tiles are split into geographic latitude bands.

    Each group gets:
    - A unique map_id derived from base map_id + group index
    - Its own set of spatial subdivisions
    - The full map bounds (ensures zoom level filtering works)
    - The zoom levels that belong to this group

    Returns:
        List of GMPGroup objects.
    """
    sorted_zooms = sorted(tile_metadata.keys())

    # Calculate JPEG size per zoom level
    zoom_jpeg_sizes: dict[int, int] = {}
    for z in sorted_zooms:
        zoom_jpeg_sizes[z] = sum(t.jpeg_size for t in tile_metadata[z])

    # Target per-group JPEG size: 85% of MAX_GMP_SIZE (leave room for headers)
    target_jpeg_per_group = int(MAX_GMP_SIZE * 0.85)

    # First pass: group zoom levels contiguously, splitting oversized zoom levels
    # Each entry is (zoom_levels: list[int], tile_metadata_subset, jpeg_size)
    raw_groups: list[tuple[list[int], dict[int, list[TileMetadata]], int]] = []

    remaining_zooms = list(sorted_zooms)
    while remaining_zooms:
        group_zooms: list[int] = []
        group_meta: dict[int, list[TileMetadata]] = {}
        group_jpeg = 0

        while remaining_zooms:
            z = remaining_zooms[0]
            z_size = zoom_jpeg_sizes[z]

            if z_size > target_jpeg_per_group and not group_zooms:
                # Single zoom level exceeds target — split by latitude bands
                n_bands = (z_size + target_jpeg_per_group - 1) // target_jpeg_per_group
                tiles = tile_metadata[z]
                # Sort by latitude (south to north) for band splitting
                tiles_sorted = sorted(tiles, key=lambda t: t.lat_min)
                band_size = (len(tiles_sorted) + n_bands - 1) // n_bands
                for i in range(n_bands):
                    band_tiles = tiles_sorted[i * band_size : (i + 1) * band_size]
                    band_jpeg = sum(t.jpeg_size for t in band_tiles)
                    raw_groups.append(([z], {z: band_tiles}, band_jpeg))
                remaining_zooms.pop(0)
                group_zooms = []  # signal we consumed this zoom already
                break

            if group_zooms and group_jpeg + z_size > target_jpeg_per_group:
                # Adding this zoom would overflow — start a new group
                break

            group_zooms.append(z)
            group_meta[z] = tile_metadata[z]
            group_jpeg += z_size
            remaining_zooms.pop(0)

        if group_zooms:
            raw_groups.append((group_zooms, group_meta, group_jpeg))

    logger.info(
        "Split %d zoom levels into %d GMP groups: %s",
        len(sorted_zooms),
        len(raw_groups),
        ", ".join(
            f"[{zs[0]}{'-' + str(zs[-1]) if len(zs) > 1 else ''}]: {sz / 1e9:.1f} GB"
            for (zs, _, sz) in raw_groups
        ),
    )

    # Create GMPGroup objects
    result: list[GMPGroup] = []
    base_map_id = img_file.map_id

    for group_idx, (group_zooms, group_meta, group_jpeg_size) in enumerate(raw_groups):
        # Generate subdivisions for this group
        group_subdivisions = generate_subdivisions_from_metadata(
            group_meta, sorted(group_zooms), bounds
        )

        # Build zoom levels for this group (from img_file's zoom_levels)
        zoom_set = set(group_zooms)
        group_zoom_levels = [
            zl
            for zl in img_file.zoom_levels
            if (zl.source_zoom or zl.level_number) in zoom_set
        ]

        # Derive unique map_id
        group_map_id = (base_map_id + group_idx + 1) & 0x7FFFFFFF

        result.append(
            GMPGroup(
                map_id=group_map_id,
                subdivisions=group_subdivisions,
                zoom_levels=group_zoom_levels,
                bounds_north=bounds.get("north", 0.0),
                bounds_south=bounds.get("south", 0.0),
                bounds_west=bounds.get("west", 0.0),
                bounds_east=bounds.get("east", 0.0),
            )
        )
        logger.info(
            "  GMP group %d: zooms %s, %d tiles, %.1f GB, map_id=0x%08X",
            group_idx,
            f"{group_zooms[0]}-{group_zooms[-1]}"
            if len(group_zooms) > 1
            else str(group_zooms[0]),
            sum(len(s.tile_entries) for s in group_subdivisions),
            group_jpeg_size / 1e9,
            group_map_id,
        )

    return result


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
        sorted_zooms = sorted(layer_config.zoom_levels)
        has_tiles = [len(compressed_tiles.get(zl, [])) > 0 for zl in sorted_zooms]
        img_file = self._build_img_structure(layer_config, attribution, has_tiles)

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

    def export_from_metadata(
        self,
        tile_metadata: dict[int, list[TileMetadata]],
        layer_config: "LayerConfig",
        output_path: Path,
        *,
        source_crs: str = "EPSG:3857",
        quality: int | None = None,
        progress_callback: ExportProgressCallback | None = None,
        tile_processor_override: Callable | None = None,
    ) -> list[Path]:
        """Export tiles to Garmin IMG using streaming writer from metadata.

        Uses the two-pass streaming writer: computes layout from TileMetadata
        (no JPEG data in memory), then streams JPEG data from source files
        during the write pass. Memory bounded to ~12 MB per batch.

        Args:
            tile_metadata: Dict mapping zoom level to list of TileMetadata
            layer_config: Layer configuration
            output_path: Path to output .img file
            source_crs: Source CRS for tile processing (default EPSG:3857)
            quality: JPEG quality for warping (1-100), or None for passthrough
            progress_callback: Called with (stage, current, total) for progress
            tile_processor_override: Custom tile processor callable. When
                provided, this replaces the default warp_tile_to_jpeg processor.
                Used by the composite pipeline to blend sub-layers.

        Returns:
            List of created .img files (may be multiple if >4GB)
        """
        logger.info(
            "Streaming export of %d zoom levels to Garmin IMG: %s",
            len(tile_metadata),
            output_path,
        )

        # 1. Resolve attribution and build IMG structure
        attribution = self._resolve_attribution(layer_config)
        sorted_zooms = sorted(layer_config.zoom_levels)
        has_tiles = [len(tile_metadata.get(zl, [])) > 0 for zl in sorted_zooms]
        img_file = self._build_img_structure(layer_config, attribution, has_tiles)

        # 2. Report tile counts
        total_tiles = sum(len(t) for t in tile_metadata.values())
        if progress_callback:
            progress_callback("writing", 0, total_tiles)
        logger.info(
            "Writing %d tiles (streaming) across %d zoom levels",
            total_tiles,
            len(tile_metadata),
        )

        # 3. Determine bounds and tile processor
        bounds = {
            "north": img_file.bounds_north,
            "south": img_file.bounds_south,
            "west": img_file.bounds_west,
            "east": img_file.bounds_east,
        }
        from functools import partial

        from ..processor.rasterio_warp import warp_tile_to_jpeg

        tile_processor = None
        if tile_processor_override is not None:
            tile_processor = tile_processor_override
        elif source_crs != "EPSG:4326":
            tile_processor = partial(warp_tile_to_jpeg, target_crs="EPSG:4326")

        # 4. Check if we need multiple GMP subfiles (uint32 section size limit)
        total_jpeg_size = sum(
            t.jpeg_size for tiles in tile_metadata.values() for t in tiles
        )
        sorted_zooms = sorted(tile_metadata.keys())

        # Rough estimate: JPEG is ~85% of total GMP size (rest is headers/RGN2/LBL)
        estimated_gmp_size = total_jpeg_size / 0.85 if total_jpeg_size > 0 else 0

        if estimated_gmp_size > MAX_GMP_SIZE:
            # Split into multiple GMP groups by zoom level bands
            gmp_groups = _split_into_gmp_groups(tile_metadata, img_file, bounds)
            logger.info(
                "Split %d tiles (%.1f GB) into %d GMP groups",
                total_tiles,
                total_jpeg_size / 1e9,
                len(gmp_groups),
            )
        else:
            # Single GMP — normal path
            subdivisions = generate_subdivisions_from_metadata(
                tile_metadata, sorted_zooms, bounds
            )
            gmp_groups = [
                GMPGroup(
                    map_id=img_file.map_id,
                    subdivisions=subdivisions,
                    zoom_levels=list(img_file.zoom_levels),
                    bounds_north=bounds.get("north", 0.0),
                    bounds_south=bounds.get("south", 0.0),
                    bounds_west=bounds.get("west", 0.0),
                    bounds_east=bounds.get("east", 0.0),
                )
            ]

        # 5. Write IMG file using streaming writer
        writer = StreamingIMGWriter(output_path)
        writer.write(
            img_file,
            gmp_groups,
            tile_processor=tile_processor,
            source_crs=source_crs,
            jpeg_quality=quality,
            progress_callback=progress_callback,
            sequential_only=tile_processor_override is not None,
        )

        output_files = [output_path]

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
        self,
        layer_config: LayerConfig,
        attribution: str,
        has_tiles: list[bool] | None = None,
    ) -> IMGFile:
        """Build the IMGFile data structure from configuration.

        Args:
            layer_config: Layer configuration with zoom levels and bounds.
            attribution: Map attribution string.
            has_tiles: Optional per-zoom-level tile presence (same order as
                sorted zoom levels). If None, all levels assumed to have tiles.
        """
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

        # Build zoom levels with dynamically computed codes.
        # Level numbers are remapped to 24-N+1..24 (where N = number of levels)
        # so the most detailed level has level_number=24 (shift=0, zero
        # quantization error in boundingRect). GPXSee uses level_number for
        # zoom selection and coordinate precision, NOT for rendering (tiles
        # are rendered at absolute 32-bit geographic bounds).
        # Example: 12 levels → level_numbers 13-24, 5 levels → 20-24.
        sorted_zooms = sorted(layer_config.zoom_levels)
        n_zoom = len(sorted_zooms)
        zoom_code_map = dict(_compute_zoom_codes(sorted_zooms, has_tiles))
        zoom_levels = []
        for z_idx, zl in enumerate(sorted_zooms):
            remapped_level = 24 - (n_zoom - 1 - z_idx)
            logger.info(
                "Zoom %d → level_number=%d (shift=%d, zoom_code=0x%02X)",
                zl,
                remapped_level,
                max(0, 24 - remapped_level),
                zoom_code_map[zl],
            )
            zoom_levels.append(
                ZoomLevel(
                    level_number=remapped_level,
                    zoom_code=zoom_code_map[zl],
                    source_zoom=zl,
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
        # Use actual zoom levels (keys of compressed_tiles), NOT remapped level_numbers.
        # compressed_tiles is keyed by source zoom level, while zoom_levels may have
        # remapped level_numbers for Garmin coordinate encoding.
        sorted_zooms = sorted(compressed_tiles.keys())
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
                    z
                    for z in img_file.zoom_levels
                    if (z.source_zoom or z.level_number) in zooms
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
                    if (z.source_zoom or z.level_number) in list(current_zooms) + [zoom]
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
