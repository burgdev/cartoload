"""
Side-by-side comparison of Garmin IMG files.

Compares RGN headers and RGN2 data between two IMG files,
useful for validating output against reference files.
"""

import struct

from .img_parser import IMGParser, map_units_to_degrees_32, format_hex_dump


def _extract_rgn_header(img_parser, gmp_key):
    """Extract RGN header bytes and GMP data from a parsed IMG file."""
    gmp = img_parser.parse_gmp_container(gmp_key)
    data = gmp["data"]
    rgn_off = gmp["sections"]["RGN"]
    rgn = data[rgn_off:]
    hdr_len = struct.unpack_from("<H", rgn, 0)[0]
    return rgn[:hdr_len], data, gmp


def _analyze_rgn_header_bytes(data, rgn_off, label, echo):
    """Dump the raw RGN header bytes showing section positions."""
    rgn = data[rgn_off:]
    hdr_len = struct.unpack_from("<H", rgn, 0)[0]

    echo(f"\n{'=' * 80}")
    echo(f"  RGN Header: {label}")
    echo(f"  Header length: {hdr_len} bytes (0x{hdr_len:X})")
    echo(f"{'=' * 80}")

    echo(f"\n  Full RGN header hex dump ({hdr_len} bytes):")
    echo(format_hex_dump(rgn[:hdr_len]))

    # Parse key fields
    echo("\n  Parsed fields:")

    sig = rgn[2:12].decode("ascii", errors="replace")
    version = rgn[12]
    echo(f"    [0x00-0x01] Header length: {hdr_len}")
    echo(f"    [0x02-0x0B] Signature: {sig!r}")
    echo(f"    [0x0C]      Version: {version}")

    field_defs = [
        (0x15, "RGN1 position"),
        (0x19, "RGN1 size"),
        (0x1D, "RGN2 position"),
        (0x21, "RGN2 size"),
    ]
    if hdr_len >= 0x41:
        field_defs.extend(
            [
                (0x39, "RGN3 position"),
                (0x3D, "RGN3 size"),
            ]
        )
    if hdr_len >= 0x5D:
        field_defs.extend(
            [
                (0x55, "RGN4 position"),
                (0x59, "RGN4 size"),
            ]
        )
    if hdr_len >= 0x75:
        field_defs.extend(
            [
                (0x71, "RGN5 position"),
                (0x75, "RGN5 size"),
            ]
        )

    for off, desc in field_defs:
        if off + 4 <= hdr_len:
            val = struct.unpack_from("<I", rgn, off)[0]
            echo(f"    [0x{off:02X}-0x{off + 3:02X}] {desc}: 0x{val:X} ({val})")

    # Show raw bytes between known fields
    gaps = [
        (0x25, 0x39, "between RGN2 and RGN3"),
        (0x41, 0x55, "between RGN3 and RGN4"),
        (0x5D, 0x71, "between RGN4 and RGN5"),
    ]
    for start, end, desc in gaps:
        if end <= hdr_len:
            echo(f"\n  Raw bytes 0x{start:02X}-0x{end - 1:02X} ({desc}):")
            echo(format_hex_dump(rgn[start:end]))

    if hdr_len > 0x79:
        echo(f"\n  Raw bytes 0x79-0x{hdr_len - 1:X} (after RGN5):")
        echo(format_hex_dump(rgn[0x79:hdr_len]))

    return hdr_len


