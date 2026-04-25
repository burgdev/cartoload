#!/usr/bin/env python3
"""
Analyze RGN2 data structure from Garmin IMG files (GMP container format).

Parses the GMP container, extracts the RGN sub-header with full field annotations,
and dumps the RGN2 section data with record type annotations.

GMP Container Header layout (at file offset where "GARMIN GMP" is found - 2):
  0x00-0x01: uint16 LE = GMP header length
  0x02-0x0B: "GARMIN GMP" (10 bytes)
  0x0C: version (uint8)
  0x0D: lock flag (uint8)
  0x0E-0x14: date (7 bytes)
  0x15-0x18: uint32 = 0 (padding/flags?)
  0x19-0x1C: uint32 LE = TRE subfile offset (relative to GMP start)
  0x1D-0x20: uint32 LE = RGN subfile offset (relative to GMP start)
  0x21-0x24: uint32 LE = LBL subfile offset (relative to GMP start)
  0x25-0x28: uint32 LE = NET subfile offset (relative to GMP start, 0 if absent)
  0x29-0x2C: uint32 LE = NOD subfile offset (relative to GMP start, 0 if absent)

RGN Sub-Header layout (at the RGN offset within GMP):
  0x00-0x01: uint16 LE = header length (typically 125 = 0x7D)
  0x02-0x0B: "GARMIN RGN" (10 bytes)
  0x0C: version (uint8)
  0x0D: lock flag (uint8)
  0x0E-0x14: date (7 bytes)
  0x15-0x18: uint32 LE = RGN1 data position (relative to RGN subfile start)
  0x19-0x1C: uint32 LE = RGN1 data size
  0x1D-0x20: uint32 LE = RGN2 data position (relative to RGN subfile start)
  0x21-0x24: uint32 LE = RGN2 data size
  0x25-0x7C: zeros (remaining header bytes)

RGN2 section contains:
  - For each zoom level: a 0x0D raster outline record (20 bytes)
  - For each tile: a 0x06 polyline preamble (18 bytes) + a 0xE0 tile record (23-24 bytes)
"""

import struct
import os


# Known RGN record type markers (first byte of a record)
RECORD_TYPES = {
    0x01: "Point (generic)",
    0x02: "Indexed Point",
    0x03: "Polyline (generic)",
    0x04: "Polygon (generic)",
    0x05: "Road",
    0x06: "Polyline preamble (raster tile)",
    0x07: "Polygon with label",
    0x08: "Indexed polygon",
    0x09: "???",
    0x0A: "Point with extra data",
    0x0B: "Indexed point",
    0x0C: "Polygon",
    0x0D: "Raster outline record",
    0x0E: "Extended point",
    0x0F: "Polygon (ext)",
    0x10: "Indexed Polygon (ext)",
    0x13: "Polygon",
    0x14: "Point",
    0x16: "Polyline (ext)",
    0x17: "Polygon (ext)",
    0x19: "Polyline",
    0x1A: "Polygon",
    0x1C: "Polyline",
    0x1D: "Polygon",
    0x1F: "Polyline",
    0x20: "Polygon",
    0x21: "Point",
    0x40: "Polyline",
    0x41: "Polygon",
    0x42: "Road",
    0x43: "Line",
    0x60: "Bitmap header",
    0x61: "Bitmap data",
    0x62: "Bitmap",
    0x80: "Extended type prefix",
    0xA0: "Ext polyline",
    0xA1: "Ext polygon",
    0xA2: "Ext road",
    0xA3: "Ext line",
    0xA4: "Ext point",
    0xBC: "BC marker",
    0xC0: "C0 marker",
    0xDE: "DE marker",
    0xE0: "E0 raster tile record",
    0xFF: "FF/padding",
}


def hexdump(data, base_offset=0, length=None, annotations=None):
    """Produce hex dump with 16 bytes per line, ASCII, and optional annotations."""
    if length is None:
        length = len(data)
    length = min(length, len(data))
    lines = []
    for i in range(0, length, 16):
        chunk = data[i : i + 16]
        hex_str = " ".join(f"{b:02X}" for b in chunk)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        line = f"  {base_offset + i:08X}  {hex_str:<48s} |{ascii_str}|"
        if annotations:
            for ann_off, ann_text in annotations:
                if ann_off <= base_offset + i + 15 and ann_off >= base_offset + i:
                    line += f"  <-- {ann_text}"
                    break
        lines.append(line)
    return "\n".join(lines)


