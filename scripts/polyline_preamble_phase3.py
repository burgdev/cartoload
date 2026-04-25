#!/usr/bin/env python3
"""
Phase 3: Final verification of the polyline preamble encoding.

Key insight from Phase 2:
- Bytes 0-1 change with lon coordinate
- Byte 2 has 2 values: 0xF5 (first lat row) and 0x90 (second lat row)
- Bytes 3-5 are FIXED: 09 11 56
- Bytes 6-7 have 2 values that differ by 16
- Bytes 8-9: 0x0080 = -32768 always
- Bytes 10-11 differ by 16 (0x171C vs 0x170C)
- Byte 12 is always 0x00
- Byte 13 increments by ~4 each record
- Bytes 14-15 are always 00 00

The polyline subtype is 0xB3 = 10110011.
In Garmin vector format, the subtype encodes the bitstream structure.
The low 2 bits = 3 means "bitmap" type.

Looking at the data more carefully, the preamble might NOT be deltas at all.
It might be a Garmin bitstream encoding of the polyline bounding box
using the bits-per-coordinate from the TRE subdivision record.

Let me try: the preamble is a bitstream where each field uses a specific
number of bits, packed MSB-first, with the following structure:

From the Willink/Pinns Garmin IMG format document:
- Polyline bitstream format:
  1. Number of extra bit pairs (2 bits)
  2. Base latitude delta (signed, N bits)
  3. Base longitude delta (signed, N bits)
  4. For each vertex:
     - Sign bit for lat delta
     - Sign bit for lon delta
     - Lat delta (unsigned)
     - Lon delta (unsigned)
  5. Extra bytes (if indicated by subtype)

But for RASTER tiles with bitmap type (subtype bits 0-1 = 11):
The polyline is a rectangle, so it has a simple structure.

Actually, let me try the simplest hypothesis: this is a Garmin bitstream
with a known number of bits per coordinate.
"""

import struct
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.img_analysis import IMGParser

IMG_PATH = "/home/tobias/kdrive/garmin/my_SwissTopo_West.img"


def garmin_32_to_deg(val):
    return val * 180.0 / (2**31)


def map_units_24_to_deg(val):
    return val * 360.0 / (2**24)


def deg_to_map_units_24(deg):
    return int(deg * (2**24) / 360)


def deg_to_garmin_32(deg):
    return int(deg * (2**31) / 180)


def read_signed_bits(bitstream, bit_offset, num_bits):
    """Read a signed value from a bitstream (MSB first, two's complement)."""
    val = 0
    for i in range(num_bits):
        byte_idx = (bit_offset + i) // 8
        bit_idx = 7 - ((bit_offset + i) % 8)  # MSB first
        if byte_idx < len(bitstream):
            val = (val << 1) | ((bitstream[byte_idx] >> bit_idx) & 1)
        else:
            val = val << 1
    # Sign extend
    if val >= (1 << (num_bits - 1)):
        val -= 1 << num_bits
    return val


def read_unsigned_bits(bitstream, bit_offset, num_bits):
    """Read an unsigned value from a bitstream (MSB first)."""
    val = 0
    for i in range(num_bits):
        byte_idx = (bit_offset + i) // 8
        bit_idx = 7 - ((bit_offset + i) % 8)  # MSB first
        if byte_idx < len(bitstream):
            val = (val << 1) | ((bitstream[byte_idx] >> bit_idx) & 1)
        else:
            val = val << 1
    return val


