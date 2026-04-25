#!/usr/bin/env python3
"""
Garmin IMG Binary Analysis Tool

Parses GMP container headers and computes TRE/RGN/LBL section offsets
from any GMP subfile in an IMG file. Supports FAT chain traversal
for multi-part subfiles (needed for IOM.img).

TRE header layout based on Alex Whiter's QMapShack wiki analysis:
  TRE+0x00:  sub-header (21 bytes: hdr_len(2), sig(10), ver(1), lock(1), date(7))
  TRE+0x15:  bounds (12 bytes: N(3), E(3), S(3), W(3))
  TRE+0x21:  TRE1 pos(4), size(4)
  TRE+0x29:  TRE2 pos(4), size(4)
  TRE+0x31:  TRE3 pos(4), size(4), item_size(2)
  TRE+0x3B:  padding(4)
  TRE+0x3F:  flags(1)
  TRE+0x40:  display priority(2)
  TRE+0x42:  more flags(8)
  TRE+0x4A:  TRE4: pos(4), size(4), rec_size(2), pad(4)
  TRE+0x58:  TRE5: pos(4), size(4), rec_size(2), pad(4)
  TRE+0x66:  TRE6: pos(4), size(4), rec_size(2), pad(4)
  TRE+0x74:  map_id(4)
  TRE+0x78:  padding(4)
  TRE+0x7C:  TRE7: pos(4), size(4), rec_size(2), pad(4)
  TRE+0x8A:  TRE8: pos(4), size(4), rec_size(2), pad(6)
  TRE+0x9A:  map_id_hash(16)
  TRE+0xAA:  padding(4)
  TRE+0xAE:  TRE9: pos(4), size(4), rec_size(2), pad(4)
  TRE+0xBC:  TRE10: pos(4), size(4), rec_size(2), pad(4)
  TRE+0xCA:  padding(5)
  TRE+0xCF:  matching number(4)
  TRE+0xD3:  name string (rest of header)

Usage:
    python img_analysis.py <img_file> [--subfile <name>] [--hex <section>] [--dump <section>]

Sections: gmp-header, tre-header, tre-levels, tre-subdivs, tre7, tre8,
          rgn-header, rgn-data, rgn2, rgn5, lbl-header, lbl-data, all
"""

import struct
import os
import argparse


def decode_garmin_date(data):
    """Decode 7-byte Garmin date format."""
    if len(data) < 7:
        return "N/A"
    year = struct.unpack_from("<H", data, 0)[0]
    month = data[2]
    day = data[3]
    hour = data[4]
    minute = data[5]
    second = data[6]
    return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"


def decode_3byte_signed(data, offset=0):
    """Decode a 3-byte signed little-endian integer."""
    b = data[offset : offset + 3]
    val = b[0] | (b[1] << 8) | (b[2] << 16)
    if val & 0x800000:
        val -= 0x1000000
    return val


def map_units_to_degrees(map_units):
    """Convert Garmin 3-byte map units to degrees."""
    return map_units * 360.0 / (2**24)


def map_units_to_degrees_32(map_units):
    """Convert Garmin 4-byte map units (int32) to degrees."""
    return map_units * 180.0 / (2**31)


