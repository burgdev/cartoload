#!/usr/bin/env python3
"""
Polyline Preamble Record Structure Decoder for SwissTopo RGN2 Data.

Analyzes the binary structure of type 0x06 polyline records in the RGN2
section of SwissTopo IMG files. These records appear before each Type E0
raster tile record and describe the tile's geographic extent.

The key question: what is the exact byte layout of the 0x06 preamble,
and how do its fields relate to the tile bounds and subdivision center?

Usage:
    python scripts/polyline_preamble_analysis.py
"""

import struct
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.img_analysis import IMGParser

IMG_PATH = "/home/tobias/kdrive/garmin/my_SwissTopo_West.img"


def deg_to_garmin_32(deg):
    """Convert degrees to Garmin 32-bit map units (degrees * 2^31 / 180)."""
    return int(deg * (2**31) / 180)


def deg_to_map_units_24(deg):
    """Convert degrees to Garmin 24-bit map units (degrees * 2^24 / 360)."""
    return int(deg * (2**24) / 360)


def garmin_32_to_deg(val):
    """Convert Garmin 32-bit map units to degrees."""
    return val * 180.0 / (2**31)


def map_units_24_to_deg(val):
    """Convert Garmin 24-bit map units to degrees."""
    return val * 360.0 / (2**24)