def main():
    print("=" * 80)
    print("Phase 3: Final Polyline Preamble Verification")
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
        # KEY INSIGHT: Look at the TRE2 group flags field
        # =====================================================================
        # In the Garmin vector format, the subdivision record contains:
        #   width (2 bytes) and height (2 bytes) - these define the bounding box
        #   of the subdivision in "units of 2^16 / 360 degrees" for longitude
        #   and "2^16 / 180 degrees" for latitude (or similar).
        #
        # But for the 16-byte raster group records, these become:
        #   subdiv_count (2 bytes) and next_level (2 bytes)
        #
        # So the raster format uses different fields. The "coordinate precision"
        # for the polyline bitstream must come from somewhere else.
        #
        # Looking at the TRE parameters at 0x42-0x49:
        #   00 01 04 24 00 01 00 00
        # GMT reports "parameters 1 4 36 1" which maps to:
        #   byte 0x43 = 0x01 → "1"
        #   byte 0x44 = 0x04 → "4"
        #   byte 0x45 = 0x24 = 36 → "36"
        #   byte 0x47 = 0x01 → "1"
        #
        # In the QMapShack wiki, these are documented as:
        #   param1 = 1 (unknown)
        #   param2 = 4 (this is the coordinate shift / bits per coordinate key)
        #   param3 = 36 (unknown, maybe tile-related constant)
        #   param4 = 1 (unknown)
        #
        # Wait - maybe param2=4 means the coordinate shift is 4.
        # In Garmin terms, the "coordinate bits" for polylines within a
        # subdivision are determined by the subdivision's width/height.
        # For raster maps, maybe it's a fixed value from the TRE parameters.

        # Actually, let me look at the QMapShack wiki more carefully.
        # From the wiki: The polyline bitstream for raster tiles uses
        # a fixed number of bits per coordinate. This number is related to
        # the zoom level.

        # For SwissTopo at zoom 24, the tile size is about 0.012 degrees.
        # In 24-bit map units: 0.012 * 2^24 / 360 = 2805
        # In 16-bit signed: 2805 fits in int16 easily.
        # But we need to know the EXACT bit width.

        # Let me try a different approach: treat the preamble as a bitstream
        # and try to decode it using different bit widths.

        # =====================================================================
        # APPROACH: Try different bit widths and see which one produces
        # coordinates matching the E0 tile bounds
        # =====================================================================
        print("\n--- Bitstream decoding attempts ---")

        # Parse first polyline
        preamble = rgn2_data[2:18]  # After 06 B3
        print(f"  Preamble hex: {preamble.hex()}")
        print("  Preamble binary:")
        for i, b in enumerate(preamble):
            print(f"    Byte {i:2d}: {b:08b} = 0x{b:02X}")

        # The corresponding E0 tile:
        e0_lat_min = struct.unpack_from("<i", rgn2_data, 20)[0]
        e0_lon_min = struct.unpack_from("<i", rgn2_data, 24)[0]
        e0_lat_max = struct.unpack_from("<i", rgn2_data, 28)[0]
        e0_lon_max = struct.unpack_from("<i", rgn2_data, 32)[0]
        e0_block_size = struct.unpack_from("<I", rgn2_data, 36)[0]

        print("\n  E0 tile coords:")
        print(f"    lat_min={garmin_32_to_deg(e0_lat_min):.6f}")
        print(f"    lon_min={garmin_32_to_deg(e0_lon_min):.6f}")
        print(f"    lat_max={garmin_32_to_deg(e0_lat_max):.6f}")
        print(f"    lon_max={garmin_32_to_deg(e0_lon_max):.6f}")
        print(f"    block_size={e0_block_size}")

        # Get the TRE2 group for this tile
        # TRE7 entry 0 → TRE2 group 0
        g = groups[0]
        c_lat_24 = g["lat_center"]
        c_lon_24 = g["lon_center"]
        c_lat_deg = g["lat_center_deg"]
        c_lon_deg = g["lon_center_deg"]

        print(f"\n  Group 0 center: ({c_lat_deg:.6f}, {c_lon_deg:.6f})")
        print(f"    lat_24={c_lat_24}, lon_24={c_lon_24}")

        # Expected deltas in 24-bit map units
        e0_lat_min_24 = e0_lat_min >> 8
        e0_lon_min_24 = e0_lon_min >> 8
        e0_lat_max_24 = e0_lat_max >> 8
        e0_lon_max_24 = e0_lon_max >> 8

        print("\n  Expected deltas from center (24-bit):")
        d_lat_min = e0_lat_min_24 - c_lat_24
        d_lon_min = e0_lon_min_24 - c_lon_24
        d_lat_max = e0_lat_max_24 - c_lat_24
        d_lon_max = e0_lon_max_24 - c_lon_24
        print(f"    d_lat_min = {d_lat_min}")
        print(f"    d_lon_min = {d_lon_min}")
        print(f"    d_lat_max = {d_lat_max}")
        print(f"    d_lon_max = {d_lon_max}")

        # Expected deltas in 32-bit map units
        c_lat_32 = deg_to_garmin_32(c_lat_deg)
        c_lon_32 = deg_to_garmin_32(c_lon_deg)
        d_lat_min_32 = e0_lat_min - c_lat_32
        d_lon_min_32 = e0_lon_min - c_lon_32
        d_lat_max_32 = e0_lat_max - c_lat_32
        d_lon_max_32 = e0_lon_max - c_lon_32
        print("\n  Expected deltas from center (32-bit):")
        print(f"    d_lat_min = {d_lat_min_32}")
        print(f"    d_lon_min = {d_lon_min_32}")
        print(f"    d_lat_max = {d_lat_max_32}")
        print(f"    d_lon_max = {d_lon_max_32}")

        # =====================================================================
        # CRITICAL TEST: Try the Garmin vector polyline bitstream format
        # =====================================================================
        print("\n--- Garmin Vector Polyline Bitstream Format ---")

        # From the Willink/Pinns "Garmin IMG File Format" document,
        # the polyline bitstream in RGN has this structure:
        #
        # For type 0x06 with subtype indicating bitmap:
        #   2 bits: extra bit pairs count (for polyline = number of additional vertices)
        #   Then for each vertex pair (lat_delta, lon_delta), using the
        #   number of bits determined by the subdivision's coordinate precision
        #
        # The coordinate precision is determined by the TRE subdivision record.
        # In the standard 14-byte format:
        #   The flags field contains the bits-per-coordinate encoding.
        #   Specifically: (flags >> 8) & 0x0F gives a value that determines
        #   the bit width.
        #
        # But for 16-byte raster records, the "flags" field is different.
        # Let me check what values we have.

        print("\n  Group flags → coordinate precision:")
        for i in range(min(10, len(groups))):
            g = groups[i]
            flags = g["flags"]
            # Standard vector format: bpc = (flags >> 8) & 0x0F
            bpc_key = (flags >> 8) & 0x0F
            # The actual bits per coordinate is 2 + 2^bpc_key (or similar)
            # Actually in Garmin format, the lookup is:
            # key → bits: 0→2, 1→4, 2→8, 3→12, 4→16, 5→20, 6→24, 7→28, 8→32
            bpc_table = {0: 2, 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 7: 28, 8: 32}
            bits_per_coord = bpc_table.get(bpc_key, f"unknown({bpc_key})")
            print(
                f"    Group {i}: flags=0x{flags:04X}, bpc_key={bpc_key}, bits_per_coord={bits_per_coord}"
            )

        # =====================================================================
        # TRY: decode the bitstream with different bit widths
        # =====================================================================
        print("\n--- Bitstream decoding with various bit widths ---")

        for bpc in [8, 10, 12, 14, 16, 20, 24]:
            print(f"\n  Trying {bpc} bits per coordinate:")

            # Garmin polyline format: first comes the bounding box as two deltas
            # Then vertex data follows.
            # For a simple rectangle, we need:
            # - 2 bits: number of extra point pairs (should be 1 for rectangle = 2 points)
            # Actually for a 2-point line: num_vertices = 2
            # The bitstream starts with the number of additional vertices (or something)

            # Let me try: just decode as pairs of signed values
            d1 = read_signed_bits(preamble, 0, bpc)
            d2 = read_signed_bits(preamble, bpc, bpc)
            d3 = read_signed_bits(preamble, 2 * bpc, bpc)
            d4 = read_signed_bits(preamble, 3 * bpc, bpc)

            print(f"    Signed deltas: {d1}, {d2}, {d3}, {d4}")
            print(
                f"    In 24-bit coords + center: "
                f"lat={map_units_24_to_deg(c_lat_24 + d1):.6f}, "
                f"lon={map_units_24_to_deg(c_lon_24 + d2):.6f}, "
                f"lat2={map_units_24_to_deg(c_lat_24 + d3):.6f}, "
                f"lon2={map_units_24_to_deg(c_lon_24 + d4):.6f}"
            )
            print(
                f"    Expected: lat=[{garmin_32_to_deg(e0_lat_min):.6f},{garmin_32_to_deg(e0_lat_max):.6f}] "
                f"lon=[{garmin_32_to_deg(e0_lon_min):.6f},{garmin_32_to_deg(e0_lon_max):.6f}]"
            )

            # Check if any combination matches
            results = [
                (c_lat_24 + d1, c_lon_24 + d2),
                (c_lat_24 + d3, c_lon_24 + d4),
            ]
            e0_points = [
                (e0_lat_min_24, e0_lon_min_24),
                (e0_lat_max_24, e0_lon_max_24),
            ]
            for r in results:
                for e in e0_points:
                    if r == e:
                        print(
                            f"    *** MATCH: ({map_units_24_to_deg(r[0]):.6f}, {map_units_24_to_deg(r[1]):.6f}) == "
                            f"({map_units_24_to_deg(e[0]):.6f}, {map_units_24_to_deg(e[1]):.6f})"
                        )

        # =====================================================================
        # CRITICAL: Look at the second row of tiles to see how lat changes
        # =====================================================================
        print("\n--- Second row analysis (lat changes) ---")

        # First record (row 1): preamble = 9c f1 f5 09 11 56 f2 08 00 80 1c 17 00 53 00 00
        # Second row first record (img_idx=27): preamble = 9c f1 90 09 11 56 f2 08 00 a0 1c 17 00 3f 02 00
        # The lat changes from f5 to 90 at byte 2, and byte 9 changes from 80 to a0

        # Records from row 1 (lat ~46.273470 to 46.264887):
        # 9c f1 f5 09 11 56 ...
        # Records from row 2 (lat ~46.264887 to 46.256218):
        # 9c f1 90 09 11 56 ...

        # f5 = 11110101 = -171 in signed (but 245 unsigned)
        # 90 = 10010000 = -17536 as int16 high byte... wait

        # Actually bytes 2-3 as int16:
        # f5 09 = 0x09F5 = 2549 (row 1)
        # 90 09 = 0x0990 = 2448 (row 2)
        # Difference = 2549 - 2448 = 101

        # In 24-bit map units, the lat difference between rows:
        # row1_lat_min_24 = e0_lat_min_24  # 2156500
        # row2_lat_min_24 = 551961600 >> 8  # = 2156100
        # Wait, that's the lat_max of row 1 = lat_min of row 2... no
        # Row 1: lat=[552064000, 551961600] → 24-bit: [2156500, 2156100]
        # Row 2: lat=[551961600, 551859200] → 24-bit: [2156100, 2155700]

        # From row 1 to row 2: lat_min changes by 2156100 - 2156500 = -400
        # The byte 2-3 value changes by 2448 - 2549 = -101

        # -400 / -101 = 3.96... ~ 4
        # So the int16 at bytes 2-3 represents lat delta / 4? (shifted right by 2 bits?)

        print(f"  Row 1 lat_min_24 = {2156500}, Row 2 lat_min_24 = {2156100}")
        print(f"  Difference = {2156100 - 2156500} = -400")
        print("  Byte 2-3 row1 = 2549, row2 = 2448")
        print(f"  Ratio = {-400 / (2448 - 2549):.4f}")

        # Hmm, that's not clean. Let me look at it differently.
        # Maybe the preamble isn't using 24-bit map units at all.
        # Maybe it uses a different scale factor.

        # Let me check the relationship between byte 0-1 and lon more carefully.
        # Record 0: b01 = -3684, lon_min = 70220800
        # Record 1: b01 = -3253, lon_min = 70663168
        # Difference: -3253 - (-3684) = 431
        # lon difference: 70663168 - 70220800 = 442368
        # Ratio: 442368 / 431 = 1026.37... not clean

        # But in 24-bit: 276028 - 274300 = 1728
        # 1728 / 431 = 4.009... ≈ 4!

        print("\n  Checking b01 vs lon in 24-bit space:")
        for i in range(min(10, 72)):
            # Parse records again
            pass

        # Let me compute more carefully with the actual data
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

                    records.append(
                        {
                            "preamble": bytes(preamble),
                            "lat_min": lat_min,
                            "lon_min": lon_min,
                            "lat_max": lat_max,
                            "lon_max": lon_max,
                            "img_idx": img_idx,
                        }
                    )
                    pos = e0_pos + 2 + idx_size + 16 + 4
                    continue
            pos += 1

        # Compute the relationship between preamble bytes 0-1 and lon_min
        print("\n  b01 vs lon_min relationship:")
        for i in range(min(10, len(records))):
            rec = records[i]
            b01 = struct.unpack_from("<h", rec["preamble"], 0)[0]
            lon_min_24 = rec["lon_min"] >> 8
            # b01 * 4 + center_lon_24 should equal lon_min_24?
            test_lon = c_lon_24 + b01 * 4
            print(
                f"  rec {i}: b01={b01:6d}, lon_min_24={lon_min_24:7d}, "
                f"center+b01*4={test_lon:7d}, diff={test_lon - lon_min_24}"
            )

        # Check bytes 2-3 vs lat
        print("\n  b23 vs lat_min relationship:")
        for i in range(min(10, len(records))):
            rec = records[i]
            b23 = struct.unpack_from("<h", rec["preamble"], 2)[0]
            lat_min_24 = rec["lat_min"] >> 8

            test_lat = c_lat_24 + b23 * 4
            print(
                f"  rec {i}: b23={b23:6d}, lat_min_24={lat_min_24:7d}, "
                f"center+b23*4={test_lat:7d}, diff={test_lat - lat_min_24}"
            )

        # Check bytes 4-5 and 6-7
        print("\n  b45 vs lat_max relationship:")
        for i in range(min(10, len(records))):
            rec = records[i]
            b45 = struct.unpack_from("<h", rec["preamble"], 4)[0]
            lat_max_24 = rec["lat_max"] >> 8

            test_lat = c_lat_24 + b45 * 4
            print(
                f"  rec {i}: b45={b45:6d}, lat_max_24={lat_max_24:7d}, "
                f"center+b45*4={test_lat:7d}, diff={test_lat - lat_max_24}"
            )

        print("\n  b67 vs lon_max relationship:")
        for i in range(min(10, len(records))):
            rec = records[i]
            b67 = struct.unpack_from("<h", rec["preamble"], 6)[0]
            lon_max_24 = rec["lon_max"] >> 8

            test_lon = c_lon_24 + b67 * 4
            print(
                f"  rec {i}: b67={b67:6d}, lon_max_24={lon_max_24:7d}, "
                f"center+b67*4={test_lon:7d}, diff={test_lon - lon_max_24}"
            )

        # =====================================================================
        # If b01*4 matches lon_min, then the encoding is:
        # preamble = [lon_min_delta/4, lat_min_delta/4, lon_max_delta/4, lat_max_delta/4]
        # Wait, but b01 is lon and b23 is lat... let me re-check the ordering
        # =====================================================================

        print("\n" + "=" * 80)
        print("CRITICAL TEST: b01*4+center = lon_min?")
        print("=" * 80)

        # From the data above:
        # rec 0: b01=-3684, center_lon_24=332672, test=332672+(-3684*4)=332672-14736=317936
        #         lon_min_24=274300
        # 317936 != 274300. NOT matching.

        # But wait - maybe it's not * 4. Let me check without any multiplication:
        print("\n  b01 + center_lon_24:")
        for i in range(min(5, len(records))):
            rec = records[i]
            b01 = struct.unpack_from("<h", rec["preamble"], 0)[0]
            lon_min_24 = rec["lon_min"] >> 8
            print(f"  rec {i}: {c_lon_24} + {b01} = {c_lon_24 + b01} vs {lon_min_24}")

        # Nope. Let me try b01 as a delta in 32-bit space / some divisor:
        # 70220800 - 85164032 = -14943232
        # -14943232 / -3684 = 4056.something... not clean.

        # Let me try a completely different interpretation.
        # What if bytes 0-1 are the LOW 16 bits of the lon coordinate?
        # lon_min_32 = 70220800 = 0x042F7C00
        # lon_min_lo = 0x7C00 = 31744
        # b01 = 0xF19C = -3684 (or 61852 unsigned)
        # 31744 != 61852. No match.

        # What about lon in 24-bit?
        # lon_min_24 = 274300 = 0x0430EC
        # lon_min_24_lo = 0x0EC... hmm

        # OK, let me try yet another approach. Let me look at the DIFFERENCE
        # between consecutive records and the DIFFERENCE between coordinates.

        print("\n--- Consecutive record differences ---")
        for i in range(1, min(10, len(records))):
            rec0 = records[i - 1]
            rec1 = records[i]
            db01 = (
                struct.unpack_from("<h", rec1["preamble"], 0)[0]
                - struct.unpack_from("<h", rec0["preamble"], 0)[0]
            )
            dlon = rec1["lon_min"] - rec0["lon_min"]
            dlon_24 = (rec1["lon_min"] >> 8) - (rec0["lon_min"] >> 8)

            db23 = (
                struct.unpack_from("<h", rec1["preamble"], 2)[0]
                - struct.unpack_from("<h", rec0["preamble"], 2)[0]
            )
            dlat_24 = (rec1["lat_min"] >> 8) - (rec0["lat_min"] >> 8)

            print(
                f"  rec {i - 1}->{i}: db01={db01:5d}, dlon_32={dlon:10d}, dlon_24={dlon_24:6d}, "
                f"ratio_32={dlon / db01 if db01 != 0 else 'N/A':.1f}, ratio_24={dlon_24 / db01 if db01 != 0 else 'N/A':.1f} | "
                f"db23={db23:5d}, dlat_24={dlat_24:6d}"
            )

        # =====================================================================
        # FINAL APPROACH: Read the QMapShack wiki directly
        # =====================================================================
        print("\n" + "=" * 80)
        print("FINAL: Try reading QMapShack raster IMG wiki")
        print("=" * 80)

        # I'll try to fetch the wiki page for the exact format description
        print("Attempting to read QMapShack wiki for raster IMG format...")


if __name__ == "__main__":
    main()
