"""
RGN2 analysis functions for Garmin IMG files.

Provides annotated hex dumps and segmented analysis of RGN2 data sections,
using TRE7 offsets to split data by zoom level.
"""

import struct

from .img_parser import (
    map_units_to_degrees_32,
    format_hex_dump,
)

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
    0x0D: "Raster outline record",
    0x0E: "Extended point",
    0x40: "Polyline",
    0x41: "Polygon",
    0x42: "Road",
    0x60: "Bitmap header",
    0x61: "Bitmap data",
    0x80: "Extended type prefix",
    0xA0: "Ext polyline",
    0xA1: "Ext polygon",
    0xBC: "BC marker",
    0xC0: "C0 marker",
    0xDE: "DE marker",
    0xE0: "E0 raster tile record",
    0xFF: "FF/padding",
}

MARKER_NAMES = {
    0x06: "POLYLINE",
    0x0D: "POLYGON",
    0xE0: "RASTER",
    0xBC: "BOUNDARY",
    0xDE: "EXT_BOUNDARY",
}


def dump_rgn_header_annotated(rgn_header, echo):
    """Dump RGN sub-header bytes with field-by-field annotations."""
    echo("\n  RGN Sub-Header field-by-field:")
    echo(f"  {'Offset':<8s} {'Bytes':<20s} {'Value':<22s} {'Description'}")
    echo(f"  {'-' * 8} {'-' * 20} {'-' * 22} {'-' * 40}")

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
            year = struct.unpack_from("<H", rgn_header, off)[0]
            month = rgn_header[off + 2]
            day = rgn_header[off + 3]
            hour = rgn_header[off + 4]
            minute = rgn_header[off + 5]
            second = rgn_header[off + 6]
            val_str = (
                f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
            )
        else:
            val_str = hex_str

        echo(f"  0x{off:04X}    {hex_str:<20s} {val_str:<22s} {desc}")

    # Check remaining bytes for non-zero content
    nonzero_offsets = []
    for i in range(0x25, len(rgn_header)):
        if rgn_header[i] != 0:
            nonzero_offsets.append(i)

    if nonzero_offsets:
        echo(
            f"\n  Non-zero bytes in remaining header (0x25-0x{len(rgn_header) - 1:02X}):"
        )
        for i in nonzero_offsets:
            echo(f"    0x{i:04X}: 0x{rgn_header[i]:02X}")
    else:
        echo(f"\n  Bytes 0x25-0x{len(rgn_header) - 1:02X}: all zeros (as expected)")


def dump_rgn2_annotated(rgn2_data, max_bytes=200, echo=None):
    """Dump RGN2 data with record type annotations."""
    if echo is None:
        return

    echo(f"\n  RGN2 Data hex dump (first {max_bytes} bytes):")
    echo(f"  {'Offset':<10s} {'Hex bytes (16 per line)':<49s} {'ASCII'}")
    echo(f"  {'-' * 10} {'-' * 49} {'-' * 16}")

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

        echo(f"  +0x{i:04X}    {hex_str:<49s} |{ascii_str}|{ann}")

    # Summary of all record markers found
    echo(f"\n  Record type marker summary (first {max_bytes} bytes):")
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
        echo(
            f"    0x{b:02X} ({RECORD_TYPES[b]:30s}): {len(offsets)} occurrences  "
            f"at {', '.join(offset_strs[:10])}{'...' if len(offsets) > 10 else ''}"
        )


def scan_rgn2_markers(seg_data, seg_start, echo):
    """Scan a segment for known record markers and print context."""
    echo("  Scanning for 0x06, 0x0D, 0xE0, 0xBC, 0xDE markers:")
    markers = []
    for i in range(len(seg_data)):
        b = seg_data[i]
        if b in (0x06, 0x0D, 0xE0, 0xBC, 0xDE):
            markers.append((i, b))

    for offset, marker in markers[:30]:
        ctx_start = max(0, offset - 2)
        ctx_end = min(len(seg_data), offset + 25)
        ctx = seg_data[ctx_start:ctx_end]
        echo(
            f"    0x{seg_start + offset:04X} (seg+0x{offset:02X}): "
            f"0x{marker:02X} ({MARKER_NAMES.get(marker, '?'):13s})  ctx: {ctx.hex()}"
        )


