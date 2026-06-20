"""Export Garmin IMG raster tiles to GeoTIFF format."""

import io
import struct
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image


def map_units_to_degrees_32(map_units: int) -> float:
    """Convert Garmin 32-bit map units to decimal degrees."""
    return map_units * 180.0 / (2**31)


def export_img_to_geotiff(
    img_path: Path,
    output_path: Path,
    bbox: Optional[tuple[float, float, float, float]] = None,
    zoom_filter: Optional[int | tuple[int, int]] = None,
    max_tiles: int = 10,
) -> dict:
    """Export IMG raster tiles to GeoTIFF.

    Args:
        img_path: Path to input IMG file
        output_path: Path to output GeoTIFF
        bbox: Optional (west, south, east, north) bounding box filter
        zoom_filter: Optional zoom level or (min, max) zoom range
        max_tiles: Maximum number of tiles to export (for testing)

    Returns:
        Statistics dict with tiles_processed, bounds, etc.
    """
    # Read raw IMG file data
    with open(img_path, "rb") as f:
        img_file_data = f.read()

    # Find GMP offset in file
    gmp_offset = _find_gmp_offset(img_file_data)
    if gmp_offset is None:
        raise ValueError("Could not locate GMP subfile in IMG")

    # Find LBL header to get section positions
    lbl_offset = img_file_data.find(b"GARMIN LBL", gmp_offset)
    if lbl_offset < 0:
        raise ValueError("Could not find LBL header")

    # Read LBL28 and LBL29 descriptors from LBL header
    # Note: lbl_offset points to "GARMIN LBL" string, actual header starts 2 bytes earlier
    lbl_start = lbl_offset - 2

    # Try standard format (0x184/0x192) — same as GPXSee's lblfile.cpp
    # GPXSee reads at _gmpOffset + 0x184: offset(4) + size(4) + recordSize(2) + flags(4)
    # then at +0x192: img_offset(4) + img_size(4)
    lbl28_pos = struct.unpack(
        "<I", img_file_data[lbl_start + 0x184 : lbl_start + 0x188]
    )[0]
    lbl28_size = struct.unpack(
        "<I", img_file_data[lbl_start + 0x188 : lbl_start + 0x18C]
    )[0]
    lbl29_pos = struct.unpack(
        "<I", img_file_data[lbl_start + 0x192 : lbl_start + 0x196]
    )[0]
    lbl29_size = struct.unpack(
        "<I", img_file_data[lbl_start + 0x196 : lbl_start + 0x19A]
    )[0]

    # If positions are 0 or unreasonable, try older format (0x108/0x116)
    if lbl28_pos == 0 or lbl28_pos > 10_000_000:
        lbl28_pos = struct.unpack(
            "<I", img_file_data[lbl_start + 0x108 : lbl_start + 0x10C]
        )[0]
        lbl28_size = struct.unpack(
            "<I", img_file_data[lbl_start + 0x10C : lbl_start + 0x110]
        )[0]
        lbl29_pos = struct.unpack(
            "<I", img_file_data[lbl_start + 0x116 : lbl_start + 0x11A]
        )[0]
        lbl29_size = struct.unpack(
            "<I", img_file_data[lbl_start + 0x11A : lbl_start + 0x11E]
        )[0]

    # Find RGN header
    rgn_offset = img_file_data.find(b"GARMIN RGN", gmp_offset)
    if rgn_offset < 0:
        raise ValueError("Could not find RGN header")

    # Read RGN2 descriptor from RGN header at offset 0x1D
    # Note: rgn_offset points to "GARMIN RGN" string, actual header starts 2 bytes earlier
    rgn2_pos = struct.unpack(
        "<I", img_file_data[rgn_offset - 2 + 0x1D : rgn_offset - 2 + 0x21]
    )[0]
    rgn2_size = struct.unpack(
        "<I", img_file_data[rgn_offset - 2 + 0x21 : rgn_offset - 2 + 0x25]
    )[0]

    if lbl28_size == 0 or lbl29_size == 0 or rgn2_size == 0:
        raise ValueError("LBL28, LBL29, or RGN2 sections are empty")

    # Extract tile data
    tiles = _extract_tiles(
        img_file_data,
        gmp_offset,
        {"pos": lbl28_pos, "size": lbl28_size},
        {"pos": lbl29_pos, "size": lbl29_size},
        {"pos": rgn2_pos, "size": rgn2_size},
        bbox=bbox,
        zoom_filter=zoom_filter,
        max_tiles=max_tiles,
    )

    if not tiles:
        return {
            "tiles_processed": 0,
            "tiles_exported": 0,
            "message": "No tiles found matching filters",
        }

    # Create GeoTIFF mosaic
    _create_geotiff(tiles, output_path)

    # Compute statistics
    bounds = _compute_bounds(tiles)
    return {
        "tiles_processed": len(tiles),
        "tiles_exported": len(tiles),
        "bounds": bounds,
        "output_path": str(output_path),
    }


def _find_gmp_offset(img_data: bytes) -> Optional[int]:
    """Find GMP subfile offset in IMG file."""
    gmp_sig = b"GARMIN GMP"
    idx = img_data.find(gmp_sig)
    if idx >= 0:
        # GMP header starts before the signature
        return idx - 2
    return None