def _analyze_rgn2_data(data, rgn2_pos, rgn2_size, label, echo, max_dump=500):
    """Deep analysis of RGN2 data section."""
    echo(f"\n{'=' * 80}")
    echo(f"  RGN2 Data Analysis: {label}")
    echo(f"  Position: 0x{rgn2_pos:X}, Size: {rgn2_size} bytes (0x{rgn2_size:X})")
    echo(f"{'=' * 80}")

    rgn2_data = data[rgn2_pos : rgn2_pos + rgn2_size]

    dump_len = min(len(rgn2_data), max_dump)
    echo(f"\n  First {dump_len} bytes of RGN2 data:")
    echo(format_hex_dump(rgn2_data[:dump_len]))

    if len(rgn2_data) > dump_len:
        echo(f"\n  ... ({len(rgn2_data) - dump_len} more bytes)")

    # Parse record-by-record
    echo("\n  --- Record-by-record parsing ---")
    pos = 0
    record_num = 0
    record_types_seen = {}

    while pos < len(rgn2_data) and record_num < 200:
        marker = rgn2_data[pos]

        if marker not in record_types_seen:
            record_types_seen[marker] = 0
        record_types_seen[marker] += 1

        if marker == 0x0D:
            next_bytes = rgn2_data[pos : min(pos + 20, len(rgn2_data))]
            echo(f"\n  Record #{record_num} @ offset 0x{pos:X}: TYPE 0x0D (polygon)")
            echo(f"    Raw bytes: {next_bytes.hex()}")
            subtype = rgn2_data[pos + 1] if pos + 1 < len(rgn2_data) else None
            if subtype is not None:
                echo(f"    Subtype/byte1: 0x{subtype:02X}")
            if pos + 20 <= len(rgn2_data):
                after_20 = rgn2_data[pos + 20]
                echo(f"    Byte after 20-byte record: 0x{after_20:02X}")
            pos += 20

        elif marker == 0x06:
            next_bytes = rgn2_data[pos : min(pos + 20, len(rgn2_data))]
            subtype = rgn2_data[pos + 1] if pos + 1 < len(rgn2_data) else None
            echo(f"\n  Record #{record_num} @ offset 0x{pos:X}: TYPE 0x06 (polyline)")
            if subtype is not None:
                echo(f"    Subtype: 0x{subtype:02X}")
            echo(f"    Raw bytes: {next_bytes.hex()}")
            # Try to determine length by looking ahead
            for try_len in [16, 18, 20, 22, 24]:
                if pos + try_len < len(rgn2_data):
                    peek = rgn2_data[pos + try_len]
                    if peek == 0xE0 or peek == 0x06 or peek == 0x0D:
                        echo(
                            f"    --> Record appears to be {try_len} bytes (next marker: 0x{peek:02X})"
                        )
                        pos += try_len
                        break
            else:
                pos += 18

        elif marker == 0xE0:
            if pos + 2 > len(rgn2_data):
                echo(
                    f"\n  Record #{record_num} @ offset 0x{pos:X}: TYPE 0xE0 (TRUNCATED)"
                )
                break

            bits_field = rgn2_data[pos + 1]
            echo(
                f"\n  Record #{record_num} @ offset 0x{pos:X}: TYPE 0xE0 (raster tile)"
            )
            echo(f"    bits_field: 0x{bits_field:02X}")

            if bits_field == 0x2B:
                idx_size = 1
                img_idx = rgn2_data[pos + 2]
            else:
                idx_size = 2
                img_idx = struct.unpack_from("<H", rgn2_data, pos + 2)[0]
                if bits_field not in (0x25, 0x2D):
                    echo(f"    WARNING: Unknown bits_field 0x{bits_field:02X}")

            rec_len = 2 + idx_size + 16 + 4
            echo(f"    image_index: {img_idx}")
            echo(f"    Record length: {rec_len}")

            if pos + rec_len <= len(rgn2_data):
                coord_off = 2 + idx_size
                lat_min = struct.unpack_from("<i", rgn2_data, pos + coord_off)[0]
                lon_min = struct.unpack_from("<i", rgn2_data, pos + coord_off + 4)[0]
                lat_max = struct.unpack_from("<i", rgn2_data, pos + coord_off + 8)[0]
                lon_max = struct.unpack_from("<i", rgn2_data, pos + coord_off + 12)[0]
                block_size = struct.unpack_from("<I", rgn2_data, pos + coord_off + 16)[
                    0
                ]

                echo(
                    f"    lat_min: {map_units_to_degrees_32(lat_min):.6f} deg (raw: 0x{lat_min & 0xFFFFFFFF:08X})"
                )
                echo(
                    f"    lon_min: {map_units_to_degrees_32(lon_min):.6f} deg (raw: 0x{lon_min & 0xFFFFFFFF:08X})"
                )
                echo(
                    f"    lat_max: {map_units_to_degrees_32(lat_max):.6f} deg (raw: 0x{lat_max & 0xFFFFFFFF:08X})"
                )
                echo(
                    f"    lon_max: {map_units_to_degrees_32(lon_max):.6f} deg (raw: 0x{lon_max & 0xFFFFFFFF:08X})"
                )
                echo(f"    block_size: {block_size}")
                echo(f"    Raw: {rgn2_data[pos : pos + rec_len].hex()}")

            pos += rec_len

        elif marker == 0xBC:
            echo(f"\n  Record #{record_num} @ offset 0x{pos:X}: TYPE 0xBC (boundary)")
            echo(f"    Raw: {rgn2_data[pos : pos + 3].hex()}")
            pos += 3

        elif marker == 0xDE:
            echo(
                f"\n  Record #{record_num} @ offset 0x{pos:X}: TYPE 0xDE (ext boundary)"
            )
            echo(f"    Raw: {rgn2_data[pos : pos + 3].hex()}")
            pos += 3

        else:
            echo(
                f"\n  Record #{record_num} @ offset 0x{pos:X}: UNKNOWN TYPE 0x{marker:02X}"
            )
            echo(f"    Context: {rgn2_data[pos : min(pos + 16, len(rgn2_data))].hex()}")
            pos += 1

        record_num += 1

    # Summary
    echo("\n  --- Record Type Summary ---")
    for mtype, count in sorted(record_types_seen.items()):
        echo(f"    0x{mtype:02X}: {count} records")
    echo(f"  Total records parsed: {record_num}")
    echo(f"  Bytes consumed: {pos} / {len(rgn2_data)}")

    if pos < len(rgn2_data):
        echo(f"  REMAINING: {len(rgn2_data) - pos} bytes unparsed!")
        echo(f"  Remaining data starts at offset 0x{pos:X}:")
        echo(format_hex_dump(rgn2_data[pos : pos + min(200, len(rgn2_data) - pos)]))


