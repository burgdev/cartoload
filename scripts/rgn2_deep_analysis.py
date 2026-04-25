#!/usr/bin/env python3
"""
Deep analysis of RGN2 data structure in Garmin IMG files.

Compares the RGN2 section between the IOM reference file and our output,
focusing on record structure, type bytes, and how GMT determines record lengths.
"""

import struct
import sys
import os

# Add parent directory so we can import img_analysis
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from img_analysis import IMGParser, map_units_to_degrees_32


def hex_dump(data, start_offset=0, bytes_per_line=16, max_bytes=None):
    """Format binary data as hex dump with offset markers."""
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


def analyze_rgn_header_bytes(data, rgn_off, label):
    """Dump the raw RGN header bytes showing section positions."""
    rgn = data[rgn_off:]
    hdr_len = struct.unpack_from("<H", rgn, 0)[0]

    print(f"\n{'=' * 80}")
    print(f"  RGN Header: {label}")
    print(f"  Header length: {hdr_len} bytes (0x{hdr_len:X})")
    print(f"{'=' * 80}")

    print(f"\n  Full RGN header hex dump ({hdr_len} bytes):")
    print(hex_dump(rgn[:hdr_len]))

    # Parse key fields
    print("\n  Parsed fields:")

    # Sub-header common (21 bytes)
    sig = rgn[2:12].decode("ascii", errors="replace")
    version = rgn[12]
    print(f"    [0x00-0x01] Header length: {hdr_len}")
    print(f"    [0x02-0x0B] Signature: {sig!r}")
    print(f"    [0x0C]      Version: {version}")

    # RGN1 at +0x15
    if hdr_len >= 0x1D:
        rgn1_pos = struct.unpack_from("<I", rgn, 0x15)[0]
        rgn1_size = struct.unpack_from("<I", rgn, 0x19)[0]
        print(f"    [0x15-0x18] RGN1 position: 0x{rgn1_pos:X} ({rgn1_pos})")
        print(f"    [0x19-0x1C] RGN1 size:     0x{rgn1_size:X} ({rgn1_size})")

    # RGN2 at +0x1D
    if hdr_len >= 0x25:
        rgn2_pos = struct.unpack_from("<I", rgn, 0x1D)[0]
        rgn2_size = struct.unpack_from("<I", rgn, 0x21)[0]
        print(f"    [0x1D-0x20] RGN2 position: 0x{rgn2_pos:X} ({rgn2_pos})")
        print(f"    [0x21-0x24] RGN2 size:     0x{rgn2_size:X} ({rgn2_size})")

    # RGN3 at +0x39
    if hdr_len >= 0x41:
        rgn3_pos = struct.unpack_from("<I", rgn, 0x39)[0]
        rgn3_size = struct.unpack_from("<I", rgn, 0x3D)[0]
        print(f"    [0x39-0x3C] RGN3 position: 0x{rgn3_pos:X} ({rgn3_pos})")
        print(f"    [0x3D-0x40] RGN3 size:     0x{rgn3_size:X} ({rgn3_size})")

    # RGN4 at +0x55
    if hdr_len >= 0x5D:
        rgn4_pos = struct.unpack_from("<I", rgn, 0x55)[0]
        rgn4_size = struct.unpack_from("<I", rgn, 0x59)[0]
        print(f"    [0x55-0x58] RGN4 position: 0x{rgn4_pos:X} ({rgn4_pos})")
        print(f"    [0x59-0x5C] RGN4 size:     0x{rgn4_size:X} ({rgn4_size})")

    # RGN5 at +0x71
    if hdr_len >= 0x75:
        rgn5_pos = struct.unpack_from("<I", rgn, 0x71)[0]
        rgn5_size = struct.unpack_from("<I", rgn, 0x75)[0]
        print(f"    [0x71-0x74] RGN5 position: 0x{rgn5_pos:X} ({rgn5_pos})")
        print(f"    [0x75-0x78] RGN5 size:     0x{rgn5_size:X} ({rgn5_size})")

    # Show any non-zero bytes between known fields
    print("\n  Raw bytes 0x25-0x39 (between RGN2 and RGN3):")
    print(hex_dump(rgn[0x25:0x39], start_offset=0x25))
    print("  Raw bytes 0x41-0x55 (between RGN3 and RGN4):")
    print(hex_dump(rgn[0x41:0x55], start_offset=0x41))
    print("  Raw bytes 0x5D-0x71 (between RGN4 and RGN5):")
    print(hex_dump(rgn[0x5D:0x71], start_offset=0x5D))
    if hdr_len > 0x79:
        print(f"  Raw bytes 0x79-0x{hdr_len - 1:X} (after RGN5):")
        print(hex_dump(rgn[0x79:hdr_len], start_offset=0x79))

    return hdr_len