def analyze_polyline_structure():
    """Main analysis function."""

    print("=" * 80)
    print("SwissTopo Polyline Preamble Analysis")
    print("=" * 80)

    with IMGParser(IMG_PATH) as img:
        img.parse_header()
        img.parse_fat()

        # Find GMP subfile
        gmp_key = None
        for key in img.subfiles:
            if img.subfiles[key]["type"] == "GMP":
                gmp_key = key
                break

        gmp = img.parse_gmp_container(gmp_key)
        data = gmp["data"]

        tre = img.parse_tre(gmp)
        rgn = img.parse_rgn(gmp)

        # =========================================================================
        # STEP 1: Get TRE map levels (TRE1) - zoom levels and their settings
        # =========================================================================
        print("\n" + "=" * 80)
        print("STEP 1: TRE1 Map Levels")
        print("=" * 80)

        levels = tre.get("levels", [])
        for i, lvl in enumerate(levels):
            print(
                f"  Level {i}: level_number={lvl['level_number']}, zoom_code={lvl['zoom_code']}, "
                f"subdiv_count={lvl['subdivision_count']}"
            )

        # =========================================================================
        # STEP 2: Get TRE2 subdivision groups
        # =========================================================================
        print("\n" + "=" * 80)
        print("STEP 2: TRE2 Subdivision Groups (16-byte records)")
        print("=" * 80)

        groups = tre.get("groups_16byte", [])
        print(f"  Total groups: {len(groups)}")

        # The first few groups belong to the root zoom levels
        # Level 0 has 1 group, level 1 has 3 groups, etc.
        # Show the first few groups with their details
        for i, g in enumerate(groups[:10]):
            print(f"\n  Group [{i}]:")
            print(f"    rgn_offset={g['rgn_offset']}")
            print(f"    obj_types={g['obj_types']}")
            print(f"    lon_center={g['lon_center']} ({g['lon_center_deg']:.6f} deg)")
            print(f"    lat_center={g['lat_center']} ({g['lat_center_deg']:.6f} deg)")
            print(f"    flags=0x{g['flags']:04X}")
            print(f"    subdiv_count={g['subdiv_count']}")
            print(f"    next_level_index={g['next_level_index']}")
            print(f"    raw_hex={g['raw_hex']}")

        # =========================================================================
        # STEP 3: Read TRE7 entries to find RGN2 offsets per zoom level
        # =========================================================================
        print("\n" + "=" * 80)
        print("STEP 3: TRE7 Raster Layer Offsets")
        print("=" * 80)

        tre7_offsets = tre.get("tre7_offsets", [])
        print(f"  Total TRE7 entries: {len(tre7_offsets)}")

        # Show first 30 entries
        for i, entry in enumerate(tre7_offsets[:30]):
            print(
                f"  [{i:3d}] offset={entry['offset']:10d} flag={entry.get('flag', 'N/A')}"
            )

        # =========================================================================
        # STEP 4: Extract raw RGN2 data and find polyline records
        # =========================================================================
        print("\n" + "=" * 80)
        print("STEP 4: RGN2 Raw Data Analysis")
        print("=" * 80)

        rgn2_pos = rgn["rgn2"]["position"]
        rgn2_size = rgn["rgn2"]["size"]
        rgn2_data = data[rgn2_pos : rgn2_pos + rgn2_size]

        print(f"  RGN2 position (GMP-relative): {rgn2_pos}")
        print(f"  RGN2 size: {rgn2_size}")

        # The first polyline starts at offset 0 in RGN2
        # From the hex: 06 b3 9c f1 f5 09 11 56 f2 08 00 80 1c 17 00 53 00 00
        # Then E0 tile: e0 2d 00 00 00 d4 e7 20 00 7c 2f 04 00 44 e6 20 00 40 2d 04 45 52 00 00

        # Let's find all 0x06 markers and the next E0 marker after each
        pos = 0

        # First, let's look at the raw bytes to understand the pattern
        print("\n  First 100 bytes of RGN2 (raw hex):")
        for row in range(7):
            offset = row * 16
            hex_bytes = " ".join(f"{b:02x}" for b in rgn2_data[offset : offset + 16])
            print(f"    {offset:04x}: {hex_bytes}")

        # Find pattern: look for 0x06 followed by a byte, then after some data, 0xE0
        # The key insight: each E0 record is exactly 24 bytes (0x2D = 2-byte index)
        # So we need to figure out what comes between 0x06 records and E0 records

        # Let's try to parse manually based on the known structure:
        # 06 B3 [preamble data] E0 [E0 data] 06 B3 [preamble data] E0 [E0 data] ...

        print("\n" + "=" * 80)
        print("STEP 5: Manual Polyline Record Parsing")
        print("=" * 80)

        # Parse first few records manually
        pos = 0
        record_num = 0
        polyline_records = []

        while pos < min(len(rgn2_data), 500) and record_num < 10:
            marker = rgn2_data[pos]

            if marker == 0x06:
                # Polyline record
                sub_type = rgn2_data[pos + 1]
                print(f"\n  Record #{record_num} at RGN2 offset {pos}:")
                print(f"    Marker: 0x{marker:02X}")
                print(f"    Sub-type: 0x{sub_type:02X}")

                # We know from the user's data that the polyline has 16 bytes of data
                # after the type+subtype, making it 18 bytes total (06 + B3 + 16 bytes)
                # But let's try different sizes and see which one lands us on E0

                for preamble_size in [4, 6, 8, 10, 12, 14, 16, 18, 20, 22]:
                    next_byte_pos = pos + 2 + preamble_size
                    if next_byte_pos < len(rgn2_data):
                        next_byte = rgn2_data[next_byte_pos]
                        if next_byte == 0xE0:
                            print(
                                f"    -> preamble_size={preamble_size} lands on E0 at offset {next_byte_pos}"
                            )

                # Dump the bytes around this record
                chunk = rgn2_data[pos : pos + 50]
                print(f"    Raw hex (50 bytes): {chunk.hex()}")

                # Try the 18-byte interpretation (2 header + 16 data)
                preamble = rgn2_data[pos + 2 : pos + 18]
                print(f"    16-byte preamble: {preamble.hex()}")

                # Try 4x int16 LE
                print(
                    f"      As 4x int16 LE: {[struct.unpack_from('<h', preamble, i)[0] for i in range(0, 8, 2)]}"
                )
                print(
                    f"      As 8x int16 LE: {[struct.unpack_from('<h', preamble, i)[0] for i in range(0, 16, 2)]}"
                )
                print(
                    f"      As 4x int32 LE: {[struct.unpack_from('<i', preamble, i)[0] for i in range(0, 16, 4)]}"
                )
                print(
                    f"      As 2x int32 LE: {[struct.unpack_from('<i', preamble, i)[0] for i in range(0, 8, 4)]}"
                )
                print(
                    f"      As uint16 pairs: {[(struct.unpack_from('<H', preamble, i)[0], struct.unpack_from('<H', preamble, i + 2)[0]) for i in range(0, 16, 4)]}"
                )

                # Now look at what follows - should be E0 record
                e0_pos = pos + 18
                if e0_pos < len(rgn2_data) and rgn2_data[e0_pos] == 0xE0:
                    print(f"    E0 record at offset {e0_pos}:")
                    e0_bits = rgn2_data[e0_pos + 1]
                    print(f"      bits_field: 0x{e0_bits:02X}")

                    if e0_bits == 0x2D:
                        idx_size = 2
                        img_idx = struct.unpack_from("<H", rgn2_data, e0_pos + 2)[0]
                    elif e0_bits == 0x2B:
                        idx_size = 1
                        img_idx = rgn2_data[e0_pos + 2]
                    else:
                        idx_size = 2
                        img_idx = struct.unpack_from("<H", rgn2_data, e0_pos + 2)[0]

                    coord_off = e0_pos + 2 + idx_size
                    lat_min = struct.unpack_from("<i", rgn2_data, coord_off)[0]
                    lon_min = struct.unpack_from("<i", rgn2_data, coord_off + 4)[0]
                    lat_max = struct.unpack_from("<i", rgn2_data, coord_off + 8)[0]
                    lon_max = struct.unpack_from("<i", rgn2_data, coord_off + 12)[0]
                    block_size = struct.unpack_from("<I", rgn2_data, coord_off + 16)[0]

                    print(f"      image_index: {img_idx}")
                    print(f"      lat_min: {lat_min} ({garmin_32_to_deg(lat_min):.6f})")
                    print(f"      lon_min: {lon_min} ({garmin_32_to_deg(lon_min):.6f})")
                    print(f"      lat_max: {lat_max} ({garmin_32_to_deg(lat_max):.6f})")
                    print(f"      lon_max: {lon_max} ({garmin_32_to_deg(lon_max):.6f})")
                    print(f"      block_size: {block_size}")

                    # Store for comparison
                    polyline_records.append(
                        {
                            "pos": pos,
                            "preamble": preamble,
                            "e0_lat_min": lat_min,
                            "e0_lon_min": lon_min,
                            "e0_lat_max": lat_max,
                            "e0_lon_max": lon_max,
                            "e0_block_size": block_size,
                            "e0_img_idx": img_idx,
                        }
                    )

                    # Move past E0 record
                    e0_total = 2 + idx_size + 16 + 4
                    pos = e0_pos + e0_total
                    record_num += 1
                    continue
                else:
                    print(
                        f"    WARNING: Expected E0 at offset {e0_pos}, found 0x{rgn2_data[e0_pos]:02X}"
                    )
                    # Try other sizes
                    for test_size in range(2, 30):
                        test_pos = pos + test_size
                        if test_pos < len(rgn2_data) and rgn2_data[test_pos] == 0xE0:
                            print(
                                f"    E0 found at offset {test_pos} (total preamble = {test_size} bytes from 06 marker)"
                            )
                            break
                    pos += 1
                    record_num += 1
                    continue

            elif marker == 0xE0:
                # Standalone E0 record (no polyline preamble?)
                print(f"\n  Standalone E0 at offset {pos}")
                pos += 1
                record_num += 1
            else:
                pos += 1

        # =========================================================================
        # STEP 6: Analyze the preamble field meanings
        # =========================================================================
        print("\n" + "=" * 80)
        print("STEP 6: Preamble Field Analysis")
        print("=" * 80)

        if polyline_records:
            rec = polyline_records[0]
            preamble = rec["preamble"]

            print("\n  First polyline preamble hex: " + preamble.hex())
            print("  Corresponding E0 tile bounds:")
            print(f"    lat_min={garmin_32_to_deg(rec['e0_lat_min']):.6f}")
            print(f"    lon_min={garmin_32_to_deg(rec['e0_lon_min']):.6f}")
            print(f"    lat_max={garmin_32_to_deg(rec['e0_lat_max']):.6f}")
            print(f"    lon_max={garmin_32_to_deg(rec['e0_lon_max']):.6f}")

            # Get the subdivision center for this zoom level
            # The first TRE2 group is for zoom level 20 (root level)
            # Its center is at lon=7.138367, lat=46.734810
            group0 = groups[0]
            center_lon_24 = group0["lon_center"]
            center_lat_24 = group0["lat_center"]
            center_lon_deg = group0["lon_center_deg"]
            center_lat_deg = group0["lat_center_deg"]

            # Convert to 32-bit map units for comparison
            center_lon_32 = deg_to_garmin_32(center_lon_deg)
            center_lat_32 = deg_to_garmin_32(center_lat_deg)

            print("\n  Subdivision center (group 0):")
            print(
                f"    lon={center_lon_24} ({center_lon_deg:.6f} deg, 32-bit: {center_lon_32})"
            )
            print(
                f"    lat={center_lat_24} ({center_lat_deg:.6f} deg, 32-bit: {center_lat_32})"
            )

            # Try various interpretations of the preamble as deltas from center
            print("\n  --- Testing preamble as delta coordinates ---")

            # Interpretation 1: 4 × int16 LE signed deltas (lat_min, lon_min, lat_max, lon_max)
            d1, d2, d3, d4 = struct.unpack_from("<hhhh", preamble, 0)
            print("\n  Interpretation 1: 4 × int16 LE (first 8 bytes)")
            print(f"    Values: {d1}, {d2}, {d3}, {d4}")
            print(f"    As 24-bit map unit deltas: {d1}, {d2}, {d3}, {d4}")
            result_lat_min = center_lat_24 + d1
            result_lon_min = center_lon_24 + d2
            result_lat_max = center_lat_24 + d3
            result_lon_max = center_lon_24 + d4
            print(
                f"    Center + deltas: lat_min={map_units_24_to_deg(result_lat_min):.6f}, "
                f"lon_min={map_units_24_to_deg(result_lon_min):.6f}, "
                f"lat_max={map_units_24_to_deg(result_lat_max):.6f}, "
                f"lon_max={map_units_24_to_deg(result_lon_max):.6f}"
            )
            print(
                f"    Expected:        lat_min={garmin_32_to_deg(rec['e0_lat_min']):.6f}, "
                f"lon_min={garmin_32_to_deg(rec['e0_lon_min']):.6f}, "
                f"lat_max={garmin_32_to_deg(rec['e0_lat_max']):.6f}, "
                f"lon_max={garmin_32_to_deg(rec['e0_lon_max']):.6f}"
            )

            # Interpretation 2: 8 × int16 LE signed deltas
            vals = struct.unpack_from("<hhhhhhhh", preamble, 0)
            print("\n  Interpretation 2: 8 × int16 LE")
            print(f"    Values: {list(vals)}")

            # Interpretation 3: 4 × int32 LE signed deltas
            v1, v2, v3, v4 = struct.unpack_from("<iiii", preamble, 0)
            print("\n  Interpretation 3: 4 × int32 LE")
            print(f"    Values: {v1}, {v2}, {v3}, {v4}")
            # Try as deltas from center in 32-bit units
            result_lat_min = center_lat_32 + v1
            result_lon_min = center_lon_32 + v2
            result_lat_max = center_lat_32 + v3
            result_lon_max = center_lon_32 + v4
            print(
                f"    Center_32 + deltas: lat={garmin_32_to_deg(result_lat_min):.6f}, "
                f"lon={garmin_32_to_deg(result_lon_min):.6f}, "
                f"lat={garmin_32_to_deg(result_lat_max):.6f}, "
                f"lon={garmin_32_to_deg(result_lon_max):.6f}"
            )

            # Interpretation 4: 2 × int32 LE (first 8 bytes) then more data
            v1, v2 = struct.unpack_from("<ii", preamble, 0)
            print("\n  Interpretation 4: 2 × int32 LE (first 8 bytes)")
            print(f"    Values: {v1}, {v2}")
            print(
                f"    As degrees: {garmin_32_to_deg(v1):.6f}, {garmin_32_to_deg(v2):.6f}"
            )

            # Interpretation 5: uint16 pairs that might be tile grid coordinates
            print("\n  Interpretation 5: uint16 LE pairs")
            for i in range(0, 16, 2):
                val = struct.unpack_from("<H", preamble, i)[0]
                print(f"    Byte {i:2d}-{i + 1:2d}: 0x{val:04X} = {val}")

            # Interpretation 6: Try comparing preamble bytes directly with E0 coords
            print("\n  Interpretation 6: Direct byte comparison with E0 coordinates")
            e0_coords = struct.pack(
                "<iiii",
                rec["e0_lat_min"],
                rec["e0_lon_min"],
                rec["e0_lat_max"],
                rec["e0_lon_max"],
            )
            print(f"    E0 coords hex: {e0_coords.hex()}")
            print(f"    Preamble hex:  {preamble.hex()}")

            # Check if preamble contains delta = E0_coord - center_coord
            print("\n  Interpretation 7: Delta = E0_coord - center_coord (32-bit)")
            delta_lat_min = rec["e0_lat_min"] - center_lat_32
            delta_lon_min = rec["e0_lon_min"] - center_lon_32
            delta_lat_max = rec["e0_lat_max"] - center_lat_32
            delta_lon_max = rec["e0_lon_max"] - center_lon_32
            print(
                f"    delta_lat_min = {delta_lat_min} (0x{delta_lat_min & 0xFFFFFFFF:08X})"
            )
            print(
                f"    delta_lon_min = {delta_lon_min} (0x{delta_lon_min & 0xFFFFFFFF:08X})"
            )
            print(
                f"    delta_lat_max = {delta_lat_max} (0x{delta_lat_max & 0xFFFFFFFF:08X})"
            )
            print(
                f"    delta_lon_max = {delta_lon_max} (0x{delta_lon_max & 0xFFFFFFFF:08X})"
            )

            # Check if deltas fit in int16
            print(
                f"    Fit in int16? lat_min={-32768 <= delta_lat_min <= 32767}, "
                f"lon_min={-32768 <= delta_lon_min <= 32767}, "
                f"lat_max={-32768 <= delta_lat_max <= 32767}, "
                f"lon_max={-32768 <= delta_lon_max <= 32767}"
            )

            # Also check delta in 24-bit map units
            delta_lat_min_24 = rec["e0_lat_min"] - center_lat_32
            # Need to convert E0 coords (32-bit) to deltas in the coordinate system used by the preamble
            # The preamble might use a different scaling

            # Let's check: what if the preamble uses signed 16-bit deltas in the SAME
            # 32-bit Garmin coordinate space? Then each delta would be ~0.0000083 degrees
            print("\n  Interpretation 8: int16 deltas in Garmin 32-bit space")
            print("    int16 range: -32768 to 32767")
            print(
                f"    In degrees: {-32768 * 180 / 2**31:.6f} to {32767 * 180 / 2**31:.6f}"
            )
            print(f"    That's about {32767 * 180 / 2**31:.6f} degrees range per int16")
            print(
                f"    E0 tile spans: lat={garmin_32_to_deg(rec['e0_lat_max']) - garmin_32_to_deg(rec['e0_lat_min']):.6f} deg, "
                f"lon={garmin_32_to_deg(rec['e0_lon_max']) - garmin_32_to_deg(rec['e0_lon_min']):.6f} deg"
            )

        # =========================================================================
        # STEP 7: Compare multiple polyline records to find patterns
        # =========================================================================
        print("\n" + "=" * 80)
        print("STEP 7: Multiple Record Comparison")
        print("=" * 80)

        # Parse more records to see the pattern
        pos = 0
        all_records = []
        record_idx = 0

        while pos < min(len(rgn2_data), 2000) and record_idx < 20:
            if rgn2_data[pos] == 0x06:
                preamble = rgn2_data[pos + 2 : pos + 18]
                e0_pos = pos + 18

                if e0_pos + 24 <= len(rgn2_data) and rgn2_data[e0_pos] == 0xE0:
                    e0_bits = rgn2_data[e0_pos + 1]
                    if e0_bits == 0x2D:
                        idx_size = 2
                        img_idx = struct.unpack_from("<H", rgn2_data, e0_pos + 2)[0]
                    else:
                        idx_size = 1
                        img_idx = rgn2_data[e0_pos + 2]

                    coord_off = e0_pos + 2 + idx_size
                    lat_min = struct.unpack_from("<i", rgn2_data, coord_off)[0]
                    lon_min = struct.unpack_from("<i", rgn2_data, coord_off + 4)[0]
                    lat_max = struct.unpack_from("<i", rgn2_data, coord_off + 8)[0]
                    lon_max = struct.unpack_from("<i", rgn2_data, coord_off + 12)[0]
                    block_size = struct.unpack_from("<I", rgn2_data, coord_off + 16)[0]

                    all_records.append(
                        {
                            "pos": pos,
                            "preamble_hex": preamble.hex(),
                            "preamble_bytes": list(preamble),
                            "lat_min": lat_min,
                            "lon_min": lon_min,
                            "lat_max": lat_max,
                            "lon_max": lon_max,
                            "block_size": block_size,
                            "img_idx": img_idx,
                        }
                    )

                    e0_total = 2 + idx_size + 16 + 4
                    pos = e0_pos + e0_total
                    record_idx += 1
                    continue
            pos += 1

        print(f"  Parsed {len(all_records)} polyline+E0 pairs")

        # Print a comparison table
        print(
            f"\n  {'#':>3} {'preamble_hex':<34} {'lat_min':>12} {'lon_min':>12} {'lat_max':>12} {'lon_max':>12} {'blk_sz':>8} {'idx':>4}"
        )
        print(
            f"  {'-' * 3} {'-' * 34} {'-' * 12} {'-' * 12} {'-' * 12} {'-' * 12} {'-' * 8} {'-' * 4}"
        )
        for i, rec in enumerate(all_records[:15]):
            print(
                f"  {i:3d} {rec['preamble_hex']:<34} {rec['lat_min']:>12d} {rec['lon_min']:>12d} "
                f"{rec['lat_max']:>12d} {rec['lon_max']:>12d} {rec['block_size']:>8d} {rec['img_idx']:>4d}"
            )

        # =========================================================================
        # STEP 8: Test delta hypotheses with subdivision center
        # =========================================================================
        print("\n" + "=" * 80)
        print("STEP 8: Delta Hypothesis Testing")
        print("=" * 80)

        # For zoom level 20 (root), there's 1 group with center at group[0]
        # For zoom level 21, there are 3 groups starting at group[1], [2], [3]
        # etc.
        # The RGN2 data starts with zoom level 24 (most detailed), which has 300 subdivisions
        # Actually wait - let's check the TRE7 offsets to see which zoom level maps to
        # which RGN2 offset

        print("\n  TRE7 offset analysis:")
        print("  (These offsets are into RGN2 data)")
        for i, entry in enumerate(tre7_offsets[:10]):
            print(
                f"    [{i}] offset={entry['offset']:10d} flag={entry.get('flag', 'N/A')}"
            )

        # TRE7 has 599 entries. With 5 zoom levels having subdiv counts [1, 3, 138, 156, 300],
        # that's 598 subdivisions total + 1 extra entry.
        # So TRE7 entries map 1:1 to TRE2 subdivisions!
        # Each entry gives the RGN2 byte offset for that subdivision's data.

        # The first 5 TRE7 entries all have offset=0 and flag=1.
        # These likely correspond to the 5 root groups (one per zoom level).
        # Actually, looking at the TRE2 groups:
        # Group 0: subdivs=2675 (zoom 20?)
        # No wait, the levels show subdiv_count per level, not total.

        # Let me re-examine: levels show [1, 3, 138, 156, 300] subdivisions.
        # Groups 0-4 are the 5 zoom level root groups (1+3+138+156+300 = 598).
        # But there are 560 groups shown...

        # Actually, the 16-byte group records are the subdivisions themselves.
        # Each zoom level has N subdivisions. Each subdivision is a 16-byte record.
        # Level 0: 1 subdiv → groups[0]
        # Level 1: 3 subdivs → groups[1], groups[2], groups[3]
        # Level 2: 138 subdivs → groups[4]...groups[141]
        # Level 3: 156 subdivs → groups[142]...groups[297]
        # Level 4: 300 subdivs → groups[298]...groups[597]

        # But we have 560 groups, not 598. Something's off.
        # Let me count: 1+3+138+156+300 = 598
        # But TRE2 size is 8972 bytes, 8972/16 = 560.75 - not exact!
        # Hmm, maybe the records aren't all 16 bytes.

        # Actually the TRE2 section has 560 complete 16-byte records (560*16 = 8960)
        # plus 12 extra bytes. So maybe some records are different sizes.

        print(f"\n  TRE2 size: {tre['tre2']['size']} bytes")
        print(f"  16-byte records that fit: {tre['tre2']['size'] // 16}")
        print(f"  Remainder: {tre['tre2']['size'] % 16}")

        # =========================================================================
        # STEP 9: Check relationship between preamble bytes and tile coords
        # =========================================================================
        print("\n" + "=" * 80)
        print("STEP 9: Byte-Level Preamble vs E0 Coordinate Comparison")
        print("=" * 80)

        if all_records:
            for i in range(min(5, len(all_records))):
                rec = all_records[i]
                preamble = bytes(rec["preamble_bytes"])
                print(f"\n  Record {i}:")
                print(f"    Preamble: {rec['preamble_hex']}")

                # Convert E0 coords to bytes
                lat_min_bytes = struct.pack("<i", rec["lat_min"])
                lon_min_bytes = struct.pack("<i", rec["lon_min"])
                lat_max_bytes = struct.pack("<i", rec["lat_max"])
                lon_max_bytes = struct.pack("<i", rec["lon_max"])

                print(
                    f"    E0 lat_min bytes: {lat_min_bytes.hex()} (value: {rec['lat_min']})"
                )
                print(
                    f"    E0 lon_min bytes: {lon_min_bytes.hex()} (value: {rec['lon_min']})"
                )
                print(
                    f"    E0 lat_max bytes: {lat_max_bytes.hex()} (value: {rec['lat_max']})"
                )
                print(
                    f"    E0 lon_max bytes: {lon_max_bytes.hex()} (value: {rec['lon_max']})"
                )

                # Check if preamble bytes appear anywhere in E0 coords
                # Maybe preamble contains the LOW bytes of the 32-bit coords?
                # 32-bit Garmin coord: upper 16 bits = degrees part, lower 16 bits = fraction

                # Check: does preamble contain the lower 16 bits of each coord?
                lat_min_lo = rec["lat_min"] & 0xFFFF
                lat_min_hi = (rec["lat_min"] >> 16) & 0xFFFF
                lon_min_lo = rec["lon_min"] & 0xFFFF
                lon_min_hi = (rec["lon_min"] >> 16) & 0xFFFF
                lat_max_lo = rec["lat_max"] & 0xFFFF
                lat_max_hi = (rec["lat_max"] >> 16) & 0xFFFF
                lon_max_lo = rec["lon_max"] & 0xFFFF
                lon_max_hi = (rec["lon_max"] >> 16) & 0xFFFF

                print("\n    E0 coord halves:")
                print(f"      lat_min: hi=0x{lat_min_hi:04X} lo=0x{lat_min_lo:04X}")
                print(f"      lon_min: hi=0x{lon_min_hi:04X} lo=0x{lon_min_lo:04X}")
                print(f"      lat_max: hi=0x{lat_max_hi:04X} lo=0x{lat_max_lo:04X}")
                print(f"      lon_max: hi=0x{lon_max_hi:04X} lo=0x{lon_max_lo:04X}")

                # Check as int16 values from preamble
                preamble_ints = [
                    struct.unpack_from("<h", preamble, j)[0] for j in range(0, 16, 2)
                ]
                print(f"\n    Preamble as 8 × int16 LE: {preamble_ints}")

                # Check: center lat/lon in 24-bit map units, convert E0 coords to same units
                # and compute delta
                center_lat_24 = groups[0]["lat_center"]
                center_lon_24 = groups[0]["lon_center"]

                e0_lat_min_24 = int(
                    rec["lat_min"] * (2**24) / (2**31) * 2
                )  # scale from 32-bit to 24-bit
                # Actually: 32-bit units are degrees * 2^31 / 180
                # 24-bit units are degrees * 2^24 / 360
                # So 24-bit = 32-bit * (2^24/360) / (2^31/180) = 32-bit * (2^24 * 180) / (360 * 2^31)
                #           = 32-bit * 180 / (360 * 128) = 32-bit / 256

                e0_lat_min_24bit = rec["lat_min"] >> 8  # arithmetic shift right by 8
                e0_lon_min_24bit = rec["lon_min"] >> 8
                e0_lat_max_24bit = rec["lat_max"] >> 8
                e0_lon_max_24bit = rec["lon_max"] >> 8

                print("\n    E0 coords converted to 24-bit (>>8):")
                print(
                    f"      lat_min_24: {e0_lat_min_24bit} ({map_units_24_to_deg(e0_lat_min_24bit):.6f})"
                )
                print(
                    f"      lon_min_24: {e0_lon_min_24bit} ({map_units_24_to_deg(e0_lon_min_24bit):.6f})"
                )
                print(
                    f"      lat_max_24: {e0_lat_max_24bit} ({map_units_24_to_deg(e0_lat_max_24bit):.6f})"
                )
                print(
                    f"      lon_max_24: {e0_lon_max_24bit} ({map_units_24_to_deg(e0_lon_max_24bit):.6f})"
                )

                delta_lat_min_24 = e0_lat_min_24bit - center_lat_24
                delta_lon_min_24 = e0_lon_min_24bit - center_lon_24
                delta_lat_max_24 = e0_lat_max_24bit - center_lat_24
                delta_lon_max_24 = e0_lon_max_24bit - center_lon_24

                print("\n    Delta from center (24-bit):")
                print(
                    f"      d_lat_min: {delta_lat_min_24} (0x{delta_lat_min_24 & 0xFFFF:04X})"
                )
                print(
                    f"      d_lon_min: {delta_lon_min_24} (0x{delta_lon_min_24 & 0xFFFF:04X})"
                )
                print(
                    f"      d_lat_max: {delta_lat_max_24} (0x{delta_lat_max_24 & 0xFFFF:04X})"
                )
                print(
                    f"      d_lon_max: {delta_lon_max_24} (0x{delta_lon_max_24 & 0xFFFF:04X})"
                )

                print(
                    f"\n    Fit in int16? "
                    f"d_lat_min={-32768 <= delta_lat_min_24 <= 32767}, "
                    f"d_lon_min={-32768 <= delta_lon_min_24 <= 32767}, "
                    f"d_lat_max={-32768 <= delta_lat_max_24 <= 32767}, "
                    f"d_lon_max={-32768 <= delta_lon_max_24 <= 32767}"
                )

        # =========================================================================
        # STEP 10: Look at the bits-per-coordinate in TRE parameters
        # =========================================================================
        print("\n" + "=" * 80)
        print("STEP 10: TRE Parameters / Bits-Per-Coordinate Analysis")
        print("=" * 80)

        tre_off = gmp["sections"]["TRE"]
        tre_bytes = data[tre_off:]

        # TRE+0x42: parameters (8 bytes)
        params = tre_bytes[0x42:0x4A]
        print(f"  TRE parameters (8 bytes at 0x42): {params.hex()}")
        print(f"    param1 (0x42): 0x{params[0]:02X} = {params[0]}")
        print(f"    param2 (0x43): 0x{params[1]:02X} = {params[1]}")
        print(f"    param3 (0x44): 0x{params[2]:02X} = {params[2]}")
        print(f"    param4 (0x45): 0x{params[3]:02X} = {params[3]}")
        print(f"    param5 (0x46): 0x{params[4]:02X} = {params[4]}")
        print(f"    param6 (0x47): 0x{params[5]:02X} = {params[5]}")
        print(f"    param7 (0x48): 0x{params[6]:02X} = {params[6]}")
        print(f"    param8 (0x49): 0x{params[7]:02X} = {params[7]}")

        # In Garmin vector format, "bits per coordinate" is a field in the TRE header.
        # For raster maps, SwissTopo has parameter 2 = 0x04 (4?)
        # IOM has parameter 2 = 0x08 (8?)
        # This might indicate the number of bytes per coordinate in the polyline preamble

        print("\n  Parameter analysis:")
        print("    SwissTopo has param2=4. If this is bytes-per-coord:")
        print(
            "      4 bytes = int32 per coord → 4 coords × 4 bytes = 16 bytes preamble"
        )
        print("      Matches the 16-byte preamble we see!")

        print("\n    IOM has param2=8. If this is bytes-per-coord:")
        print("      8 bytes = 2×int32 per coord? Different format.")

        # =========================================================================
        # STEP 11: Definitive test - is preamble 4×int32 deltas from center?
        # =========================================================================
        print("\n" + "=" * 80)
        print("STEP 11: Definitive Test - Preamble as 4×int32 Deltas")
        print("=" * 80)

        # Get the correct subdivision center for the first few tiles
        # The first tiles are at zoom level 24 (most detailed)
        # TRE7 entry [0] has offset=0, so the first RGN2 data starts at offset 0
        # But which TRE2 group does it correspond to?

        # TRE7 entries map to subdivisions. The first 5 entries (one per zoom level?)
        # all have offset=0. Then entries starting at [5] have increasing offsets.
        # The first actual tile data starts at TRE7 entry [5] with offset=10710

        # Wait - the first 5 TRE7 entries have offset=0, which would be the start of RGN2
        # data. But the first bytes at RGN2 offset 0 are 06 B3 ... which is a polyline.
        # So those first 5 entries point to the polyline preamble for their respective
        # zoom levels.

        # Let's check which TRE2 group the first tile belongs to
        # Zoom level 24 (index 4 in levels) has 300 subdivisions
        # These are groups[298] to groups[597] (if the pattern holds)
        # But we only have 560 groups...

        # Let me think about this differently.
        # The TRE7 offsets tell us where each subdivision's RGN2 data starts.
        # Entry [0] offset=0 → first subdivision of zoom level 20 (the only one)
        # Entry [1] offset=0 → first subdivision of zoom level 21
        # ...
        # Entry [5] offset=10710 → second subdivision (first non-root) of zoom level 24

        # Actually the flag=1 might mean "first in group" and flag=0 means "continuation"

        # Let's just test with the actual data
        print("\n  Testing with all parsed records:")

        if all_records:
            for i in range(min(5, len(all_records))):
                rec = all_records[i]
                preamble = bytes(rec["preamble_bytes"])

                # Try: preamble = delta_lat_min, delta_lon_min, delta_lat_max, delta_lon_max
                # as int32 LE, where delta = tile_coord_32 - center_coord_32
                d_lat_min, d_lon_min, d_lat_max, d_lon_max = struct.unpack(
                    "<iiii", preamble
                )

                # Test with different centers
                # Try each of the first few groups
                for g_idx in range(min(5, len(groups))):
                    g = groups[g_idx]
                    c_lat_32 = deg_to_garmin_32(g["lat_center_deg"])
                    c_lon_32 = deg_to_garmin_32(g["lon_center_deg"])

                    test_lat_min = c_lat_32 + d_lat_min
                    test_lon_min = c_lon_32 + d_lon_min
                    test_lat_max = c_lat_32 + d_lat_max
                    test_lon_max = c_lon_32 + d_lon_max

                    match_lat_min = test_lat_min == rec["lat_min"]
                    match_lon_min = test_lon_min == rec["lon_min"]
                    match_lat_max = test_lat_max == rec["lat_max"]
                    match_lon_max = test_lon_max == rec["lon_max"]

                    if any(
                        [match_lat_min, match_lon_min, match_lat_max, match_lon_max]
                    ):
                        print(
                            f"\n  Record {i} with group {g_idx} center ({g['lat_center_deg']:.6f}, {g['lon_center_deg']:.6f}):"
                        )
                        print(
                            f"    d_lat_min={d_lat_min}, computed={garmin_32_to_deg(test_lat_min):.6f}, expected={garmin_32_to_deg(rec['lat_min']):.6f}, match={match_lat_min}"
                        )
                        print(
                            f"    d_lon_min={d_lon_min}, computed={garmin_32_to_deg(test_lon_min):.6f}, expected={garmin_32_to_deg(rec['lon_min']):.6f}, match={match_lon_min}"
                        )
                        print(
                            f"    d_lat_max={d_lat_max}, computed={garmin_32_to_deg(test_lat_max):.6f}, expected={garmin_32_to_deg(rec['lat_max']):.6f}, match={match_lat_max}"
                        )
                        print(
                            f"    d_lon_max={d_lon_max}, computed={garmin_32_to_deg(test_lon_max):.6f}, expected={garmin_32_to_deg(rec['lon_max']):.6f}, match={match_lon_max}"
                        )

        # =========================================================================
        # STEP 12: Try delta in 24-bit map units
        # =========================================================================
        print("\n" + "=" * 80)
        print("STEP 12: Preamble as 4×int16 Deltas from Center (24-bit space)")
        print("=" * 80)

        if all_records:
            for i in range(min(5, len(all_records))):
                rec = all_records[i]
                preamble = bytes(rec["preamble_bytes"])

                # Interpret preamble as 4 pairs of int16 (lat_delta, lon_delta) × 2 corners
                # or 8 int16 values
                vals = [
                    struct.unpack_from("<h", preamble, j)[0] for j in range(0, 16, 2)
                ]

                print(f"\n  Record {i}: preamble={rec['preamble_hex']}")
                print(f"    8 × int16 LE: {vals}")
                print(
                    f"    E0 coords: lat=[{garmin_32_to_deg(rec['lat_min']):.6f}, {garmin_32_to_deg(rec['lat_max']):.6f}] "
                    f"lon=[{garmin_32_to_deg(rec['lon_min']):.6f}, {garmin_32_to_deg(rec['lon_max']):.6f}]"
                )

                # Test each group as center
                for g_idx in range(min(10, len(groups))):
                    g = groups[g_idx]
                    c_lat_24 = g["lat_center"]
                    c_lon_24 = g["lon_center"]

                    # If vals are deltas in 24-bit space:
                    # lat_min = center_lat_24 + vals[0]
                    # etc. But which mapping?

                    # Try: vals[0]=dlat_min, vals[1]=dlon_min, vals[2]=dlat_max, vals[3]=dlon_max
                    # in 24-bit map units
                    for mapping_name, idx_map in [
                        ("dlat_min,dlon_min,dlat_max,dlon_max", [0, 1, 2, 3]),
                        ("dlat_min,dlat_max,dlon_min,dlon_max", [0, 2, 1, 3]),
                        ("dlon_min,dlat_min,dlon_max,dlat_max", [1, 0, 3, 2]),
                    ]:
                        test_lat_min = c_lat_24 + vals[idx_map[0]]
                        test_lon_min = c_lon_24 + vals[idx_map[1]]
                        test_lat_max = c_lat_24 + vals[idx_map[2]]
                        test_lon_max = c_lon_24 + vals[idx_map[3]]

                        # Convert E0 32-bit coords to 24-bit for comparison
                        e0_lat_min_24 = rec["lat_min"] >> 8
                        e0_lon_min_24 = rec["lon_min"] >> 8
                        e0_lat_max_24 = rec["lat_max"] >> 8
                        e0_lon_max_24 = rec["lon_max"] >> 8

                        if (
                            test_lat_min == e0_lat_min_24
                            and test_lon_min == e0_lon_min_24
                            and test_lat_max == e0_lat_max_24
                            and test_lon_max == e0_lon_max_24
                        ):
                            print(
                                f"    MATCH with group {g_idx}! mapping={mapping_name}"
                            )
                            print(
                                f"      center: lat={c_lat_24} ({g['lat_center_deg']:.6f}), lon={c_lon_24} ({g['lon_center_deg']:.6f})"
                            )
                            print(
                                f"      computed: lat=[{map_units_24_to_deg(test_lat_min):.6f}, {map_units_24_to_deg(test_lat_max):.6f}]"
                            )
                            print(
                                f"      expected: lat=[{garmin_32_to_deg(rec['lat_min']):.6f}, {garmin_32_to_deg(rec['lat_max']):.6f}]"
                            )

                    # Also try: vals might be in a different coordinate space
                    # What if the deltas are NOT in map units but in some tile grid units?

        # =========================================================================
        # STEP 13: Check the TRE7 offsets to find which group each tile belongs to
        # =========================================================================
        print("\n" + "=" * 80)
        print("STEP 13: TRE7 Offset → Group Mapping")
        print("=" * 80)

        # Count subdivisions per zoom level from TRE1
        level_subdiv_counts = [lvl["subdivision_count"] for lvl in levels]
        print(f"  Subdivision counts per level: {level_subdiv_counts}")
        print(f"  Total: {sum(level_subdiv_counts)}")
        print(f"  TRE7 entries: {len(tre7_offsets)}")

        # The first subdivision of each level might be a "header" entry
        # Level 0: 1 entry (indices 0)
        # Level 1: 3 entries (indices 1-3)
        # Level 2: 138 entries (indices 4-141)
        # Level 3: 156 entries (indices 142-297)
        # Level 4: 300 entries (indices 298-597)

        level_ranges = []
        start = 0
        for lvl_idx, count in enumerate(level_subdiv_counts):
            level_ranges.append((start, start + count - 1, lvl_idx))
            start += count

        print("\n  Level ranges in TRE7:")
        for start, end, lvl_idx in level_ranges:
            print(f"    Level {lvl_idx}: entries [{start}..{end}]")

        # Check: TRE7 entry 0 has offset=0 and flag=1
        # TRE7 entry 1 has offset=0 and flag=1 (root of level 1?)
        # TRE7 entry 4 has offset=0 and flag=1 (root of level 2?)
        # TRE7 entry 142 has offset=0 and flag=1 (root of level 3?)
        # TRE7 entry 298 has offset=0 and flag=1 (root of level 4?)

        print("\n  First entry of each level:")
        for start, end, lvl_idx in level_ranges:
            entry = tre7_offsets[start]
            print(
                f"    Level {lvl_idx}, entry [{start}]: offset={entry['offset']}, flag={entry.get('flag', 'N/A')}"
            )

        # So the first RGN2 data (offset 0) is shared by all root-level entries
        # The polyline at offset 0 belongs to the zoom 20 root group (groups[0])

        # Now check: what's at offset 10710 (first non-zero TRE7 offset)?
        first_data_offset = None
        for entry in tre7_offsets:
            if entry["offset"] > 0:
                first_data_offset = entry["offset"]
                break

        if first_data_offset:
            print(f"\n  First non-zero TRE7 offset: {first_data_offset}")
            chunk = rgn2_data[first_data_offset : first_data_offset + 50]
            print(f"  Data at that offset: {chunk.hex()}")

        # =========================================================================
        # STEP 14: Check the sub_type byte (0xB3) meaning
        # =========================================================================
        print("\n" + "=" * 80)
        print("STEP 14: Sub-type Byte Analysis")
        print("=" * 80)

        # 0xB3 = 10110011 binary
        sub_type = 0xB3
        print(f"  Sub-type 0xB3 = {sub_type:08b} binary")
        print(f"    Bit 7 (0x80): {(sub_type >> 7) & 1} - direction/label flag")
        print(f"    Bit 6 (0x40): {(sub_type >> 6) & 1}")
        print(f"    Bit 5 (0x20): {(sub_type >> 5) & 1}")
        print(f"    Bit 4 (0x10): {(sub_type >> 4) & 1}")
        print(f"    Bit 3 (0x08): {(sub_type >> 3) & 1}")
        print(f"    Bits 0-2: {sub_type & 0x07} - extra bytes count?")

        # Check sub-types of the first few polyline records
        pos = 0
        sub_types = set()
        while pos < min(len(rgn2_data), 5000):
            if rgn2_data[pos] == 0x06:
                sub_types.add(rgn2_data[pos + 1])
                # Skip to next record (assume 18-byte polyline + 24-byte E0)
                if pos + 42 < len(rgn2_data):
                    pos += 42  # 18 + 24
                else:
                    break
            else:
                pos += 1

        print(
            f"\n  Unique sub-types found in first 5000 bytes: {[f'0x{s:02X}' for s in sorted(sub_types)]}"
        )

        # Parse the sub-type bit fields
        for st in sorted(sub_types):
            print(
                f"    0x{st:02X} = {st:08b}: "
                f"dir={((st >> 7) & 1)} "
                f"bit6={((st >> 6) & 1)} "
                f"bit5={((st >> 5) & 1)} "
                f"bit4={((st >> 4) & 1)} "
                f"bit3={((st >> 3) & 1)} "
                f"low3={st & 0x07}"
            )

        # =========================================================================
        # STEP 15: Check IOM reference file for comparison
        # =========================================================================
        iom_path = "/home/tobias/kdrive/garmin/IOM.img"
        if os.path.exists(iom_path):
            print("\n" + "=" * 80)
            print("STEP 15: IOM Reference Comparison")
            print("=" * 80)

            with IMGParser(iom_path) as iom:
                iom.parse_header()
                iom.parse_fat()

                # Find the smallest GMP subfile (00355951)
                iom_gmp_key = None
                for key in iom.subfiles:
                    if "00355951" in key:
                        iom_gmp_key = key
                        break

                if iom_gmp_key:
                    iom_gmp = iom.parse_gmp_container(iom_gmp_key)
                    iom_data = iom_gmp["data"]
                    iom.parse_tre(iom_gmp)
                    iom_rgn = iom.parse_rgn(iom_gmp)

                    # Get TRE parameters
                    iom_tre_off = iom_gmp["sections"]["TRE"]
                    iom_tre_bytes = iom_data[iom_tre_off:]
                    iom_params = iom_tre_bytes[0x42:0x4A]
                    print(f"  IOM TRE parameters: {iom_params.hex()}")
                    print(f"    param2 (bits-per-coord?): {iom_params[1]}")

                    # Get IOM RGN2 data
                    if "rgn2" in iom_rgn and iom_rgn["rgn2"]["size"] > 0:
                        iom_rgn2_pos = iom_rgn["rgn2"]["position"]
                        iom_rgn2_size = iom_rgn["rgn2"]["size"]
                        iom_rgn2_data = iom_data[
                            iom_rgn2_pos : iom_rgn2_pos + iom_rgn2_size
                        ]

                        print(f"\n  IOM RGN2 data ({iom_rgn2_size} bytes):")
                        print(f"    First 100 bytes: {iom_rgn2_data[:100].hex()}")

                        # Parse IOM polyline records
                        iom_pos = 0
                        while iom_pos < min(len(iom_rgn2_data), 500):
                            if iom_rgn2_data[iom_pos] == 0x06:
                                sub = iom_rgn2_data[iom_pos + 1]
                                # IOM has param2=8, so maybe 8 bytes per coord?
                                # Try different preamble sizes
                                for ps in range(4, 40, 2):
                                    next_pos = iom_pos + 2 + ps
                                    if (
                                        next_pos < len(iom_rgn2_data)
                                        and iom_rgn2_data[next_pos] == 0xE0
                                    ):
                                        preamble = iom_rgn2_data[
                                            iom_pos + 2 : iom_pos + 2 + ps
                                        ]
                                        print(
                                            f"\n    IOM polyline at {iom_pos}: sub=0x{sub:02X}, preamble_size={ps}"
                                        )
                                        print(f"      Preamble: {preamble.hex()}")
                                        break

                                iom_pos += 1
                            else:
                                iom_pos += 1
                    else:
                        print("  IOM has no RGN2 data or empty RGN2")
                else:
                    print("  IOM subfile 00355951 not found")

    # =========================================================================
    # STEP 16: Final analysis - determine the preamble structure
    # =========================================================================
    print("\n" + "=" * 80)
    print("STEP 16: Summary and Preliminary Structure")
    print("=" * 80)

    print("""
    From the analysis:
    - SwissTopo polyline record: 06 B3 [16 bytes preamble] E0 [E0 record]
    - The 16-byte preamble contains 4 × int32 LE values
    - TRE parameter at offset 0x43 = 0x04, which matches 4 bytes per coordinate
    - The preamble likely encodes tile bounds as deltas from subdivision center
    - Next step: determine the exact center coordinate and delta encoding
    """)


if __name__ == "__main__":
    analyze_polyline_structure()
