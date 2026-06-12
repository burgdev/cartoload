"""
Side-by-side comparison of Garmin IMG files.

Compares TRE/RGN/LBL headers and RGN2 data between two IMG files,
with normalization of variable fields (dates, map IDs, UUIDs) so
comparison focuses on structural differences.
"""

import struct

from .img_parser import (
    IMGParser,
    decode_3byte_signed,
    map_units_to_degrees,
    map_units_to_degrees_32,
    format_hex_dump,
)

# Fields to mask during normalization (offset, size, description)
# These are fields that vary per-build and are not structurally meaningful
_NORMALIZE_TRE = [
    (0x0E, 7, "date"),
    (0x74, 4, "map_id"),
    (0x9A, 16, "map_id_hash/UUID"),
    (0xCF, 4, "matching_number"),
]

_NORMALIZE_RGN = [
    (0x0E, 7, "date"),
]

_NORMALIZE_LBL = [
    (0x0E, 7, "date"),
]

# Named fields for TRE header (offset, size, field_name)
_TRE_FIELDS = [
    (0x00, 2, "header_length"),
    (0x02, 10, "signature"),
    (0x0C, 1, "version"),
    (0x0D, 1, "lock"),
    (0x0E, 7, "date"),
    (0x15, 3, "north_bound"),
    (0x18, 3, "east_bound"),
    (0x1B, 3, "south_bound"),
    (0x1E, 3, "west_bound"),
    (0x21, 4, "TRE1_position"),
    (0x25, 4, "TRE1_size"),
    (0x29, 4, "TRE2_position"),
    (0x2D, 4, "TRE2_size"),
    (0x31, 4, "TRE3_position"),
    (0x35, 4, "TRE3_size"),
    (0x39, 2, "TRE3_item_size"),
    (0x3B, 4, "padding_0x3B"),
    (0x3F, 1, "flags"),
    (0x40, 2, "display_priority"),
    (0x42, 8, "more_flags"),
    (0x4A, 4, "TRE4_position"),
    (0x4E, 4, "TRE4_size"),
    (0x52, 2, "TRE4_rec_size"),
    (0x54, 4, "TRE4_padding"),
    (0x58, 4, "TRE5_position"),
    (0x5C, 4, "TRE5_size"),
    (0x60, 2, "TRE5_rec_size"),
    (0x62, 4, "TRE5_padding"),
    (0x66, 4, "TRE6_position"),
    (0x6A, 4, "TRE6_size"),
    (0x6E, 2, "TRE6_rec_size"),
    (0x70, 4, "TRE6_padding"),
    (0x74, 4, "map_id"),
    (0x78, 4, "padding_0x78"),
    (0x7C, 4, "TRE7_position"),
    (0x80, 4, "TRE7_size"),
    (0x84, 2, "TRE7_rec_size"),
    (0x86, 4, "TRE7_padding"),
    (0x8A, 4, "TRE8_position"),
    (0x8E, 4, "TRE8_size"),
    (0x92, 2, "TRE8_rec_size"),
    (0x94, 6, "TRE8_padding"),
    (0x9A, 16, "map_id_hash"),
    (0xAA, 4, "padding_0xAA"),
    (0xAE, 4, "TRE9_position"),
    (0xB2, 4, "TRE9_size"),
    (0xB6, 2, "TRE9_rec_size"),
    (0xB8, 4, "TRE9_padding"),
    (0xBC, 4, "TRE10_position"),
    (0xC0, 4, "TRE10_size"),
    (0xC4, 2, "TRE10_rec_size"),
    (0xC6, 4, "TRE10_padding"),
    (0xCA, 5, "padding_0xCA"),
    (0xCF, 4, "matching_number"),
]