class IMGParser:
    def __init__(self, filepath):
        self.filepath = filepath
        self.f = open(filepath, "rb")
        self.filesize = os.path.getsize(filepath)
        self.block_size = None
        self.header = {}
        self.fat_entries = []
        self.subfiles = {}

    def close(self):
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def read_at(self, offset, size):
        """Read bytes at absolute file offset."""
        self.f.seek(offset)
        return self.f.read(size)

    def parse_header(self):
        """Parse the 512-byte IMG file header."""
        data = self.read_at(0, 512)

        xor = data[0]
        magic = data[0x10:0x16].decode("ascii", errors="replace").rstrip("\x00")
        version = data[0x17]
        _sectors = struct.unpack_from("<H", data, 0x18)[0]
        _heads = struct.unpack_from("<H", data, 0x1A)[0]
        fat_block = data[0x40]
        creator = data[0x41:0x49].decode("ascii", errors="replace").rstrip("\x00")
        description = data[0x49:0x5D].decode("ascii", errors="replace").rstrip("\x00 ")

        # Date
        year = struct.unpack_from("<H", data, 0x39)[0]
        month = data[0x3B]
        day = data[0x3C]
        hour = data[0x3D]
        sec = data[0x3E]

        e1 = data[0x61]
        e2 = data[0x62]
        self.block_size = 512 * (2**e2)
        total_blocks = struct.unpack_from("<H", data, 0x63)[0]

        self.header = {
            "xor": xor,
            "magic": magic,
            "version": version,
            "fat_block": fat_block,
            "creator": creator,
            "description": description,
            "date": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:xx:{sec:02d}",
            "block_size": self.block_size,
            "total_blocks": total_blocks,
            "e1": e1,
            "e2": e2,
        }
        return self.header

    def parse_fat(self):
        """Parse FAT entries to find all subfiles and their block chains."""
        fat_start = self.header["fat_block"] * 512
        self.fat_entries = []
        self.subfiles = {}

        offset = fat_start
        while True:
            data = self.read_at(offset, 512)
            flag = data[0]
            if flag == 0x00:
                break

            name = data[0x01:0x09].decode("ascii", errors="replace").rstrip()
            stype = data[0x09:0x0C].decode("ascii", errors="replace").rstrip()
            subfile_size = struct.unpack_from("<I", data, 0x0C)[0]
            flag2 = data[0x10]
            part = data[0x11]

            # Extract block pointers
            blocks = []
            for i in range(240):
                blk = struct.unpack_from("<H", data, 0x20 + i * 2)[0]
                if blk == 0xFFFF:
                    break
                blocks.append(blk)

            entry = {
                "flag": flag,
                "name": name,
                "type": stype,
                "size": subfile_size,
                "flag2": flag2,
                "part": part,
                "blocks": blocks,
                "offset": offset,
            }
            self.fat_entries.append(entry)

            # Group by subfile
            key = f"{name}.{stype}"
            if key not in self.subfiles:
                self.subfiles[key] = {
                    "name": name,
                    "type": stype,
                    "size": subfile_size,
                    "parts": [],
                }
            self.subfiles[key]["parts"].append(entry)

            offset += 512

        return self.subfiles

    def reconstruct_subfile(self, subfile_key):
        """Reconstruct complete subfile data by following FAT block chains."""
        sf = self.subfiles[subfile_key]

        # Sort parts by part number
        parts = sorted(sf["parts"], key=lambda p: p["part"])

        data = bytearray()
        for part in parts:
            for blk in part["blocks"]:
                chunk = self.read_at(blk * self.block_size, self.block_size)
                data.extend(chunk)

        # Trim to actual size
        return bytes(data[: sf["size"]])

    def parse_gmp_container(self, subfile_key):
        """Parse GMP container header to find section offsets."""
        data = self.reconstruct_subfile(subfile_key)

        hdr_size = data[0]
        _flag = data[1]
        sig = data[2:12].decode("ascii", errors="replace")
        version = struct.unpack_from("<H", data, 12)[0]
        date = decode_garmin_date(data[14:21])
        section_table_off = struct.unpack_from("<I", data, 21)[0]

        # Section offsets (7 x uint32 LE) start at offset 25
        sections = {}
        section_names = ["TRE", "RGN", "LBL", "NET", "S5", "S6", "S7"]
        for i, name in enumerate(section_names):
            sec_off = struct.unpack_from("<I", data, 25 + i * 4)[0]
            if sec_off > 0:
                sections[name] = sec_off

        container = {
            "header_size": hdr_size,
            "signature": sig,
            "version": version,
            "date": date,
            "section_table_offset": section_table_off,
            "sections": sections,
            "data": data,
            "data_size": len(data),
        }
        return container

    def parse_sub_header(self, data, section_name):
        """Parse a common 21-byte sub-header prefix."""
        hdr_len = struct.unpack_from("<H", data, 0)[0]
        sig = data[2:12].decode("ascii", errors="replace")
        version = data[12]
        lock = data[13]
        date = decode_garmin_date(data[14:21])

        return {
            "header_length": hdr_len,
            "signature": sig,
            "version": version,
            "lock": lock,
            "date": date,
        }

    def _parse_tre_section_descriptor(self, tre, offset):
        """Parse a TRE extended section descriptor: pos(4), size(4), rec_size(2), pad(4).
        Returns dict or None if not enough data or section is empty."""
        if offset + 14 > len(tre):
            return None
        pos = struct.unpack_from("<I", tre, offset)[0]
        size = struct.unpack_from("<I", tre, offset + 4)[0]
        rec_size = struct.unpack_from("<H", tre, offset + 8)[0]
        # 4 bytes padding after rec_size
        return {
            "position": pos,
            "size": size,
            "record_size": rec_size,
            "header_offset": offset,
        }

    def parse_tre(self, gmp):
        """Parse TRE sub-header and data sections using QMapShack layout.

        CRITICAL: TRE section position/size values stored in the TRE header
        (TRE1, TRE2, etc.) are offsets relative to the START OF THE GMP DATA,
        not relative to the TRE block start.

        The QMapShack wiki offsets like TRE+0x21 are relative to the TRE block
        start, but the VALUES stored there (positions like 0x508) are GMP-relative.
        """
        tre_off = gmp["sections"]["TRE"]
        data = gmp["data"]
        tre = data[tre_off:]

        # Sub-header (21 bytes)
        sub = self.parse_sub_header(tre, "TRE")
        hdr_len = sub["header_length"]

        result = {
            "sub_header": sub,
        }

        # Bounds at TRE+0x15 (offset 21)
        north = decode_3byte_signed(tre, 21)
        east = decode_3byte_signed(tre, 24)
        south = decode_3byte_signed(tre, 27)
        west = decode_3byte_signed(tre, 30)
        result.update(
            {
                "north": north,
                "east": east,
                "south": south,
                "west": west,
                "north_deg": map_units_to_degrees(north),
                "east_deg": map_units_to_degrees(east),
                "south_deg": map_units_to_degrees(south),
                "west_deg": map_units_to_degrees(west),
            }
        )

        # Helper: read section data using GMP-relative positions from TRE header
        def get_section_data(tre_offset):
            """Read pos(4) and size(4) from TRE header, return data from GMP start."""
            pos = struct.unpack_from("<I", tre, tre_offset)[0]
            size = struct.unpack_from("<I", tre, tre_offset + 4)[0]
            return pos, size, data[pos : pos + size] if pos > 0 and size > 0 else b""

        # TRE1 (levels) at TRE+0x21
        tre1_pos, tre1_size, levels_data = get_section_data(0x21)
        if tre1_pos > 0:
            result["tre1"] = {"position": tre1_pos, "size": tre1_size}
            result["map_levels_pos"] = tre1_pos
            result["map_levels_size"] = tre1_size

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
            result["levels"] = levels

        # TRE2 (groups/subdivisions) at TRE+0x29
        tre2_pos, tre2_size, subdivs_data = get_section_data(0x29)
        if tre2_pos > 0:
            result["tre2"] = {"position": tre2_pos, "size": tre2_size}
            result["subdivs_pos"] = tre2_pos
            result["subdivs_size"] = tre2_size

            result["subdivs_hex"] = subdivs_data.hex()

            # Try parsing as 16-byte group records (raster format)
            groups = []
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
                    groups.append(
                        {
                            "rgn_offset": rgn_off,
                            "obj_types": f"0x{obj_types:02X}",
                            "lon_center": lon,
                            "lat_center": lat,
                            "lon_center_deg": map_units_to_degrees(lon),
                            "lat_center_deg": map_units_to_degrees(lat),
                            "flags": flags,
                            "subdiv_count": subdiv_count,
                            "next_level_index": next_level,
                            "raw_hex": rec.hex(),
                        }
                    )
            result["groups_16byte"] = groups

            # Also try 14-byte vector subdivision records
            vec_groups = []
            for i in range(0, len(subdivs_data) - 14, 14):
                if i + 14 <= len(subdivs_data):
                    rec = subdivs_data[i : i + 14]
                    rgn_off = rec[0] | (rec[1] << 8) | (rec[2] << 16)
                    obj_types = rec[3]
                    lon = decode_3byte_signed(rec, 4)
                    lat = decode_3byte_signed(rec, 7)
                    width = struct.unpack_from("<H", rec, 10)[0]
                    height = struct.unpack_from("<H", rec, 12)[0]
                    vec_groups.append(
                        {
                            "rgn_offset": rgn_off,
                            "obj_types": f"0x{obj_types:02X}",
                            "lon_center": lon,
                            "lat_center": lat,
                            "lon_center_deg": map_units_to_degrees(lon),
                            "lat_center_deg": map_units_to_degrees(lat),
                            "width": width,
                            "height": height,
                            "raw_hex": rec.hex(),
                        }
                    )
            result["groups_14byte"] = vec_groups

        # TRE3 (copyright) at TRE+0x31
        tre3_pos = struct.unpack_from("<I", tre, 0x31)[0]
        tre3_size = struct.unpack_from("<I", tre, 0x35)[0]
        tre3_item = struct.unpack_from("<H", tre, 0x39)[0]
        result["tre3"] = {
            "position": tre3_pos,
            "size": tre3_size,
            "item_size": tre3_item,
        }

        # Display priority at TRE+0x40 (2 bytes)
        if hdr_len > 0x42:
            result["display_priority"] = struct.unpack_from("<H", tre, 0x40)[0]

        # TRE4-TRE10 descriptors (positions are GMP-relative)
        for name, off in [("tre4", 0x4A), ("tre5", 0x58), ("tre6", 0x66)]:
            sec = self._parse_tre_section_descriptor(tre, off)
            if sec:
                result[name] = sec

        # Map ID at TRE+0x74
        if hdr_len > 0x78:
            result["map_id"] = struct.unpack_from("<I", tre, 0x74)[0]

        # TRE7 (raster layer) at TRE+0x7C - position is GMP-relative
        tre7_hdr = self._parse_tre_section_descriptor(tre, 0x7C)
        if tre7_hdr and tre7_hdr["position"] > 0:
            result["tre7"] = tre7_hdr
            tre7_data = data[
                tre7_hdr["position"] : tre7_hdr["position"] + tre7_hdr["size"]
            ]
            result["tre7_hex"] = tre7_data.hex()

            offsets = []
            rec_size = tre7_hdr["record_size"]
            if rec_size == 0:
                rec_size = 4  # fallback for files without rec_size
            for i in range(0, len(tre7_data), rec_size):
                if i + rec_size <= len(tre7_data):
                    off = struct.unpack_from("<I", tre7_data, i)[0]
                    flag = tre7_data[i + 4] if rec_size >= 5 else None
                    entry = {"offset": off}
                    if flag is not None:
                        entry["flag"] = flag
                    offsets.append(entry)
            result["tre7_offsets"] = offsets

        # TRE8 (object type params) at TRE+0x8A - position is GMP-relative
        tre8_hdr = self._parse_tre_section_descriptor(tre, 0x8A)
        if tre8_hdr and tre8_hdr["size"] > 0:
            result["tre8"] = tre8_hdr
            tre8_data = data[
                tre8_hdr["position"] : tre8_hdr["position"] + tre8_hdr["size"]
            ]
            result["tre8_hex"] = tre8_data.hex()

            entries = []
            for i in range(0, len(tre8_data), 3):
                if i + 3 <= len(tre8_data):
                    entries.append(
                        {
                            "type": f"0x{tre8_data[i]:02X}",
                            "param1": f"0x{tre8_data[i + 1]:02X}",
                            "param2": f"0x{tre8_data[i + 2]:02X}",
                            "raw": tre8_data[i : i + 3].hex(),
                        }
                    )
            result["tre8_entries"] = entries

        # TRE9 at TRE+0xAE, TRE10 at TRE+0xBC
        for name, off in [("tre9", 0xAE), ("tre10", 0xBC)]:
            sec = self._parse_tre_section_descriptor(tre, off)
            if sec:
                result[name] = sec

        # Matching number at TRE+0xCF
        if hdr_len > 0xD3:
            result["matching_number"] = struct.unpack_from("<I", tre, 0xCF)[0]

        # Map name at TRE+0xD3
        if hdr_len > 0xD4:
            name_data = tre[0xD3:hdr_len]
            result["map_name"] = name_data.decode("ascii", errors="replace").rstrip(
                "\x00 "
            )

        # Store header hex for debugging
        result["tre_header_hex"] = tre[:hdr_len].hex()

        return result

    def parse_rgn(self, gmp):
        """Parse RGN sub-header and data sections.

        RGN section positions (like TRE) are GMP-relative offsets.
        The QMapShack wiki RGN layout for IOM subfile 00355951:
          RGN+0x00: sub-header (21 bytes)
          RGN+0x15: RGN1 pos(4), size(4) - standard data
          RGN+0x1D: RGN2 pos(4), size(4) - extended type data (raster layers)
          RGN+0x25: 20 bytes flags/padding
          RGN+0x39: RGN3 pos(4), size(4)
          RGN+0x41: 20 bytes flags/padding
          RGN+0x55: RGN4 pos(4), size(4)
          RGN+0x5D: 20 bytes flags/padding
          RGN+0x71: RGN5 pos(4), size(4) + extra(4)
          RGN+0x79: RGNEXT header
        """
        rgn_off = gmp["sections"]["RGN"]
        data = gmp["data"]
        rgn = data[rgn_off:]

        sub = self.parse_sub_header(rgn, "RGN")
        hdr_len = sub["header_length"]

        result = {
            "sub_header": sub,
        }

        # Helper: read section data using GMP-relative positions
        def get_rgn_section(rgn_offset):
            pos = struct.unpack_from("<I", rgn, rgn_offset)[0]
            size = struct.unpack_from("<I", rgn, rgn_offset + 4)[0]
            return pos, size, data[pos : pos + size] if pos > 0 and size > 0 else b""

        # RGN1 at RGN+0x15
        if hdr_len >= 0x1D:
            pos, size, _ = get_rgn_section(0x15)
            result["rgn1"] = {"position": pos, "size": size}
            result["data_position"] = pos
            result["data_size"] = size

        # RGN2 at RGN+0x1D
        if hdr_len >= 0x25:
            pos, size, rgn2_data = get_rgn_section(0x1D)
            result["rgn2"] = {"position": pos, "size": size}
            if size > 0:
                result["rgn2_hex"] = rgn2_data.hex()
                result["rgn2_records"] = self._parse_rgn2_records(rgn2_data)

        # RGN3 at RGN+0x39
        if hdr_len >= 0x41:
            pos, size, _ = get_rgn_section(0x39)
            result["rgn3"] = {"position": pos, "size": size}

        # RGN4 at RGN+0x55
        if hdr_len >= 0x5D:
            pos, size, _ = get_rgn_section(0x55)
            result["rgn4"] = {"position": pos, "size": size}

        # RGN5 at RGN+0x71
        if hdr_len >= 0x75:
            pos, size, rgn5_data = get_rgn_section(0x71)
            result["rgn5"] = {"position": pos, "size": size}
            if size > 0:
                result["rgn5_hex"] = rgn5_data.hex()

        # Parse RGN1 (main data) if present
        if "rgn1" in result and result["rgn1"]["size"] > 0:
            pos = result["rgn1"]["position"]
            size = result["rgn1"]["size"]
            result["rgn1_hex"] = data[pos : pos + size].hex()

        # Store header hex
        result["rgn_header_hex"] = rgn[:hdr_len].hex()

        return result

    def _parse_rgn2_records(self, data):
        """Parse RGN2 subdivision records (raster layer descriptions).

        These contain a mix of record types:
        - 0D xx: POI-like record (xx = length indicator)
        - 06 xx: polyline-like record
        - BC 00 00: boundary marker
        - DE 00 00: extended boundary marker
        - E0 xx yy: raster tile (Type E0) with bits_field and image index
          followed by 4 x int32 coordinates and uint32 block_size
        """
        records = []
        pos = 0

        while pos < len(data):
            marker = data[pos]

            if marker == 0x0D:
                # POI-like: 0D + length_byte + data
                if pos + 8 <= len(data):
                    length = data[pos + 1]
                    rec_end = min(pos + 2 + length, len(data))
                    records.append(
                        {
                            "type": "0D (POI-like)",
                            "offset": pos,
                            "raw_hex": data[pos:rec_end].hex(),
                        }
                    )
                    pos = rec_end
                else:
                    records.append(
                        {
                            "type": "0D (truncated)",
                            "offset": pos,
                            "raw_hex": data[pos:].hex(),
                        }
                    )
                    break

            elif marker == 0x06:
                # Polyline-like: 06 + type_byte + delta coordinates
                if pos + 8 <= len(data):
                    sub_type = data[pos + 1]
                    # Fixed 8-byte record based on QMapShack analysis
                    records.append(
                        {
                            "type": "06 (polyline-like)",
                            "offset": pos,
                            "sub_type": f"0x{sub_type:02X}",
                            "raw_hex": data[pos : pos + 8].hex(),
                        }
                    )
                    pos += 8
                else:
                    records.append(
                        {
                            "type": "06 (truncated)",
                            "offset": pos,
                            "raw_hex": data[pos:].hex(),
                        }
                    )
                    break

            elif marker == 0xBC:
                # Boundary marker: BC 00 00
                rec_end = min(pos + 3, len(data))
                records.append(
                    {
                        "type": "BC (boundary)",
                        "offset": pos,
                        "raw_hex": data[pos:rec_end].hex(),
                    }
                )
                pos = rec_end

            elif marker == 0xDE:
                # Extended boundary: DE 00 00
                rec_end = min(pos + 3, len(data))
                records.append(
                    {
                        "type": "DE (ext boundary)",
                        "offset": pos,
                        "raw_hex": data[pos:rec_end].hex(),
                    }
                )
                pos = rec_end

            elif marker == 0xE0:
                # Type E0 raster tile record
                if pos + 3 <= len(data):
                    bits_field = data[pos + 1]

                    # Determine index size from bits_field:
                    # 0x2B = 1-byte image index (few images, e.g. IOM)
                    # 0x25 = 2-byte image index (many images, e.g. Lake District)
                    # 0x2D = 2-byte image index (SwissTopo variant)
                    if bits_field in (0x2B,):
                        idx_size = 1
                    elif bits_field in (0x25, 0x2D):
                        idx_size = 2
                    else:
                        # Unknown - assume 2-byte as fallback for large maps
                        idx_size = 2

                    rec_len = (
                        2 + idx_size + 16 + 4
                    )  # E0(1)+bits(1) + idx + coords(16) + blksize(4)
                    if pos + rec_len <= len(data):
                        if idx_size == 1:
                            img_idx = data[pos + 2]
                        else:
                            img_idx = struct.unpack_from("<H", data, pos + 2)[0]

                        coord_off = pos + 2 + idx_size
                        lat_min = struct.unpack_from("<i", data, coord_off)[0]
                        lon_min = struct.unpack_from("<i", data, coord_off + 4)[0]
                        lat_max = struct.unpack_from("<i", data, coord_off + 8)[0]
                        lon_max = struct.unpack_from("<i", data, coord_off + 12)[0]
                        block_size = struct.unpack_from("<I", data, coord_off + 16)[0]

                        records.append(
                            {
                                "type": "E0 (raster tile)",
                                "offset": pos,
                                "bits_field": f"0x{bits_field:02X}",
                                "lat_min_deg": map_units_to_degrees_32(lat_min),
                                "lon_min_deg": map_units_to_degrees_32(lon_min),
                                "lat_max_deg": map_units_to_degrees_32(lat_max),
                                "lon_max_deg": map_units_to_degrees_32(lon_max),
                                "block_size": block_size,
                                "image_index": img_idx,
                                "raw_hex": data[pos : pos + rec_len].hex(),
                            }
                        )
                        pos += rec_len
                    else:
                        records.append(
                            {
                                "type": "E0 (truncated)",
                                "offset": pos,
                                "raw_hex": data[pos:].hex(),
                            }
                        )
                        break
                else:
                    records.append(
                        {
                            "type": "E0 (truncated)",
                            "offset": pos,
                            "raw_hex": data[pos:].hex(),
                        }
                    )
                    break
            else:
                # Unknown byte
                records.append(
                    {
                        "type": f"unknown (0x{marker:02X})",
                        "offset": pos,
                        "raw_hex": data[pos : min(pos + 16, len(data))].hex(),
                    }
                )
                pos += 1

        return records

    def parse_lbl(self, gmp):
        """Parse LBL sub-header. Section positions are GMP-relative."""
        lbl_off = gmp["sections"].get("LBL", 0)
        if lbl_off == 0:
            return None

        data = gmp["data"]
        lbl = data[lbl_off:]

        sub = self.parse_sub_header(lbl, "LBL")
        hdr_len = sub["header_length"]

        result = {
            "sub_header": sub,
        }

        # Helper: read section data using GMP-relative positions
        def get_lbl_section(lbl_offset, size_only=False):
            pos = struct.unpack_from("<I", lbl, lbl_offset)[0]
            size = struct.unpack_from("<I", lbl, lbl_offset + 4)[0]
            if size_only:
                return pos, size, b""
            return pos, size, data[pos : pos + size] if pos > 0 and size > 0 else b""

        # LBL1 at LBL+0x15: pos(4), size(4), offset_mult(1), encoding(1)
        if hdr_len >= 0x1F:
            labels_pos, labels_size, _ = get_lbl_section(0x15, size_only=True)
            offset_mult = lbl[0x1D]
            encoding = lbl[0x1E]
            result["lbl1"] = {
                "position": labels_pos,
                "size": labels_size,
                "offset_multiplier": offset_mult,
                "encoding": encoding,
            }
            result["labels_position"] = labels_pos
            result["labels_size"] = labels_size
            result["offset_multiplier"] = offset_mult
            result["encoding"] = encoding

        # LBL28 at LBL+0x108: pos(4), size(4)
        if hdr_len >= 0x110:
            pos, size, _ = get_lbl_section(0x108, size_only=True)
            result["lbl28"] = {"position": pos, "size": size}

        # LBL29 at LBL+0x116: pos(4), size(4)
        if hdr_len >= 0x11E:
            pos, size, _ = get_lbl_section(0x116, size_only=True)
            result["lbl29"] = {"position": pos, "size": size}

        # Parse labels text (GMP-relative)
        if "labels_position" in result and result["labels_size"] > 0:
            pos = result["labels_position"]
            size = result["labels_size"]
            labels_data = data[pos : pos + size]
            labels = labels_data.decode("ascii", errors="replace").split("\x00")
            labels = [label for label in labels if label]
            result["labels"] = labels[:20]
            result["total_labels"] = len(labels)

        # Store header hex
        result["lbl_header_hex"] = lbl[: min(hdr_len, 512)].hex()

        return result

    def dump_section_hex(self, gmp, section):
        """Dump hex of a section for analysis. Uses GMP-relative offsets."""
        data = gmp["data"]

        if section == "gmp-header":
            return data[: gmp["header_size"]].hex()

        if section == "tre-header":
            tre_off = gmp["sections"]["TRE"]
            hdr_len = struct.unpack_from("<H", data, tre_off)[0]
            return data[tre_off : tre_off + hdr_len].hex()

        tre_off = gmp["sections"]["TRE"]
        tre = data[tre_off:]

        if section == "tre-levels":
            pos = struct.unpack_from("<I", tre, 0x21)[0]
            size = struct.unpack_from("<I", tre, 0x25)[0]
            return data[pos : pos + size].hex() if pos > 0 else ""

        if section == "tre-subdivs":
            pos = struct.unpack_from("<I", tre, 0x29)[0]
            size = struct.unpack_from("<I", tre, 0x2D)[0]
            return data[pos : pos + size].hex() if pos > 0 else ""

        if section == "tre7":
            pos = struct.unpack_from("<I", tre, 0x7C)[0]
            size = struct.unpack_from("<I", tre, 0x80)[0]
            return data[pos : pos + size].hex() if pos > 0 and size > 0 else ""

        if section == "tre8":
            pos = struct.unpack_from("<I", tre, 0x8A)[0]
            size = struct.unpack_from("<I", tre, 0x8E)[0]
            return data[pos : pos + size].hex() if pos > 0 and size > 0 else ""

        if section == "tre-full":
            hdr_len = struct.unpack_from("<H", data, tre_off)[0]
            return tre[:hdr_len].hex()

        rgn_off = gmp["sections"]["RGN"]
        rgn = data[rgn_off:]

        if section == "rgn-header":
            hdr_len = struct.unpack_from("<H", data, rgn_off)[0]
            return data[rgn_off : rgn_off + hdr_len].hex()

        if section == "rgn-data":
            pos = struct.unpack_from("<I", rgn, 0x15)[0]
            size = struct.unpack_from("<I", rgn, 0x19)[0]
            return data[pos : pos + size].hex() if pos > 0 else ""

        if section == "rgn2":
            pos = struct.unpack_from("<I", rgn, 0x1D)[0]
            size = struct.unpack_from("<I", rgn, 0x21)[0]
            return data[pos : pos + size].hex() if pos > 0 and size > 0 else ""

        if section == "rgn5":
            hdr_len = struct.unpack_from("<H", data, rgn_off)[0]
            if hdr_len >= 0x75:
                pos = struct.unpack_from("<I", rgn, 0x71)[0]
                size = struct.unpack_from("<I", rgn, 0x75)[0]
                return data[pos : pos + size].hex() if pos > 0 and size > 0 else ""
            return ""

        lbl_off = gmp["sections"].get("LBL", 0)
        if lbl_off == 0:
            return ""
        lbl = data[lbl_off:]

        if section == "lbl-header":
            hdr_len = struct.unpack_from("<H", data, lbl_off)[0]
            return data[lbl_off : lbl_off + hdr_len].hex()

        if section == "lbl-data":
            pos = struct.unpack_from("<I", lbl, 0x15)[0]
            size = struct.unpack_from("<I", lbl, 0x19)[0]
            return data[pos : pos + min(size, 200)].hex() if pos > 0 else ""

        return f"(Unknown section: {section})"


