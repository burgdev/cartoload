#!/usr/bin/env python3
"""
Validation script for Garmin IMG data model.

Parses GMT (GMapTool) verbose output and populates the IMGFile data model
to verify that all fields from the format specification are captured correctly.
"""

import re
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cartoload.exporters.garmin_img_model import (
    IMGFile,
    IMGHeader,
    SubfileHeader,
    SubfileType,
    ZoomLevel,
    DrawOrderEntry,
)


def parse_gmt_output(gmt_output_path: Path) -> IMGFile:
    """
    Parse GMT verbose output (-i -v) into IMGFile data model.

    Args:
        gmt_output_path: Path to GMT output text file

    Returns:
        Populated IMGFile instance
    """
    with open(gmt_output_path, "r", encoding="utf-8") as f:
        content = f.read()

    img = IMGFile(header=IMGHeader())

    # Parse file-level metadata
    # File: /path/to/file.img, length 1495072768
    file_match = re.search(r"File:\s+(.+?),\s+length\s+(\d+)", content)
    if file_match:
        file_size = int(file_match.group(2))
        print(f"  File size: {file_size:,} bytes")

    # Parse header date
    # Header: 16.04.2022 15:03:56, DSKIMG, XOR 00, V 0.00, Ms 0
    header_match = re.search(
        r"Header:\s+(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2}):(\d{2}),\s+"
        r"(\w+),\s+XOR\s+(\w+),\s+V\s+([\d.]+)",
        content,
    )
    if header_match:
        day, month, year = (
            int(header_match.group(1)),
            int(header_match.group(2)),
            int(header_match.group(3)),
        )
        hour, minute, second = (
            int(header_match.group(4)),
            int(header_match.group(5)),
            int(header_match.group(6)),
        )
        img.header.creation_date = datetime(year, month, day, hour, minute, second)
        img.header.magic = header_match.group(7)  # Should be "DSKIMG"
        xor_value = header_match.group(8)
        img.header.xor_byte = int(xor_value, 16) if xor_value != "00" else 0
        print(f"  Header date: {img.header.creation_date}")
        print(f"  Magic: {img.header.magic}")
        print(f"  XOR: {img.header.xor_byte:#04x}")

    # Parse mapset name
    # Mapset: Svizzera_W Raster Map
    mapset_match = re.search(r"Mapset:\s+(.+)", content)
    if mapset_match:
        img.header.map_name = mapset_match.group(1).strip()
        print(f"  Map name: {img.header.map_name}")

    # Parse FAT configuration
    # fat: 1000h - 1200h - 20000h, block 32768
    fat_match = re.search(
        r"fat:\s+([0-9a-fA-F]+)h\s+-\s+([0-9a-fA-F]+)h\s+-\s+([0-9a-fA-F]+)h,\s+block\s+(\d+)",
        content,
    )
    if fat_match:
        img.header.fat_start_offset = int(fat_match.group(1), 16)
        img.header.fat_directory_offset = int(fat_match.group(2), 16)
        img.header.fat_size = int(fat_match.group(3), 16)
        img.header.block_size = int(fat_match.group(4))
        print(f"  FAT start: {img.header.fat_start_offset:#06x}")
        print(f"  FAT directory: {img.header.fat_directory_offset:#06x}")
        print(f"  FAT size: {img.header.fat_size:#06x} ({img.header.fat_size:,} bytes)")
        print(f"  Block size: {img.header.block_size:,} bytes")

    # Parse subfile count
    # maps: 2, sub-files 2
    subfile_count_match = re.search(r"sub-files\s+(\d+)", content)
    if subfile_count_match:
        subfile_count = int(subfile_count_match.group(1))
        print(f"  Subfile count: {subfile_count}")

    # Parse subfiles
    # Sub-file         fat     length
    #  09C102B0 GMP   1200h 1494878658
    #  MAPSOURC MPS  19000h        98
    subfile_pattern = re.compile(
        r"^\s+([0-9A-F]{8}|MAPSOURC)\s+(\w{3})\s+([0-9a-fA-F]+)h\s+(\d+)", re.MULTILINE
    )
    for match in subfile_pattern.finditer(content):
        name = match.group(1)
        type_str = match.group(2)
        start_offset = int(match.group(3), 16)
        length = int(match.group(4))

        try:
            subfile_type = SubfileType[type_str]
        except KeyError:
            print(f"  Warning: Unknown subfile type '{type_str}', skipping")
            continue

        subfile = SubfileHeader(
            subfile_type=subfile_type,
            name=name,
            start_block_offset=start_offset,
            length=length,
        )
        img.subfiles.append(subfile)
        print(
            f"  Subfile: {name} ({type_str}) at {start_offset:#06x}, {length:,} bytes"
        )

    # Parse GMP-specific data (for the main raster subfile)
    # map 9c102b0 (163644080)
    # date 16.04.2022 16:59:25
    # priority 24, parameters 1 4 36 1
    # levels [20,21,22,23,24], zoom [84,83,2,1,0]
    # N: 47.652683, S: 45.816593, W: 5.873523, E: 8.403554
    # Raster Map
    # Copyright 1995-2022 by GARMIN Corporation.
    # CP 1252, Western European
    # Bitmaps 32443, size 1490182836 (4)

    # Map ID
    map_id_match = re.search(r"map\s+([0-9a-fA-F]+)\s+\((\d+)\)", content)
    if map_id_match:
        img.map_id = int(map_id_match.group(1), 16)
        print(f"  Map ID: {img.map_id:#010x} ({img.map_id})")

    # GMP creation date
    gmp_date_match = re.search(
        r"date\s+(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2}):(\d{2})", content
    )
    if gmp_date_match:
        day, month, year = (
            int(gmp_date_match.group(1)),
            int(gmp_date_match.group(2)),
            int(gmp_date_match.group(3)),
        )
        hour, minute, second = (
            int(gmp_date_match.group(4)),
            int(gmp_date_match.group(5)),
            int(gmp_date_match.group(6)),
        )
        img.gmp_creation_date = datetime(year, month, day, hour, minute, second)
        print(f"  GMP creation date: {img.gmp_creation_date}")

    # Priority (draw order)
    priority_match = re.search(r"priority\s+(\d+),\s+parameters\s+([\d\s]+)", content)
    if priority_match:
        priority = int(priority_match.group(1))
        params = [int(x) for x in priority_match.group(2).split()]
        img.draw_order = DrawOrderEntry(
            priority=priority,
            param1=params[0] if len(params) > 0 else 1,
            param2=params[1] if len(params) > 1 else 4,
            param3=params[2] if len(params) > 2 else 36,
            param4=params[3] if len(params) > 3 else 1,
        )
        print(f"  Draw order priority: {priority}")
        print(f"  Parameters: {params}")

    # Zoom levels
    levels_match = re.search(r"levels\s+\[([0-9,]+)\],\s+zoom\s+\[([0-9,]+)\]", content)
    if levels_match:
        level_numbers = [int(x) for x in levels_match.group(1).split(",")]
        zoom_codes = [int(x) for x in levels_match.group(2).split(",")]

        for level_num, zoom_code in zip(level_numbers, zoom_codes):
            zoom = ZoomLevel(level_number=level_num, zoom_code=zoom_code)
            img.zoom_levels.append(zoom)
        print(f"  Zoom levels: {level_numbers}")
        print(f"  Zoom codes: {zoom_codes}")

    # Bounds
    bounds_match = re.search(
        r"N:\s+([-\d.]+),\s+S:\s+([-\d.]+),\s+W:\s+([-\d.]+),\s+E:\s+([-\d.]+)", content
    )
    if bounds_match:
        img.bounds_north = float(bounds_match.group(1))
        img.bounds_south = float(bounds_match.group(2))
        img.bounds_west = float(bounds_match.group(3))
        img.bounds_east = float(bounds_match.group(4))
        print(
            f"  Bounds: N={img.bounds_north}, S={img.bounds_south}, W={img.bounds_west}, E={img.bounds_east}"
        )

    # Description
    desc_match = re.search(r"^\s+(Raster Map|Vector Map)\s*$", content, re.MULTILINE)
    if desc_match:
        img.description = desc_match.group(1)
        print(f"  Description: {img.description}")

    # Copyright
    copyright_match = re.search(r"Copyright\s+(.+)", content)
    if copyright_match:
        img.copyright_string = copyright_match.group(0).strip()
        print(f"  Copyright: {img.copyright_string}")

    # Character encoding
    encoding_match = re.search(r"CP\s+(\d+),\s+(.+)", content)
    if encoding_match:
        img.character_encoding = f"CP-{encoding_match.group(1)}"
        print(f"  Encoding: {img.character_encoding}")

    # Bitmap count
    bitmap_match = re.search(r"Bitmaps\s+(\d+),\s+size\s+(\d+)\s+\((\d+)\)", content)
    if bitmap_match:
        bitmap_count = int(bitmap_match.group(1))
        bitmap_size = int(bitmap_match.group(2))
        compression_type = int(bitmap_match.group(3))
        print(f"  Tile count: {bitmap_count:,}")
        print(f"  Total bitmap size: {bitmap_size:,} bytes")
        print(f"  Compression type: {compression_type} (likely JPEG)")

    return img