def analyze_rgn2_data(data, rgn2_pos, rgn2_size, label, max_dump=500):
    """Deep analysis of RGN2 data section."""
    print(f"\n{'=' * 80}")
    print(f"  RGN2 Data Analysis: {label}")
    print(f"  Position: 0x{rgn2_pos:X}, Size: {rgn2_size} bytes (0x{rgn2_size:X})")
    print(f"{'=' * 80}")

    rgn2_data = data[rgn2_pos : rgn2_pos + rgn2_size]

    # Dump first ~500 bytes
    dump_len = min(len(rgn2_data), max_dump)
    print(f"\n  First {dump_len} bytes of RGN2 data:")
    print(hex_dump(rgn2_data, start_offset=0, max_bytes=dump_len))

    if len(rgn2_data) > dump_len:
        print(f"\n  ... ({len(rgn2_data) - dump_len} more bytes)")

    # Now try to parse record-by-record
    print("\n  --- Record-by-record parsing ---")
    pos = 0
    record_num = 0
    record_types_seen = {}

    while pos < len(rgn2_data) and record_num < 200:
        marker = rgn2_data[pos]

        if marker not in record_types_seen:
            record_types_seen[marker] = 0
        record_types_seen[marker] += 1

        if marker == 0x0D:
            # Type 0x0D - polygon/POI record
            # Need to determine length. In Garmin format, 0x0D records
            # use a variable-length encoding.
            # Let's look at the next few bytes to understand structure
            next_bytes = rgn2_data[pos : pos + 20]
            print(f"\n  Record #{record_num} @ offset 0x{pos:X}: TYPE 0x0D (polygon)")
            print(f"    Raw bytes: {next_bytes.hex()}")

            # Try to figure out length from the data
            # 0x0D records in RGN2 seem to be 20 bytes (per our writer)
            # Let's check: the byte at pos+1 might indicate length or subtype
            subtype = rgn2_data[pos + 1] if pos + 1 < len(rgn2_data) else None
            print(
                f"    Subtype/byte1: 0x{subtype:02X}"
                if subtype is not None
                else "    (truncated)"
            )

            # Look at what comes after various lengths to find the boundary
            if pos + 20 <= len(rgn2_data):
                after_20 = rgn2_data[pos + 20]
                print(f"    Byte after 20-byte record: 0x{after_20:02X}")
            if pos + 22 <= len(rgn2_data):
                after_22 = rgn2_data[pos + 22]
                print(f"    Byte after 22-byte record: 0x{after_22:02X}")

            # The raster outline in our writer is 20 bytes: 0D 01 + 0000 + 0000 + 14*00
            # Let's try 20 bytes and see what follows
            rec_len = 20
            pos += rec_len

        elif marker == 0x06:
            # Type 0x06 - polyline record
            next_bytes = rgn2_data[pos : pos + 20]
            subtype = rgn2_data[pos + 1] if pos + 1 < len(rgn2_data) else None
            print(f"\n  Record #{record_num} @ offset 0x{pos:X}: TYPE 0x06 (polyline)")
            print(f"    Subtype: 0x{subtype:02X}" if subtype is not None else "")
            print(f"    Raw bytes: {next_bytes.hex()}")

            # Our writer produces 18-byte polyline preambles
            if pos + 18 < len(rgn2_data):
                after_18 = rgn2_data[pos + 18]
                print(f"    Byte after 18 bytes: 0x{after_18:02X}")
            if pos + 20 < len(rgn2_data):
                after_20 = rgn2_data[pos + 20]
                print(f"    Byte after 20 bytes: 0x{after_20:02X}")

            # Try to determine actual length
            # Look ahead: if byte at pos+18 is 0xE0, record is 18 bytes
            # If byte at pos+20 is 0xE0, record is 20 bytes
            for try_len in [16, 18, 20, 22, 24]:
                if pos + try_len < len(rgn2_data):
                    peek = rgn2_data[pos + try_len]
                    if peek == 0xE0 or peek == 0x06 or peek == 0x0D:
                        print(
                            f"    --> Record appears to be {try_len} bytes (next marker: 0x{peek:02X})"
                        )
                        pos += try_len
                        break
            else:
                # Default: 18 bytes (our writer's size)
                pos += 18

        elif marker == 0xE0:
            # Type E0 - raster tile record
            if pos + 2 > len(rgn2_data):
                print(
                    f"\n  Record #{record_num} @ offset 0x{pos:X}: TYPE 0xE0 (TRUNCATED)"
                )
                break

            bits_field = rgn2_data[pos + 1]
            print(
                f"\n  Record #{record_num} @ offset 0x{pos:X}: TYPE 0xE0 (raster tile)"
            )
            print(f"    bits_field: 0x{bits_field:02X}")

            # Determine index size
            if bits_field == 0x2B:
                idx_size = 1
                img_idx = rgn2_data[pos + 2]
            elif bits_field == 0x25:
                idx_size = 2
                img_idx = struct.unpack_from("<H", rgn2_data, pos + 2)[0]
            else:
                idx_size = 2
                img_idx = struct.unpack_from("<H", rgn2_data, pos + 2)[0]
                print(f"    WARNING: Unknown bits_field 0x{bits_field:02X}")

            rec_len = 2 + idx_size + 16 + 4  # E0 + bits + idx + 4*coords + block_size
            print(f"    image_index: {img_idx}")
            print(f"    Record length: {rec_len}")

            if pos + rec_len <= len(rgn2_data):
                coord_off = 2 + idx_size
                lat_min = struct.unpack_from("<i", rgn2_data, pos + coord_off)[0]
                lon_min = struct.unpack_from("<i", rgn2_data, pos + coord_off + 4)[0]
                lat_max = struct.unpack_from("<i", rgn2_data, pos + coord_off + 8)[0]
                lon_max = struct.unpack_from("<i", rgn2_data, pos + coord_off + 12)[0]
                block_size = struct.unpack_from("<I", rgn2_data, pos + coord_off + 16)[
                    0
                ]

                print(
                    f"    lat_min: {map_units_to_degrees_32(lat_min):.6f} deg (raw: 0x{lat_min & 0xFFFFFFFF:08X})"
                )
                print(
                    f"    lon_min: {map_units_to_degrees_32(lon_min):.6f} deg (raw: 0x{lon_min & 0xFFFFFFFF:08X})"
                )
                print(
                    f"    lat_max: {map_units_to_degrees_32(lat_max):.6f} deg (raw: 0x{lat_max & 0xFFFFFFFF:08X})"
                )
                print(
                    f"    lon_max: {map_units_to_degrees_32(lon_max):.6f} deg (raw: 0x{lon_max & 0xFFFFFFFF:08X})"
                )
                print(f"    block_size: {block_size}")
                print(f"    Raw: {rgn2_data[pos : pos + rec_len].hex()}")

            pos += rec_len

        elif marker == 0xBC:
            print(f"\n  Record #{record_num} @ offset 0x{pos:X}: TYPE 0xBC (boundary)")
            print(f"    Raw: {rgn2_data[pos : pos + 3].hex()}")
            pos += 3

        elif marker == 0xDE:
            print(
                f"\n  Record #{record_num} @ offset 0x{pos:X}: TYPE 0xDE (ext boundary)"
            )
            print(f"    Raw: {rgn2_data[pos : pos + 3].hex()}")
            pos += 3

        else:
            print(
                f"\n  Record #{record_num} @ offset 0x{pos:X}: UNKNOWN TYPE 0x{marker:02X}"
            )
            print(f"    Context: {rgn2_data[pos : pos + 16].hex()}")
            pos += 1

        record_num += 1

    # Summary
    print("\n  --- Record Type Summary ---")
    for mtype, count in sorted(record_types_seen.items()):
        print(f"    0x{mtype:02X}: {count} records")
    print(f"  Total records parsed: {record_num}")
    print(f"  Bytes consumed: {pos} / {len(rgn2_data)}")

    if pos < len(rgn2_data):
        print(f"  REMAINING: {len(rgn2_data) - pos} bytes unparsed!")
        print(f"  Remaining data starts at offset 0x{pos:X}:")
        print(hex_dump(rgn2_data[pos:], start_offset=pos, max_bytes=200))