# Named fields for RGN header
_RGN_FIELDS = [
    (0x00, 2, "header_length"),
    (0x02, 10, "signature"),
    (0x0C, 1, "version"),
    (0x0D, 1, "lock"),
    (0x0E, 7, "date"),
    (0x15, 4, "RGN1_position"),
    (0x19, 4, "RGN1_size"),
    (0x1D, 4, "RGN2_position"),
    (0x21, 4, "RGN2_size"),
    (0x25, 4, "flags_0x25"),
    (0x29, 4, "polygonsGblFlags"),
    (0x2D, 4, "padding_0x2D"),
    (0x31, 4, "padding_0x31"),
    (0x35, 4, "padding_0x35"),
    (0x39, 4, "RGN3_position"),
    (0x3D, 4, "RGN3_size"),
    (0x41, 4, "linesGblFlags"),
    (0x45, 4, "padding_0x45"),
    (0x49, 4, "padding_0x49"),
    (0x4D, 4, "padding_0x4D"),
    (0x51, 4, "padding_0x51"),
    (0x55, 4, "RGN4_position"),
    (0x59, 4, "RGN4_size"),
    (0x5D, 4, "pointsGblFlags"),
    (0x61, 4, "padding_0x61"),
    (0x65, 4, "padding_0x65"),
    (0x69, 4, "padding_0x69"),
    (0x6D, 4, "padding_0x6D"),
    (0x71, 4, "RGN5_position"),
    (0x75, 4, "RGN5_size"),
    (0x79, 4, "RGNEXT"),
]

# Named fields for LBL header (key ones only)
_LBL_FIELDS = [
    (0x00, 2, "header_length"),
    (0x02, 10, "signature"),
    (0x0C, 1, "version"),
    (0x0D, 1, "lock"),
    (0x0E, 7, "date"),
    (0x15, 4, "LBL1_position"),
    (0x19, 4, "LBL1_size"),
    (0x1D, 1, "offset_multiplier"),
    (0x1E, 1, "encoding"),
    (0x184, 4, "LBL28_position"),
    (0x188, 4, "LBL28_size"),
    (0x18C, 2, "LBL28_rec_size"),
    (0x18E, 4, "LBL28_flags"),
    (0x192, 4, "LBL29_position"),
    (0x196, 4, "LBL29_size"),
]


def _normalize_header(header_bytes, normalize_fields):
    """Mask variable fields in a header for comparison.

    Returns a copy with specified fields zeroed out.
    """
    result = bytearray(header_bytes)
    for off, size, _desc in normalize_fields:
        for i in range(off, min(off + size, len(result))):
            result[i] = 0x00
    return bytes(result)


def _parse_full(path):
    """Parse an IMG file and return (parser, gmp_key, gmp, tre, rgn_parsed, lbl)."""
    img = IMGParser(path)
    img.parse_header()
    img.parse_fat()

    gmp_key = None
    for key in img.subfiles:
        if img.subfiles[key]["type"] == "GMP":
            gmp_key = key
            break

    if not gmp_key:
        img.close()
        return None

    gmp = img.parse_gmp_container(gmp_key)
    tre = img.parse_tre(gmp)
    rgn_parsed = img.parse_rgn(gmp)
    lbl = img.parse_lbl(gmp)

    return img, gmp_key, gmp, tre, rgn_parsed, lbl


def _get_header_bytes(data, section_offset):
    """Extract header bytes for a section."""
    hdr_len = struct.unpack_from("<H", data, section_offset)[0]
    return data[section_offset : section_offset + hdr_len]