def decode_garmin_date(data, offset):
    """Decode Garmin 7-byte date at given offset."""
    if offset + 7 > len(data):
        return "N/A"
    b = data[offset : offset + 7]
    # Format: year_lo, year_hi, month, day, hour, minute, second
    year = b[0] | (b[1] << 8)
    month = b[2]
    day = b[3]
    hour = b[4]
    minute = b[5]
    second = b[6]
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"


def find_gmp_start(data):
    """Find the GMP container start in the IMG file."""
    sig_pos = data.find(b"GARMIN GMP")
    if sig_pos < 0:
        return None
    # The 2-byte header length precedes the signature
    return sig_pos - 2


def parse_gmp_header(gmp_data):
    """Parse the GMP container header and return a dict of fields."""
    result = {}
    result["header_length"] = struct.unpack_from("<H", gmp_data, 0)[0]
    result["signature"] = gmp_data[2:12].decode("ascii", errors="replace")
    result["version"] = gmp_data[12]
    result["lock"] = gmp_data[13]
    result["date"] = decode_garmin_date(gmp_data, 14)
    result["tre_offset"] = struct.unpack_from("<I", gmp_data, 0x19)[0]
    result["rgn_offset"] = struct.unpack_from("<I", gmp_data, 0x1D)[0]
    result["lbl_offset"] = struct.unpack_from("<I", gmp_data, 0x21)[0]
    result["net_offset"] = struct.unpack_from("<I", gmp_data, 0x25)[0]
    result["nod_offset"] = struct.unpack_from("<I", gmp_data, 0x29)[0]
    return result


def parse_rgn_subheader(gmp_data, rgn_offset):
    """Parse the RGN sub-header at the given GMP-relative offset."""
    rgn = gmp_data[rgn_offset:]
    result = {}
    result["header_length"] = struct.unpack_from("<H", rgn, 0)[0]
    result["signature"] = rgn[2:12].decode("ascii", errors="replace")
    result["version"] = rgn[12]
    result["lock"] = rgn[13]
    result["date"] = decode_garmin_date(rgn, 14)
    result["rgn1_pos"] = struct.unpack_from("<I", rgn, 0x15)[0]
    result["rgn1_size"] = struct.unpack_from("<I", rgn, 0x19)[0]
    result["rgn2_pos"] = struct.unpack_from("<I", rgn, 0x1D)[0]
    result["rgn2_size"] = struct.unpack_from("<I", rgn, 0x21)[0]
    result["raw_header"] = rgn[:125]
    return result


def dump_rgn_header_annotated(rgn_header):
    """Dump RGN sub-header bytes with field-by-field annotations."""
    print("\n  RGN Sub-Header field-by-field:")
    print(f"  {'Offset':<8s} {'Bytes':<20s} {'Value':<22s} {'Description'}")
    print(f"  {'-' * 8} {'-' * 20} {'-' * 22} {'-' * 40}")

    fields = [
        (0x00, 2, "H", "Header length (uint16 LE)"),
        (0x02, 10, "s", "Signature: 'GARMIN RGN'"),
        (0x0C, 1, "B", "Version (uint8)"),
        (0x0D, 1, "B", "Lock flag (uint8, 0=unlocked)"),
        (0x0E, 7, "date", "Creation date (7 bytes)"),
        (0x15, 4, "I", "RGN1 position (uint32 LE, offset from RGN start)"),
        (0x19, 4, "I", "RGN1 size (uint32 LE)"),
        (0x1D, 4, "I", "RGN2 position (uint32 LE, offset from RGN start)"),
        (0x21, 4, "I", "RGN2 size (uint32 LE)"),
    ]

    for off, size, fmt, desc in fields:
        raw = rgn_header[off : off + size]
        hex_str = " ".join(f"{b:02X}" for b in raw)

        if fmt == "H":
            val = struct.unpack_from("<H", rgn_header, off)[0]
            val_str = str(val)
        elif fmt == "B":
            val = rgn_header[off]
            val_str = str(val)
        elif fmt == "I":
            val = struct.unpack_from("<I", rgn_header, off)[0]
            val_str = f"{val} (0x{val:08X})"
        elif fmt == "s":
            val_str = raw.decode("ascii", errors="replace")
        elif fmt == "date":
            val_str = decode_garmin_date(rgn_header, off)
        else:
            val_str = hex_str

        print(f"  0x{off:04X}    {hex_str:<20s} {val_str:<22s} {desc}")

    # Check remaining bytes for non-zero content
    nonzero_offsets = []
    for i in range(0x25, len(rgn_header)):
        if rgn_header[i] != 0:
            nonzero_offsets.append(i)

    if nonzero_offsets:
        print(
            f"\n  Non-zero bytes in remaining header (0x25-0x{len(rgn_header) - 1:02X}):"
        )
        for i in nonzero_offsets:
            print(f"    0x{i:04X}: 0x{rgn_header[i]:02X}")
    else:
        print(f"\n  Bytes 0x25-0x{len(rgn_header) - 1:02X}: all zeros (as expected)")


