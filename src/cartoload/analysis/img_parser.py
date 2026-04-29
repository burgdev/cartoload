"""
Garmin IMG Binary Parser

Parses GMP container headers and computes TRE/RGN/LBL section offsets
from any GMP subfile in an IMG file. Supports FAT chain traversal
for multi-part subfiles.

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
"""

import os
import struct


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


def format_hex_dump(data, bytes_per_line=16):
    """Format binary data as hex dump with ASCII."""
    lines = []
    for i in range(0, len(data), bytes_per_line):
        chunk = data[i : i + bytes_per_line]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:04x}  {hex_part:<{bytes_per_line * 3}}  {ascii_part}")
    return "\n".join(lines)


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
        fat_block = self.header["fat_block"]
        assert isinstance(fat_block, int)
        fat_start = fat_block * 512
        self.fat_entries = []
        self.subfiles = {}

        fat_offset = fat_start
        while True:
            data = self.read_at(fat_offset, 512)
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

            file_offset = fat_offset
            entry = {
                "flag": flag,
                "name": name,
                "type": stype,
                "size": subfile_size,
                "flag2": flag2,
                "part": part,
                "blocks": blocks,
                "offset": file_offset,
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

            fat_offset += 512

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
                            "zoom_code": levels_data[i],
                            "level_number": levels_data[i + 1],
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

            # Parse subdivisions using level information for correct record sizes.
            # Non-last zoom levels: 16-byte records (with nextLevel field)
            # Last zoom level: 14-byte records (no nextLevel field)
            # + 4 trailing bytes for total RGN2 data extent
            parsed_levels = result.get("levels", [])
            subdivisions = []
            offset = 0
            for li, level in enumerate(parsed_levels):
                is_last = li == len(parsed_levels) - 1
                rec_size = 14 if is_last else 16
                for si in range(level["subdivision_count"]):
                    if offset + rec_size > len(subdivs_data):
                        break
                    rec = subdivs_data[offset : offset + rec_size]
                    rgn_off = rec[0] | (rec[1] << 8) | (rec[2] << 16)
                    obj_types = rec[3]
                    lon = decode_3byte_signed(rec, 4)
                    lat = decode_3byte_signed(rec, 7)
                    entry = {
                        "level_index": li,
                        "subdiv_index": si,
                        "zoom_code": level["zoom_code"],
                        "level_number": level["level_number"],
                        "rgn_offset": rgn_off,
                        "obj_types": f"0x{obj_types:02X}",
                        "lon_center": lon,
                        "lat_center": lat,
                        "lon_center_deg": map_units_to_degrees(lon),
                        "lat_center_deg": map_units_to_degrees(lat),
                        "raw_hex": rec.hex(),
                    }
                    if is_last:
                        width = struct.unpack_from("<H", rec, 10)[0]
                        height = struct.unpack_from("<H", rec, 12)[0]
                        entry["width"] = width
                        entry["height"] = height
                    else:
                        flags = struct.unpack_from("<H", rec, 10)[0]
                        subdiv_count = struct.unpack_from("<H", rec, 12)[0]
                        next_level = struct.unpack_from("<H", rec, 14)[0]
                        entry["flags"] = flags
                        entry["subdiv_count"] = subdiv_count
                        entry["next_level_index"] = next_level
                    subdivisions.append(entry)
                    offset += rec_size

            result["subdivisions"] = subdivisions

            # Keep legacy 16-byte and 14-byte parsing for backward compatibility
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

    @staticmethod
    def _read_vuint32(data, pos):
        """Read a variable-length unsigned int (GPXSee encoding).

        Returns (value, bytes_consumed).
        Encoding based on low bits of first byte:
          bit0=1 → 1 byte: val = byte >> 1
          bit0=0, bit1=1 → 2 bytes: val = (b0>>2) | (b1 << 6)
          bit0=0, bit1=0, bit2=1 → 3 bytes: val = (b0>>3) | (b1<<5) | (b2<<13)
          bit0=0, bit1=0, bit2=0 → 4 bytes: val = (b0>>4) | (b1<<4) | (b2<<12) | (b3<<20)
        """
        if pos >= len(data):
            return 0, 0
        b = data[pos]
        if b & 1:
            return b >> 1, 1
        if b & 2:
            if pos + 1 >= len(data):
                return 0, 0
            val = (b >> 2) | (data[pos + 1] << 6)
            return val, 2
        if b & 4:
            if pos + 2 >= len(data):
                return 0, 0
            val = (b >> 3) | (data[pos + 1] << 5) | (data[pos + 2] << 13)
            return val, 3
        if pos + 3 >= len(data):
            return 0, 0
        val = (
            (b >> 4)
            | (data[pos + 1] << 4)
            | (data[pos + 2] << 12)
            | (data[pos + 3] << 20)
        )
        return val, 4

    def _parse_rgn2_records(self, data):
        """Parse RGN2 compound records following GPXSee extPolyObjects flow.

        Each compound record has:
          type(1) + subtype(1) + lon_delta(2) + lat_delta(2)
          + VUInt32(bitstream_len) + bitstream(len)
          + VUInt32(label_ptr)
          + class_flags(1)
          + [if class_flags>>5==7: VUInt32(remaining_size) + raster_info]

        Raster info contains: imgId(variable) + top(4) + right(4) + bottom(4) + left(4)
        Remaining after bounds: jpeg_size(4)
        """
        records = []
        pos = 0

        while pos < len(data):
            rec_start = pos
            if pos + 7 > len(data):
                records.append(
                    {"type": "truncated", "offset": pos, "raw_hex": data[pos:].hex()}
                )
                break

            type_byte = data[pos]
            subtype = data[pos + 1]
            lon_delta = struct.unpack_from("<h", data, pos + 2)[0]
            lat_delta = struct.unpack_from("<h", data, pos + 4)[0]
            pos += 6

            # VUInt32: bitstream length
            bs_len, bs_vuint_sz = self._read_vuint32(data, pos)
            pos += bs_vuint_sz

            # Skip bitstream
            pos += bs_len

            # Label pointer: uint24 (3 bytes) if subtype & 0x20, else absent
            if subtype & 0x20:
                pos += 3  # readUInt24 — fixed 3 bytes

            # Class flags
            if pos >= len(data):
                records.append(
                    {
                        "type": f"0x{type_byte:02X} (truncated at class_flags)",
                        "offset": rec_start,
                        "raw_hex": data[rec_start:].hex(),
                    }
                )
                break
            class_flags = data[pos]
            pos += 1

            # Check for raster info (class_flags >> 5 == 7)
            is_raster = (class_flags >> 5) == 7

            if is_raster and pos + 21 <= len(data):
                # VUInt32: remaining size
                rs_val, rs_vuint_sz = self._read_vuint32(data, pos)
                pos += rs_vuint_sz

                # Remaining = imgId(variable) + top(4) + right(4) + bottom(4) + left(4) + jpeg_size(4)
                # rs_val = imgId_size + 16 + 4
                img_id_size = rs_val - 20

                if img_id_size < 1 or pos + rs_val > len(data):
                    records.append(
                        {
                            "type": f"0x{type_byte:02X} (raster, invalid rs={rs_val})",
                            "offset": rec_start,
                            "raw_hex": data[rec_start:].hex(),
                        }
                    )
                    break

                # Read imgId
                if img_id_size == 1:
                    img_idx = data[pos]
                elif img_id_size == 2:
                    img_idx = struct.unpack_from("<H", data, pos)[0]
                else:
                    img_idx = int.from_bytes(data[pos : pos + img_id_size], "little")
                pos += img_id_size

                # Read bounds
                top = struct.unpack_from("<I", data, pos)[0]
                right = struct.unpack_from("<I", data, pos + 4)[0]
                bottom = struct.unpack_from("<I", data, pos + 8)[0]
                left = struct.unpack_from("<I", data, pos + 12)[0]
                pos += 16

                # Read jpeg_size
                jpeg_size = struct.unpack_from("<I", data, pos)[0]
                pos += 4

                rec_end = pos
                records.append(
                    {
                        "type": "raster tile",
                        "offset": rec_start,
                        "type_byte": f"0x{type_byte:02X}",
                        "subtype": f"0x{subtype:02X}",
                        "lon_delta": lon_delta,
                        "lat_delta": lat_delta,
                        "class_flags": f"0x{class_flags:02X}",
                        "image_index": img_idx,
                        "top_deg": map_units_to_degrees_32(top),
                        "right_deg": map_units_to_degrees_32(right),
                        "bottom_deg": map_units_to_degrees_32(bottom),
                        "left_deg": map_units_to_degrees_32(left),
                        "jpeg_size": jpeg_size,
                        "lat_min_deg": map_units_to_degrees_32(bottom),
                        "lon_min_deg": map_units_to_degrees_32(left),
                        "lat_max_deg": map_units_to_degrees_32(top),
                        "lon_max_deg": map_units_to_degrees_32(right),
                        "block_size": jpeg_size,
                        "image_index_compat": img_idx,
                        "raw_hex": data[rec_start:rec_end].hex(),
                    }
                )
            else:
                # Non-raster compound record or invalid raster — can't determine
                # exact record length without TRE7 segment boundaries.
                # Record what we parsed and advance past the preamble.
                pos = rec_start + 1  # fall back to byte scanning
                records.append(
                    {
                        "type": f"0x{type_byte:02X} (compound, cf=0x{class_flags:02X})",
                        "offset": rec_start,
                        "subtype": f"0x{subtype:02X}",
                        "lon_delta": lon_delta,
                        "lat_delta": lat_delta,
                        "class_flags": f"0x{class_flags:02X}",
                        "raw_hex": data[rec_start:pos].hex(),
                    }
                )

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

        # LBL28/LBL29 raster descriptors (GPXSee reads at 0x184/0x192 when hdrLen >= 0x19A)
        # Layout at LBL+0x184: offset(4) + size(4) + recordSize(2) + flags(4)
        # Layout at LBL+0x192: img_offset(4) + img_size(4)
        if hdr_len >= 0x19A:
            lbl28_pos, lbl28_size, _ = get_lbl_section(0x184, size_only=True)
            result["lbl28"] = {"position": lbl28_pos, "size": lbl28_size}

            lbl29_pos = struct.unpack_from("<I", lbl, 0x192)[0]
            lbl29_size = struct.unpack_from("<I", lbl, 0x196)[0]
            result["lbl29"] = {"position": lbl29_pos, "size": lbl29_size}
        elif hdr_len >= 0x11E:
            # Old format fallback
            pos, size, _ = get_lbl_section(0x108, size_only=True)
            result["lbl28"] = {"position": pos, "size": size}

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

    def validate_coordinates(self, gmp):
        """Validate coordinate encoding round-trips and consistency.

        Returns a dict with validation results:
          - garmin_32bit: round-trip validation of deg_to_garmin / map_units_to_degrees_32
          - map_units_24bit: round-trip validation of deg_to_map_units / map_units_to_degrees
          - tile_bounds: RGN2 raster tile bounds vs TRE map bounds
          - subdivision_deltas: lon/lat delta consistency in RGN2 records
          - tile_details: per-tile decoded coordinates
        """
        results = {
            "garmin_32bit": [],
            "map_units_24bit": [],
            "tile_bounds": [],
            "subdivision_deltas": [],
            "tile_details": [],
        }

        # --- 1. Garmin 32-bit round-trip validation ---
        test_values = [
            0.0,
            1.0,
            -1.0,
            45.0,
            -45.0,
            90.0,
            -90.0,
            180.0,
            -180.0,
            47.5,
            7.5,
            46.26,
            5.87,
        ]
        for deg in test_values:
            encoded = int(deg * (2**31) / 180)
            decoded = encoded * 180.0 / (2**31)
            err = abs(decoded - deg)
            ok = err < 1e-6  # 32-bit quantization: ~8.4e-8 deg resolution
            results["garmin_32bit"].append(
                {
                    "input_deg": deg,
                    "encoded": encoded,
                    "decoded_deg": decoded,
                    "error": err,
                    "pass": ok,
                }
            )

        # --- 2. 24-bit map units round-trip validation ---
        for deg in test_values:
            encoded = int(deg * (2**24) / 360)
            decoded = encoded * 360.0 / (2**24)
            err = abs(decoded - deg)
            # 24-bit has ~0.00002 degree resolution, tolerance should reflect that
            ok = err < 2.2e-5
            results["map_units_24bit"].append(
                {
                    "input_deg": deg,
                    "encoded": encoded,
                    "decoded_deg": decoded,
                    "error": err,
                    "pass": ok,
                }
            )

        # --- 3 & 4. Validate against parsed data ---
        tre = gmp.get("tre", {})
        rgn = gmp.get("rgn", {})
        if not tre or not rgn:
            results["error"] = "TRE or RGN not parsed"
            return results

        map_n = tre.get("north_deg", 90.0)
        map_s = tre.get("south_deg", -90.0)
        map_e = tre.get("east_deg", 180.0)
        map_w = tre.get("west_deg", -180.0)

        # Get subdivision centers from properly parsed subdivisions
        subdivisions = tre.get("subdivisions", [])
        subdiv_centers = [
            (
                s.get("lon_center_deg", 0),
                s.get("lat_center_deg", 0),
                s.get("level_number", 0),
            )
            for s in subdivisions
        ]

        # Group subdivisions by level_number for per-level matching
        subdiv_by_level: dict[int, list[tuple[float, float]]] = {}
        for lon, lat, lvl in subdiv_centers:
            subdiv_by_level.setdefault(lvl, []).append((lon, lat))

        # Validate RGN2 raster tiles
        rgn2_records = rgn.get("rgn2_records", [])
        for i, rec in enumerate(rgn2_records):
            if rec.get("type") != "raster tile":
                continue

            detail = {
                "tile_index": i,
                "image_index": rec.get("image_index_compat", rec.get("image_index")),
                "top_deg": rec["top_deg"],
                "right_deg": rec["right_deg"],
                "bottom_deg": rec["bottom_deg"],
                "left_deg": rec["left_deg"],
                "lon_delta": rec["lon_delta"],
                "lat_delta": rec["lat_delta"],
                "jpeg_size": rec.get("jpeg_size", 0),
            }

            # Check bounds are within map extent
            in_bounds = (
                map_s - 0.01 <= rec["bottom_deg"] <= map_n + 0.01
                and map_w - 0.01 <= rec["left_deg"] <= map_e + 0.01
                and map_s - 0.01 <= rec["top_deg"] <= map_n + 0.01
                and map_w - 0.01 <= rec["right_deg"] <= map_e + 0.01
            )
            detail["in_map_bounds"] = in_bounds

            # Check top > bottom, right > left
            detail["valid_orientation"] = (
                rec["top_deg"] > rec["bottom_deg"]
                and rec["right_deg"] > rec["left_deg"]
            )

            # Validate lon_delta / lat_delta against subdivision centers
            lon_delta_mu = rec["lon_delta"]
            lat_delta_mu = rec["lat_delta"]
            tile_center_lon = (rec["left_deg"] + rec["right_deg"]) / 2
            tile_center_lat = (rec["bottom_deg"] + rec["top_deg"]) / 2

            detail["tile_center_lon"] = tile_center_lon
            detail["tile_center_lat"] = tile_center_lat

            # Find nearest subdivision center across all levels
            if subdiv_centers:
                best_sc = min(
                    subdiv_centers,
                    key=lambda c: (
                        (c[0] - tile_center_lon) ** 2 + (c[1] - tile_center_lat) ** 2
                    ),
                )
                sc_lon_mu = int(best_sc[0] * (2**24) / 360)
                sc_lat_mu = int(best_sc[1] * (2**24) / 360)
                tc_lon_mu = int(tile_center_lon * (2**24) / 360)
                tc_lat_mu = int(tile_center_lat * (2**24) / 360)
                expected_lon_delta = max(-32768, min(32767, tc_lon_mu - sc_lon_mu))
                expected_lat_delta = max(-32768, min(32767, tc_lat_mu - sc_lat_mu))
                delta_match = (
                    lon_delta_mu == expected_lon_delta
                    and lat_delta_mu == expected_lat_delta
                )
                detail["nearest_subdiv_center"] = best_sc
                detail["expected_lon_delta"] = expected_lon_delta
                detail["expected_lat_delta"] = expected_lat_delta
                detail["delta_match"] = delta_match

            results["tile_details"].append(detail)

            # Tile bounds summary
            results["tile_bounds"].append(
                {
                    "tile": i,
                    "in_bounds": in_bounds,
                    "valid_orientation": detail["valid_orientation"],
                }
            )

            # Delta summary
            results["subdivision_deltas"].append(
                {
                    "tile": i,
                    "lon_delta": lon_delta_mu,
                    "lat_delta": lat_delta_mu,
                    "delta_match": detail.get("delta_match"),
                }
            )

        return results

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