def validate_data_model(img: IMGFile, expected_name: str) -> list[str]:
    """
    Validate that the parsed IMGFile contains all expected fields.

    Args:
        img: Parsed IMGFile instance
        expected_name: Expected map name substring

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check header fields
    if img.header.magic != "DSKIMG":
        errors.append(f"Invalid magic bytes: {img.header.magic}")

    if img.header.block_size != 32768:
        errors.append(f"Unexpected block size: {img.header.block_size}")

    if img.header.fat_start_offset != 0x1000:
        errors.append(f"Unexpected FAT start: {img.header.fat_start_offset:#06x}")

    if img.header.fat_directory_offset != 0x1200:
        errors.append(
            f"Unexpected FAT directory: {img.header.fat_directory_offset:#06x}"
        )

    if expected_name not in img.header.map_name:
        errors.append(
            f"Map name '{img.header.map_name}' doesn't contain '{expected_name}'"
        )

    # Check subfiles
    if len(img.subfiles) == 0:
        errors.append("No subfiles found")

    has_gmp = any(s.subfile_type == SubfileType.GMP for s in img.subfiles)
    if not has_gmp:
        errors.append("Missing required GMP subfile")

    # Check zoom levels
    if len(img.zoom_levels) == 0:
        errors.append("No zoom levels found")

    expected_levels = [20, 21, 22, 23, 24]
    actual_levels = [z.level_number for z in img.zoom_levels]
    if actual_levels != expected_levels:
        errors.append(
            f"Zoom levels mismatch: expected {expected_levels}, got {actual_levels}"
        )

    # Check bounds
    if img.bounds_north <= img.bounds_south:
        errors.append(f"Invalid bounds: N={img.bounds_north} <= S={img.bounds_south}")

    if img.bounds_east <= img.bounds_west:
        errors.append(f"Invalid bounds: E={img.bounds_east} <= W={img.bounds_west}")

    # Check draw order
    if img.draw_order.priority != 24:
        errors.append(f"Unexpected priority: {img.draw_order.priority}")

    return errors


def main():
    """Main validation script."""
    test_data_dir = Path(__file__).parent / "data" / "garmin_samples"

    print("=" * 80)
    print("Garmin IMG Data Model Validation")
    print("=" * 80)
    print()

    # Validate SwissTopo West
    print("Parsing SwissTopo West (my_SwissTopo_West.img)...")
    west_file = test_data_dir / "SwissTopo_West_gmt_output.txt"
    if not west_file.exists():
        print(f"ERROR: {west_file} not found")
        return 1

    img_west = parse_gmt_output(west_file)
    print()

    print("Validating SwissTopo West data model...")
    errors_west = validate_data_model(img_west, "Svizzera_W")
    if errors_west:
        print("  VALIDATION FAILED:")
        for error in errors_west:
            print(f"    - {error}")
    else:
        print("  ✓ VALIDATION PASSED")
    print()

    # Validate SwissTopo Est
    print("Parsing SwissTopo Est (my_SwissTopo_Est.img)...")
    est_file = test_data_dir / "SwissTopo_Est_gmt_output.txt"
    if not est_file.exists():
        print(f"ERROR: {est_file} not found")
        return 1

    img_est = parse_gmt_output(est_file)
    print()

    print("Validating SwissTopo Est data model...")
    errors_est = validate_data_model(img_est, "Svizzera_E")
    if errors_est:
        print("  VALIDATION FAILED:")
        for error in errors_est:
            print(f"    - {error}")
    else:
        print("  ✓ VALIDATION PASSED")
    print()

    # Summary
    print("=" * 80)
    print("Summary:")
    print(
        f"  SwissTopo West: {'PASS' if not errors_west else 'FAIL'} ({len(errors_west)} errors)"
    )
    print(
        f"  SwissTopo Est:  {'PASS' if not errors_est else 'FAIL'} ({len(errors_est)} errors)"
    )
    print("=" * 80)

    return 0 if not (errors_west or errors_est) else 1


if __name__ == "__main__":
    sys.exit(main())
