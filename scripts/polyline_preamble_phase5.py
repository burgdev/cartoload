#!/usr/bin/env python3
"""
Phase 5: Final decoding using QMapShack wiki as reference.

From the wiki, the IOM 00355951 RGN2 structure is:

RGN2 + 000:  0D 01 FFFE 0000 07 1B 21 F8
RGN2 + 008:  06 B3 FFFE 0000 07 1B 21 F8
RGN2 + 010:  BC 00 00
RGN2 + 013:  E0 2B 01
RGN2 + 016:  26940000 FCE90000 2693C000 FCE80000
RGN2 + 026:  00000278

So the structure is:
1. 0D record: 0D 01 FFFE 0000 07 1B 21 F8 (8 bytes)
   - 0D = type marker
   - 01 = length/flags
   - FFFE 0000 = 2 × int16 LE = (-2, 0)
   - 07 1B = 2 × uint8
   - 21 F8 = 2 × uint8

2. 06 record: 06 B3 FFFE 0000 07 1B 21 F8 (8 bytes)
   - 06 = polyline type
   - B3 = subtype
   - FFFE 0000 07 1B 21 F8 = SAME 6 bytes as the 0D record!

3. BC 00 00 (3 bytes) - boundary marker

4. E0 2B 01 (3 bytes) - raster tile type
   - E0 = marker
   - 2B = bits field (1-byte image index)
   - 01 = image index = 1

5. 4 × uint32 LE coords (16 bytes):
   26940000 FCE90000 2693C000 FCE80000
   = lat_min, lon_min, lat_max, lon_max

6. uint32 LE block_size (4 bytes):
   00000278 = 632 bytes

CRITICAL INSIGHT: The 06 polyline record is ONLY 8 BYTES TOTAL in IOM!
06 B3 FFFE 0000 07 1B 21 F8

The preamble after 06 B3 is only 6 bytes: FFFE 0000 07 1B 21 F8

But in SwissTopo, the preamble is 16 bytes! Why?

Looking at the IOM TRE parameters: 10 01 08 24 00 01 00 00
The third byte is 0x08.

SwissTopo TRE parameters: 00 01 04 24 00 01 00 00
The third byte is 0x04.

IOM has 0x08 and the polyline is 6 bytes.
SwissTopo has 0x04 and the polyline is 16 bytes.

Wait, that's inverse! Let me re-examine...

Actually, looking more carefully at the IOM RGN2 data:
0D 01 FFFE 0000 07 1B 21 F8 = 8 bytes (0D + 01 + 6 data bytes)
06 B3 FFFE 0000 07 1B 21 F8 = 8 bytes (06 + B3 + 6 data bytes)

The data after 06 B3 is: FFFE 0000 07 1B 21 F8 (6 bytes)
As int16 LE: -2, 0, 231, -2024 (but that's 4 × int16 = 8 bytes... we only have 6 bytes!)

Let me re-parse: FFFE 0000 07 1B 21 F8
- FFFE = int16 LE = -2
- 0000 = int16 LE = 0
- 07 = uint8 = 7
- 1B = uint8 = 27
- 21 = uint8 = 33
- F8 = uint8 = 248 (or -8 signed)

Hmm, 6 bytes. Let me try different groupings:
- 2 × int16 LE + 4 × uint8: (-2, 0), (7, 27, 33, 248)
- 3 × int16 LE: (-2, 0, 7161)... 0x1B07 = 6919... no.
  FFFE 0000 071B → int16: -2, 0, 0x1B07=6919... that's wrong

Wait, FFFE 0000 07 1B 21 F8 as bytes:
FE FF 00 00 07 1B 21 F8... no, it's stored as FFFE which in LE is bytes FE FF.

Actually, the wiki hex dump shows the bytes in order:
FFFE = bytes FF, FE → uint16 LE = 0xFEFF = 65279 or int16 LE = -257
Hmm no. The wiki says "FFFE" which means bytes 0xFF, 0xFE.
As uint16 LE: 0xFEFF = 65279
As int16 LE: -257

Actually wait. The wiki format shows data as it appears in the hex dump.
So "FFFE" means byte 0xFF followed by byte 0xFE.
As uint16 LE (little-endian): value = 0xFE * 256 + 0xFF = 0xFEFF? No!
LE means low byte first. So byte 0xFF is low, byte 0xFE is high.
uint16 = 0xFEFF = 65279. As int16 = -257.

Hmm, let me look at this differently. In Garmin polyline format,
the data after 06 B3 is a bitstream.

For IOM: 06 B3 [6 bytes bitstream] BC 00 00 E0 ...
For SwissTopo: 06 B3 [16 bytes bitstream] E0 ...

The bitstream length depends on the number of coordinate bits.
In Garmin vector format, the coordinate precision is determined by
the TRE2 subdivision record's flags field.

For IOM, the TRE2 group records show flags like 0x8001, 0x8002, etc.
The low byte of flags is related to the number of bits per coordinate.
0x01 → 2 bits, 0x02 → 4 bits, etc.? That seems too small.

Actually from the Garmin format docs, the subdivision record has:
- width (2 bytes) and height (2 bytes) for vector maps
- These define the extent of the subdivision
- The coordinate bits are derived from width/height

For raster maps, the 16-byte TRE2 record has:
- subdiv_count and next_level instead of width/height
- So where does the coordinate precision come from?

ANSWER: It comes from the TRE header parameters!
IOM: 10 01 08 24 00 01 00 00 → param3 = 0x08 = 8
SwissTopo: 00 01 04 24 00 01 00 00 → param3 = 0x04 = 4

But the polyline is LONGER for SwissTopo (16 bytes) than IOM (6 bytes).
If param3=4 means fewer bits per coord, that would mean LESS data, not more.
Unless param3 is the INVERSE (like a shift value).

Wait - in Garmin format, the coordinate bits per subdivision is often
expressed as a shift/powers-of-2 encoding.
param3=8 → shift by 8 → each coord unit = 256 map units → fewer bits needed
param3=4 → shift by 4 → each coord unit = 16 map units → MORE bits needed

This makes sense! With shift=8, coordinates are coarser (less precision per bit)
so you need fewer bits total. With shift=4, you need more bits.

Let me verify: if shift=4 (SwissTopo), each int16 value represents
a delta of int16 * 2^4 = int16 * 16 in 24-bit map units.

From Phase 3, we found that b01 * 4 ≈ lon delta in 24-bit map units.
But actually, it should be b01 * 2^shift where shift might not be exactly 4.

Wait, we found the ratio was exactly 4.0 between consecutive differences.
Let me reconsider: if b01 is an int16 delta and the actual coordinate
is center + b01 * 2^param, then param would be log2(4) = 2.

Hmm, that doesn't match param3=4 either.

Let me just directly decode the IOM data and compare.
"""