def dump_rgn2_data(rgn2_data, max_bytes=200):
    """Dump RGN2 data with record type annotations."""
    print(f"\n  RGN2 Data hex dump (first {max_bytes} bytes):")
    print(f"  {'Offset':<10s} {'Hex bytes (16 per line)':<49s} {'ASCII'}")
    print(f"  {'-' * 10} {'-' * 49} {'-' * 16}")

    for i in range(0, min(max_bytes, len(rgn2_data)), 16):
        chunk = rgn2_data[i : i + 16]
        hex_str = " ".join(f"{b:02X}" for b in chunk)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)

        # Build annotations for this line
        ann_parts = []
        for j, b in enumerate(chunk):
            if b in RECORD_TYPES:
                ann_parts.append(f"+{i + j:02X}:0x{b:02X}={RECORD_TYPES[b]}")

        ann = "  ".join(ann_parts)
        if ann:
            ann = f"  [{ann}]"

        print(f"  +0x{i:04X}    {hex_str:<49s} |{ascii_str}|{ann}")

    # Summary of all record markers found
    print(f"\n  Record type marker summary (first {max_bytes} bytes):")
    markers = {}
    for i in range(min(max_bytes, len(rgn2_data))):
        b = rgn2_data[i]
        if b in RECORD_TYPES:
            if b not in markers:
                markers[b] = []
            markers[b].append(i)

    for b in sorted(markers.keys()):
        offsets = markers[b]
        offset_strs = [f"+0x{o:04X}" for o in offsets]
        print(
            f"    0x{b:02X} ({RECORD_TYPES[b]:30s}): {len(offsets)} occurrences  at {', '.join(offset_strs[:10])}{'...' if len(offsets) > 10 else ''}"
        )