def compare_files(path1, path2, echo):
    """Compare two IMG files side by side.

    Args:
        path1: Path to the first (reference) IMG file.
        path2: Path to the second (output) IMG file.
        echo: Callable for output (e.g. click.echo).
    """
    label1 = "File 1 (reference)"
    label2 = "File 2 (output)"

    # Parse both files
    results = {}
    for label, path in [(label1, path1), (label2, path2)]:
        echo(f"\n{'#' * 80}")
        echo(f"#  {label}: {path}")
        echo(f"{'#' * 80}")

        with IMGParser(path) as img:
            img.parse_header()
            img.parse_fat()

            gmp_key = None
            for key in img.subfiles:
                if img.subfiles[key]["type"] == "GMP":
                    gmp_key = key
                    break

            if not gmp_key:
                echo(f"  ERROR: No GMP subfile found in {path}")
                results[label] = None
                continue

            echo(f"  GMP subfile: {gmp_key}")
            gmp = img.parse_gmp_container(gmp_key)
            data = gmp["data"]
            echo(f"  GMP data size: {len(data)} bytes")

            rgn_off = gmp["sections"]["RGN"]
            rgn = data[rgn_off:]
            rgn2_pos = struct.unpack_from("<I", rgn, 0x1D)[0]
            rgn2_size = struct.unpack_from("<I", rgn, 0x21)[0]

            # Show TRE7/8 cross-reference
            tre_off = gmp["sections"]["TRE"]
            tre = data[tre_off:]

            tre7_pos = struct.unpack_from("<I", tre, 0x7C)[0]
            tre7_size = struct.unpack_from("<I", tre, 0x80)[0]
            tre7_rec_size = struct.unpack_from("<H", tre, 0x84)[0]
            echo(
                f"\n  TRE7 (raster layer): pos=0x{tre7_pos:X}, size={tre7_size}, rec_size={tre7_rec_size}"
            )

            if tre7_pos > 0 and tre7_size > 0:
                tre7_data = data[tre7_pos : tre7_pos + tre7_size]
                echo(f"  TRE7 raw data: {tre7_data.hex()}")
                rec_size = tre7_rec_size if tre7_rec_size > 0 else 4
                echo("  TRE7 offsets into RGN2:")
                for i in range(0, len(tre7_data), rec_size):
                    if i + rec_size <= len(tre7_data):
                        off = struct.unpack_from("<I", tre7_data, i)[0]
                        echo(f"    Entry {i // rec_size}: offset 0x{off:X} ({off})")

            tre8_pos = struct.unpack_from("<I", tre, 0x8A)[0]
            tre8_size = struct.unpack_from("<I", tre, 0x8E)[0]
            if tre8_pos > 0 and tre8_size > 0:
                tre8_data = data[tre8_pos : tre8_pos + tre8_size]
                echo(f"\n  TRE8 (object types): pos=0x{tre8_pos:X}, size={tre8_size}")
                echo(f"  TRE8 raw data: {tre8_data.hex()}")
                for i in range(0, len(tre8_data), 3):
                    if i + 3 <= len(tre8_data):
                        echo(
                            f"    Entry {i // 3}: type=0x{tre8_data[i]:02X} param1=0x{tre8_data[i + 1]:02X} param2=0x{tre8_data[i + 2]:02X}"
                        )

            for name, off in [("TRE4", 0x4A), ("TRE5", 0x58), ("TRE6", 0x66)]:
                p = struct.unpack_from("<I", tre, off)[0]
                s = struct.unpack_from("<I", tre, off + 4)[0]
                echo(f"  {name}: pos=0x{p:X}, size={s}")

            # RGN header analysis
            _analyze_rgn_header_bytes(data, rgn_off, label, echo)

            # RGN2 data analysis
            if rgn2_size > 0:
                _analyze_rgn2_data(data, rgn2_pos, rgn2_size, label, echo, max_dump=500)
            else:
                echo("\n  RGN2 size is 0 - no data to analyze!")

            results[label] = (rgn_off, gmp, data)

    # Side-by-side header comparison
    echo(f"\n\n{'=' * 80}")
    echo("  KEY COMPARISON - RGN Header Bytes 0x15-0x7C")
    echo(f"{'=' * 80}")

    hdr1, _, _ = results.get(label1, (None, None, None))
    hdr2, _, _ = (
        results.get(label2, (None, None, None))
        if results.get(label2)
        else (None, None, None)
    )

    # Re-extract headers for comparison
    def _get_header(path):
        with IMGParser(path) as img:
            img.parse_header()
            img.parse_fat()
            gmp_key = None
            for key in img.subfiles:
                if img.subfiles[key]["type"] == "GMP":
                    gmp_key = key
                    break
            if not gmp_key:
                return None
            gmp = img.parse_gmp_container(gmp_key)
            data = gmp["data"]
            rgn_off = gmp["sections"]["RGN"]
            rgn = data[rgn_off:]
            hdr_len = struct.unpack_from("<H", rgn, 0)[0]
            return rgn[:hdr_len]

    iom_hdr = _get_header(path1)
    our_hdr = _get_header(path2)

    if iom_hdr is not None and our_hdr is not None:
        echo(f"\n  {'Offset':<10} {'File 1 Bytes':<40} {'File 2 Bytes':<40} {'Match'}")
        echo(f"  {'-' * 10} {'-' * 40} {'-' * 40} {'-' * 6}")

        max_len = max(len(iom_hdr), len(our_hdr))
        for off in range(0x15, min(max_len, 0x7D), 4):
            chunk1 = iom_hdr[off : off + 4]
            chunk2 = our_hdr[off : off + 4]
            hex1 = chunk1.hex() if len(chunk1) == 4 else "(short)"
            hex2 = chunk2.hex() if len(chunk2) == 4 else "(short)"
            match = "OK" if chunk1 == chunk2 else "DIFF"
            echo(f"  0x{off:02X}-0x{off + 3:02X}  {hex1:<40} {hex2:<40} {match}")