def main():
    iom_path = "/home/tobias/git/burgdev/cartoload/tests/data/garmin_samples/IOM.img"
    our_path = "/home/tobias/git/burgdev/cartoload/output/ch_basemap_test.img"

    # =========================================================
    # Part 1: Analyze IOM reference file
    # =========================================================
    print("\n" + "=" * 80)
    print("  PART 1: IOM REFERENCE FILE ANALYSIS")
    print("=" * 80)

    with IMGParser(iom_path) as img:
        img.parse_header()
        img.parse_fat()

        # Find GMP subfile
        gmp_key = None
        for key in img.subfiles:
            if img.subfiles[key]["type"] == "GMP":
                gmp_key = key
                break

        if not gmp_key:
            print("ERROR: No GMP subfile found in IOM.img")
            return

        print(f"  GMP subfile: {gmp_key}")
        gmp = img.parse_gmp_container(gmp_key)
        data = gmp["data"]

        print(f"  GMP data size: {len(data)} bytes")

        # Parse RGN header
        rgn_off = gmp["sections"]["RGN"]
        rgn = data[rgn_off:]

        # RGN2 section info
        rgn2_pos = struct.unpack_from("<I", rgn, 0x1D)[0]
        rgn2_size = struct.unpack_from("<I", rgn, 0x21)[0]

        # Also get TRE7 for cross-reference
        tre_off = gmp["sections"]["TRE"]
        tre = data[tre_off:]
        tre7_pos_field = struct.unpack_from("<I", tre, 0x7C)[0]
        tre7_size_field = struct.unpack_from("<I", tre, 0x80)[0]
        tre7_rec_size = struct.unpack_from("<H", tre, 0x84)[0]

        print(
            f"\n  TRE7 (raster layer): pos=0x{tre7_pos_field:X}, size={tre7_size_field}, rec_size={tre7_rec_size}"
        )

        if tre7_pos_field > 0 and tre7_size_field > 0:
            tre7_data = data[tre7_pos_field : tre7_pos_field + tre7_size_field]
            print(f"  TRE7 raw data: {tre7_data.hex()}")
            print("  TRE7 offsets into RGN2:")
            for i in range(
                0, len(tre7_data), tre7_rec_size if tre7_rec_size > 0 else 4
            ):
                rs = tre7_rec_size if tre7_rec_size > 0 else 4
                if i + rs <= len(tre7_data):
                    off = struct.unpack_from("<I", tre7_data, i)[0]
                    print(f"    Entry {i // rs}: offset 0x{off:X} ({off})")

        # TRE8 data
        tre8_pos_field = struct.unpack_from("<I", tre, 0x8A)[0]
        tre8_size_field = struct.unpack_from("<I", tre, 0x8E)[0]
        if tre8_pos_field > 0 and tre8_size_field > 0:
            tre8_data = data[tre8_pos_field : tre8_pos_field + tre8_size_field]
            print(
                f"\n  TRE8 (object types): pos=0x{tre8_pos_field:X}, size={tre8_size_field}"
            )
            print(f"  TRE8 raw data: {tre8_data.hex()}")
            for i in range(0, len(tre8_data), 3):
                if i + 3 <= len(tre8_data):
                    print(
                        f"    Entry {i // 3}: type=0x{tre8_data[i]:02X} param1=0x{tre8_data[i + 1]:02X} param2=0x{tre8_data[i + 2]:02X}"
                    )

        # TRE4/5/6 check
        print(
            f"\n  TRE4: pos=0x{struct.unpack_from('<I', tre, 0x4A)[0]:X}, size={struct.unpack_from('<I', tre, 0x4E)[0]}"
        )
        print(
            f"  TRE5: pos=0x{struct.unpack_from('<I', tre, 0x58)[0]:X}, size={struct.unpack_from('<I', tre, 0x5C)[0]}"
        )
        print(
            f"  TRE6: pos=0x{struct.unpack_from('<I', tre, 0x66)[0]:X}, size={struct.unpack_from('<I', tre, 0x6A)[0]}"
        )

        # RGN header analysis
        analyze_rgn_header_bytes(data, rgn_off, "IOM Reference")

        # RGN2 data analysis
        analyze_rgn2_data(data, rgn2_pos, rgn2_size, "IOM Reference", max_dump=500)

    # =========================================================
    # Part 2: Analyze our output file
    # =========================================================
    print("\n\n" + "=" * 80)
    print("  PART 2: OUR OUTPUT FILE ANALYSIS")
    print("=" * 80)

    if os.path.exists(our_path):
        with IMGParser(our_path) as img:
            img.parse_header()
            img.parse_fat()

            gmp_key = None
            for key in img.subfiles:
                if img.subfiles[key]["type"] == "GMP":
                    gmp_key = key
                    break

            if not gmp_key:
                print("ERROR: No GMP subfile found in output file")
                return

            print(f"  GMP subfile: {gmp_key}")
            gmp = img.parse_gmp_container(gmp_key)
            data = gmp["data"]

            print(f"  GMP data size: {len(data)} bytes")

            # Parse RGN header
            rgn_off = gmp["sections"]["RGN"]
            rgn = data[rgn_off:]

            # RGN2 section info
            rgn2_pos = struct.unpack_from("<I", rgn, 0x1D)[0]
            rgn2_size = struct.unpack_from("<I", rgn, 0x21)[0]

            # TRE7 cross-reference
            tre_off = gmp["sections"]["TRE"]
            tre = data[tre_off:]
            tre7_pos_field = struct.unpack_from("<I", tre, 0x7C)[0]
            tre7_size_field = struct.unpack_from("<I", tre, 0x80)[0]
            tre7_rec_size = struct.unpack_from("<H", tre, 0x84)[0]

            print(
                f"\n  TRE7 (raster layer): pos=0x{tre7_pos_field:X}, size={tre7_size_field}, rec_size={tre7_rec_size}"
            )
            if tre7_pos_field > 0 and tre7_size_field > 0:
                tre7_data = data[tre7_pos_field : tre7_pos_field + tre7_size_field]
                print(f"  TRE7 raw data: {tre7_data.hex()}")

            # TRE8
            tre8_pos_field = struct.unpack_from("<I", tre, 0x8A)[0]
            tre8_size_field = struct.unpack_from("<I", tre, 0x8E)[0]
            if tre8_pos_field > 0 and tre8_size_field > 0:
                tre8_data = data[tre8_pos_field : tre8_pos_field + tre8_size_field]
                print(f"\n  TRE8 raw data: {tre8_data.hex()}")

            # TRE4/5/6
            print(
                f"\n  TRE4: pos=0x{struct.unpack_from('<I', tre, 0x4A)[0]:X}, size={struct.unpack_from('<I', tre, 0x4E)[0]}"
            )
            print(
                f"  TRE5: pos=0x{struct.unpack_from('<I', tre, 0x58)[0]:X}, size={struct.unpack_from('<I', tre, 0x5C)[0]}"
            )
            print(
                f"  TRE6: pos=0x{struct.unpack_from('<I', tre, 0x66)[0]:X}, size={struct.unpack_from('<I', tre, 0x6A)[0]}"
            )

            # RGN header analysis
            analyze_rgn_header_bytes(data, rgn_off, "Our Output")

            # RGN2 data analysis
            if rgn2_size > 0:
                analyze_rgn2_data(data, rgn2_pos, rgn2_size, "Our Output", max_dump=500)
            else:
                print("\n  RGN2 size is 0 - no data to analyze!")
    else:
        print(f"  Output file not found: {our_path}")

    # =========================================================
    # Part 3: Side-by-side comparison summary
    # =========================================================
    print("\n\n" + "=" * 80)
    print("  PART 3: KEY COMPARISON - RGN Header Bytes 0x15-0x7C")
    print("=" * 80)

    def extract_rgn_header(path, label):
        with IMGParser(path) as img:
            img.parse_header()
            img.parse_fat()
            gmp_key = None
            for key in img.subfiles:
                if img.subfiles[key]["type"] == "GMP":
                    gmp_key = key
                    break
            if not gmp_key:
                return None, None
            gmp = img.parse_gmp_container(gmp_key)
            data = gmp["data"]
            rgn_off = gmp["sections"]["RGN"]
            rgn = data[rgn_off:]
            hdr_len = struct.unpack_from("<H", rgn, 0)[0]
            return rgn[:hdr_len], data

    iom_hdr, iom_data = extract_rgn_header(iom_path, "IOM")
    our_hdr, our_data = extract_rgn_header(our_path, "Ours")

    if iom_hdr and our_hdr:
        print(f"\n  {'Offset':<10} {'IOM Bytes':<40} {'Our Bytes':<40} {'Match'}")
        print(f"  {'-' * 10} {'-' * 40} {'-' * 40} {'-' * 6}")

        max_len = max(len(iom_hdr), len(our_hdr))
        for off in range(0x15, min(max_len, 0x7D), 4):
            iom_chunk = iom_hdr[off : off + 4]
            our_chunk = our_hdr[off : off + 4]
            iom_hex = iom_chunk.hex() if len(iom_chunk) == 4 else "(short)"
            our_hex = our_chunk.hex() if len(our_chunk) == 4 else "(short)"
            match = "OK" if iom_chunk == our_chunk else "DIFF"
            print(f"  0x{off:02X}-0x{off + 3:02X}  {iom_hex:<40} {our_hex:<40} {match}")


if __name__ == "__main__":
    main()
