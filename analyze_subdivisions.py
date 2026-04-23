#!/usr/bin/env python3
"""
Analyze Garmin IMG raster subdivision format - REVISED.

Key discovery from previous run:
  - The TRE section pointers are correctly at offsets 33, 37, 41, 45, ...
  - But the interpretation was WRONG. Let's re-examine.

From TRE hex dump at offset 33 (0x109):
  0x28c0 (10432), 0x0014 (20)     <- Pair 0: pos=0x28c0, size=20
  0x05b4 (1460),  0x230c (8972)   <- Pair 1: pos=0x5b4, size=8972
  0x05ae (1454),  0x0006 (6)      <- Pair 2: pos=0x5ae, size=6

But wait - these positions should be AFTER the TRE header (273 bytes).
0x28c0 = 10432 >> 273. Plausible as map_levels (small section)
0x5b4 = 1460 >> 273. Plausible as subdivisions start

The subdivision section at 0x5b4 contains 8972 bytes.
Looking at the hexdump, records appear to repeat every 16 bytes with
a very clear pattern.
"""

import struct
import sys
from pathlib import Path

BLOCK_SIZE = 32768
HEADER_SIZE = 512
FAT_ENTRY_SIZE = 512
FAT_BLOCK_NUMBER = 8
FAT_START = FAT_BLOCK_NUMBER * 512

IMG_PATH = Path(
    "/home/tobias/git/burgdev/cartoload/tests/data/garmin_samples/SwissTopo_West.img"
)

EXPECTED_BITMAPS = 32443