def try_parse_rgn2_records(rgn2_data, max_bytes=500):
    """Try to parse RGN2 records starting from byte 0."""
    print(f"\n  Attempting to parse RGN2 records (first {max_bytes} bytes):")

    pos = 0
    record_num = 0
    while pos < min(max_bytes, len(rgn2_data)):
        rec_type = rgn2_data[pos]

        if rec_type == 0x0D:
            # Raster outline record: 20 bytes
            # 0x0D subtype(1) + 18 bytes of data
            if pos + 20 <= len(rgn2_data):
                rec = rgn2_data[pos : pos + 20]
                subtype = rec[1]
                print(
                    f"    Record {record_num} at +0x{pos:04X}: Type 0x0D (Raster outline)"
                )
                print(f"      Subtype: 0x{subtype:02X}")
                print(f"      Raw: {rec.hex()}")
                pos += 20
                record_num += 1
                continue

        elif rec_type == 0x06:
            # Polyline preamble: 18 bytes
            # 0x06 subtype(1) + 16 bytes
            if pos + 18 <= len(rgn2_data):
                rec = rgn2_data[pos : pos + 18]
                subtype = rec[1]
                print(
                    f"    Record {record_num} at +0x{pos:04X}: Type 0x06 (Polyline preamble)"
                )
                print(f"      Subtype: 0x{subtype:02X}")
                print(f"      Raw: {rec.hex()}")
                pos += 18
                record_num += 1
                continue

        elif rec_type == 0xE0:
            # E0 tile record: typically 23 or 24 bytes
            # First check if next 3 bytes after E0 look like 0x2B (common pattern)
            if pos + 23 <= len(rgn2_data):
                rec = rgn2_data[pos : pos + 24]  # try 24 first
                # E0 records in our format: 0xE0 + 0x2B + tile_index(1) + ...
                byte2 = rec[1]
                print(
                    f"    Record {record_num} at +0x{pos:04X}: Type 0xE0 (Raster tile)"
                )
                print(f"      Byte[1]: 0x{byte2:02X}")
                # Show context
                ctx = rgn2_data[pos : min(pos + 24, len(rgn2_data))]
                print(f"      Raw ({len(ctx)} bytes): {ctx.hex()}")
                # Determine size: if byte2 == 0x2B, likely 23 bytes
                rec_size = 23 if byte2 == 0x2B else 24
                pos += rec_size
                record_num += 1
                continue

        # Unknown - skip one byte
        pos += 1