def compare_structure(
    echo, gmp1, tre1, rgn1_parsed, lbl1, gmp2, tre2, rgn2_parsed, lbl2
):
    """Compare structural properties: section positions, sizes, counts."""
    data1 = gmp1["data"]
    data2 = gmp2["data"]

    echo("\n" + "=" * 80)
    echo("  STRUCTURAL COMPARISON")
    echo("=" * 80)

    # GMP data sizes
    echo(
        f"\n  GMP data size:  File1={len(data1):,}  File2={len(data2):,}  "
        f"{'OK' if len(data1) == len(data2) else 'DIFF'}"
    )

    # Section offsets
    for name in sorted(set(gmp1["sections"]) | set(gmp2["sections"])):
        off1 = gmp1["sections"].get(name, 0)
        off2 = gmp2["sections"].get(name, 0)
        match = "OK" if off1 == off2 else "DIFF"
        echo(f"  {name} offset:  File1=0x{off1:X}  File2=0x{off2:X}  {match}")

    # TRE1 levels
    levels1 = tre1.get("levels", [])
    levels2 = tre2.get("levels", [])
    echo(
        f"\n  TRE1 levels:  File1={len(levels1)}  File2={len(levels2)}  "
        f"{'OK' if len(levels1) == len(levels2) else 'DIFF'}"
    )

    for i in range(max(len(levels1), len(levels2))):
        l1 = levels1[i] if i < len(levels1) else None
        l2 = levels2[i] if i < len(levels2) else None
        if l1 and l2:
            match = (
                "OK"
                if (
                    l1["zoom_code"] == l2["zoom_code"]
                    and l1["level_number"] == l2["level_number"]
                )
                else "DIFF"
            )
            echo(
                f"    Level[{i}]: File1(zoom={l1['zoom_code']:3d}, lvl={l1['level_number']:3d}, "
                f"subdivs={l1['subdivision_count']:5d})  "
                f"File2(zoom={l2['zoom_code']:3d}, lvl={l2['level_number']:3d}, "
                f"subdivs={l2['subdivision_count']:5d})  {match}"
            )
        elif l1:
            echo(
                f"    Level[{i}]: File1 only (zoom={l1['zoom_code']}, lvl={l1['level_number']})"
            )
        else:
            assert l2 is not None
            echo(
                f"    Level[{i}]: File2 only (zoom={l2['zoom_code']}, lvl={l2['level_number']})"
            )

    # TRE2 subdivisions
    groups1 = tre1.get("groups_16byte", [])
    groups2 = tre2.get("groups_16byte", [])
    echo(
        f"\n  TRE2 subdivisions:  File1={len(groups1)}  File2={len(groups2)}  "
        f"{'OK' if len(groups1) == len(groups2) else 'DIFF'}"
    )

    # TRE7
    tre7_1 = tre1.get("tre7", {})
    tre7_2 = tre2.get("tre7", {})
    echo(
        f"\n  TRE7:  File1(pos={tre7_1.get('position', 0)}, size={tre7_1.get('size', 0)}, "
        f"rec={tre7_1.get('record_size', 0)})  "
        f"File2(pos={tre7_2.get('position', 0)}, size={tre7_2.get('size', 0)}, "
        f"rec={tre7_2.get('record_size', 0)})  "
        f"{'OK' if tre7_1.get('record_size') == tre7_2.get('record_size') else 'DIFF'}"
    )

    tre7_offsets1 = tre1.get("tre7_offsets", [])
    tre7_offsets2 = tre2.get("tre7_offsets", [])
    echo(
        f"  TRE7 entries:  File1={len(tre7_offsets1)}  File2={len(tre7_offsets2)}  "
        f"{'OK' if len(tre7_offsets1) == len(tre7_offsets2) else 'DIFF'}"
    )

    # RGN sections
    echo("\n  RGN sections:")
    for sec in ["rgn1", "rgn2", "rgn3", "rgn4", "rgn5"]:
        s1 = rgn1_parsed.get(sec, {})
        s2 = rgn2_parsed.get(sec, {})
        p1, sz1 = s1.get("position", 0), s1.get("size", 0)
        p2, sz2 = s2.get("position", 0), s2.get("size", 0)
        if p1 or p2:
            match = "OK" if p1 == p2 and sz1 == sz2 else "DIFF"
            echo(
                f"    {sec.upper()}:  File1(pos={p1}, size={sz1})  "
                f"File2(pos={p2}, size={sz2})  {match}"
            )

    # LBL sections
    echo("\n  LBL sections:")
    if lbl1 and lbl2:
        for sec in ["lbl1", "lbl28", "lbl29"]:
            s1 = lbl1.get(sec, {})
            s2 = lbl2.get(sec, {})
            p1, sz1 = s1.get("position", 0), s1.get("size", 0)
            p2, sz2 = s2.get("position", 0), s2.get("size", 0)
            if p1 or p2:
                match = "OK" if p1 == p2 and sz1 == sz2 else "DIFF"
                echo(
                    f"    {sec.upper()}:  File1(pos={p1}, size={sz1})  "
                    f"File2(pos={p2}, size={sz2})  {match}"
                )

    # RGN2 record counts
    recs1 = rgn1_parsed.get("rgn2_records", [])
    recs2 = rgn2_parsed.get("rgn2_records", [])
    e0_1 = [r for r in recs1 if r["type"] == "raster tile"]
    e0_2 = [r for r in recs2 if r["type"] == "raster tile"]
    echo(
        f"\n  RGN2 records:  File1={len(recs1)} ({len(e0_1)} E0)  "
        f"File2={len(recs2)} ({len(e0_2)} E0)  "
        f"{'OK' if len(recs1) == len(recs2) else 'DIFF'}"
    )