def hexdump(data, offset=0, max_bytes=256, prefix=""):
    lines = []
    for i in range(0, min(len(data), max_bytes), 16):
        chunk = data[i : i + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{prefix}{offset + i:08x}: {hex_part:<48s}  {ascii_part}")
    return "\n".join(lines)


def u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def i24(d, o):
    v = d[o] | (d[o + 1] << 8) | (d[o + 2] << 16)
    if v & 0x800000:
        v -= 0x1000000
    return v


def i32(d, o):
    return struct.unpack_from("<i", d, o)[0]


def mu2deg(v):
    return v * 360.0 / (2**24)


def main():
    if not IMG_PATH.exists():
        print(f"ERROR: {IMG_PATH} not found")
        sys.exit(1)

    f = open(IMG_PATH, "rb")

    # Parse header
    f.seek(0)
    header = f.read(HEADER_SIZE)
    fat_start = header[0x40] * 512

    # Read FAT, find GMP
    gmp_blocks = []
    gmp_size = 0
    entry_num = 0
    while True:
        f.seek(fat_start + entry_num * FAT_ENTRY_SIZE)
        ed = f.read(FAT_ENTRY_SIZE)
        if len(ed) < FAT_ENTRY_SIZE or ed[0] == 0x00:
            break
        stype = ed[0x09:0x0C].decode("ascii", errors="replace")
        if stype == "GMP":
            if ed[0x11] == 0:
                gmp_size = u32(ed, 0x0C)
            for i in range(240):
                blk = u16(ed, 0x20 + i * 2)
                if blk == 0xFFFF:
                    break
                gmp_blocks.append(blk)
        entry_num += 1
        if entry_num > 500:
            break

    gmp_start = gmp_blocks[0] * BLOCK_SIZE
    print(f"GMP: start=0x{gmp_start:x}, size={gmp_size:,}")

    # Read enough GMP data to cover all headers + TRE data
    READ_SIZE = 0x40000  # 256KB should be plenty
    f.seek(gmp_start)
    gmp_data = bytearray(f.read(READ_SIZE))

    # GMP container header
    tre_offset = u32(gmp_data, 25)
    rgn_offset = u32(gmp_data, 29)
    lbl_offset = u32(gmp_data, 33)
    net_offset = u32(gmp_data, 37)
    print(
        f"Sections: TRE=0x{tre_offset:x}, RGN=0x{rgn_offset:x}, LBL=0x{lbl_offset:x}, NET=0x{net_offset:x}"
    )

    # ── TRE HEADER ─────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("TRE SUB-HEADER (273 bytes)")
    print("=" * 80)

    tre = gmp_data[tre_offset:]
    tre_hdr_len = u16(tre, 0)
    print(f"  Header length: {tre_hdr_len}")

    # Parse bounds
    north = i24(tre, 21)
    east = i24(tre, 24)
    south = i24(tre, 27)
    west = i24(tre, 30)
    print(
        f"  Bounds: N={mu2deg(north):.6f} E={mu2deg(east):.6f} "
        f"S={mu2deg(south):.6f} W={mu2deg(west):.6f}"
    )

    # Section pointers at offset 33
    # Looking at the hex dump:
    # 0x109: 28 c0 00 00  -> 0x28c0 (pos of section 0)
    # 0x10d: 14 00 00 00  -> 20 (size of section 0)
    # 0x111: b4 05 00 00  -> 0x5b4 (pos of section 1)
    # 0x115: 0c 23 00 00  -> 0x230c = 8972 (size of section 1)
    # 0x119: ae 05 00 00  -> 0x5ae (pos of section 2)
    # 0x11d: 06 00 00 00  -> 6 (size of section 2)
    # 0x121: 00 03 00 00  -> 0x300 = 768 (item_size? or another section?)

    # BUT WAIT - looking at the doc format more carefully:
    # From garmin-img.md section 3.5:
    #   offset 33: map_levels position (uint32)
    #   offset 37: map_levels size (uint32)
    #   offset 41: subdivisions position (uint32)
    #   offset 45: subdivisions size (uint32)
    #   offset 49: copyright position (uint32)
    #   offset 53: copyright size (uint32)
    #   offset 57: copyright item size (uint16)

    # So: map_levels at 0x28c0 (20 bytes), subdivisions at 0x5b4 (8972 bytes),
    #     copyright at 0x5ae (6 bytes)

    # BUT this is WRONG because 0x5ae < 0x5b4 -- copyright starts BEFORE subdivisions!
    # That means the sections are NOT in the order documented.

    # Let me re-read the hex dump carefully.
    # TRE bytes at offset 33 from TRE start (i.e., gmp_data[tre_offset+33]):
    # 28 c0 00 00 14 00 00 00 b4 05 00 00 0c 23 00 00
    # ae 05 00 00 06 00 00 00 00 03

    # Interpretation A (as documented):
    #   +33: map_levels_pos = 0x28c0
    #   +37: map_levels_size = 20
    #   +41: subdivisions_pos = 0x5b4
    #   +45: subdivisions_size = 0x230c (8972)
    #   +49: copyright_pos = 0x5ae
    #   +53: copyright_size = 6
    #   +57: copyright_item_size = 0x0300? That's 768, not 3.

    # Interpretation B (reordered):
    #   The sections might be: subdiv, map_levels, copyright
    #   or some other order.

    # Let me check what's at each position
    print("\n  Section pointer pairs at TRE offset 33:")
    sec_pairs = []
    off = 33
    while off + 8 <= tre_hdr_len:
        pos_val = u32(tre, off)
        size_val = u32(tre, off + 4)
        # Stop if both are 0 or if values look unreasonable
        if pos_val == 0 and size_val == 0:
            break
        if pos_val > 0x100000:  # beyond reasonable TRE data
            break
        sec_pairs.append((pos_val, size_val))
        print(f"    +{off}: pos=0x{pos_val:x} ({pos_val}), size={size_val}")
        off += 8

    # Check the actual content at each position
    print("\n  Content at each section position:")
    for idx, (pos_val, size_val) in enumerate(sec_pairs):
        if pos_val + size_val <= len(tre) and size_val > 0 and size_val < 10000:
            content = tre[pos_val : pos_val + min(size_val, 64)]
            print(f"\n  Section at TRE+0x{pos_val:x} ({size_val} bytes):")
            print(hexdump(content, tre_offset + pos_val, len(content), "    "))
            # Check for ASCII strings
            try:
                as_text = content.decode("ascii", errors="replace")
                if any(c.isalpha() for c in as_text):
                    print(f"    As text: '{as_text}'")
            except Exception:
                pass

    # ── MAP LEVELS RE-ANALYSIS ─────────────────────────────────────────
    # The "map_levels" section at 0x28c0 is 20 bytes.
    # Raw: 8e 05 00 00 c8 b8 05 00 00 9e e2 05 00 00 74 0c 06 00 00 4a

    # These are NOT {level(1), zoom(1), n_subdiv(2)} format!
    # They look like uint32 values. Let's check if they're offsets.

    print("\n" + "=" * 80)
    print("MAP LEVELS SECTION RE-ANALYSIS")
    print("=" * 80)

    ml_pos = u32(tre, 33)  # 0x28c0
    ml_size = u32(tre, 37)  # 20

    ml_raw = tre[ml_pos : ml_pos + ml_size]
    print(f"\n  Map levels raw ({ml_size} bytes):")
    print(f"  {ml_raw.hex()}")

    # Parse as 5 x uint32 LE
    print("\n  As 5 uint32 LE values:")
    ml_values = []
    for i in range(ml_size // 4):
        val = u32(ml_raw, i * 4)
        ml_values.append(val)
        print(f"    [{i}]: 0x{val:08x} ({val})")

    # Check if these are tile counts per level
    print(f"\n  Sum of values: {sum(ml_values)} (GMT bitmaps: {EXPECTED_BITMAPS})")

    # Check differences between consecutive values
    print("\n  Differences (cumulative?):")
    cumsum = 0
    for i, v in enumerate(ml_values):
        cumsum += v
        print(f"    Level {i}: value={v}, cumsum={cumsum}")

    # Actually, looking at the raw bytes more carefully:
    # 8e 05 00 00 -> 0x58e = 1422
    # c8 b8 05 00 -> This is NOT uint32! The second byte is b8, not a clean value.
    # Wait - let me re-read. The hex is: 8e 05 00 00 c8 b8 05 00 00 9e e2 05 00 00 74 0c 06 00 00 4a
    #
    # As 5 x uint32 LE:
    #   [0]: 0x0000058e = 1422
    #   [1]: 0x0005b8c8 = 375240
    #   [2]: 0x0005e29e = 385822
    #   [3]: 0x000c7400 = 817152
    #   [4]: 0x4a000006 = 1241513986
    # That doesn't look right either. The last value is way too large.

    # Hmm, but if these are OFFSETS into the subdivision section...
    # 1422, 375240, 385822 -- these don't make sense for an 8972-byte section.

    # Wait - maybe the map_levels format IS 4 bytes per level but NOT uint32.
    # Let me try: {level(1), zoom(1), n_subdiv(2)}
    # BUT the data at 0x28c0 doesn't match levels [20,21,22,23,24].

    # UNLESS we're reading the WRONG section as map_levels!
    # Maybe the TRE header offsets are wrong, or the format is different.

    # Let me look at the TRE header bytes more carefully to find
    # where the level numbers 20,21,22,23,24 appear.
    print(
        "\n  Searching for level byte values 0x14(20) 0x15(21) 0x16(22) 0x17(23) 0x18(24) in TRE data:"
    )
    for i in range(len(tre) - 5):
        if (
            tre[i] == 0x14
            and tre[i + 1] == 0x15
            and tre[i + 2] == 0x16
            and tre[i + 3] == 0x17
            and tre[i + 4] == 0x18
        ):
            print(f"    Found at TRE offset 0x{i:x}: {tre[i : i + 8].hex()}")

    # Also search for the zoom values 84(0x54), 83(0x53), 2, 1, 0
    print("\n  Searching for zoom values 0x54(84) 0x53(83) 0x02 0x01 0x00:")
    for i in range(len(tre) - 5):
        if (
            tre[i] == 0x54
            and tre[i + 1] == 0x53
            and tre[i + 2] == 0x02
            and tre[i + 3] == 0x01
            and tre[i + 4] == 0x00
        ):
            print(f"    Found at TRE offset 0x{i:x}: {tre[i : i + 8].hex()}")

    # ── SUBDIVISION SECTION ANALYSIS ───────────────────────────────────
    print("\n" + "=" * 80)
    print("SUBDIVISION SECTION ANALYSIS")
    print("=" * 80)

    sd_pos = u32(tre, 41)  # 0x5b4
    sd_size = u32(tre, 45)  # 0x230c = 8972

    # Extend buffer if needed
    sd_abs = tre_offset + sd_pos + sd_size
    if sd_abs > len(gmp_data):
        f.seek(gmp_start + len(gmp_data))
        gmp_data.extend(f.read(sd_abs - len(gmp_data) + 1024))

    sd_raw = bytes(tre[sd_pos : sd_pos + sd_size])
    print(f"\n  Subdivision section: TRE offset 0x{sd_pos:x}, size {sd_size} bytes")

    # 8972 / 16 = 560.75 -- not evenly divisible by 16!
    # 8972 / 8 = 1121.5 -- not evenly divisible by 8!
    # 8972 / 4 = 2243
    # 8972 / 2 = 4486

    # From the hex dump, records clearly repeat every 16 bytes in many places.
    # But the total size is not divisible by 16. This means either:
    # 1. The last record is shorter (like vector format where lowest level = 14 bytes)
    # 2. There's a mix of record sizes
    # 3. There's padding/header in the section

    print("\n  Divisibility check:")
    for rs in range(1, 33):
        if sd_size % rs == 0:
            print(f"    {rs:2d} bytes -> {sd_size // rs} records")
        else:
            remainder = sd_size % rs
            full_recs = sd_size // rs
            print(f"    {rs:2d} bytes -> {full_recs} full + {remainder} remainder")

    # ── Look at repeating pattern ──────────────────────────────────────
    # From the hex dump, many records repeat: "ed 00 00 00 40 c0 05 38 e8 20 66 0e e4 14 00 00"
    # This is clearly a 16-byte record.

    # Let's count unique 16-byte records
    unique_16 = set()
    unique_8 = set()
    for i in range(0, len(sd_raw) - 15, 16):
        unique_16.add(sd_raw[i : i + 16])
    for i in range(0, len(sd_raw) - 7, 8):
        unique_8.add(sd_raw[i : i + 8])

    print(
        f"\n  Unique 16-byte patterns: {len(unique_16)} (from {sd_size // 16} possible)"
    )
    print(f"  Unique 8-byte patterns: {len(unique_8)} (from {sd_size // 8} possible)")

    # Show the unique 16-byte patterns sorted by frequency
    from collections import Counter

    pattern_counts = Counter()
    for i in range(0, len(sd_raw) - 15, 16):
        pattern_counts[sd_raw[i : i + 16]] += 1

    print("\n  Top 20 most frequent 16-byte patterns:")
    for pattern, count in pattern_counts.most_common(20):
        print(f"    {pattern.hex()} x {count}")

    # ── Check if first record has a header ─────────────────────────────
    # The first 16 bytes:
    first_16 = sd_raw[:16]
    print(f"\n  First 16 bytes: {first_16.hex()}")
    print(f"  Second 16 bytes: {sd_raw[16:32].hex()}")

    # ── Re-examine the "map_levels" section ────────────────────────────
    # Maybe map_levels at 0x28c0 contains OFFSETS into the subdivision section
    # rather than counts
    print("\n  Map levels as subdivision offsets:")
    for i in range(ml_size // 4):
        off_val = u32(ml_raw, i * 4)
        print(f"    Level {i}: offset 0x{off_val:x} ({off_val})")

    # Check if these map to positions within the 8972-byte subdivision section
    # 0x58e = 1422
    # The subdivision section is 8972 bytes. If offset 1422 is within it...
    # That means levels 0 starts at byte 0 of subdivisions, level 1 at 1422, etc.
    # 1422 / 16 = 88.875 -- not clean
    # But if it's counting subdivision records (not bytes)...

    # Let me check: what if the map_levels contains TILE COUNTS per level?
    # And the subdivision section has one record per TILE?
    # Then 8972 bytes for 32443 tiles doesn't work (too few bytes).

    # ALTERNATIVELY: maybe the map_levels values are tile OFFSETS into the
    # tile data section (not the subdivision section).
    # 0x58e = 1422 as a tile index offset
    # 0x5b8c8 = 375240 as a tile index offset... too big for 32443 tiles.

    # Hmm, let me re-check the raw bytes.
    # ml_raw = 8e 05 00 00 c8 b8 05 00 00 9e e2 05 00 00 74 0c 06 00 00 4a

    # Could the format be {byte, byte3_padding, uint24} or similar?
    # Or maybe the format is {uint24, byte}?

    # Let me try: 3 bytes + 1 byte per entry (NOT uint32)
    print("\n  Map levels as mixed 3+1 byte entries:")
    pos = 0
    while pos < len(ml_raw):
        rec = ml_raw[pos : pos + 4]
        v24 = rec[0] | (rec[1] << 8) | (rec[2] << 16)
        print(f"    +{pos}: uint24={v24} (0x{v24:x}), byte3={rec[3]} (0x{rec[3]:02x})")
        pos += 4

    # ── Try different map_levels section pointer ───────────────────────
    # Maybe we have the map_levels and subdivision pointers SWAPPED
    # What if: subdivisions are at 0x28c0 (20 bytes) and
    #           map_levels are at 0x5b4 (8972 bytes)?

    # subdivisions at 0x28c0, 20 bytes:
    subd_alt = tre[0x28C0 : 0x28C0 + 20]
    print("\n  Alternative: subdivisions at 0x28c0 (20 bytes):")
    print(f"    {subd_alt.hex()}")
    # 20 bytes = 5 x 4-byte records
    for i in range(5):
        rec = subd_alt[i * 4 : (i + 1) * 4]
        print(
            f"    Level {i}: {rec.hex()} -> byte0={rec[0]} byte1={rec[1]} u16={u16(rec, 2)}"
        )

    # map_levels at 0x5b4, 8972 bytes:
    ml_alt = tre[0x5B4 : 0x5B4 + 64]
    print("\n  Alternative: map_levels at 0x5b4 (first 64 bytes of 8972):")
    print(hexdump(ml_alt, tre_offset + 0x5B4, 64, "    "))

    # ── Re-examine the TRE header layout ───────────────────────────────
    # Let's dump the ENTIRE TRE header with annotations
    print("\n" + "=" * 80)
    print("TRE HEADER BYTE-BY-BYTE ANNOTATION")
    print("=" * 80)

    tre_hdr = tre[:tre_hdr_len]
    print(f"\n  TRE header ({tre_hdr_len} bytes):")

    # Print in groups of 16 with annotations
    for base in range(0, tre_hdr_len, 16):
        chunk = tre_hdr[base : base + 16]
        hex_str = " ".join(f"{b:02x}" for b in chunk)
        annotations = []

        # Annotate known fields
        if base == 0:
            annotations.append("header_length(u16)")
        elif base == 2:
            annotations.append("signature 'GARMIN TRE'")
        elif base == 12:
            annotations.append("version(1) lock(1)")
        elif base == 14:
            annotations.append("date(7)")
        elif base == 21:
            annotations.append("N bound (3-byte)")
        elif base == 24:
            annotations.append("E bound (3-byte)")
        elif base == 27:
            annotations.append("S bound (3-byte)")
        elif base == 30:
            annotations.append("W bound (3-byte)")
        elif base == 33:
            annotations.append(
                f"sec0_pos=0x{u32(tre_hdr, 33):x} sec0_size={u32(tre_hdr, 37)}"
            )
        elif base == 41:
            annotations.append(
                f"sec1_pos=0x{u32(tre_hdr, 41):x} sec1_size={u32(tre_hdr, 45)}"
            )
        elif base == 49:
            annotations.append(
                f"sec2_pos=0x{u32(tre_hdr, 49):x} sec2_size={u32(tre_hdr, 53)}"
            )
        elif base == 57:
            annotations.append(f"sec2_item_size={u16(tre_hdr, 57)}")

        ann = " ; ".join(annotations) if annotations else ""
        print(f"  +{base:3d}: {hex_str}")
        if ann:
            print(f"        ^-- {ann}")

    # ── KEY INSIGHT: Check TRE header for the map ID and priority ──────
    print("\n  TRE header key values:")
    print(f"    Map ID at +116: 0x{u32(tre_hdr, 116):08x}")
    print(f"    Map ID at +207: 0x{u32(tre_hdr, 207):08x}")

    # Search for priority=24 (0x18)
    for i in range(tre_hdr_len):
        if tre_hdr[i] == 24 and i > 50:
            context = tre_hdr[max(0, i - 2) : i + 3]
            # print(f"    Byte 0x18 at offset +{i}: context={context.hex()}")

    # ── Look at what's BEFORE the map_levels section ───────────────────
    # TRE data sections should be: copyright + subdivisions + map_levels
    # In that order, based on the position values:
    #   copyright at 0x5ae (6 bytes)
    #   subdivisions at 0x5b4 (8972 bytes)
    #   map_levels at 0x28c0 (20 bytes)
    # But 0x28c0 > 0x5b4 + 8972 = 0x28c0!  <-- THIS IS THE KEY!
    # 0x5b4 + 8972 = 0x5b4 + 0x230c = 0x28c0!
    # The map_levels section starts RIGHT AFTER the subdivisions section!

    print(
        f"\n  CRITICAL: subdivision end = 0x{sd_pos:x} + {sd_size} = 0x{sd_pos + sd_size:x}"
    )
    print(f"            map_levels start = 0x{ml_pos:x}")
    print(f"            Match: {sd_pos + sd_size == ml_pos}")

    # Also check copyright
    cp_pos = u32(tre, 49)  # 0x5ae
    cp_size = u32(tre, 53)  # 6
    print(f"\n  Copyright at 0x{cp_pos:x}, size={cp_size}")
    print(f"  Subdivisions start at 0x{sd_pos:x}")
    print(
        f"  Gap between copyright end and subdiv start: {sd_pos - (cp_pos + cp_size)}"
    )

    # ── Now re-examine the map_levels as uint32 ────────────────────────
    # They could be: cumulative tile count per level, or something else
    # Let me check with known total: 32443 tiles
    print("\n  Map levels as uint32 values (cumulative offsets?):")
    for i in range(5):
        val = u32(ml_raw, i * 4)
        print(f"    Level {i}: {val}")

    # The values are: 1422, 375240, 385822, 817152, ...last one weird
    # These are WAY too large for 32443 tiles (max index would be ~32442)
    # But they could be byte offsets into the RGN data section

    # ── RGN SECTION ────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("RGN SECTION ANALYSIS")
    print("=" * 80)

    rgn = gmp_data[rgn_offset:]
    rgn_hdr_len = u16(rgn, 0)
    rgn_data_pos = u32(rgn, 21)
    rgn_data_size = u32(rgn, 25)
    print(f"\n  RGN data: pos=0x{rgn_data_pos:x}, size={rgn_data_size:,}")

    # Check ext sections
    ext_sections = []
    off = 29
    while off + 8 <= rgn_hdr_len:
        p = u32(rgn, off)
        s = u32(rgn, off + 4)
        ext_sections.append((p, s))
        off += 8

    for idx, (p, s) in enumerate(ext_sections[:4]):
        if s > 0:
            print(f"  Ext section {idx}: pos=0x{p:x}, size={s:,}")

    # The RGN data section contains subdivision data
    # In the vector format, each subdivision has an RGN record
    # For raster, this might contain tile index offsets

    # Read RGN data
    rgn_abs = rgn_offset + rgn_data_pos
    if rgn_abs + min(rgn_data_size, 4096) > len(gmp_data):
        f.seek(gmp_start + len(gmp_data))
        gmp_data.extend(f.read(rgn_abs + 4096 - len(gmp_data)))

    rgn_section = bytes(gmp_data[rgn_abs : rgn_abs + min(rgn_data_size, 4096)])
    print("\n  RGN data (first 256 bytes):")
    print(hexdump(rgn_section, rgn_abs, 256, "    "))

    # Check if RGN ext sections contain the actual tile data
    # The first ext section might be the bitmap area
    for idx, (p, s) in enumerate(ext_sections[:2]):
        if s > 0:
            ext_abs = rgn_offset + p
            if ext_abs + 64 > len(gmp_data):
                f.seek(gmp_start + len(gmp_data))
                gmp_data.extend(f.read(ext_abs + 64 - len(gmp_data) + 1024))
            ext_data = bytes(gmp_data[ext_abs : ext_abs + min(64, s)])
            print(f"\n  RGN ext {idx} at RGN+0x{p:x}, size={s:,}:")
            print(hexdump(ext_data, ext_abs, len(ext_data), "    "))

            # Check for JPEG signature
            if s > 1000:
                # Read a bit more
                if ext_abs + 1024 > len(gmp_data):
                    f.seek(gmp_start + len(gmp_data))
                    gmp_data.extend(f.read(ext_abs + 1024 - len(gmp_data)))
                more_data = bytes(gmp_data[ext_abs : ext_abs + 1024])
                jpeg_pos = more_data.find(b"\xff\xd8\xff")
                if jpeg_pos >= 0:
                    print(f"    JPEG SOI found at offset {jpeg_pos}!")

    # ── The REAL map_levels interpretation ─────────────────────────────
    # Going back to the TRE header. The 4-byte map_levels records
    # might actually be in a DIFFERENT format.
    #
    # Let me look at the raw bytes again: 8e 05 00 00 c8 b8 05 00 00 9e e2 05 00 00 74 0c 06 00 00 4a
    #
    # If these are tile COUNTS per level:
    # Level 0: 0x0000058e = 1422 tiles
    # Level 1: 0x0005b8c8 = 375240 tiles  <-- too many
    #
    # If these are byte OFFSETS into RGN data:
    # Level 0 offset: 1422
    # Level 1 offset: 375240
    # Level 2 offset: 385822
    # Total RGN data: depends on ext sections

    # Wait - maybe the format in the TRE header is NOT what I documented.
    # Let me look at what position/size pairs ACTUALLY make sense.

    # Section at 0x5ae, size 6 (copyright)
    cp_content = tre[0x5AE : 0x5AE + 6]
    print(f"\n  Copyright section at TRE+0x5ae (6 bytes): {cp_content.hex()}")

    # Section at 0x5b4, size 8972 (subdivisions) - already analyzed
    # Section at 0x28c0, size 20 (map_levels?)

    # Actually, let me reconsider: what if the "map_levels" section
    # at 0x28c0 contains the number of subdivisions per level as uint32?
    # 1422, 375240, ... No, that doesn't work.

    # Let me try interpreting the 20 bytes differently:
    # As 5 x (n_subdivisions_u16, zoom_level_u8, bits_u8) - reversed order?
    print("\n  Map levels bytes re-examined:")
    print(f"  {ml_raw.hex()}")
    print("  As pairs: ", end="")
    for i in range(0, 20, 4):
        b = ml_raw[i : i + 4]
        # Try: n_subdiv(u16 LE), level_zoom(u8), pad(u8)
        ns = u16(ml_raw, i)
        b2 = b[2]
        b3 = b[3]
        print(f"[ns={ns}, b2={b2}, b3={b3}]", end=" ")
    print()

    # Or: level(1), zoom(1), n_subdiv(u16)
    print("  As level/zoom/nsub: ", end="")
    for i in range(0, 20, 4):
        b = ml_raw[i : i + 4]
        level = b[0]
        zoom = b[1]
        ns = u16(b, 2)
        print(f"[lv={level}, zm={zoom}, ns={ns}]", end=" ")
    print()

    # Hmm. The values are: [lv=142, zm=5, ns=0] etc. Not matching [20,21,22,23,24]

    # Wait - maybe the map_levels section is somewhere ELSE entirely.
    # Let me search the ENTIRE TRE header for the byte sequence
    # 14 00 15 00 16 00 17 00 18 00 or similar (level numbers as uint16)
    print("\n  Searching for level values in various encodings:")
    # As bytes: 14 15 16 17 18
    # As uint16 LE: 14 00 15 00 16 00 17 00 18 00
    for pattern in [
        bytes([20, 21, 22, 23, 24]),
        struct.pack("<5H", 20, 21, 22, 23, 24),
        struct.pack(">5H", 20, 21, 22, 23, 24),
    ]:
        pos = tre.find(pattern)
        if pos >= 0:
            print(f"    Found {pattern.hex()} at TRE offset 0x{pos:x}")
            context = tre[pos : pos + 20]
            print(f"    Context: {context.hex()}")

    # Also search for zoom values
    for pattern in [bytes([84, 83, 2, 1, 0]), struct.pack("<5H", 84, 83, 2, 1, 0)]:
        pos = tre.find(pattern)
        if pos >= 0:
            print(f"    Found zoom pattern {pattern.hex()} at TRE offset 0x{pos:x}")

    # ── Look at the subdivision records more carefully ─────────────────
    print("\n" + "=" * 80)
    print("SUBDIVISION RECORD DEEP DIVE")
    print("=" * 80)

    # The subdivision section has 8972 bytes.
    # Looking at the hex, records repeat in 16-byte patterns.
    # But 8972 / 16 = 560.75
    # 8972 = 560 * 16 + 12 = 8960 + 12

    # In vector format, the LAST level uses 14-byte records (no next_subdiv field)
    # 8972 = N * 16 + M * 14
    # If M = 612 (level 24 count), then N * 16 = 8972 - 612 * 14 = 8972 - 8568 = 404
    # 404 / 16 = 25.25 -- not clean

    # If M = 612 and we use 14-byte for last: 612 * 14 = 8568, remaining = 404
    # Remaining subdivisions: 1 + 3 + 16 + 96 = 116
    # 404 / 116 = 3.48... not clean

    # Let's try: what if the LAST level uses a different size?
    # What sizes make the math work for 116 records + 612 records = 8972 bytes?
    for first_size in range(8, 20):
        for last_size in range(8, 20):
            total = 116 * first_size + 612 * last_size
            if total == 8972:
                print(
                    f"  MATCH: first_116 * {first_size} + last_612 * {last_size} = {total}"
                )

    # Also try with different level counts
    counts = [1, 3, 16, 96, 612]
    for first_n in range(1, 6):
        first_count = sum(counts[:first_n])
        last_count = sum(counts[first_n:])
        for first_size in range(8, 20):
            for last_size in range(8, 20):
                total = first_count * first_size + last_count * last_size
                if total == 8972:
                    print(
                        f"  MATCH: first_{first_count}({counts[:first_n]})*{first_size} + "
                        f"last_{last_count}({counts[first_n:]})*{last_size} = {total}"
                    )

    # ── Try ALL-SAME record sizes with remainder ──────────────────────
    # Maybe there's a header at the start
    for hdr_size in range(0, 32):
        remaining = sd_size - hdr_size
        for rs in [8, 12, 14, 16]:
            if remaining % rs == 0:
                cnt = remaining // rs
                print(
                    f"  HDR={hdr_size} + {cnt} * {rs} = {hdr_size + cnt * rs} "
                    f"(records={cnt})"
                )

    # ── Parse the actual 16-byte records ───────────────────────────────
    print("\n  Parsing first 20 records as 16-byte (vector format):")
    print(
        f"  {'#':>4s}  {'rgn_ptr':>8s} {'obj':>4s} {'lon_c':>8s} {'lat_c':>8s} "
        f"{'width':>6s} {'height':>6s} {'next':>6s}"
    )

    for i in range(min(20, len(sd_raw) // 16)):
        rec = sd_raw[i * 16 : (i + 1) * 16]
        rgn_ptr = rec[0] | (rec[1] << 8) | (rec[2] << 16)
        obj_types = rec[3]
        lon_c = i24(rec, 4)
        lat_c = i24(rec, 7)
        width = u16(rec, 10)
        height = u16(rec, 12)
        next_sub = u16(rec, 14)

        term = (width >> 15) & 1
        w_val = width & 0x7FFF

        print(
            f"  {i:4d}  0x{rgn_ptr:06x} 0x{obj_types:02x} {lon_c:>8d} {lat_c:>8d} "
            f"{w_val:>5d}t{term} {height:>6d} {next_sub:>6d}"
        )

    # ── Check last few records ─────────────────────────────────────────
    # If last level uses 14-byte records, the boundary would be at:
    # 8972 - 612 * 14 = 404 bytes from start
    # Or: 8972 - 612 * 16 = -8812 -- nope, last level would exceed section

    # The last 14 bytes:
    print("\n  Last 32 bytes of subdivision section:")
    print(f"  {sd_raw[-32:].hex()}")
    print("\n  Last 16 bytes as vector record:")
    rec = sd_raw[-16:]
    rgn_ptr = rec[0] | (rec[1] << 8) | (rec[2] << 16)
    obj_types = rec[3]
    lon_c = i24(rec, 4)
    lat_c = i24(rec, 7)
    width = u16(rec, 10)
    height = u16(rec, 12)
    next_sub = u16(rec, 14)
    print(
        f"    rgn_ptr=0x{rgn_ptr:x} obj=0x{obj_types:02x} lon={lon_c}({mu2deg(lon_c):.4f}) "
        f"lat={lat_c}({mu2deg(lat_c):.4f}) w={width} h={height} next={next_sub}"
    )

    # ── Final: look at the ext_type_areas RGN section ──────────────────
    # This might be where the actual tile data pointers are
    print("\n" + "=" * 80)
    print("RGN EXT TYPE SECTIONS")
    print("=" * 80)

    for idx, (p, s) in enumerate(ext_sections[:4]):
        if s > 0:
            print(f"\n  RGN ext section {idx}: pos=0x{p:x} (rel to RGN), size={s:,}")
            ext_abs = rgn_offset + p
            if s > 1000000:
                print("    (very large, reading first 128 bytes)")
                read_sz = 128
            else:
                read_sz = min(256, s)

            if ext_abs + read_sz > len(gmp_data):
                f.seek(gmp_start + len(gmp_data))
                gmp_data.extend(f.read(ext_abs + read_sz - len(gmp_data) + 1024))

            ext_data = bytes(gmp_data[ext_abs : ext_abs + read_sz])
            print(hexdump(ext_data, ext_abs, len(ext_data), "    "))

            # Check for JPEG marker
            for j in range(len(ext_data) - 2):
                if ext_data[j] == 0xFF and ext_data[j + 1] == 0xD8:
                    print(f"    JPEG SOI at offset +{j}")
                    break

    f.close()

    # ── FINAL SUMMARY ──────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print(f"""
  GMP subfile: 0x{gmp_start:x}, {gmp_size:,} bytes

  TRE sub-header (273 bytes):
    Bounds: N={mu2deg(north):.4f} S={mu2deg(south):.4f} W={mu2deg(west):.4f} E={mu2deg(east):.4f}
    Section layout (relative to TRE start):
      Copyright:      0x{cp_pos:x} - 0x{cp_pos + cp_size:x} ({cp_size} bytes)
      Subdivisions:   0x{sd_pos:x} - 0x{sd_pos + sd_size:x} ({sd_size} bytes)
      Map levels:     0x{ml_pos:x} - 0x{ml_pos + ml_size:x} ({ml_size} bytes)
      (subdiv end == map_levels start: {sd_pos + sd_size == ml_pos})

  Map levels section (20 bytes, 5 levels):
    Raw: {ml_raw.hex()}
    Values as uint32: {[u32(ml_raw, i * 4) for i in range(5)]}

  Subdivision section ({sd_size} bytes):
    Record pattern: clearly 16-byte repeating patterns visible
    8972 / 16 = {8972 / 16:.2f} (not evenly divisible)
    8972 = 560 * 16 + 12 (12 bytes remainder)

  RGN data section: pos=0x{rgn_data_pos:x}, size={rgn_data_size:,}
  RGN ext sections: {[(f"0x{p:x}", f"{s:,}") for p, s in ext_sections[:4]]}
""")


if __name__ == "__main__":
    main()