def analyze_file(filepath, label=None):
    """Full analysis of a single IMG file."""
    if label is None:
        label = os.path.basename(filepath)

    print(f"\n{'#' * 80}")
    print(f"# {label}")
    print(f"# File: {filepath}")
    print(f"{'#' * 80}")

    if not os.path.exists(filepath):
        print("  FILE NOT FOUND!")
        return

    with open(filepath, "rb") as f:
        data = f.read()

    print(f"  File size: {len(data):,} bytes ({len(data) / 1024:.1f} KB)")

    # Find GMP container
    gmp_start = find_gmp_start(data)
    if gmp_start is None:
        print("  ERROR: Could not find 'GARMIN GMP' signature in file!")
        return

    print(f"  GMP container at file offset: 0x{gmp_start:08X}")
    gmp_data = data[gmp_start:]

    # Parse GMP header
    gmp = parse_gmp_header(gmp_data)
    print("\n  GMP Container Header:")
    print(f"    Header length: {gmp['header_length']}")
    print(f"    Signature:     {gmp['signature']}")
    print(f"    Version:       {gmp['version']}")
    print(f"    Lock:          {gmp['lock']}")
    print(f"    Date:          {gmp['date']}")
    print(f"    TRE offset:    0x{gmp['tre_offset']:08X}")
    print(f"    RGN offset:    0x{gmp['rgn_offset']:08X}")
    print(f"    LBL offset:    0x{gmp['lbl_offset']:08X}")
    print(f"    NET offset:    0x{gmp['net_offset']:08X}")
    print(f"    NOD offset:    0x{gmp['nod_offset']:08X}")

    # GMP header raw dump
    print("\n  GMP Header raw bytes (first 128 bytes):")
    print(hexdump(gmp_data, base_offset=0, length=128))

    # Parse RGN sub-header
    if gmp["rgn_offset"] == 0:
        print("\n  No RGN subfile in this IMG!")
        return

    rgn = parse_rgn_subheader(gmp_data, gmp["rgn_offset"])

    print(f"\n{'=' * 80}")
    print(
        f"  RGN Sub-Header at GMP+0x{gmp['rgn_offset']:08X} (file 0x{gmp_start + gmp['rgn_offset']:08X})"
    )
    print(f"{'=' * 80}")
    print(f"    Header length: {rgn['header_length']}")
    print(f"    Signature:     {rgn['signature']}")
    print(f"    Version:       {rgn['version']}")
    print(f"    Lock:          {rgn['lock']}")
    print(f"    Date:          {rgn['date']}")
    print(f"    RGN1 position: {rgn['rgn1_pos']} (0x{rgn['rgn1_pos']:08X})")
    print(f"    RGN1 size:     {rgn['rgn1_size']} (0x{rgn['rgn1_size']:08X})")
    print(f"    RGN2 position: {rgn['rgn2_pos']} (0x{rgn['rgn2_pos']:08X})")
    print(f"    RGN2 size:     {rgn['rgn2_size']} (0x{rgn['rgn2_size']:08X})")

    # Annotated field dump
    dump_rgn_header_annotated(rgn["raw_header"])

    # Raw hex dump of RGN header
    print(f"\n  RGN Sub-Header raw hex (all {rgn['header_length']} bytes):")
    print(
        hexdump(
            rgn["raw_header"],
            base_offset=gmp["rgn_offset"],
            length=rgn["header_length"],
        )
    )

    # RGN2 data analysis
    rgn2_abs_gmp = gmp["rgn_offset"] + rgn["rgn2_pos"]
    rgn2_abs_file = gmp_start + rgn2_abs_gmp

    print(f"\n{'=' * 80}")
    print("  RGN2 Data Section")
    print(f"{'=' * 80}")
    print(
        f"    RGN2 offset from RGN start: {rgn['rgn2_pos']} (0x{rgn['rgn2_pos']:08X})"
    )
    print(f"    RGN2 GMP-relative offset:   {rgn2_abs_gmp} (0x{rgn2_abs_gmp:08X})")
    print(f"    RGN2 file-absolute offset:  {rgn2_abs_file} (0x{rgn2_abs_file:08X})")
    print(
        f"    RGN2 size:                  {rgn['rgn2_size']} (0x{rgn['rgn2_size']:08X})"
    )

    if rgn["rgn2_size"] == 0:
        print("\n    RGN2 is empty (size = 0)!")
        return

    if rgn2_abs_gmp + rgn["rgn2_size"] > len(gmp_data):
        avail = len(gmp_data) - rgn2_abs_gmp
        print("\n    WARNING: RGN2 extends beyond available GMP data!")
        print(f"    Available: {avail} bytes of {rgn['rgn2_size']} expected")
        if avail <= 0:
            return
        rgn2_data = gmp_data[rgn2_abs_gmp : rgn2_abs_gmp + avail]
    else:
        rgn2_data = gmp_data[rgn2_abs_gmp : rgn2_abs_gmp + rgn["rgn2_size"]]

    # RGN1 data (for reference)
    if rgn["rgn1_size"] > 0:
        rgn1_abs_gmp = gmp["rgn_offset"] + rgn["rgn1_pos"]
        rgn1_data = gmp_data[rgn1_abs_gmp : rgn1_abs_gmp + min(rgn["rgn1_size"], 100)]
        print(f"\n  RGN1 Data reference (first 100 of {rgn['rgn1_size']} bytes):")
        print(
            f"    RGN1 offset from RGN start: {rgn['rgn1_pos']} (0x{rgn['rgn1_pos']:08X})"
        )
        print(f"    RGN1 GMP-relative offset:   {rgn1_abs_gmp} (0x{rgn1_abs_gmp:08X})")
        print(hexdump(rgn1_data, base_offset=0, length=min(len(rgn1_data), 100)))
    else:
        print("\n  RGN1 is empty (size = 0) -- all data is in RGN2")

    # Dump RGN2 first 200 bytes
    print("\n  --- RGN2 first 200 bytes ---")
    dump_rgn2_data(rgn2_data, max_bytes=200)

    # Dump RGN2 first 500 bytes with parsed records
    try_parse_rgn2_records(rgn2_data, max_bytes=500)

    # Additional: show RGN2 data at boundaries (last 100 bytes)
    if rgn["rgn2_size"] > 200:
        tail_start = max(200, len(rgn2_data) - 100)
        tail_data = rgn2_data[tail_start:]
        print(f"\n  --- RGN2 last bytes (from +0x{tail_start:04X}) ---")
        print(hexdump(tail_data, base_offset=tail_start, length=len(tail_data)))


if __name__ == "__main__":
    iom_path = "/home/tobias/git/burgdev/cartoload/tests/data/garmin_samples/IOM.img"
    output_path = "/home/tobias/git/burgdev/cartoload/output/ch_basemap_test.img"

    analyze_file(iom_path, label="IOM Reference File (Isle of Man)")
    analyze_file(output_path, label="Our Output File (CH Basemap Test)")