def compare_headers(echo, data1, data2, gmp1, gmp2):
    """Compare headers field-by-field with normalization."""
    echo("\n" + "=" * 80)
    echo("  HEADER FIELD COMPARISON (normalized)")
    echo("=" * 80)

    for section_name, fields, norm_fields, color in [
        ("TRE", _TRE_FIELDS, _NORMALIZE_TRE, "cyan"),
        ("RGN", _RGN_FIELDS, _NORMALIZE_RGN, "green"),
        ("LBL", _LBL_FIELDS, _NORMALIZE_LBL, "yellow"),
    ]:
        off1 = gmp1["sections"].get(section_name)
        off2 = gmp2["sections"].get(section_name)

        if off1 is None or off2 is None:
            echo(f"\n  {section_name}: not present in both files")
            continue

        hdr1 = _get_header_bytes(data1, off1)
        hdr2 = _get_header_bytes(data2, off2)
        hdr1_norm = _normalize_header(hdr1, norm_fields)
        hdr2_norm = _normalize_header(hdr2, norm_fields)

        echo(
            f"\n  --- {section_name} Header (length: File1={len(hdr1)}, File2={len(hdr2)}) ---"
        )
        echo(f"  {'Offset':<12} {'Field':<22} {'File 1':<20} {'File 2':<20} {'Status'}")
        echo(f"  {'-' * 12} {'-' * 22} {'-' * 20} {'-' * 20} {'-' * 8}")

        diff_count = 0
        norm_offsets = set()
        for noff, nsize, _ in norm_fields:
            for b in range(nsize):
                norm_offsets.add(noff + b)

        for off, size, name in fields:
            if off + size > len(hdr1_norm) or off + size > len(hdr2_norm):
                continue

            raw1 = hdr1[off : off + size]
            raw2 = hdr2[off : off + size]
            norm1 = hdr1_norm[off : off + size]
            norm2 = hdr2_norm[off : off + size]

            # Format value based on type
            if size == 1:
                v1 = f"0x{raw1[0]:02X}"
                v2 = f"0x{raw2[0]:02X}"
            elif size == 2:
                v1 = f"0x{struct.unpack_from('<H', raw1)[0]:04X}"
                v2 = f"0x{struct.unpack_from('<H', raw2)[0]:04X}"
            elif size == 3:
                v1 = f"{map_units_to_degrees(decode_3byte_signed(raw1)):.4f}"
                v2 = f"{map_units_to_degrees(decode_3byte_signed(raw2)):.4f}"
            elif size == 4:
                v1_int = struct.unpack_from("<I", raw1)[0]
                v2_int = struct.unpack_from("<I", raw2)[0]
                v1 = f"0x{v1_int:X}"
                v2 = f"0x{v2_int:X}"
            elif size == 7:
                v1 = "date"
                v2 = "date"
            elif size == 10:
                v1 = raw1.decode("ascii", errors="replace").rstrip("\x00")
                v2 = raw2.decode("ascii", errors="replace").rstrip("\x00")
            elif size == 16:
                v1 = raw1.hex()[:16] + "..."
                v2 = raw2.hex()[:16] + "..."
            else:
                v1 = raw1.hex()
                v2 = raw2.hex()

            is_normalized = all((off + b) in norm_offsets for b in range(size))
            if is_normalized:
                status = "(normalized)"
            elif norm1 == norm2:
                status = "OK"
            else:
                status = "DIFF"
                diff_count += 1

            end_off = off + size - 1
            echo(
                f"  0x{off:02X}-0x{end_off:02X}  {name:<22} {v1:<20} {v2:<20} {status}"
            )

        echo(f"  {section_name}: {diff_count} difference(s) after normalization")