def _extract_tiles(
    img_data: bytes,
    gmp_offset: int,
    lbl28_info: dict,
    lbl29_info: dict,
    rgn2_info: dict,
    bbox: Optional[tuple[float, float, float, float]] = None,
    zoom_filter: Optional[int | tuple[int, int]] = None,
    max_tiles: int = 10,
) -> list[dict]:
    """Extract tiles from IMG file.

    Returns list of dicts with: jpeg_data, lat_min, lon_min, lat_max, lon_max
    """
    tiles = []

    # Read LBL28 offset table
    lbl28_pos = gmp_offset + lbl28_info.get("pos", 0)
    lbl28_size = lbl28_info.get("size", 0)

    if lbl28_size == 0:
        return []

    num_entries = lbl28_size // 4  # uint32 entries
    lbl28_data = img_data[lbl28_pos : lbl28_pos + lbl28_size]

    # Read LBL29 JPEG data
    lbl29_pos = gmp_offset + lbl29_info.get("pos", 0)
    lbl29_size = lbl29_info.get("size", 0)
    lbl29_data = img_data[lbl29_pos : lbl29_pos + lbl29_size]

    # Read RGN2 raster records
    rgn2_pos = gmp_offset + rgn2_info.get("pos", 0)
    rgn2_size = rgn2_info.get("size", 0)
    rgn2_data = img_data[rgn2_pos : rgn2_pos + rgn2_size]

    # RGN2 records are 42 bytes each
    RGN2_RECORD_SIZE = 42
    num_rgn2_records = rgn2_size // RGN2_RECORD_SIZE

    # Process tiles
    for i in range(min(num_rgn2_records, num_entries, max_tiles)):
        try:
            # Get JPEG offset from LBL28
            jpeg_offset = struct.unpack("<I", lbl28_data[i * 4 : i * 4 + 4])[0]

            # Get next offset for size calculation
            if i + 1 < num_entries:
                next_offset = struct.unpack(
                    "<I", lbl28_data[(i + 1) * 4 : (i + 1) * 4 + 4]
                )[0]
            else:
                next_offset = lbl29_size

            jpeg_size = next_offset - jpeg_offset

            # Extract JPEG data
            jpeg_data = lbl29_data[jpeg_offset : jpeg_offset + jpeg_size]

            # Parse RGN2 record to get coordinates
            rgn2_record = rgn2_data[i * RGN2_RECORD_SIZE : (i + 1) * RGN2_RECORD_SIZE]

            # E0 record coordinates are at bytes 22-37:
            # top(4), right(4), bottom(4), left(4)
            top = struct.unpack("<i", rgn2_record[22:26])[0]
            right = struct.unpack("<i", rgn2_record[26:30])[0]
            bottom = struct.unpack("<i", rgn2_record[30:34])[0]
            left = struct.unpack("<i", rgn2_record[34:38])[0]

            # Convert to degrees
            lat_max = map_units_to_degrees_32(top)
            lon_max = map_units_to_degrees_32(right)
            lat_min = map_units_to_degrees_32(bottom)
            lon_min = map_units_to_degrees_32(left)

            # Apply bbox filter
            if bbox:
                west, south, east, north = bbox
                if (
                    lon_max < west
                    or lon_min > east
                    or lat_max < south
                    or lat_min > north
                ):
                    continue

            tiles.append(
                {
                    "jpeg_data": jpeg_data,
                    "lat_min": lat_min,
                    "lon_min": lon_min,
                    "lat_max": lat_max,
                    "lon_max": lon_max,
                    "tile_index": i,
                }
            )

        except Exception as e:
            print(f"Warning: Failed to process tile {i}: {e}")
            continue

    return tiles


def _create_geotiff(tiles: list[dict], output_path: Path) -> None:
    """Create GeoTIFF mosaic from tiles."""
    try:
        import rasterio
        from rasterio.transform import from_bounds
    except ImportError:
        raise ImportError(
            "rasterio is required for GeoTIFF export. Install with: uv add rasterio"
        )

    # Compute overall bounds
    bounds = _compute_bounds(tiles)

    # Decode all JPEGs to get dimensions
    tile_images = []
    max_height = 0
    max_width = 0
    for tile in tiles:
        try:
            img = Image.open(io.BytesIO(tile["jpeg_data"]))
            img_array = np.array(img)
            tile_images.append((tile, img_array))
            max_height = max(max_height, img_array.shape[0])
            max_width = max(max_width, img_array.shape[1])
        except Exception as e:
            print(f"Warning: Failed to decode JPEG for tile {tile['tile_index']}: {e}")
            continue

    if not tile_images:
        raise ValueError("No valid JPEG tiles found")

    # Compute output dimensions: fit tiles in a grid
    tiles_per_row = min(4, len(tile_images))
    tiles_per_col = (len(tile_images) + tiles_per_row - 1) // tiles_per_row
    width = tiles_per_row * max_width
    height = tiles_per_col * max_height

    # Create output array (RGB)
    output = np.zeros((height, width, 3), dtype=np.uint8)

    # Place tiles in grid
    for idx, (tile, img_array) in enumerate(tile_images):
        row = idx // tiles_per_row
        col = idx % tiles_per_row
        y = row * max_height
        x = col * max_width

        # Handle variable tile sizes - just place at top-left corner of cell
        tile_h, tile_w = img_array.shape[:2]
        if y + tile_h <= height and x + tile_w <= width:
            output[y : y + tile_h, x : x + tile_w] = img_array[:, :, :3]

    # Create geotransform
    transform = from_bounds(
        bounds["west"], bounds["south"], bounds["east"], bounds["north"], width, height
    )

    # Write GeoTIFF
    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=3,
        dtype=output.dtype,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        for i in range(3):
            dst.write(output[:, :, i], i + 1)


def _compute_bounds(tiles: list[dict]) -> dict:
    """Compute overall bounds from tiles."""
    if not tiles:
        return {"west": 0, "south": 0, "east": 0, "north": 0}

    west = min(t["lon_min"] for t in tiles)
    south = min(t["lat_min"] for t in tiles)
    east = max(t["lon_max"] for t in tiles)
    north = max(t["lat_max"] for t in tiles)

    return {"west": west, "south": south, "east": east, "north": north}