def find_e0_records(seg_data, seg_start, echo):
    """Find and parse E0 raster tile records in a segment."""
    echo("\n  E0 record search (looking for E0 2B/25/2D patterns):")
    for i in range(len(seg_data) - 5):
        if seg_data[i] == 0xE0 and seg_data[i + 1] in (0x2B, 0x25, 0x2D):
            bits_field = seg_data[i + 1]
            if bits_field in (0x2B,):
                idx_size = 1
            else:
                idx_size = 2

            rec_len = 2 + idx_size + 16 + 4
            if i + rec_len > len(seg_data):
                continue

            rec = seg_data[i : i + rec_len]
            if idx_size == 1:
                img_idx = rec[2]
            else:
                img_idx = struct.unpack_from("<H", rec, 2)[0]

            coord_off = 2 + idx_size
            lat_min = struct.unpack_from("<i", rec, coord_off)[0]
            lon_min = struct.unpack_from("<i", rec, coord_off + 4)[0]
            lat_max = struct.unpack_from("<i", rec, coord_off + 8)[0]
            lon_max = struct.unpack_from("<i", rec, coord_off + 12)[0]
            block_size = struct.unpack_from("<I", rec, coord_off + 16)[0]

            echo(
                f"    @0x{seg_start + i:04X}: idx={img_idx:3d} "
                f"lat=[{map_units_to_degrees_32(lat_min):.4f},{map_units_to_degrees_32(lat_max):.4f}] "
                f"lon=[{map_units_to_degrees_32(lon_min):.4f},{map_units_to_degrees_32(lon_max):.4f}] "
                f"blk_sz={block_size}"
            )


def analyze_rgn2(img_parser, gmp_key, echo):
    """Full RGN2 annotated analysis using IMGParser.

    Args:
        img_parser: Initialized IMGParser instance (header and FAT already parsed).
        gmp_key: Subfile key for the GMP container.
        echo: Callable for output (e.g. click.echo).
    """
    gmp = img_parser.parse_gmp_container(gmp_key)
    data = gmp["data"]
    rgn = img_parser.parse_rgn(gmp)

    sub = rgn["sub_header"]
    echo(
        f"\n  RGN Sub-Header: {sub['header_length']} bytes, version={sub['version']}, date={sub['date']}"
    )

    if "rgn2" not in rgn or rgn["rgn2"]["size"] == 0:
        echo("  RGN2 is empty (size = 0)!")
        return

    rgn2_info = rgn["rgn2"]
    echo(f"  RGN2: pos=0x{rgn2_info['position']:X}, size={rgn2_info['size']}")

    # Annotated header dump
    rgn_off = gmp["sections"]["RGN"]
    rgn_header_bytes = data[rgn_off : rgn_off + sub["header_length"]]
    dump_rgn_header_annotated(rgn_header_bytes, echo)

    # Raw hex dump of RGN header
    echo(f"\n  RGN Sub-Header raw hex ({sub['header_length']} bytes):")
    echo(format_hex_dump(rgn_header_bytes))

    # RGN2 data
    rgn2_data = data[rgn2_info["position"] : rgn2_info["position"] + rgn2_info["size"]]

    # Annotated RGN2 dump
    dump_rgn2_annotated(rgn2_data, max_bytes=200, echo=echo)

    # Parsed records from IMGParser
    if "rgn2_records" in rgn:
        recs = rgn["rgn2_records"]
        echo(f"\n  Parsed RGN2 records ({len(recs)}):")
        for rec in recs[:30]:
            if rec["type"] == "E0 (raster tile)":
                echo(
                    f"    {rec['type']} @{rec['offset']}: "
                    f"bounds=({rec['lat_min_deg']:.6f},{rec['lon_min_deg']:.6f})-"
                    f"({rec['lat_max_deg']:.6f},{rec['lon_max_deg']:.6f}) "
                    f"blk_sz={rec['block_size']} img_idx={rec['image_index']}"
                )
            else:
                echo(f"    {rec['type']} @{rec['offset']}: {rec.get('raw_hex', '')}")
        if len(recs) > 30:
            echo(f"    ... ({len(recs) - 30} more records)")


