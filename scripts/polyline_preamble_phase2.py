#!/usr/bin/env python3
"""
Phase 2: Crack the exact polyline preamble encoding.

Key observations from Phase 1:
- The preamble is always 16 bytes after 06 B3
- It always ends with E0 at offset 18 from the 06 marker
- TRE parameters at 0x43 = 0x01, 0x44 = 0x04
- The low3 bits of 0xB3 = 3, which may indicate extra data length
- Some preambles have 0xF2 at byte 8, others have 0x02 0x09
- The last two int16 values vary (last uint16 seems to be an offset/counter)
- All E0 tiles at zoom 24 have the same lat range: [46.273470, 46.264887]
- The lon values differ between tiles

Let me look more carefully at the byte-level structure and compare with
the Garmin vector polyline format from QMapShack/wiki.
"""

import struct
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.img_analysis import IMGParser

IMG_PATH = "/home/tobias/kdrive/garmin/my_SwissTopo_West.img"


def deg_to_garmin_32(deg):
    return int(deg * (2**31) / 180)


def garmin_32_to_deg(val):
    return val * 180.0 / (2**31)


def map_units_24_to_deg(val):
    return val * 360.0 / (2**24)


def main():
    print("=" * 80)
    print("Phase 2: Cracking the Polyline Preamble Encoding")
    print("=" * 80)

    with IMGParser(IMG_PATH) as img:
        img.parse_header()
        img.parse_fat()

        gmp_key = None
        for key in img.subfiles:
            if img.subfiles[key]["type"] == "GMP":
                gmp_key = key
                break

        gmp = img.parse_gmp_container(gmp_key)
        data = gmp["data"]

        tre = img.parse_tre(gmp)
        rgn = img.parse_rgn(gmp)
        groups = tre.get("groups_16byte", [])

        rgn2_pos = rgn["rgn2"]["position"]
        rgn2_size = rgn["rgn2"]["size"]
        rgn2_data = data[rgn2_pos : rgn2_pos + rgn2_size]

        # =====================================================================
        # STEP A: Parse the polyline record in the context of the vector format
        # =====================================================================
        # In Garmin vector format (from QMapShack wiki and Willink docs):
        # Type 0x06 is a polyline. The record format is:
        #   byte 0: type (0x06)
        #   byte 1: subtype/label_info byte
        #     bits 5-7: label offset type (0=no label, 1=1-byte offset, 2=2-byte)
        #     bits 0-4: direction + number of extra bytes
        #     Actually, the QMapShack wiki says:
        #       byte 0: type
        #       byte 1: subtype
        #         bit 7: if set, extra data follows
        #         bits 6-0: depends on type
        #       For polylines with bitstreams:
        #         The subtype byte encodes info about the bitstream
        #
        # More specifically from QMapShack RasterImg wiki for the polyline in RGN2:
        # The polyline record type 0x06 with subtype 0xB3 represents a "bitmap polyline"
        # that wraps a raster tile.
        #
        # 0xB3 = 10110011
        # From the Willink/Pinns doc, polyline subtype byte:
        #   bits 0-1: 11 = bitmap with long image index
        #   bit 2: 0 = no label
        #   bit 3: 0 = no direction info
        #   bit 4: 1 = has extra data
        #   bit 5: 1 = has bitmap/extended data
        #   bit 6: 0
        #   bit 7: 1 = two-byte label offset or has bitstream
        #
        # Actually the Willink doc says for RGN type 0x06 (polyline):
        #   subtype byte:
        #     bits 0-1: coord type (00=2D, 01=3D, 10=2D+extra, 11=bitmap)
        #     bit 2: label type (0=none, 1=present)
        #     ...
        #
        # But for RASTER maps, the polyline record might be different!

        print("\n--- Understanding the sub-type byte ---")
        sub = 0xB3
        print(f"  0xB3 = {sub:08b}")
        print(f"  bits 0-1 = {sub & 0x03} (= 3, bitmap type)")
        print(f"  bit 2 = {(sub >> 2) & 1} (label flag)")
        print(f"  bit 3 = {(sub >> 3) & 1} (direction flag)")
        print(f"  bit 4 = {(sub >> 4) & 1}")
        print(f"  bit 5 = {(sub >> 5) & 1}")
        print(f"  bit 6 = {(sub >> 6) & 1}")
        print(f"  bit 7 = {(sub >> 7) & 1}")

        # =====================================================================
        # STEP B: Look at the Garmin vector polyline bitstream format
        # =====================================================================
        # From Willink/Pinns "Garmin IMG Format" document:
        # Polyline record in RGN:
        #   type (1 byte): 0x01-0x3F = polyline, 0x40-0x7F = polygon, etc.
        #   BUT for raster IMG, type 0x06 seems to be a "wrapper" polyline
        #   subtype (1 byte): see above
        #   Then: coordinate data as a bitstream
        #
        # The bitstream format encodes delta coordinates from the subdivision center.
        # First two deltas are lat_min and lon_min of the bounding box.
        # Then the polyline vertices.
        #
        # For a RASTER tile, the "polyline" is just a rectangle (4 vertices).
        # The bitstream would encode:
        #   1. Bounding box deltas (lat_delta, lon_delta) as signed integers
        #   2. Vertex deltas as a bitstream

        # =====================================================================
        # STEP C: Parse the 16-byte preamble as a Garmin bitstream
        # =====================================================================
        print("\n--- Parsing preamble as Garmin bitstream ---")

        # The first polyline at offset 0:
        # 06 B3 9c f1 f5 09 11 56 f2 08 00 80 1c 17 00 53 00 00
        # After 06 B3, the data is: 9c f1 f5 09 11 56 f2 08 00 80 1c 17 00 53 00 00

        # In Garmin vector format, the bitstream starts with:
        # - base_lat (signed, N bits) = delta from subdivision center
        # - base_lon (signed, N bits) = delta from subdivision center
        # - Then polyline vertex data

        # The number of bits per coordinate is stored in TRE.
        # For SwissTopo, the TRE parameter at 0x43 is 0x01, 0x44 is 0x04.
        # In vector format, the bits per coordinate is typically 16 or 24.
        # But wait - in the TRE header, there's a field at offset 0x42 that
        # encodes the coordinate precision.

        # Let me look at the TRE flags more carefully
        tre_off = gmp["sections"]["TRE"]
        tre_bytes = data[tre_off:]

        print("\n  TRE header flags area (0x3F-0x49):")
        for i in range(0x3F, 0x4A):
            print(f"    TRE+0x{i:02X}: 0x{tre_bytes[i]:02X} = {tre_bytes[i]}")

        # In QMapShack wiki analysis of IOM.img:
        # TRE+0x42 is called "bytes per coord entry in subdiv rec"
        # It's actually a pair: [0x42]=0x00, [0x43]=0x01, [0x44]=0x04, [0x45]=0x24
        # This might be: encoding=0x00, bpc_low=0x01, bpc_high=0x04, tile_const=0x24(36)

        # But wait - QMapShack says the bits-per-coordinate is encoded differently.
        # Let me check the actual QMapShack raster IMG analysis.

        # =====================================================================
        # STEP D: Direct byte-level analysis of the preamble
        # =====================================================================
        print("\n--- Direct byte-level analysis ---")

        # Parse 20 polyline+E0 pairs
        pos = 0
        records = []
        while pos < min(len(rgn2_data), 3000):
            if rgn2_data[pos] == 0x06 and rgn2_data[pos + 1] == 0xB3:
                preamble = rgn2_data[pos + 2 : pos + 18]
                e0_pos = pos + 18

                if e0_pos + 24 <= len(rgn2_data) and rgn2_data[e0_pos] == 0xE0:
                    bits_field = rgn2_data[e0_pos + 1]
                    idx_size = 2 if bits_field in (0x2D, 0x25) else 1
                    img_idx = struct.unpack_from(
                        "<H" if idx_size == 2 else "<B", rgn2_data, e0_pos + 2
                    )[0]

                    coord_off = e0_pos + 2 + idx_size
                    lat_min = struct.unpack_from("<i", rgn2_data, coord_off)[0]
                    lon_min = struct.unpack_from("<i", rgn2_data, coord_off + 4)[0]
                    lat_max = struct.unpack_from("<i", rgn2_data, coord_off + 8)[0]
                    lon_max = struct.unpack_from("<i", rgn2_data, coord_off + 12)[0]
                    block_size = struct.unpack_from("<I", rgn2_data, coord_off + 16)[0]

                    records.append(
                        {
                            "pos": pos,
                            "preamble": list(preamble),
                            "preamble_hex": preamble.hex(),
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
                    continue
            pos += 1

        print(f"\n  Parsed {len(records)} polyline+E0 pairs")

        # =====================================================================
        # STEP E: Focus on the FIXED vs VARIABLE parts of the preamble
        # =====================================================================
        print("\n--- Fixed vs Variable bytes analysis ---")

        # Group preambles by which bytes change
        for byte_idx in range(16):
            values = set()
            for rec in records:
                values.add(rec["preamble"][byte_idx])
            if len(values) == 1:
                print(f"  Byte {byte_idx:2d}: FIXED = 0x{list(values)[0]:02X}")
            else:
                print(
                    f"  Byte {byte_idx:2d}: VARIABLE ({len(values)} values): {[f'0x{v:02X}' for v in sorted(values)[:10]]}"
                )

        # =====================================================================
        # STEP F: Look at the relationship between variable bytes and E0 coords
        # =====================================================================
        print("\n--- Correlating variable bytes with E0 tile coordinates ---")

        # From the analysis, bytes 0-1 and bytes 12-13 are variable.
        # Bytes 2-7 seem to be fixed: f5 09 11 56 f2 08 (or 02 09)
        # Bytes 8-9: either 00 80 or 02 09
        # Bytes 10-11: variable (0c 17 or 1c 17)
        # Bytes 14-15: always 00 00

        # Wait, let me look at this more carefully. Let me group the records
        # by the "row" pattern (same lat range) and look at how bytes change.

        # All first 10+ tiles have the same lat range (same row):
        # lat_min=552064000, lat_max=551961600
        # Only lon changes. So bytes related to lat should be fixed.

        print("\n  Records grouped by lat range (should indicate rows):")
        lat_groups = {}
        for rec in records:
            key = (rec["lat_min"], rec["lat_max"])
            if key not in lat_groups:
                lat_groups[key] = []
            lat_groups[key].append(rec)

        for key, recs in list(lat_groups.items())[:5]:
            lat_min_deg = garmin_32_to_deg(key[0])
            lat_max_deg = garmin_32_to_deg(key[1])
            print(
                f"\n  Lat range [{lat_max_deg:.6f}, {lat_min_deg:.6f}]: {len(recs)} tiles"
            )
            for rec in recs[:5]:
                lon_min_deg = garmin_32_to_deg(rec["lon_min"])
                lon_max_deg = garmin_32_to_deg(rec["lon_max"])
                print(
                    f"    lon=[{lon_min_deg:.6f}, {lon_max_deg:.6f}] img_idx={rec['img_idx']} "
                    f"preamble={rec['preamble_hex']}"
                )

        # =====================================================================
        # STEP G: Key insight - look at bytes 0-1 and 12-13 vs lon_min/lon_max
        # =====================================================================
        print("\n--- Bytes 0-1 and 12-13 vs lon coordinates ---")

        for rec in records[:15]:
            # Bytes 0-1 as uint16 LE
            b01 = struct.unpack_from("<H", bytes(rec["preamble"]), 0)[0]
            # Bytes 12-13 as uint16 LE
            b1213 = struct.unpack_from("<H", bytes(rec["preamble"]), 12)[0]
            # Bytes 10-11 as uint16 LE
            b1011 = struct.unpack_from("<H", bytes(rec["preamble"]), 10)[0]

            # E0 lon values in different formats
            lon_min_deg = garmin_32_to_deg(rec["lon_min"])
            lon_max_deg = garmin_32_to_deg(rec["lon_max"])

            # Also check lon in "map units" (24-bit style)
            lon_min_24 = rec["lon_min"] >> 8
            lon_max_24 = rec["lon_max"] >> 8

            print(
                f"  b01=0x{b01:04X}({b01:5d}) b1011=0x{b1011:04X}({b1011:5d}) "
                f"b1213=0x{b1213:04X}({b1213:5d}) | "
                f"lon=[{rec['lon_min']:10d}({lon_min_deg:.4f}), {rec['lon_max']:10d}({lon_max_deg:.4f})] "
                f"lon24=[{lon_min_24},{lon_max_24}]"
            )

        # =====================================================================
        # STEP H: Check if b1213 is a running byte offset / tile index
        # =====================================================================
        print("\n--- Bytes 12-13 as tile offset counter ---")

        for rec in records[:15]:
            b1213 = struct.unpack_from("<H", bytes(rec["preamble"]), 12)[0]
            prev_idx = records.index(rec) - 1
            prev_b13 = records[prev_idx]["preamble"][13] if prev_idx >= 0 else 0
            if rec["img_idx"] > 0:
                ratio = f"{b1213 / rec['img_idx']:.2f}"
            else:
                ratio = "N/A"
            print(
                f"  img_idx={rec['img_idx']:5d} b1213={b1213:5d} "
                f"ratio={ratio} "
                f"diff_from_prev={b1213 - prev_b13}"
            )

        # =====================================================================
        # STEP I: Check if the preamble encodes a single point (center of tile)
        # =====================================================================
        print("\n--- Preamble as center point of tile in 32-bit map units ---")

        # What if the preamble encodes just the tile's lon_min (or center) as
        # a delta from the subdivision center, in some bit-packed format?
        #
        # The Garmin vector bitstream uses variable-length encoding.
        # For raster, it might use a fixed-length encoding based on the
        # bits-per-coordinate field from TRE.

        # Let me try: the preamble might be structured as:
        # [2 bytes: lon delta in some format] [6 bytes: fixed?] [2 bytes: something]
        # [2 bytes: another param] [2 bytes: tile offset] [2 bytes: zero]

        # Or the Garmin polyline format for a raster tile might be:
        # From QMapShack wiki, the polyline for raster is actually:
        # 06 B3 [lon_lo lon_hi] [lat_lo lat_hi] [bitmap_info] [bitmap_offset]
        # where lon/lat are deltas from subdivision center in 16-bit signed format

        # Wait - let me re-examine. The QMapShack wiki says for raster IMG:
        # The "polyline" record with type 0x06 subtype 0xB3 actually contains
        # a reference to a bitmap. The structure is:
        #   06 B3 [2 bytes lat_delta] [2 bytes lon_delta] [bitmap info] [bitmap index]

        # But we have 16 bytes of data, not just 8. Let me look at this as
        # TWO separate deltas: one for min corner and one for max corner.

        print(
            "\n--- Hypothesis: preamble = (lat_min_delta, lon_min_delta, lat_max_delta, lon_max_delta) ---"
        )
        print("--- each as int16 LE, in some coordinate space ---")

        # Let's check ALL groups to find the right center
        # The tiles at RGN2 offset 0 belong to TRE7 entry 0, which is
        # for the first subdivision of level 0 (zoom 20), i.e., groups[0]

        # But wait - TRE7 entries 0-4 all have offset=0.
        # That means ALL 5 zoom levels share the same starting data at offset 0.
        # The first polyline+E0 pair at offset 0 is the root tile for zoom 20.

        # Let me check: the root group (groups[0]) center is at:
        g0 = groups[0]
        c_lat_24 = g0["lat_center"]  # 2178000
        c_lon_24 = g0["lon_center"]  # 332672

        c_lat_32 = deg_to_garmin_32(g0["lat_center_deg"])  # should be 557568000
        c_lon_32 = deg_to_garmin_32(g0["lon_center_deg"])  # should be 85164032

        print(f"\n  Group 0 center: lat_24={c_lat_24}, lon_24={c_lon_24}")
        print(f"  Group 0 center: lat_32={c_lat_32}, lon_32={c_lon_32}")
        print(
            f"  Group 0 center: lat_deg={g0['lat_center_deg']:.6f}, lon_deg={g0['lon_center_deg']:.6f}"
        )

        # For the first record:
        rec = records[0]
        preamble = bytes(rec["preamble"])

        # The E0 coords for tile 0:
        print("\n  First tile E0 coords (32-bit):")
        print(f"    lat_min={rec['lat_min']} ({garmin_32_to_deg(rec['lat_min']):.6f})")
        print(f"    lon_min={rec['lon_min']} ({garmin_32_to_deg(rec['lon_min']):.6f})")
        print(f"    lat_max={rec['lat_max']} ({garmin_32_to_deg(rec['lat_max']):.6f})")
        print(f"    lon_max={rec['lon_max']} ({garmin_32_to_deg(rec['lon_max']):.6f})")

        # Convert to 24-bit
        e0_lat_min_24 = rec["lat_min"] >> 8
        e0_lon_min_24 = rec["lon_min"] >> 8
        e0_lat_max_24 = rec["lat_max"] >> 8
        e0_lon_max_24 = rec["lon_max"] >> 8

        print("\n  First tile E0 coords (24-bit, >>8):")
        print(f"    lat_min={e0_lat_min_24}, lon_min={e0_lon_min_24}")
        print(f"    lat_max={e0_lat_max_24}, lon_max={e0_lon_max_24}")

        # Delta from center in 24-bit space
        d_lat_min_24 = e0_lat_min_24 - c_lat_24
        d_lon_min_24 = e0_lon_min_24 - c_lon_24
        d_lat_max_24 = e0_lat_max_24 - c_lat_24
        d_lon_max_24 = e0_lon_max_24 - c_lon_24

        print("\n  Delta from center (24-bit):")
        print(f"    d_lat_min={d_lat_min_24} (0x{d_lat_min_24 & 0xFFFF:04X})")
        print(f"    d_lon_min={d_lon_min_24} (0x{d_lon_min_24 & 0xFFFF:04X})")
        print(f"    d_lat_max={d_lat_max_24} (0x{d_lat_max_24 & 0xFFFF:04X})")
        print(f"    d_lon_max={d_lon_max_24} (0x{d_lon_max_24 & 0xFFFF:04X})")

        # Now check the preamble bytes
        print(f"\n  Preamble: {preamble.hex()}")

        # Check: are the deltas anywhere in the preamble?
        # d_lat_min_24 = -21500 = 0xAC04 as uint16
        # d_lon_min_24 = -58372 = overflow! doesn't fit in int16

        # Hmm, the lon deltas don't fit in int16 from the group 0 center.
        # But maybe the center is NOT group 0. Maybe it's a different subdivision.
        # The tiles at zoom 24 might use a subdivision center that's much closer.

        # Let me check ALL groups to find one where the deltas fit in int16
        print("\n  Searching for a group center where deltas fit in int16...")

        for g_idx, g in enumerate(groups):
            c_lat_24 = g["lat_center"]
            c_lon_24 = g["lon_center"]

            d_lat_min = e0_lat_min_24 - c_lat_24
            d_lon_min = e0_lon_min_24 - c_lon_24
            d_lat_max = e0_lat_max_24 - c_lat_24
            d_lon_max = e0_lon_max_24 - c_lon_24

            if (
                -32768 <= d_lat_min <= 32767
                and -32768 <= d_lon_min <= 32767
                and -32768 <= d_lat_max <= 32767
                and -32768 <= d_lon_max <= 32767
            ):
                print(
                    f"  Group {g_idx}: center=({g['lat_center_deg']:.6f}, {g['lon_center_deg']:.6f}) "
                    f"deltas=({d_lat_min}, {d_lon_min}, {d_lat_max}, {d_lon_max})"
                )

                # Check if preamble bytes match
                p_vals = [
                    struct.unpack_from("<h", preamble, j)[0] for j in range(0, 16, 2)
                ]

                # Try: p_vals[0] = d_lat_min, p_vals[1] = d_lon_min, etc.
                if (
                    p_vals[0] == d_lat_min
                    and p_vals[1] == d_lon_min
                    and p_vals[2] == d_lat_max
                    and p_vals[3] == d_lon_max
                ):
                    print("    EXACT MATCH with p_vals[0:4]!")
                elif p_vals[0] == d_lat_min:
                    print(f"    p_vals[0]={p_vals[0]} matches d_lat_min={d_lat_min}")

        # =====================================================================
        # STEP J: Check the TRE2 group format more carefully
        # =====================================================================
        print("\n--- TRE2 group record format analysis ---")

        # Let me look at the 16-byte group record more carefully
        # Groups[5] has rgn_offset=24 and is the first non-root group for zoom 21
        # The raw hex for groups[5]: 18000000d0660470be20660e720a0000
        # Parse: rgn_off=0x18=24, obj=0x00, lon=0x0466D0=288464, lat=0x2070BE=2130110...
        # Wait, lat should be 0x20_70BE but that's 2129086. But the parser says lat_center_deg=46.046104
        # 46.046104 * 2^24 / 360 = 46.046104 * 46603.7 = 2145904
        # Let me recheck: the raw hex is d0660470be20
        # LE: d0 66 04 = 0x0466D0 = 288464
        #     70 be 20 = 0x20BE70 = 2145904
        # 2145904 * 360 / 2^24 = 2145904 * 360 / 16777216 = 46.046104
        # OK good, that matches.

        # But groups[5] has subdiv_count=2674 and next_level_index=0.
        # What does "flags=0x0E66" mean?
        # And the obj_types byte is 0x00 for groups[0-4] and 0x80 for some others.

        # In the QMapShack wiki analysis, the 16-byte group records are called
        # "TRE2 group records" and have this format:
        #   bytes 0-2: RGN offset (3 bytes LE)
        #   byte 3: object types bitmask
        #   bytes 4-6: center longitude (3 bytes signed LE)
        #   bytes 7-9: center latitude (3 bytes signed LE)
        #   bytes 10-11: flags (uint16 LE)
        #   bytes 12-13: subdivision count (uint16 LE)
        #   bytes 14-15: next group index (uint16 LE)

        # But the standard vector format uses 14-byte subdivision records:
        #   bytes 0-2: RGN offset
        #   byte 3: object types
        #   bytes 4-6: center longitude
        #   bytes 7-9: center latitude
        #   bytes 10-11: width (uint16 LE)
        #   bytes 12-13: height (uint16 LE)

        # So the 16-byte records are NOT standard vector subdivisions.
        # They must be a raster-specific format with subdiv_count + next_level.

        # =====================================================================
        # STEP K: Try interpreting preamble bytes as a Garmin bitstream
        # =====================================================================
        print("\n--- Preamble as Garmin bitstream ---")

        # In the vector polyline format, coordinates are encoded as a bitstream
        # where each coordinate uses a variable number of bits.
        # The number of bits is determined by the TRE bits-per-coordinate setting.

        # For SwissTopo, the TRE has:
        # - TRE+0x42: 0x00, 0x01, 0x04, 0x24, 0x00, 0x01, 0x00, 0x00
        # This might mean: encoding=0, bpc_multiplier=1, bpc_base=4, ...

        # From the Willink doc, the "coordinate bit width" for a subdivision is:
        #   width = flags & 0x3F (or something similar)
        # But for raster maps, the flags field has different meaning.

        # Let me look at the flags field of groups more carefully
        print("\n  Group flags analysis:")
        for i in range(min(10, len(groups))):
            g = groups[i]
            flags = g["flags"]
            print(f"  Group {i}: flags=0x{flags:04X} = {flags:016b}")
            print(f"    bits 0-5 (0x003F): {flags & 0x3F}")
            print(f"    bits 6-7 (0x00C0): {(flags >> 6) & 3}")
            print(f"    bits 8-11 (0x0F00): {(flags >> 8) & 0xF}")
            print(f"    bits 12-15 (0xF000): {(flags >> 12) & 0xF}")

        # =====================================================================
        # STEP L: Look at this from the QMapShack wiki perspective
        # =====================================================================
        print("\n--- QMapShack Raster IMG Wiki Analysis ---")

        # From the QMapShack wiki on RasterImg_AWhiter:
        # The polyline record (type 0x06 subtype 0xB3) in RGN2 for raster maps
        # contains the following structure:
        #
        # Byte 0: 0x06 (polyline type)
        # Byte 1: 0xB3 (subtype: bitmap with extra data)
        # Bytes 2-3: unsigned 16-bit value = extra data length or something
        #   Actually no, let me re-read the wiki more carefully.
        #
        # The wiki says the RGN2 data for the smallest IOM subfile (00355951)
        # has this structure:
        #   0D 01 [8 bytes of POI data]
        #   06 B3 [preamble data]
        #   BC 00 00
        #   E0 2B 01 [E0 record]
        #
        # But I don't have the wiki text here. Let me try to decode from the data.

        # Let me look at the IOM file's RGN2 data for comparison
        iom_path = "/home/tobias/kdrive/garmin/IOM.img"
        if os.path.exists(iom_path):
            with IMGParser(iom_path) as iom:
                iom.parse_header()
                iom.parse_fat()

                iom_gmp_key = None
                for key in iom.subfiles:
                    if "00355951" in key:
                        iom_gmp_key = key
                        break

                if iom_gmp_key:
                    iom_gmp = iom.parse_gmp_container(iom_gmp_key)
                    iom_data = iom_gmp["data"]
                    iom_tre = iom.parse_tre(iom_gmp)
                    iom_rgn = iom.parse_rgn(iom_gmp)

                    iom_groups = iom_tre.get("groups_16byte", [])

                    if "rgn2" in iom_rgn and iom_rgn["rgn2"]["size"] > 0:
                        iom_rgn2_pos = iom_rgn["rgn2"]["position"]
                        iom_rgn2_size = iom_rgn["rgn2"]["size"]
                        iom_rgn2 = iom_data[iom_rgn2_pos : iom_rgn2_pos + iom_rgn2_size]

                        print(f"\n  IOM subfile 00355951 RGN2 ({iom_rgn2_size} bytes):")

                        # Hex dump first 200 bytes
                        for row in range(0, min(200, len(iom_rgn2)), 16):
                            hex_bytes = " ".join(
                                f"{b:02x}" for b in iom_rgn2[row : row + 16]
                            )
                            print(f"    {row:04x}: {hex_bytes}")

                        # Parse polyline records
                        print("\n  IOM polyline records:")
                        iom_pos = 0
                        iom_rec_num = 0
                        while iom_pos < min(len(iom_rgn2), 500) and iom_rec_num < 10:
                            marker = iom_rgn2[iom_pos]

                            if marker == 0x0D:
                                # POI record
                                length = iom_rgn2[iom_pos + 1]
                                rec_end = iom_pos + 2 + length
                                print(f"    0D record at {iom_pos}: length={length}")
                                print(f"      hex: {iom_rgn2[iom_pos:rec_end].hex()}")
                                iom_pos = rec_end
                                iom_rec_num += 1

                            elif marker == 0x06:
                                sub = iom_rgn2[iom_pos + 1]
                                print(f"\n    06 record at {iom_pos}: sub=0x{sub:02X}")

                                # Find the E0 that follows
                                for test_len in range(4, 50):
                                    if (
                                        iom_pos + test_len < len(iom_rgn2)
                                        and iom_rgn2[iom_pos + test_len] == 0xE0
                                    ):
                                        preamble = iom_rgn2[
                                            iom_pos + 2 : iom_pos + test_len
                                        ]
                                        print(f"      preamble_size={test_len - 2}")
                                        print(f"      preamble hex: {preamble.hex()}")

                                        # Parse E0
                                        e0_pos = iom_pos + test_len
                                        e0_bits = iom_rgn2[e0_pos + 1]
                                        idx_size = 1 if e0_bits == 0x2B else 2
                                        img_idx = (
                                            iom_rgn2[e0_pos + 2]
                                            if idx_size == 1
                                            else struct.unpack_from(
                                                "<H", iom_rgn2, e0_pos + 2
                                            )[0]
                                        )
                                        coord_off = e0_pos + 2 + idx_size
                                        lat_min = struct.unpack_from(
                                            "<i", iom_rgn2, coord_off
                                        )[0]
                                        lon_min = struct.unpack_from(
                                            "<i", iom_rgn2, coord_off + 4
                                        )[0]
                                        lat_max = struct.unpack_from(
                                            "<i", iom_rgn2, coord_off + 8
                                        )[0]
                                        lon_max = struct.unpack_from(
                                            "<i", iom_rgn2, coord_off + 12
                                        )[0]
                                        blk_sz = struct.unpack_from(
                                            "<I", iom_rgn2, coord_off + 16
                                        )[0]

                                        print(
                                            f"      E0: bits=0x{e0_bits:02X} idx={img_idx}"
                                        )
                                        print(
                                            f"      E0: lat=[{garmin_32_to_deg(lat_min):.6f},{garmin_32_to_deg(lat_max):.6f}]"
                                        )
                                        print(
                                            f"      E0: lon=[{garmin_32_to_deg(lon_min):.6f},{garmin_32_to_deg(lon_max):.6f}]"
                                        )
                                        print(f"      E0: blk_sz={blk_sz}")

                                        # Get IOM group center for this subdivision
                                        # The first TRE7 entry should map to a group
                                        if iom_groups:
                                            g = iom_groups[0]
                                            print(
                                                f"      Group 0 center: ({g['lat_center_deg']:.6f}, {g['lon_center_deg']:.6f})"
                                            )

                                        break
                                iom_pos += 1
                                iom_rec_num += 1

                            elif marker == 0xBC:
                                print(f"\n    BC boundary at {iom_pos}")
                                iom_pos += 3
                                iom_rec_num += 1

                            elif marker == 0xE0:
                                print(f"\n    E0 at {iom_pos}")
                                iom_pos += 1
                                iom_rec_num += 1

                            else:
                                iom_pos += 1

                        # IOM TRE parameters
                        iom_tre_off = iom_gmp["sections"]["TRE"]
                        iom_tre_bytes = iom_data[iom_tre_off:]
                        print(
                            f"\n  IOM TRE parameters (0x42-0x49): {iom_tre_bytes[0x42:0x4A].hex()}"
                        )

                        # IOM levels
                        print(f"  IOM levels: {iom_tre.get('levels', [])}")

                        # IOM groups
                        if iom_groups:
                            print("  IOM groups (first 5):")
                            for i in range(min(5, len(iom_groups))):
                                g = iom_groups[i]
                                print(
                                    f"    [{i}] rgn_off={g['rgn_offset']} center=({g['lat_center_deg']:.6f},{g['lon_center_deg']:.6f}) "
                                    f"flags=0x{g['flags']:04X} subdivs={g['subdiv_count']} next={g['next_level_index']}"
                                )

        # =====================================================================
        # STEP M: Final decoding attempt - look at the actual byte patterns
        # =====================================================================
        print("\n" + "=" * 80)
        print("STEP M: Final Pattern Analysis")
        print("=" * 80)

        # Key observation from the data:
        # Records 0,4,8,12 have: f2 08 at bytes 8-9 (0x08F2 = 2290 as int16)
        # Records 1,2,3,5,6,7,9,10,11,13,14 have: 02 09 at bytes 8-9 (0x0902 = 2306 as int16)
        #
        # The difference is: 2306 - 2290 = 16
        # And the E0 block_size for records with 0x08F2 (2290) are: 21061, 59602, 50962, 41662
        # The E0 block_size for records with 0x0902 (2306) are: 55937, 55743, 51766, 50118, 57064, 47430, 36761, 47323, 51026, 39939, 39349
        # The first set (2290) might be "last tile in row" (smaller JPEGs?)

        # Wait - the value 2290 and 2306 might be related to the tile width in some units.
        # Let me check: the tile at record 0 spans lon=[5.885839, 5.873566] = 0.012273 deg
        # The tile at record 1 spans lon=[5.922918, 5.910559] = 0.012359 deg
        # In 32-bit Garmin units: 70074368 - 70220800 = -146432 (absolute = 146432)
        # vs 70515712 - 70663168 = -147456 (absolute = 147456)
        # Hmm, not directly related to 2290 or 2306.

        # Let me look at bytes 10-11 more carefully:
        # Records with f208: have 1c17 at bytes 10-11 (0x171C = 5916)
        # Records with 0209: have 0c17 at bytes 10-11 (0x170C = 5900)
        # 5916 - 5900 = 16 (same difference!)
        # These might be tile heights.

        # And bytes 0-1 are clearly related to lon:
        # Record 0: b01=0xF19C, lon=[70220800, 70074368]
        # Record 1: b01=0xF34B, lon=[70663168, 70515712]
        # Record 2: b01=0xF2BB, lon=[70515712, 70368256]
        # The bytes change when lon changes.

        # bytes 4-7 are always: 1156 (= 22033 as int16 = 0x5611)
        # This is a large positive value. 22033 * 360 / 2^24 = 0.473 degrees
        # Or in 32-bit units: 22033 * 180 / 2^31 = 0.001847 degrees
        # Neither of these makes sense as a delta.

        # Wait - bytes 2-3 are always f5 09 (= 2549 as int16)
        # bytes 4-5 are always 11 56 (= 22033 as int16)
        # bytes 6-7 are either f2 08 (= 2290) or 02 09 (= 2306)
        # bytes 8-9 are either 00 80 (= -32768 as int16 or 32768 as uint16) or... wait

        # Let me re-read the raw bytes more carefully
        print("\n  Detailed byte-by-byte analysis:")
        for rec_idx in range(min(15, len(records))):
            rec = records[rec_idx]
            p = rec["preamble"]
            print(f"\n  Record {rec_idx} (img_idx={rec['img_idx']}):")
            print(f"    Bytes: {' '.join(f'{b:02x}' for b in p)}")
            print(
                f"    b0-1:  0x{p[0]:02x}{p[1]:02x} = {struct.unpack_from('<h', bytes(p), 0)[0]}"
            )
            print(
                f"    b2-3:  0x{p[2]:02x}{p[3]:02x} = {struct.unpack_from('<h', bytes(p), 2)[0]}"
            )
            print(
                f"    b4-5:  0x{p[4]:02x}{p[5]:02x} = {struct.unpack_from('<h', bytes(p), 4)[0]}"
            )
            print(
                f"    b6-7:  0x{p[6]:02x}{p[7]:02x} = {struct.unpack_from('<h', bytes(p), 6)[0]}"
            )
            print(
                f"    b8-9:  0x{p[8]:02x}{p[9]:02x} = {struct.unpack_from('<h', bytes(p), 8)[0]}"
            )
            print(
                f"    b10-11: 0x{p[10]:02x}{p[11]:02x} = {struct.unpack_from('<h', bytes(p), 10)[0]}"
            )
            print(
                f"    b12-13: 0x{p[12]:02x}{p[13]:02x} = {struct.unpack_from('<h', bytes(p), 12)[0]}"
            )
            print(
                f"    b14-15: 0x{p[14]:02x}{p[15]:02x} = {struct.unpack_from('<h', bytes(p), 14)[0]}"
            )

        # =====================================================================
        # STEP N: Check the QMapShack wiki RGN2 structure
        # =====================================================================
        print("\n" + "=" * 80)
        print("STEP N: Trying QMapShack Wiki RGN2 Bitmap Structure")
        print("=" * 80)

        # From the QMapShack wiki "RasterImg_AWhiter":
        # The polyline record 06 B3 for raster maps has this structure:
        #
        # 06 B3 [d_lon_start:2] [d_lat_start:2] [d_lon_end:2] [d_lat_end:2]
        #       [d_lon_end2:2] [d_lat_end2:2] [bitmap_flags:2] [bitmap_idx:2]
        #
        # Where d_lon/d_lat are signed 16-bit deltas from the subdivision center
        # in 24-bit map unit space.
        #
        # Actually, the exact structure from the wiki is likely:
        # The polyline has vertices that define the tile boundary.
        # For a rectangular raster tile, it has 4 vertices forming a rectangle.
        # The bitstream encodes these vertices as deltas.

        # But let me try a simpler hypothesis first: maybe the 16 bytes contain
        # exactly what the Garmin vector polyline format would have for a
        # 2-point line (the diagonal of the tile rectangle).

        # In Garmin vector format, a polyline with 2 vertices needs:
        # - First vertex: absolute delta from center (lat, lon)
        # - Second vertex: relative delta from first (lat, lon)
        # Each delta uses a certain number of bits.

        # For SwissTopo with param2=4, maybe each coord delta is 16 bits (2 bytes)?
        # Then 4 deltas × 2 bytes = 8 bytes for the vertices.
        # Plus 8 more bytes for... something else (bitmap index? tile size?)

        # Let me try: bytes 0-7 are the polyline vertices, bytes 8-15 are bitmap info.

        print("\n  Hypothesis: bytes 0-7 = polyline vertices, bytes 8-15 = bitmap info")
        print("  Polyline: start(lat,lon) + end(lat,lon) as int16 deltas from center")

        for rec_idx in range(min(5, len(records))):
            rec = records[rec_idx]
            p = bytes(rec["preamble"])

            # First vertex delta
            d_lat1 = struct.unpack_from("<h", p, 0)[0]
            d_lon1 = struct.unpack_from("<h", p, 2)[0]
            # Second vertex delta
            d_lat2 = struct.unpack_from("<h", p, 4)[0]
            d_lon2 = struct.unpack_from("<h", p, 6)[0]

            # Bitmap info
            info1 = struct.unpack_from("<H", p, 8)[0]
            info2 = struct.unpack_from("<H", p, 10)[0]
            info3 = struct.unpack_from("<H", p, 12)[0]
            info4 = struct.unpack_from("<H", p, 14)[0]

            print(f"\n  Record {rec_idx}:")
            print(f"    Vertex 1 delta: lat={d_lat1}, lon={d_lon1}")
            print(f"    Vertex 2 delta: lat={d_lat2}, lon={d_lon2}")
            print(f"    Bitmap info: {info1}, {info2}, {info3}, {info4}")

            # Try to convert vertex deltas to degrees using group 0 center
            # (using 24-bit map units)
            g = groups[0]
            c_lat = g["lat_center"]  # 2178000
            c_lon = g["lon_center"]  # 332672

            lat1 = c_lat + d_lat1
            lon1 = c_lon + d_lon1
            lat2 = c_lat + d_lat2
            lon2 = c_lon + d_lon2

            print(
                f"    With group 0 center: "
                f"v1=({map_units_24_to_deg(lat1):.6f},{map_units_24_to_deg(lon1):.6f}) "
                f"v2=({map_units_24_to_deg(lat2):.6f},{map_units_24_to_deg(lon2):.6f})"
            )

            # The actual E0 coords are:
            print(
                f"    E0 actual: lat=[{garmin_32_to_deg(rec['lat_min']):.6f},{garmin_32_to_deg(rec['lat_max']):.6f}] "
                f"lon=[{garmin_32_to_deg(rec['lon_min']):.6f},{garmin_32_to_deg(rec['lon_max']):.6f}]"
            )


if __name__ == "__main__":
    main()