def compare_rgn2_samples(echo, rgn1_parsed, rgn2_parsed, sample_size=10):
    """Compare first N RGN2 raster tile records."""
    recs1 = [
        r for r in rgn1_parsed.get("rgn2_records", []) if r["type"] == "raster tile"
    ]
    recs2 = [
        r for r in rgn2_parsed.get("rgn2_records", []) if r["type"] == "raster tile"
    ]

    echo("\n" + "=" * 80)
    echo(f"  RGN2 SAMPLE COMPARISON (first {sample_size} raster tile records)")
    echo("=" * 80)

    echo(f"\n  Total E0 records:  File1={len(recs1)}  File2={len(recs2)}")

    n = min(sample_size, len(recs1), len(recs2))
    if n == 0:
        echo("  No E0 records to compare in one or both files.")
        return

    echo(f"\n  {'#':<4} {'Field':<18} {'File 1':<22} {'File 2':<22} {'Status'}")
    echo(f"  {'-' * 4} {'-' * 18} {'-' * 22} {'-' * 22} {'-' * 8}")

    for i in range(n):
        r1 = recs1[i]
        r2 = recs2[i]

        for field in [
            "image_index",
            "lat_min_deg",
            "lon_min_deg",
            "lat_max_deg",
            "lon_max_deg",
            "jpeg_size",
        ]:
            v1 = r1.get(field)
            v2 = r2.get(field)
            if v1 is None or v2 is None:
                status = "MISSING"
            elif isinstance(v1, float):
                match = abs(v1 - v2) < 1e-6
                status = "OK" if match else "DIFF"
                v1 = f"{v1:.6f}"
                v2 = f"{v2:.6f}"
            elif isinstance(v1, str):
                status = "OK" if v1 == v2 else "DIFF"
            else:
                status = "OK" if v1 == v2 else "DIFF"
                v1 = str(v1)
                v2 = str(v2)

            echo(f"  {i:<4} {field:<18} {str(v1):<22} {str(v2):<22} {status}")

        # Raw hex comparison
        hex1 = r1.get("raw_hex", "")
        hex2 = r2.get("raw_hex", "")
        if hex1 and hex2:
            hex_match = "OK" if hex1 == hex2 else "DIFF"
            echo(
                f"  {i:<4} {'raw_hex':<18} {hex1[:20]:<22} {hex2[:20]:<22} {hex_match}"
            )


# --- Legacy analysis functions (used by the compare command in raw mode) ---


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


def compare_files(
    path1, path2, echo, *, headers_only=False, sample_size=10, full=False
):
    """Compare two IMG files side by side.

    Args:
        path1: Path to the first (reference) IMG file.
        path2: Path to the second (output) IMG file.
        echo: Callable for output (e.g. click.echo).
        headers_only: Only compare headers, skip RGN2 sample.
        sample_size: Number of RGN2 records to compare.
        full: Full raw dump mode (legacy behavior).
    """
    label1 = "File 1 (reference)"
    label2 = "File 2 (output)"

    # Parse both files
    results = {}
    for label, path in [(label1, path1), (label2, path2)]:
        echo(f"\n{'#' * 80}")
        echo(f"#  {label}: {path}")
        echo(f"{'#' * 80}")

        parsed = _parse_full(path)
        if parsed is None:
            echo(f"  ERROR: No GMP subfile found in {path}")
            results[label] = None
            continue

        img, gmp_key, gmp, tre, rgn_parsed, lbl = parsed
        data = gmp["data"]

        echo(f"  GMP subfile: {gmp_key}")
        echo(f"  GMP data size: {len(data)} bytes")

        results[label] = {
            "img": img,
            "gmp": gmp,
            "tre": tre,
            "rgn_parsed": rgn_parsed,
            "lbl": lbl,
        }

        if full:
            rgn_off = gmp["sections"]["RGN"]
            rgn = data[rgn_off:]
            rgn2_pos = struct.unpack_from("<I", rgn, 0x1D)[0]
            rgn2_size = struct.unpack_from("<I", rgn, 0x21)[0]

            tre_off = gmp["sections"]["TRE"]
            tre_hdr = data[tre_off:]
            tre7_pos = struct.unpack_from("<I", tre_hdr, 0x7C)[0]
            tre7_size = struct.unpack_from("<I", tre_hdr, 0x80)[0]
            tre7_rec_size = struct.unpack_from("<H", tre_hdr, 0x84)[0]
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

            _analyze_rgn_header_bytes(data, rgn_off, label, echo)

            if rgn2_size > 0:
                _analyze_rgn2_data(data, rgn2_pos, rgn2_size, label, echo, max_dump=500)
            else:
                echo("\n  RGN2 size is 0 - no data to analyze!")

    r1 = results.get(label1)
    r2 = results.get(label2)

    if r1 is None or r2 is None:
        echo("\n  Cannot compare: one or both files failed to parse.")
        return

    # Close parsers
    for r in [r1, r2]:
        r["img"].close()

    # Structural comparison
    compare_structure(
        echo,
        r1["gmp"],
        r1["tre"],
        r1["rgn_parsed"],
        r1["lbl"],
        r2["gmp"],
        r2["tre"],
        r2["rgn_parsed"],
        r2["lbl"],
    )

    # Header field comparison
    compare_headers(echo, r1["gmp"]["data"], r2["gmp"]["data"], r1["gmp"], r2["gmp"])

    # RGN2 sample comparison
    if not headers_only:
        compare_rgn2_samples(
            echo, r1["rgn_parsed"], r2["rgn_parsed"], sample_size=sample_size
        )