def format_hex_dump(data, bytes_per_line=16):
    """Format binary data as hex dump with ASCII."""
    lines = []
    for i in range(0, len(data), bytes_per_line):
        chunk = data[i : i + bytes_per_line]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:04x}  {hex_part:<{bytes_per_line * 3}}  {ascii_part}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Garmin IMG Binary Analysis Tool")
    parser.add_argument("img_file", help="Path to IMG file")
    parser.add_argument(
        "--subfile", default=None, help='Subfile name (e.g., "00355951")'
    )
    parser.add_argument("--hex", default=None, help="Dump hex of section")
    parser.add_argument(
        "--dump", default=None, help="Full hex dump of section with ASCII"
    )
    parser.add_argument("--all", action="store_true", help="Dump all sections")
    parser.add_argument("--list", action="store_true", help="List subfiles")
    parser.add_argument(
        "--raw-offset", type=int, default=None, help="Read raw bytes at offset"
    )
    parser.add_argument("--raw-size", type=int, default=64, help="Size for raw read")

    args = parser.parse_args()

    with IMGParser(args.img_file) as img:
        print(f"=== IMG File: {args.img_file} ({img.filesize:,} bytes) ===\n")

        img.parse_header()
        print(
            f"Header: magic={img.header['magic']}, block_size={img.header['block_size']}"
        )
        print(f"Date: {img.header['date']}")
        print(f"Description: {img.header['description']}")
        print()

        img.parse_fat()
        print(f"Found {len(img.subfiles)} subfiles:")
        for key, sf in img.subfiles.items():
            total_blocks = sum(len(p["blocks"]) for p in sf["parts"])
            print(
                f"  {sf['name']:12s} {sf['type']:3s}  size={sf['size']:>10,}  "
                f"parts={len(sf['parts'])}  blocks={total_blocks}"
            )
        print()

        if args.list:
            return

        # Select subfile
        gmp_key = None
        if args.subfile:
            for key in img.subfiles:
                if args.subfile.upper() in key.upper():
                    gmp_key = key
                    break
            if not gmp_key:
                print(f"Subfile '{args.subfile}' not found. Available:")
                for key in img.subfiles:
                    print(f"  {key}")
                return
        else:
            # Auto-select first GMP subfile
            for key in img.subfiles:
                if img.subfiles[key]["type"] == "GMP":
                    gmp_key = key
                    break

        if not gmp_key:
            print("No GMP subfile found!")
            return

        print(f"=== Analyzing GMP subfile: {gmp_key} ===\n")

        gmp = img.parse_gmp_container(gmp_key)
        print(
            f"GMP Container: sig={gmp['signature']}, version={gmp['version']}, date={gmp['date']}"
        )
        print(f"  Data size: {gmp['data_size']:,} bytes")
        print(f"  Sections: {list(gmp['sections'].keys())}")
        print()

        if args.hex:
            hex_str = img.dump_section_hex(gmp, args.hex)
            print(f"=== Hex: {args.hex} ===")
            print(hex_str)
            return

        if args.dump:
            hex_str = img.dump_section_hex(gmp, args.dump)
            if hex_str and not hex_str.startswith("("):
                print(f"=== Hex dump: {args.dump} ===")
                print(format_hex_dump(bytes.fromhex(hex_str)))
            else:
                print(hex_str)
            return

        # Parse all sections
        print("--- TRE ---")
        tre = img.parse_tre(gmp)
        print(
            f"Header: {tre['sub_header']['header_length']} bytes, version={tre['sub_header']['version']}"
        )
        print(
            f"Bounds: N={tre['north_deg']:.6f} S={tre['south_deg']:.6f} "
            f"W={tre['west_deg']:.6f} E={tre['east_deg']:.6f}"
        )

        if "levels" in tre:
            print(f"\n  TRE1 Levels ({len(tre['levels'])}):")
            for i, lvl in enumerate(tre["levels"]):
                print(
                    f"    [{i}] level={lvl['level_number']:3d}  zoom={lvl['zoom_code']:3d}  "
                    f"subdivs={lvl['subdivision_count']:5d}"
                )

        if "display_priority" in tre:
            print(f"\n  Display priority: {tre['display_priority']}")

        if "map_id" in tre:
            print(f"  Map ID: 0x{tre['map_id']:08X}")

        if "matching_number" in tre:
            print(f"  Matching number: 0x{tre['matching_number']:08X}")

        if "map_name" in tre:
            print(f"  Map name: {tre['map_name']}")

        # TRE2 groups
        if "tre2" in tre:
            t2 = tre["tre2"]
            print(f"\n  TRE2 Groups: pos={t2['position']}, size={t2['size']}")
            if "groups_16byte" in tre:
                print(f"    16-byte group records ({len(tre['groups_16byte'])}):")
                for i, g in enumerate(tre["groups_16byte"][:20]):
                    print(
                        f"      [{i}] rgn_off={g['rgn_offset']:8d} obj={g['obj_types']} "
                        f"lon={g['lon_center_deg']:.6f} lat={g['lat_center_deg']:.6f} "
                        f"flags=0x{g['flags']:04X} subdivs={g['subdiv_count']} next={g['next_level_index']}"
                    )
                if len(tre["groups_16byte"]) > 20:
                    print(f"      ... ({len(tre['groups_16byte']) - 20} more)")

        if "tre7" in tre:
            t7 = tre["tre7"]
            print(
                f"\n  TRE7 (raster layer): pos={t7['position']}, size={t7['size']}, "
                f"rec_size={t7['record_size']}"
            )
            if "tre7_offsets" in tre:
                print(
                    f"    Offset table ({len(tre['tre7_offsets'])} entries): {tre['tre7_offsets'][:20]}"
                )
                if len(tre["tre7_offsets"]) > 20:
                    print(f"    ... ({len(tre['tre7_offsets']) - 20} more entries)")

        if "tre8" in tre:
            t8 = tre["tre8"]
            print(
                f"\n  TRE8 (object types): pos={t8['position']}, size={t8['size']}, "
                f"rec_size={t8['record_size']}"
            )
            if "tre8_entries" in tre:
                for entry in tre["tre8_entries"]:
                    print(
                        f"    Entry: type={entry['type']} param1={entry['param1']} "
                        f"param2={entry['param2']} raw={entry['raw']}"
                    )

        # TRE4-TRE6
        for sec_name in ["tre4", "tre5", "tre6", "tre9", "tre10"]:
            if sec_name in tre:
                sec = tre[sec_name]
                print(
                    f"\n  {sec_name.upper()}: pos={sec['position']}, size={sec['size']}, "
                    f"rec_size={sec['record_size']}"
                )

        print()
        print("--- RGN ---")
        rgn = img.parse_rgn(gmp)
        print(f"Header: {rgn['sub_header']['header_length']} bytes")

        for sec_name in ["rgn1", "rgn2", "rgn3", "rgn4", "rgn5"]:
            if sec_name in rgn:
                sec = rgn[sec_name]
                print(
                    f"  {sec_name.upper()}: pos={sec['position']}, size={sec['size']}"
                )

        if "rgn2_records" in rgn:
            recs = rgn["rgn2_records"]
            print(f"\n  RGN2 records ({len(recs)}):")
            for rec in recs[:30]:
                if rec["type"] == "E0 (raster tile)":
                    print(
                        f"    {rec['type']} @{rec['offset']}: "
                        f"bounds=({rec['lat_min_deg']:.6f},{rec['lon_min_deg']:.6f})-"
                        f"({rec['lat_max_deg']:.6f},{rec['lon_max_deg']:.6f}) "
                        f"blk_sz={rec['block_size']} img_idx={rec['image_index']}"
                    )
                else:
                    print(
                        f"    {rec['type']} @{rec['offset']}: {rec.get('raw_hex', '')}"
                    )
            if len(recs) > 30:
                print(f"    ... ({len(recs) - 30} more records)")

        if "rgn5_hex" in rgn:
            print(f"\n  RGN5 data hex: {rgn['rgn5_hex'][:200]}")

        print()
        print("--- LBL ---")
        lbl = img.parse_lbl(gmp)
        if lbl:
            print(f"Header: {lbl['sub_header']['header_length']} bytes")
            if "lbl1" in lbl:
                print(
                    f"  LBL1: pos={lbl['lbl1']['position']}, size={lbl['lbl1']['size']}, "
                    f"offset_mult={lbl['lbl1']['offset_multiplier']}, encoding={lbl['lbl1']['encoding']}"
                )
            if "lbl28" in lbl:
                print(
                    f"  LBL28 (img offsets): pos={lbl['lbl28']['position']}, size={lbl['lbl28']['size']}"
                )
            if "lbl29" in lbl:
                print(
                    f"  LBL29 (img storage): pos={lbl['lbl29']['position']}, size={lbl['lbl29']['size']}"
                )
            if "labels" in lbl:
                print(f"  Labels (first 10): {lbl['labels'][:10]}")
                print(f"  Total labels: {lbl['total_labels']}")
        else:
            print("(No LBL section)")

        if args.all:
            print("\n=== Full GMP Container Hex Dump ===")
            all_data = gmp["data"]
            limit = min(len(all_data), 2048)
            print(format_hex_dump(all_data[:limit]))
            if len(all_data) > limit:
                print(f"... ({len(all_data) - limit:,} more bytes)")

        if args.raw_offset is not None:
            raw = img.read_at(args.raw_offset, args.raw_size)
            print(
                f"\n=== Raw read at 0x{args.raw_offset:X} ({args.raw_size} bytes) ==="
            )
            print(format_hex_dump(raw))


if __name__ == "__main__":
    main()