def analyze_rgn2_segments(img_parser, gmp_key, echo):
    """Segment RGN2 data by zoom level using TRE7 offsets.

    Args:
        img_parser: Initialized IMGParser instance (header and FAT already parsed).
        gmp_key: Subfile key for the GMP container.
        echo: Callable for output (e.g. click.echo).
    """
    gmp = img_parser.parse_gmp_container(gmp_key)
    data = gmp["data"]
    tre = img_parser.parse_tre(gmp)
    rgn = img_parser.parse_rgn(gmp)

    # Need TRE7 offsets
    if "tre7" not in tre or "tre7_offsets" not in tre:
        echo("No TRE7 data found — cannot segment RGN2 by zoom level.")
        return

    tre7_offsets = tre["tre7_offsets"]

    # Need RGN2 data
    if "rgn2" not in rgn or rgn["rgn2"]["size"] == 0:
        echo("RGN2 is empty — nothing to segment.")
        return

    rgn2_info = rgn["rgn2"]
    rgn2_data = data[rgn2_info["position"] : rgn2_info["position"] + rgn2_info["size"]]

    # Show map levels
    if "levels" in tre:
        echo(f"\n  Map Levels ({len(tre['levels'])}):")
        for i, lvl in enumerate(tre["levels"]):
            echo(
                f"    Level {i}: number={lvl['level_number']}, "
                f"zoom_code={lvl['zoom_code']}, subdivs={lvl['subdivision_count']}"
            )

    echo(f"\n  TRE7 offsets ({len(tre7_offsets)}): {[hex(o) for o in tre7_offsets]}")

    # Show TRE2 subdivisions
    if "groups_16byte" in tre:
        subdivs = tre["groups_16byte"]
        echo(f"\n  TRE2 Subdivisions ({len(subdivs)}), 16-byte records:")
        for i, sd in enumerate(subdivs):
            echo(
                f"    Subdiv {i}: rgn_off=0x{sd['rgn_offset']:X} ({sd['rgn_offset']}), "
                f"obj_types={sd['obj_types']}, flags=0x{sd['flags']:04X}, "
                f"subdiv_count={sd['subdiv_count']}, next_level={sd['next_level_index']}, "
                f"lon={sd['lon_center_deg']:.4f}, lat={sd['lat_center_deg']:.4f}"
            )

    # Segment RGN2 by TRE7 offsets
    echo("\n  === RGN2 Segmented by TRE7 offsets ===")

    for seg_idx in range(len(tre7_offsets)):
        seg_start = tre7_offsets[seg_idx]
        if seg_idx + 1 < len(tre7_offsets):
            seg_end = tre7_offsets[seg_idx + 1]
        else:
            seg_end = rgn2_info["size"]
        seg_size = seg_end - seg_start

        echo(
            f"\n  --- Segment {seg_idx} (zoom level): offset 0x{seg_start:X}-0x{seg_end:X}, {seg_size} bytes ---"
        )

        seg_data = rgn2_data[seg_start:seg_end]

        # Show first ~150 bytes of segment
        dump_len = min(len(seg_data), 150)
        echo(f"  First {dump_len} bytes:")
        echo(format_hex_dump(seg_data[:dump_len]))

        # Check TRE2 subdivision alignment
        if "groups_16byte" in tre and seg_idx < len(tre["groups_16byte"]):
            sd = tre["groups_16byte"][seg_idx]
            echo(
                f"\n  TRE2 subdiv {seg_idx}: rgn_offset=0x{sd['rgn_offset']:X}, "
                f"obj_types={sd['obj_types']}"
            )
            echo("    -> rgn_offset is RELATIVE to RGN2 data start")
            echo(f"    -> This subdiv starts at RGN2+0x{sd['rgn_offset']:X}")
            echo(f"    -> Segment starts at RGN2+0x{seg_start:X}")

            if sd["rgn_offset"] != seg_start:
                echo("    *** MISMATCH: TRE2 rgn_offset != TRE7 segment start! ***")

        # Detailed scan of first segment
        if seg_idx == 0:
            echo("\n  === DETAILED: First segment record scan ===")
            scan_rgn2_markers(seg_data, seg_start, echo)
            find_e0_records(seg_data, seg_start, echo)