import struct
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.img_analysis import IMGParser

IMG_PATH = "/home/tobias/kdrive/garmin/my_SwissTopo_West.img"
IOM_PATH = "/home/tobias/kdrive/garmin/IOM.img"


def garmin_32_to_deg(val):
    return val * 180.0 / (2**31)


def map_units_24_to_deg(val):
    return val * 360.0 / (2**24)


def main():
    print("=" * 80)
    print("Phase 5: Final Decoding with QMapShack Wiki Reference")
    print("=" * 80)

    # =====================================================================
    # STEP 1: Decode the IOM RGN2 data from the wiki
    # =====================================================================
    print("\n--- IOM 00355951 RGN2 decoding (from wiki) ---")

    # From the wiki hex dump:
    # RGN2 + 000: 0D 01 FFFE 0000 07 1B 21 F8
    #              06 B3 FFFE 0000 07 1B 21 F8
    #              BC 00 00
    #              E0 2B 01
    #              26940000 FCE90000 2693C000 FCE80000
    #              00000278

    # The polyline (06) record data (after 06 B3) is 6 bytes: FFFE 0000 07 1B 21 F8
    # Let me parse this as a Garmin bitstream.

    iom_polyline_data = bytes.fromhex("FFFE0000071B21F8")

    print(f"  IOM polyline data: {iom_polyline_data.hex()}")
    print(f"  As bits: {''.join(f'{b:08b}' for b in iom_polyline_data)}")

    # The E0 coordinates for this tile:
    # 26940000 FCE90000 2693C000 FCE80000
    iom_lat_min = 0x00009426  # LE: 26940000 → 0x00009426 = 37926
    iom_lon_min = 0x0000E9FC  # LE: FCE90000 → 0x0000E9FC... wait

    # Actually these are stored as hex pairs in the wiki:
    # 26940000 = bytes 26 94 00 00 → uint32 LE = 0x00009426 = 37926
    # Hmm, that doesn't make sense for a latitude.

    # Let me re-read: the wiki shows "26940000 FCE90000 2693C000 FCE80000"
    # These are 32-bit values. In Garmin map units:
    # 0x00009426 = 37926 (way too small for lat)
    # But wait - the wiki might be showing the bytes in a different order!

    # Let me parse the raw hex more carefully:
    # 26 94 00 00 → uint32 LE = 0x00009426 = 37926
    # That's not right. Let me try the other way:
    # 26 94 00 00 → uint32 BE = 0x26940000 = 647491584

    # 647491584 * 180 / 2^31 = 647491584 * 180 / 2147483648 = 54.249...
    # Isle of Man is at ~54.25 degrees! This is lat_min.

    # So the coordinates are stored BIG-ENDIAN in the wiki dump?
    # No - the wiki is just showing the raw hex bytes in file order.
    # uint32 LE: bytes 26 94 00 00 → value = 0x00009426 = 37926? No!

    # Wait. In the file, the bytes are: 26 94 00 00
    # uint32 little-endian: value = 0x00 + 0x00*256 + 0x94*65536 + 0x26*16777216
    # = 0x26940000 = 647491584. YES!

    # So: lat_min = 0x26940000 = 647491584 → 54.249° ✓

    iom_lat_min = struct.unpack("<I", bytes.fromhex("26940000"))[0]
    iom_lon_min = struct.unpack("<I", bytes.fromhex("FCE90000"))[0]
    iom_lat_max = struct.unpack("<I", bytes.fromhex("2693C000"))[0]
    iom_lon_max = struct.unpack("<I", bytes.fromhex("FCE80000"))[0]
    iom_blk_sz = struct.unpack("<I", bytes.fromhex("00000278"))[0]

    print("\n  E0 tile coords (from wiki):")
    print(f"    lat_min = {iom_lat_min} ({garmin_32_to_deg(iom_lat_min):.6f})")
    print(f"    lon_min = {iom_lon_min} ({garmin_32_to_deg(iom_lon_min):.6f})")
    print(f"    lat_max = {iom_lat_max} ({garmin_32_to_deg(iom_lat_max):.6f})")
    print(f"    lon_max = {iom_lon_max} ({garmin_32_to_deg(iom_lon_max):.6f})")
    print(f"    blk_sz  = {iom_blk_sz}")

    # The IOM TRE2 groups show center at: FCE880 269380
    # (from wiki: 000000 00 FCE880 269380 8001 0001 0002)
    # lon_center = 0xFCE880 (3 bytes LE: 80 E8 FC) = signed = 0x80 + 0xE8*256 + 0xFC*65536
    # = 0xFCE880 → as signed 24-bit: 0xFCE880 - 0x1000000 = -297856
    # → -297856 * 360 / 2^24 = -6.397... that's the LON? Wait, Garmin lon is negative for west.
    # Actually: 0xFCE880 as 24-bit signed = -297856 → -297856 * 360 / 2^24 = -6.397°
    # Isle of Man is at about -4.5° longitude. Hmm, not matching.

    # Wait, let me re-read the TRE2 format from the wiki:
    # 000000 00 FCE880 269380 8001 0001 0002
    # 3 bytes rgn_off: 000000
    # 1 byte obj_type: 00
    # 3 bytes lon: FCE880 → bytes FC E8 80 → LE = 0x80E8FC? Or 0xFCE880?
    #   LE: 80 E8 FC = 0x80 + 0xE8*256 + 0xFC*65536 = 128 + 59392 + 16515072 = 16574592
    #   → 16574592 * 360 / 2^24 = 355.6°? That's -4.4° (mod 360)
    #   Actually as signed: 0xFCE880 = 16574592 unsigned, but bit 23 is set
    #   So signed = 16574592 - 16777216 = -202624
    #   → -202624 * 360 / 2^24 = -4.349°
    #   Hmm, Isle of Man is at about -4.5°, so close but not exact.
    #   Actually 0x80E8FC might be wrong. Let me recalculate.
    #   Bytes: 80 E8 FC. Little-endian 3-byte: 0x80 + (0xE8 << 8) + (0xFC << 16)
    #   = 128 + 59392 + 16515072 = 16574592
    #   As signed 24-bit: 16574592 - 16777216 = -202624
    #   → -202624 * 360 / 16777216 = -4.348°

    # 3 bytes lat: 269380 → bytes 26 93 80 → LE = 0x80 + 0x93*256 + 0x26*65536
    #   = 128 + 37632 + 2555904 = 2593664
    #   → 2593664 * 360 / 16777216 = 55.67°? No, that's wrong.
    #   Actually for latitude: Garmin uses degrees * 2^24 / 360
    #   Wait no, for lat it should be different. Let me check.
    #   In the existing code: map_units_to_degrees = val * 360.0 / 2^24
    #   2593664 * 360 / 16777216 = 55.67° — too far north
    #   But Isle of Man is at ~54.25°
    #   Let me try: 26 93 80 → 0x809326? No, LE means first byte is least significant.
    #   0x809326 = 8419110. 8419110 * 360 / 16777216 = 180.6°? No.
    #   Hmm. Let me look at this more carefully.
    #   Actually the wiki format might show the data in a different byte order.
    #   "FCE880" in the wiki is the hex representation of the 3-byte value.
    #   So lon_center = 0xFCE880 = -297856 as signed 24-bit (bit 23 set)
    #   → -297856 * 360 / 16777216 = -6.397°? Hmm.

    # OK, I think I'm confusing myself with the wiki format. Let me just
    # parse the IOM binary directly.

    if os.path.exists(IOM_PATH):
        print("\n" + "=" * 80)
        print("IOM Binary Analysis")
        print("=" * 80)

        with IMGParser(IOM_PATH) as iom:
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

                iom_tre_off = iom_gmp["sections"]["TRE"]
                iom_tre_bytes = iom_data[iom_tre_off:]

                print(
                    f"\n  IOM TRE parameters (0x42-0x49): {iom_tre_bytes[0x42:0x4A].hex()}"
                )
                print("  SwissTopo: 00 01 04 24 00 01 00 00")
                print(f"  IOM:       {iom_tre_bytes[0x42:0x4A].hex()}")

                # IOM group centers
                print("\n  IOM TRE2 groups (first 9):")
                for i in range(min(9, len(iom_groups))):
                    g = iom_groups[i]
                    print(
                        f"    [{i}] center=({g['lat_center_deg']:.6f}, {g['lon_center_deg']:.6f}) "
                        f"lat_24={g['lat_center']} lon_24={g['lon_center']} "
                        f"flags=0x{g['flags']:04X} subdivs={g['subdiv_count']} next={g['next_level_index']}"
                    )

                if "rgn2" in iom_rgn and iom_rgn["rgn2"]["size"] > 0:
                    iom_rgn2_pos = iom_rgn["rgn2"]["position"]
                    iom_rgn2 = iom_data[
                        iom_rgn2_pos : iom_rgn2_pos + iom_rgn["rgn2"]["size"]
                    ]

                    print("\n  IOM RGN2 hex dump (first 170 bytes):")
                    for row in range(0, min(170, len(iom_rgn2)), 16):
                        hex_bytes = " ".join(
                            f"{b:02x}" for b in iom_rgn2[row : row + 16]
                        )
                        print(f"    {row:04x}: {hex_bytes}")

                    # Parse the IOM polyline records
                    print("\n  IOM polyline record parsing:")
                    iom_pos = 0
                    rec_num = 0
                    while iom_pos < len(iom_rgn2) and rec_num < 20:
                        marker = iom_rgn2[iom_pos]

                        if marker == 0x0D:
                            length = iom_rgn2[iom_pos + 1]
                            rec_data = iom_rgn2[iom_pos : iom_pos + 2 + length]
                            print(
                                f"\n    0D at {iom_pos}: length={length}, hex={rec_data.hex()}"
                            )
                            # Parse 0D record: same structure as polyline
                            # 0D + length + [data bytes]
                            if length == 6:
                                d = rec_data[2:]
                                vals = [
                                    struct.unpack_from("<h", d, j)[0]
                                    for j in range(0, len(d), 2)
                                ]
                                print(f"      As int16s: {vals}")
                            iom_pos += 2 + length
                            rec_num += 1

                        elif marker == 0x06:
                            sub = iom_rgn2[iom_pos + 1]
                            # The polyline data after 06 B3
                            # We need to figure out how long it is.
                            # Look for the next BC or E0 marker
                            data_start = iom_pos + 2
                            end_pos = data_start
                            while end_pos < len(iom_rgn2):
                                if iom_rgn2[end_pos] in (0xBC, 0xDE, 0xE0, 0x0D, 0x06):
                                    break
                                end_pos += 1

                            polyline_data = iom_rgn2[data_start:end_pos]
                            print(
                                f"\n    06 at {iom_pos}: sub=0x{sub:02X}, data_len={len(polyline_data)}"
                            )
                            print(
                                f"      hex: {iom_rgn2[iom_pos : min(iom_pos + 30, len(iom_rgn2))].hex()}"
                            )
                            print(f"      data: {polyline_data.hex()}")

                            # Parse as int16 LE values
                            if len(polyline_data) >= 2:
                                vals = [
                                    struct.unpack_from("<h", polyline_data, j)[0]
                                    for j in range(0, len(polyline_data) - 1, 2)
                                ]
                                print(f"      As int16s: {vals}")

                            iom_pos = end_pos
                            rec_num += 1

                        elif marker == 0xBC:
                            print(f"\n    BC at {iom_pos}")
                            iom_pos += 3
                            rec_num += 1

                        elif marker == 0xDE:
                            print(f"\n    DE at {iom_pos}")
                            iom_pos += 3
                            rec_num += 1

                        elif marker == 0xE0:
                            e0_bits = iom_rgn2[iom_pos + 1]
                            idx_size = 1 if e0_bits == 0x2B else 2
                            img_idx = (
                                iom_rgn2[iom_pos + 2]
                                if idx_size == 1
                                else struct.unpack_from("<H", iom_rgn2, iom_pos + 2)[0]
                            )
                            coord_off = iom_pos + 2 + idx_size
                            lat_min = struct.unpack_from("<i", iom_rgn2, coord_off)[0]
                            lon_min = struct.unpack_from("<i", iom_rgn2, coord_off + 4)[
                                0
                            ]
                            lat_max = struct.unpack_from("<i", iom_rgn2, coord_off + 8)[
                                0
                            ]
                            lon_max = struct.unpack_from(
                                "<i", iom_rgn2, coord_off + 12
                            )[0]
                            blk_sz = struct.unpack_from("<I", iom_rgn2, coord_off + 16)[
                                0
                            ]

                            print(
                                f"\n    E0 at {iom_pos}: bits=0x{e0_bits:02X} idx={img_idx}"
                            )
                            print(
                                f"      lat=[{garmin_32_to_deg(lat_min):.6f}, {garmin_32_to_deg(lat_max):.6f}]"
                            )
                            print(
                                f"      lon=[{garmin_32_to_deg(lon_min):.6f}, {garmin_32_to_deg(lon_max):.6f}]"
                            )
                            print(f"      blk_sz={blk_sz}")

                            iom_pos += 2 + idx_size + 20
                            rec_num += 1

                        else:
                            iom_pos += 1

                    # Now compare IOM and SwissTopo polyline structures
                    print("\n" + "=" * 80)
                    print("COMPARISON: IOM vs SwissTopo")
                    print("=" * 80)

                    print("""
  IOM polyline data after 06 B3: 6 bytes
    TRE param3 = 0x08
    Sub-type = 0xB3

  SwissTopo polyline data after 06 B3: 16 bytes
    TRE param3 = 0x04
    Sub-type = 0xB3

  Key difference: param3 (0x08 vs 0x04) affects polyline data length.
  The polyline seems to use param3 as a coordinate shift/precision value.

  If param3 = 8 (IOM): coordinates are shifted right by 8 bits → coarser
  If param3 = 4 (SwissTopo): coordinates are shifted right by 4 bits → finer

  The polyline data encodes the tile's geographic bounds as deltas from
  the subdivision center, using the precision specified by param3.

  Let me now verify this with the IOM data...
""")

                    # Get the IOM group 0 center
                    if iom_groups:
                        g = iom_groups[0]
                        c_lat_24 = g["lat_center"]
                        c_lon_24 = g["lon_center"]
                        c_lat_deg = g["lat_center_deg"]
                        c_lon_deg = g["lon_center_deg"]

                        print(
                            f"  IOM Group 0 center: ({c_lat_deg:.6f}, {c_lon_deg:.6f})"
                        )
                        print(f"    lat_24={c_lat_24}, lon_24={c_lon_24}")

                        # The first polyline data: FFFE 0000 07 1B 21 F8 (6 bytes)
                        # Let me parse the first record from binary
                        if len(iom_rgn2) > 8:
                            # First record: 0D 01 FFFE 0000 07 1B 21 F8 (8 bytes total)
                            # Second record: 06 B3 FFFE 0000 07 1B 21 F8 (8 bytes total)
                            # Then: BC 00 00 (3 bytes)
                            # Then: E0 2B 01 + coords + size

                            iom_poly_data = iom_rgn2[
                                10:16
                            ]  # bytes after 06 B3 at offset 8
                            print(
                                f"\n  First IOM polyline data (from offset 10): {iom_poly_data.hex()}"
                            )

                            # Parse as different formats
                            print(
                                f"  As int16 LE: {[struct.unpack_from('<h', iom_poly_data, j)[0] for j in range(0, 6, 2)]}"
                            )
                            print(
                                f"  As uint16 LE: {[struct.unpack_from('<H', iom_poly_data, j)[0] for j in range(0, 6, 2)]}"
                            )

                            # The E0 tile coords:
                            # From wiki: lat_min=0x26940000, lon_min=0xFCE90000, etc.
                            # But let me parse from the actual binary
                            e0_start = (
                                iom_rgn2.index(b"\xe0") if b"\xe0" in iom_rgn2 else -1
                            )
                            if e0_start >= 0:
                                e0_bits = iom_rgn2[e0_start + 1]
                                idx_size = 1 if e0_bits == 0x2B else 2
                                coord_off = e0_start + 2 + idx_size
                                lat_min = struct.unpack_from("<i", iom_rgn2, coord_off)[
                                    0
                                ]
                                lon_min = struct.unpack_from(
                                    "<i", iom_rgn2, coord_off + 4
                                )[0]
                                lat_max = struct.unpack_from(
                                    "<i", iom_rgn2, coord_off + 8
                                )[0]
                                lon_max = struct.unpack_from(
                                    "<i", iom_rgn2, coord_off + 12
                                )[0]

                                print("\n  IOM E0 tile coords:")
                                print(
                                    f"    lat_min = {lat_min} ({garmin_32_to_deg(lat_min):.6f})"
                                )
                                print(
                                    f"    lon_min = {lon_min} ({garmin_32_to_deg(lon_min):.6f})"
                                )
                                print(
                                    f"    lat_max = {lat_max} ({garmin_32_to_deg(lat_max):.6f})"
                                )
                                print(
                                    f"    lon_max = {lon_max} ({garmin_32_to_deg(lon_max):.6f})"
                                )

                                # Convert to 24-bit
                                e0_lat_min_24 = lat_min >> 8
                                e0_lon_min_24 = lon_min >> 8
                                e0_lat_max_24 = lat_max >> 8
                                e0_lon_max_24 = lon_max >> 8

                                # Deltas from center in 24-bit
                                d_lat_min = e0_lat_min_24 - c_lat_24
                                d_lon_min = e0_lon_min_24 - c_lon_24
                                d_lat_max = e0_lat_max_24 - c_lat_24
                                d_lon_max = e0_lon_max_24 - c_lon_24

                                print("\n  Deltas from group 0 center (24-bit):")
                                print(f"    d_lat_min = {d_lat_min}")
                                print(f"    d_lon_min = {d_lon_min}")
                                print(f"    d_lat_max = {d_lat_max}")
                                print(f"    d_lon_max = {d_lon_max}")

                                # If param3=8, shift deltas right by 8:
                                print("\n  Deltas >> 8 (param3=8):")
                                print(f"    d_lat_min >> 8 = {d_lat_min >> 8}")
                                print(f"    d_lon_min >> 8 = {d_lon_min >> 8}")
                                print(f"    d_lat_max >> 8 = {d_lat_max >> 8}")
                                print(f"    d_lon_max >> 8 = {d_lon_max >> 8}")

                                # Parse polyline data as int16
                                poly_vals = [
                                    struct.unpack_from("<h", iom_poly_data, j)[0]
                                    for j in range(0, 6, 2)
                                ]
                                print(f"\n  Polyline int16 values: {poly_vals}")
                                print(
                                    f"  Expected (d_lat_min>>8, d_lon_min>>8, d_lat_max>>8): "
                                    f"({d_lat_min >> 8}, {d_lon_min >> 8}, {d_lat_max >> 8})"
                                )

                                # Check: do poly_vals match deltas >> 8?
                                if len(poly_vals) >= 3:
                                    print("\n  Match check:")
                                    print(
                                        f"    poly[0]={poly_vals[0]} vs d_lat_min>>8={d_lat_min >> 8}: {poly_vals[0] == (d_lat_min >> 8)}"
                                    )
                                    print(
                                        f"    poly[1]={poly_vals[1]} vs d_lon_min>>8={d_lon_min >> 8}: {poly_vals[1] == (d_lon_min >> 8)}"
                                    )
                                    print(
                                        f"    poly[2]={poly_vals[2]} vs d_lat_max>>8={d_lat_max >> 8}: {poly_vals[2] == (d_lat_max >> 8)}"
                                    )

    # =====================================================================
    # STEP 2: Now verify with SwissTopo using param3=4
    # =====================================================================
    print("\n" + "=" * 80)
    print("SwissTopo Verification with param3=4")
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
        rgn2_data = data[rgn2_pos : rgn2_pos + rgn["rgn2"]["size"]]

        # Parse records
        pos = 0
        records = []
        while pos < min(len(rgn2_data), 5000):
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
                    pos = e0_pos + 2 + idx_size + 20
                    continue
            pos += 1

        # Group 0 center
        g = groups[0]
        c_lat_24 = g["lat_center"]
        c_lon_24 = g["lon_center"]

        print(f"  Group 0 center: lat_24={c_lat_24}, lon_24={c_lon_24}")
        print("  SwissTopo param3 = 4 (shift right by 4)")

        # If param3=4, then deltas in the polyline are:
        # polyline_val = (tile_coord_24 - center_coord_24) >> 4
        # OR: polyline_val = (tile_coord_24 - center_coord_24) / 16

        print("\n  Testing: polyline_val = (tile_24 - center_24) >> 4")
        for i in range(min(5, len(records))):
            rec = records[i]
            preamble = rec["preamble"]

            # Parse preamble as int16 LE values
            vals = [struct.unpack_from("<h", preamble, j)[0] for j in range(0, 16, 2)]

            e0_lat_min_24 = rec["lat_min"] >> 8
            e0_lon_min_24 = rec["lon_min"] >> 8
            e0_lat_max_24 = rec["lat_max"] >> 8
            e0_lon_max_24 = rec["lon_max"] >> 8

            # Expected deltas >> 4
            d_lat_min = (e0_lat_min_24 - c_lat_24) >> 4
            d_lon_min = (e0_lon_min_24 - c_lon_24) >> 4
            d_lat_max = (e0_lat_max_24 - c_lat_24) >> 4
            d_lon_max = (e0_lon_max_24 - c_lon_24) >> 4

            print(f"\n  Record {i} (img_idx={rec['img_idx']}):")
            print(f"    Preamble int16: {vals}")
            print(
                f"    Expected (d_lat_min>>4, d_lon_min>>4, d_lat_max>>4, d_lon_max>>4): "
                f"({d_lat_min}, {d_lon_min}, {d_lat_max}, {d_lon_max})"
            )
            print(
                f"    Match: {[v == e for v, e in zip(vals[:4], [d_lat_min, d_lon_min, d_lat_max, d_lon_max])]}"
            )

            # Also try: maybe the ordering is different
            # What if vals[0] = d_lon_min, vals[1] = d_lat_min, etc.?
            alt_expected = [
                (d_lon_min, d_lat_min, d_lon_max, d_lat_max),
                (d_lat_min, d_lon_min, d_lat_max, d_lon_max),
                (d_lat_min, d_lon_min, d_lon_max, d_lon_max),
                (d_lon_min, d_lat_min, d_lon_max, d_lat_max),
            ]
            for name, exp in [
                ("lon,lat,lon,lat", alt_expected[0]),
                ("lat,lon,lat,lon", alt_expected[1]),
            ]:
                match = all(v == e for v, e in zip(vals[:4], exp))
                if match:
                    print(f"    MATCH with ordering {name}: {exp}")

        # Try with different groups
        print("\n  Trying different group centers:")
        for g_idx in range(min(5, len(groups))):
            g = groups[g_idx]
            c_lat = g["lat_center"]
            c_lon = g["lon_center"]

            rec = records[0]
            preamble = rec["preamble"]
            vals = [struct.unpack_from("<h", preamble, j)[0] for j in range(0, 16, 2)]

            e0_lat_min_24 = rec["lat_min"] >> 8
            e0_lon_min_24 = rec["lon_min"] >> 8
            e0_lat_max_24 = rec["lat_max"] >> 8
            e0_lon_max_24 = rec["lon_max"] >> 8

            d_lat_min = (e0_lat_min_24 - c_lat) >> 4
            d_lon_min = (e0_lon_min_24 - c_lon) >> 4

            if vals[0] == d_lat_min or vals[0] == d_lon_min:
                print(
                    f"  Group {g_idx} center ({g['lat_center_deg']:.6f}, {g['lon_center_deg']:.6f}): "
                    f"d_lat_min>>4={d_lat_min}, d_lon_min>>4={d_lon_min}, vals[0]={vals[0]}"
                )

        # Try with the computed center from Phase 4 (lon_24=289040, lat_24=2146304)
        print("\n  Trying Phase 4 computed center (lon_24=289040, lat_24=2146304):")
        computed_lon = 289040
        computed_lat = 2146304

        for i in range(min(5, len(records))):
            rec = records[i]
            preamble = rec["preamble"]
            vals = [struct.unpack_from("<h", preamble, j)[0] for j in range(0, 16, 2)]

            e0_lat_min_24 = rec["lat_min"] >> 8
            e0_lon_min_24 = rec["lon_min"] >> 8
            e0_lat_max_24 = rec["lat_max"] >> 8
            e0_lon_max_24 = rec["lon_max"] >> 8

            # Try >> 4
            d_lat_min = (e0_lat_min_24 - computed_lat) >> 4
            d_lon_min = (e0_lon_min_24 - computed_lon) >> 4
            d_lat_max = (e0_lat_max_24 - computed_lat) >> 4
            d_lon_max = (e0_lon_max_24 - computed_lon) >> 4

            match1 = (
                vals[0] == d_lat_min
                and vals[1] == d_lon_min
                and vals[2] == d_lat_max
                and vals[3] == d_lon_max
            )
            match2 = (
                vals[0] == d_lon_min
                and vals[1] == d_lat_min
                and vals[2] == d_lon_max
                and vals[3] == d_lat_max
            )

            if match1 or match2:
                print(
                    f"  Record {i}: MATCH! Ordering={'lat,lon,lat,lon' if match1 else 'lon,lat,lon,lat'}"
                )

        # Final: try exact arithmetic (no shift, just raw delta)
        print("\n  Final attempt: exact deltas from computed center:")
        for i in range(min(3, len(records))):
            rec = records[i]
            preamble = rec["preamble"]
            vals = [struct.unpack_from("<h", preamble, j)[0] for j in range(0, 16, 2)]

            e0_lat_min_24 = rec["lat_min"] >> 8
            e0_lon_min_24 = rec["lon_min"] >> 8
            e0_lat_max_24 = rec["lat_max"] >> 8
            e0_lon_max_24 = rec["lon_max"] >> 8

            d_lat_min = e0_lat_min_24 - computed_lat
            d_lon_min = e0_lon_min_24 - computed_lon
            d_lat_max = e0_lat_max_24 - computed_lat
            d_lon_max = e0_lon_max_24 - computed_lon

            print(f"\n  Record {i}:")
            print(
                f"    Raw deltas: lat_min={d_lat_min}, lon_min={d_lon_min}, lat_max={d_lat_max}, lon_max={d_lon_max}"
            )
            print(f"    Polyline:   {vals[:4]}")
            print(
                f"    Ratios: lat_min={d_lat_min / vals[0] if vals[0] != 0 else 'N/A':.1f}, "
                f"lon_min={d_lon_min / vals[1] if vals[1] != 0 else 'N/A':.1f}, "
                f"lat_max={d_lat_max / vals[2] if vals[2] != 0 else 'N/A':.1f}, "
                f"lon_max={d_lon_max / vals[3] if vals[3] != 0 else 'N/A':.1f}"
            )


if __name__ == "__main__":
    main()
