#!/usr/bin/env python3
"""
Targeted RGN2 analysis: Use TRE7 offsets to segment RGN2 data by zoom level,
then analyze the record structure within each segment.

Key insight: GMT uses TRE7 offsets to jump to each zoom level's data block
within RGN2. The subdivision records in TRE2 tell GMT the exact byte extent
of each subdivision's RGN data. Record lengths are NOT self-describing --
they come from the TRE2 subdivision metadata.
"""

import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from img_analysis import (
    IMGParser,
    decode_3byte_signed,
    map_units_to_degrees,
    map_units_to_degrees_32,
)


def hex_dump(data, start_offset=0, bytes_per_line=16, max_bytes=None):
    if max_bytes and len(data) > max_bytes:
        data = data[:max_bytes]
    lines = []
    for i in range(0, len(data), bytes_per_line):
        chunk = data[i : i + bytes_per_line]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(
            f"  {start_offset + i:06x}  {hex_part:<{bytes_per_line * 3}}  |{ascii_part}|"
        )
    return "\n".join(lines)


def main():
    iom_path = "/home/tobias/git/burgdev/cartoload/tests/data/garmin_samples/IOM.img"
    our_path = "/home/tobias/git/burgdev/cartoload/output/ch_basemap_test.img"

    for label, path in [("IOM REFERENCE", iom_path), ("OUR OUTPUT", our_path)]:
        print(f"\n{'#' * 80}")
        print(f"#  {label}: {path}")
        print(f"{'#' * 80}")

        with IMGParser(path) as img:
            img.parse_header()
            img.parse_fat()

            gmp_key = None
            for key in img.subfiles:
                if img.subfiles[key]["type"] == "GMP":
                    gmp_key = key
                    break
            if not gmp_key:
                print("  ERROR: No GMP subfile found")
                continue

            gmp = img.parse_gmp_container(gmp_key)
            data = gmp["data"]

            tre_off = gmp["sections"]["TRE"]
            tre = data[tre_off:]

            # Get TRE2 (subdivisions)
            tre2_pos = struct.unpack_from("<I", tre, 0x29)[0]
            tre2_size = struct.unpack_from("<I", tre, 0x2D)[0]

            # Get TRE7 offsets
            tre7_pos = struct.unpack_from("<I", tre, 0x7C)[0]
            tre7_size = struct.unpack_from("<I", tre, 0x80)[0]
            tre7_rec_size = struct.unpack_from("<H", tre, 0x84)[0]

            # Get TRE1 (map levels)
            tre1_pos = struct.unpack_from("<I", tre, 0x21)[0]
            tre1_size = struct.unpack_from("<I", tre, 0x25)[0]

            # Parse map levels
            levels_data = data[tre1_pos : tre1_pos + tre1_size]
            levels = []
            for i in range(0, len(levels_data), 4):
                if i + 4 <= len(levels_data):
                    levels.append(
                        {
                            "level_number": levels_data[i],
                            "zoom_code": levels_data[i + 1],
                            "subdivision_count": struct.unpack_from(
                                "<H", levels_data, i + 2
                            )[0],
                        }
                    )

            print(f"\n  Map Levels ({len(levels)}):")
            for i, lvl in enumerate(levels):
                print(
                    f"    Level {i}: number={lvl['level_number']}, zoom_code={lvl['zoom_code']}, subdivs={lvl['subdivision_count']}"
                )

            # Parse TRE7 offsets
            tre7_data = data[tre7_pos : tre7_pos + tre7_size]
            tre7_offsets = []
            rec_size = tre7_rec_size if tre7_rec_size > 0 else 4
            for i in range(0, len(tre7_data), rec_size):
                if i + rec_size <= len(tre7_data):
                    off = struct.unpack_from("<I", tre7_data, i)[0]
                    tre7_offsets.append(off)

            print(
                f"\n  TRE7 offsets ({len(tre7_offsets)}): {[hex(o) for o in tre7_offsets]}"
            )

            # Parse TRE2 subdivisions (16-byte group records)
            subdivs_data = data[tre2_pos : tre2_pos + tre2_size]
            subdivs = []
            for i in range(0, len(subdivs_data), 16):
                if i + 16 <= len(subdivs_data):
                    rec = subdivs_data[i : i + 16]
                    rgn_off = rec[0] | (rec[1] << 8) | (rec[2] << 16)
                    obj_types = rec[3]
                    lon = decode_3byte_signed(rec, 4)
                    lat = decode_3byte_signed(rec, 7)
                    flags = struct.unpack_from("<H", rec, 10)[0]
                    subdiv_count = struct.unpack_from("<H", rec, 12)[0]
                    next_level = struct.unpack_from("<H", rec, 14)[0]
                    subdivs.append(
                        {
                            "rgn_offset": rgn_off,
                            "obj_types": obj_types,
                            "lon": lon,
                            "lat": lat,
                            "flags": flags,
                            "subdiv_count": subdiv_count,
                            "next_level": next_level,
                        }
                    )

            print(f"\n  TRE2 Subdivisions ({len(subdivs)}), 16-byte records:")
            for i, sd in enumerate(subdivs):
                print(
                    f"    Subdiv {i}: rgn_off=0x{sd['rgn_offset']:X} ({sd['rgn_offset']}), "
                    f"obj_types=0x{sd['obj_types']:02X}, flags=0x{sd['flags']:04X}, "
                    f"subdiv_count={sd['subdiv_count']}, next_level={sd['next_level']}, "
                    f"lon={map_units_to_degrees(lon):.4f}, lat={map_units_to_degrees(lat):.4f}"
                )

            # Now get RGN section info
            rgn_off = gmp["sections"]["RGN"]
            rgn = data[rgn_off:]
            rgn2_pos = struct.unpack_from("<I", rgn, 0x1D)[0]
            rgn2_size = struct.unpack_from("<I", rgn, 0x21)[0]

            print(f"\n  RGN2: pos=0x{rgn2_pos:X}, size={rgn2_size}")

            rgn2_data = data[rgn2_pos : rgn2_pos + rgn2_size]

            # Segment RGN2 using TRE7 offsets
            print("\n  === RGN2 Segmented by TRE7 offsets ===")

            # Build segments: each TRE7 offset marks the start of a zoom level's data
            for seg_idx in range(len(tre7_offsets)):
                seg_start = tre7_offsets[seg_idx]
                if seg_idx + 1 < len(tre7_offsets):
                    seg_end = tre7_offsets[seg_idx + 1]
                else:
                    seg_end = rgn2_size
                seg_size = seg_end - seg_start

                print(
                    f"\n  --- Segment {seg_idx} (zoom level): offset 0x{seg_start:X}-0x{seg_end:X}, {seg_size} bytes ---"
                )

                seg_data = rgn2_data[seg_start:seg_end]

                # Show first ~150 bytes of segment
                dump_len = min(len(seg_data), 150)
                print(f"  First {dump_len} bytes:")
                print(hex_dump(seg_data, start_offset=seg_start, max_bytes=dump_len))

                # Look at the TRE2 subdivision for this level to find the rgn_offset
                if seg_idx < len(subdivs):
                    sd = subdivs[seg_idx]
                    print(
                        f"\n  TRE2 subdiv {seg_idx}: rgn_offset=0x{sd['rgn_offset']:X}, obj_types=0x{sd['obj_types']:02X}"
                    )
                    print("    -> rgn_offset is RELATIVE to RGN2 data start")
                    print(f"    -> This subdiv starts at RGN2+0x{sd['rgn_offset']:X}")
                    print(f"    -> Segment starts at RGN2+0x{seg_start:X}")

                    if sd["rgn_offset"] != seg_start:
                        print(
                            "    *** MISMATCH: TRE2 rgn_offset != TRE7 segment start! ***"
                        )

            # Now let's look at the IOM first segment in detail to understand
            # the record structure. Focus on where the polyline and E0 records are.
            print("\n\n  === DETAILED: First segment record scan ===")
            if len(tre7_offsets) >= 1:
                seg_start = tre7_offsets[0]
                seg_end = tre7_offsets[1] if len(tre7_offsets) > 1 else rgn2_size
                seg_data = rgn2_data[seg_start:seg_end]

                # Scan for known markers
                print("  Scanning for 0x06, 0x0D, 0xE0, 0xBC, 0xDE markers:")
                markers = []
                for i in range(len(seg_data)):
                    b = seg_data[i]
                    if b in (0x06, 0x0D, 0xE0, 0xBC, 0xDE):
                        markers.append((i, b))

                for offset, marker in markers[:30]:
                    # Show context around marker
                    ctx_start = max(0, offset - 2)
                    ctx_end = min(len(seg_data), offset + 25)
                    ctx = seg_data[ctx_start:ctx_end]
                    marker_names = {
                        0x06: "POLYLINE",
                        0x0D: "POLYGON",
                        0xE0: "RASTER",
                        0xBC: "BOUNDARY",
                        0xDE: "EXT_BOUNDARY",
                    }
                    print(
                        f"    0x{seg_start + offset:04X} (seg+0x{offset:02X}): 0x{marker:02X} ({marker_names.get(marker, '?'):13s})  ctx: {ctx.hex()}"
                    )

                # Try to identify the E0 records by looking for the pattern:
                # E0 2B followed by valid-looking coordinates
                print("\n  E0 record search (looking for E0 2B pattern):")
                for i in range(len(seg_data) - 5):
                    if seg_data[i] == 0xE0 and seg_data[i + 1] == 0x2B:
                        rec = seg_data[i : i + 23]
                        if len(rec) == 23:
                            img_idx = rec[2]
                            lat_min = struct.unpack_from("<i", rec, 3)[0]
                            lon_min = struct.unpack_from("<i", rec, 7)[0]
                            lat_max = struct.unpack_from("<i", rec, 11)[0]
                            lon_max = struct.unpack_from("<i", rec, 15)[0]
                            block_size = struct.unpack_from("<I", rec, 19)[0]
                            print(
                                f"    @0x{seg_start + i:04X}: idx={img_idx:3d} "
                                f"lat=[{map_units_to_degrees_32(lat_min):.4f},{map_units_to_degrees_32(lat_max):.4f}] "
                                f"lon=[{map_units_to_degrees_32(lon_min):.4f},{map_units_to_degrees_32(lon_max):.4f}] "
                                f"blk_sz={block_size}"
                            )

    # =========================================================
    # KEY ANALYSIS: How does GMT determine record lengths?
    # =========================================================
    print(f"\n\n{'#' * 80}")
    print("#  KEY ANALYSIS: How GMT determines record boundaries in RGN2")
    print(f"{'#' * 80}")

    print("""
The RGN2 data is NOT a simple stream of self-delimiting records.
Instead, GMT navigates RGN2 using:

1. TRE7 offsets - One entry per zoom level, pointing to the start of
   each zoom level's raster data block in RGN2.

2. TRE2 subdivision records - Each 16-byte record has a 3-byte rgn_offset
   that is an offset into RGN2 data. The subdivision also contains:
   - obj_types byte (which object types are present)
   - A next_level index that helps determine the extent

3. The subdivision's rgn_offset + the next subdivision's rgn_offset
   determines the byte range of data for that subdivision.

4. WITHIN a subdivision's byte range, the Garmin bitstream format applies:
   - Each record starts with a type byte (0x06, 0x0D, 0xE0, etc.)
   - The bitstream encoding determines the record length:
     * 0x06 (polyline): Variable length based on bitstream encoding
     * 0x0D (polygon): Variable length based on bitstream encoding
     * 0xE0 (raster): Fixed 23 or 24 bytes based on bits_field
     * 0xBC/0xDE: 3-byte boundary markers

The bitstream encoding for polylines/polygons works like this:
  - Byte 0: type (0x06 or 0x0D)
  - Byte 1: subtype (includes direction bit, extra byte count, etc.)
  - The rest is a bitstream with variable-length coordinate deltas

For our output file, the records parse cleanly because our polyline preambles
are simple 18-byte records with all-zero bitstreams.

For the IOM reference, the polyline/polygon records contain REAL coordinate
data in the bitstream, making them variable-length.
""")


if __name__ == "__main__":
    main()
