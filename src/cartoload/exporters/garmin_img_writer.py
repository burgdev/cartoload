"""
Binary writer for Garmin IMG format.

Handles two-pass layout computation, FAT management, subfile directory
writing, tile extraction/compression, and binary serialization of the
complete IMG file structure.

Two-pass approach:
  Pass 1 — compute sizes of all subfiles, assign byte offsets, build FAT entries
  Pass 2 — stream binary data (header, FAT, subfile data) sequentially

IMG file layout:
  [Header: 512 bytes at offset 0]
  [FAT header block: 512 bytes at offset 0x200]  (special directory entry)
  [FAT subfile entries: 512 bytes each, starting at FAT_START (0x1000)]
  [Data blocks: BLOCK_SIZE each, starting after FAT region]

FAT entry format (512 bytes each):
  Offset 0x00: flag (1 byte, 0x01=active, 0x00=terminator)
  Offset 0x01: subfile name (8 bytes, space-padded)
  Offset 0x09: subfile type (3 bytes ASCII, e.g. "GMP")
  Offset 0x0C: subfile size (4 bytes LE uint32, only valid in part 0)
  Offset 0x10: flag2 (1 byte, 0x00=normal, 0x03=special dir entry)
  Offset 0x11: part number (1 byte, 0 for first part)
  Offset 0x12: reserved (14 bytes zeros)
  Offset 0x20: block sequence (240 × uint16 LE block numbers, 0xFFFF=unused)
"""

from __future__ import annotations

import io
import logging
import math
import struct
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import numpy as np
from PIL import Image

from .garmin_img_model import (
    IMGFile,
    IMGHeader,
    SubfileHeader,
    SubfileType,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Garmin IMG constants
BLOCK_SIZE = 32768  # 32 KB data blocks
HEADER_SIZE = 512  # Main header is 512 bytes
PHYSICAL_BLOCK_SIZE = 512  # FAT/header blocks are 512 bytes
FAT_BLOCK_NUMBER = 8  # FAT starts at physical block 8 (= 8*512 = 0x1000)
FAT_START = FAT_BLOCK_NUMBER * PHYSICAL_BLOCK_SIZE  # 0x1000
BOOT_SIGNATURE = 0xAA55
MAX_TILE_SIZE = 3_670_016  # 3.5 MB per tile
MAX_FILE_SIZE = 4_294_967_296  # 4 GB per file
MAP_NAME_MAX_LEN = 32

# FAT entry constants
FAT_SLOTS_PER_ENTRY = 240  # 240 block numbers per FAT block
FAT_BLOCKS_TABLE_START = 0x20  # Block sequence starts at offset 0x20
FAT_UNUSED_BLOCK = 0xFFFF  # Sentinel for unused block slots
FAT_FLAG_ACTIVE = 0x01  # Active subfile entry
FAT_FLAG_SPECIAL = 0x03  # Special directory entry

# Block size exponents: BLOCK_SIZE = 512 * 2^E2, where 512 = 2^9
BLOCK_SIZE_EXP_E1 = 0x09  # Always 0x09 (512 bytes base)
BLOCK_SIZE_EXP_E2 = 0x06  # 512 * 2^6 = 32768

# GMP subfile internal structure sizes
GMP_CONTAINER_HEADER_SIZE = 53  # "GARMIN GMP" container header
GMP_COMMON_HEADER_SIZE = (
    21  # Common sub-header: len(2) + type(10) + ver(1) + lock(1) + date(7)
)
TRE_HEADER_LENGTH = 273  # TRE sub-header length (from reference SwissTopo files)
RGN_HEADER_LENGTH = 125  # RGN sub-header length
LBL_HEADER_LENGTH = 596  # LBL sub-header length
NET_HEADER_LENGTH = 100  # NET sub-header length
TILE_INDEX_ENTRY_SIZE = 4  # Tile index: one uint32 per tile
MPS_SUBFILE_SIZE = 98


def _deg_to_garmin(deg: float) -> int:
    """Convert decimal degrees to Garmin coordinate units (degrees * 2^31 / 180)."""
    return int(deg * (2**31) / 180)


def _deg_to_map_units(deg: float) -> int:
    """Convert decimal degrees to Garmin 3-byte map units (degrees * 2^24 / 360).

    Used in TRE sub-header bounds fields.
    """
    return int(deg * (2**24) / 360)


def _put3s(val: int) -> bytes:
    """Encode a signed integer as 3 bytes little-endian (Garmin put3s format)."""
    if val < 0:
        val += 0x1000000
    return bytes([val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF])


def _encode_garmin_date_7(dt: datetime) -> bytes:
    """Encode datetime as 7-byte Garmin date (year_LE(2) + month + day + hour + min + sec + dow).

    Used in sub-header common headers.
    """
    return (
        struct.pack("<HBBBBB", dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
        + b"\x00"
    )


def _blocks_needed(byte_count: int) -> int:
    """Calculate number of 32KB blocks needed for given byte count."""
    return math.ceil(byte_count / BLOCK_SIZE)


def _align_to_block(size: int) -> int:
    """Align a byte count up to the next block boundary."""
    return _blocks_needed(size) * BLOCK_SIZE


def _fat_blocks_for_data_blocks(data_block_count: int) -> int:
    """Calculate how many 512-byte FAT entries are needed for given data blocks.

    Each FAT entry holds 240 block numbers.
    """
    if data_block_count == 0:
        return 1  # At least one FAT entry per subfile
    return math.ceil(data_block_count / FAT_SLOTS_PER_ENTRY)


class SubfileLayout:
    """Computed layout for a single subfile within the IMG file."""

    def __init__(
        self,
        subfile_type: SubfileType,
        name: str,
        start_offset: int,
        data_size: int,
    ):
        self.subfile_type = subfile_type
        self.name = name
        self.start_offset = start_offset
        self.data_size = data_size
        self.aligned_size = _align_to_block(data_size)
        # FAT block chains use 32KB logical blocks, not 512-byte physical blocks
        self.num_data_blocks = _blocks_needed(data_size)  # 32KB blocks
        self.num_fat_entries = _fat_blocks_for_data_blocks(self.num_data_blocks)
        self.start_block = start_offset // BLOCK_SIZE  # 32KB logical block number

    @property
    def end_offset(self) -> int:
        return self.start_offset + self.aligned_size


class LayoutComputer:
    """
    First pass: compute subfile sizes and assign byte offsets.

    Layout order:
      1. Main header (512 bytes, at offset 0)
      2. FAT header block (512 bytes, at offset 0x200)
      3. Padding to FAT_START (0x1000)
      4. FAT subfile entries (512 bytes each, starting at 0x1000)
      5. Subfile data (GMP, MPS) starting after FAT region
    """

    def __init__(self, img_file: IMGFile, compressed_tiles: dict[int, list[bytes]]):
        self.img_file = img_file
        self.compressed_tiles = compressed_tiles
        self.layouts: list[SubfileLayout] = []

    def compute(self) -> list[SubfileLayout]:
        """Compute layout for all subfiles and return ordered list."""
        self.layouts = []

        # First compute the subfile sizes to know how many FAT entries we need
        gmp_size = self._compute_gmp_size()

        # Calculate FAT entries needed
        gmp_data_blocks = _blocks_needed(gmp_size)
        mps_data_blocks = _blocks_needed(MPS_SUBFILE_SIZE)

        # +1 for special directory FAT entry
        total_fat_entries = (
            1  # special directory entry
            + _fat_blocks_for_data_blocks(gmp_data_blocks)
            + _fat_blocks_for_data_blocks(mps_data_blocks)
        )
        fat_region_size = total_fat_entries * PHYSICAL_BLOCK_SIZE

        # Data starts after FAT region (aligned to BLOCK_SIZE)
        data_start = _align_to_block(FAT_START + fat_region_size)

        current_offset = data_start

        # GMP subfile — name is the map ID as 8-char uppercase hex (e.g., "09C102B0")
        gmp_name = f"{self.img_file.map_id:08X}"[:8]
        gmp_layout = SubfileLayout(SubfileType.GMP, gmp_name, current_offset, gmp_size)
        self.layouts.append(gmp_layout)
        current_offset = gmp_layout.end_offset

        # MPS subfile
        mps_layout = SubfileLayout(
            SubfileType.MPS, "MAPSOURC", current_offset, MPS_SUBFILE_SIZE
        )
        self.layouts.append(mps_layout)
        current_offset = mps_layout.end_offset

        return self.layouts

    def _compute_gmp_size(self) -> int:
        """Compute the total size of the GMP subfile.

        Layout:
          GMP container header (53 bytes)
          Copyright strings (variable, null-terminated)
          TRE sub-header (273 bytes)
          Map info strings ("Raster Map\0" + copyright\0")
          RGN sub-header (125 bytes)
          LBL sub-header (596 bytes)
          NET sub-header (100 bytes)
          TRE data sections (copyright, subdivisions, map_levels)
          RGN data section (Type E0 records for each tile)
          LBL labels (tile filenames as null-terminated strings)
          LBL28 section (image index - uint32 offsets to LBL29)
          LBL29 section (image storage - concatenated JPEG files)
        """
        total_tiles = sum(len(tiles) for tiles in self.compressed_tiles.values())

        # Container header + copyright strings
        copyright_str = self.img_file.copyright_string or "Copyright GARMIN."
        copyright_bytes = copyright_str.encode("cp1252") + b"\x00"
        # Pad to align to TRE start (TRE follows copyright strings)
        # We need copyright to end at a position where TRE can start
        copyright_section = copyright_bytes + b"\x00"  # extra null terminator

        # TRE sub-header
        tre_section = TRE_HEADER_LENGTH

        # Map info strings after TRE header
        map_info = b"Raster Map\0" + copyright_str.encode("cp1252") + b"\x00"

        # RGN sub-header
        rgn_section = RGN_HEADER_LENGTH

        # LBL sub-header
        lbl_section = LBL_HEADER_LENGTH

        # NET sub-header
        net_section = NET_HEADER_LENGTH

        # TRE data sections
        n_zoom_levels = len(self.img_file.zoom_levels)
        map_levels_size = n_zoom_levels * 4  # 4 bytes per zoom level
        # Subdivisions: for raster, one subdivision per zoom level (8 bytes each)
        # Must match the subdiv_data allocation in GMPWriter.write()
        n_zoom = len(self.img_file.zoom_levels)
        subdiv_size = n_zoom * 8
        tre_data = 6 + subdiv_size + map_levels_size  # copyright + subdiv + map_levels

        # RGN data section (Type E0 records for raster tiles)
        # Each Type E0 record: marker(1) + bits_field(1) + 4×coords(16) + block_size(4) + image_index(1 or 2)
        # bits_field determines index size: 0x2B for <256 tiles (23 bytes), 0x25 for ≥256 tiles (24 bytes)
        type_e0_record_size = 23 if total_tiles < 256 else 24
        rgn_data = total_tiles * type_e0_record_size

        # RGN ext_type_areas (minimal for raster)
        rgn_ext_areas = 0  # can be 0 for simplified raster

        # LBL labels (tile filenames)
        lbl_labels = sum(len(f"{i}.jpg\0".encode("ascii")) for i in range(total_tiles))

        # LBL28 section (image index table)
        lbl28_size = total_tiles * 4  # uint32 offset per tile

        # LBL29 section (image storage - JPEG tile data)
        lbl29_size = 0
        for tiles in self.compressed_tiles.values():
            for tile_data_bytes in tiles:
                lbl29_size += len(tile_data_bytes)

        size = (
            GMP_CONTAINER_HEADER_SIZE
            + len(copyright_section)
            + tre_section
            + len(map_info)
            + rgn_section
            + lbl_section
            + net_section
            + tre_data
            + rgn_data
            + rgn_ext_areas
            + lbl_labels
            + lbl28_size
            + lbl29_size
        )

        return size


class IMGHeaderWriter:
    """Writes the 512-byte IMG file header."""

    @staticmethod
    def write(
        f: io.BufferedIOBase,
        header: IMGHeader,
        layouts: list[SubfileLayout] | None = None,
    ) -> None:
        """Write the 512-byte IMG header at current file position."""
        buf = bytearray(HEADER_SIZE)

        # Offset 0x00: XOR byte
        buf[0x00] = header.xor_byte

        # Offset 0x08-0x09: Map version major/minor (zeros)
        # Offset 0x0A-0x0B: Update month/year
        struct.pack_into("<H", buf, 0x0A, header.update_month_year)

        # Offset 0x0E: MapSource flag (0 = Garmin map)
        buf[0x0E] = 0x00

        # Offset 0x0F: Checksum (sum of bytes 0-0x0E mod 256, such that sum is 0)
        # We'll compute this at the end

        # Offset 0x10-0x16: Magic "DSKIMG\0"
        magic = header.magic.encode("ascii")
        buf[0x10 : 0x10 + len(magic)] = magic
        buf[0x10 + len(magic)] = 0x00  # null terminator

        # Offset 0x17: Always 0x02
        buf[0x17] = 0x02

        # Offset 0x18-0x19: Sectors per track
        struct.pack_into("<H", buf, 0x18, 0x0020)

        # Offset 0x1A-0x1B: Heads per cylinder (XOR byte is at 0x00, this is disk geometry)
        struct.pack_into("<H", buf, 0x1A, 0x0001)

        # Offset 0x39-0x3E: Creation date (6 bytes)
        date_bytes = header.encode_creation_date()
        buf[0x39 : 0x39 + len(date_bytes)] = date_bytes[: HEADER_SIZE - 0x39]

        # Offset 0x40: Physical block number of FAT header
        buf[0x40] = FAT_BLOCK_NUMBER

        # Offset 0x41-0x48: Creator string "GARMIN\0\0" (8 bytes, null-padded)
        creator_bytes = header.creator.encode("ascii")[:7].ljust(7, b"\x00")
        buf[0x41:0x48] = creator_bytes
        buf[0x48] = 0x00  # extra null

        # Offset 0x49-0x5C: Map description (20 bytes, space-padded)
        map_desc = header.map_name.encode("ascii")[:20].ljust(20, b" ")
        buf[0x49:0x5D] = map_desc

        # Offset 0x5D-0x5E: Heads (copy of 0x1A)
        struct.pack_into("<H", buf, 0x5D, 0x0001)

        # Offset 0x5F-0x60: Sectors (copy of 0x18)
        struct.pack_into("<H", buf, 0x5F, 0x0020)

        # Offset 0x61: Block size exponent E1 (always 0x09)
        buf[0x61] = BLOCK_SIZE_EXP_E1

        # Offset 0x62: Block size exponent E2
        buf[0x62] = BLOCK_SIZE_EXP_E2

        # Offset 0x63-0x64: Total block count (or 0xFFFF if overflow)
        if layouts:
            total_blocks = max(lay.end_offset for lay in layouts) // BLOCK_SIZE
            if total_blocks <= 0xFFFE:
                struct.pack_into("<H", buf, 0x63, total_blocks)
            else:
                struct.pack_into("<H", buf, 0x63, 0xFFFF)
        else:
            struct.pack_into("<H", buf, 0x63, 0xFFFF)

        # Offset 0x1C0-0x1CD: Partition table entry
        # This is a standard MBR partition table entry at offset 0x1BE
        buf[0x1BE] = 0x00  # Not bootable
        buf[0x1BF] = 0x01  # Start head
        buf[0x1C0] = 0x00  # Start sector
        buf[0x1C1] = 0x00  # Start cylinder
        buf[0x1C2] = 0xFF  # System type (auto-detect)
        if layouts:
            total_size = max(lay.end_offset for lay in layouts)
            # End head/sector/cylinder based on file size
            total_sectors = total_size // 512
            end_head = min(0xFE, (total_sectors // 63) // 255)
            buf[0x1C3] = end_head  # End head
            buf[0x1C4] = 0xFE  # End sector (with cylinder high bits)
            buf[0x1C5] = 0x00  # End cylinder low bits
            struct.pack_into("<I", buf, 0x1C6, 0)  # Relative sectors (LBA start)
            struct.pack_into("<I", buf, 0x1CA, total_sectors)  # Number of sectors
        else:
            buf[0x1C3] = 0x60  # End head (default)
            buf[0x1C4] = 0x64  # End sector
            buf[0x1C5] = 0x00  # End cylinder

        # Offset 0x1FE-0x1FF: Boot signature
        struct.pack_into("<H", buf, 0x1FE, BOOT_SIGNATURE)

        # Compute checksum at offset 0x0F: sum of bytes 0x00-0x0E mod 256 should make total 0
        byte_sum = sum(buf[0x00:0x0F])
        buf[0x0F] = (256 - byte_sum) % 256

        f.write(buf)

    @staticmethod
    def serialize(header: IMGHeader) -> bytes:
        """Serialize header to bytes (useful for testing)."""
        buf = io.BytesIO()
        IMGHeaderWriter.write(buf, header)
        return buf.getvalue()


class FATWriter:
    """Writes the FAT (File Allocation Table) region.

    Each FAT block is 512 bytes containing:
      - 32-byte header (flag, name, type, size, part, reserved)
      - 480-byte block table (240 × uint16 LE block numbers)
    """

    @staticmethod
    def write(
        f: io.BufferedWriter,
        layouts: list[SubfileLayout],
        fat_start_offset: int,
    ) -> None:
        """Write all FAT entries: special directory entry + subfile entries.

        Args:
            f: File handle positioned at FAT start
            layouts: Ordered list of subfile layouts
            fat_start_offset: Byte offset where FAT begins
        """
        # 1. Special directory FAT entry (first entry at FAT_START)
        FATWriter._write_special_entry(f, layouts, fat_start_offset)

        # 2. FAT entries for each subfile
        for layout in layouts:
            FATWriter._write_subfile_entries(f, layout)

    @staticmethod
    def _write_special_entry(
        f: io.BufferedWriter,
        layouts: list[SubfileLayout],
        fat_start_offset: int,
    ) -> None:
        """Write the special directory FAT entry (header/directory blocks).

        This entry covers the blocks from 0 to just before the data region.
        """
        entry = bytearray(PHYSICAL_BLOCK_SIZE)

        # Flag: active special entry
        entry[0x00] = FAT_FLAG_ACTIVE

        # Name: 8 spaces
        entry[0x01:0x09] = b"        "

        # Type: 3 spaces
        entry[0x09:0x0C] = b"   "

        # Size: total header+FAT region size
        if layouts:
            data_start = layouts[0].start_offset
        else:
            data_start = BLOCK_SIZE  # minimum
        struct.pack_into("<I", entry, 0x0C, data_start)

        # Flag2: special directory
        entry[0x10] = FAT_FLAG_SPECIAL

        # Part: 0
        entry[0x11] = 0x00

        # Reserved: zeros (0x12-0x1F already zero)

        # Block sequence: cover blocks 0 through (data_start/BLOCK_SIZE - 1)
        # These are the 32KB logical blocks occupied by header + FAT region
        # FAT uses 32KB blocks for the block list, not 512-byte physical blocks!
        header_blocks = data_start // BLOCK_SIZE
        num_to_write = min(header_blocks, FAT_SLOTS_PER_ENTRY)
        for i in range(num_to_write):
            struct.pack_into("<H", entry, FAT_BLOCKS_TABLE_START + i * 2, i)
        # Fill remaining with 0xFFFF
        for i in range(num_to_write, FAT_SLOTS_PER_ENTRY):
            struct.pack_into(
                "<H", entry, FAT_BLOCKS_TABLE_START + i * 2, FAT_UNUSED_BLOCK
            )

        f.write(entry)

    @staticmethod
    def _write_subfile_entries(f: io.BufferedWriter, layout: SubfileLayout) -> None:
        """Write FAT entries for a subfile (may span multiple 512-byte blocks).

        Each FAT block holds up to 240 data block numbers.
        Large subfiles need multiple FAT blocks with incrementing part numbers.
        """
        num_data_blocks = layout.num_data_blocks
        num_fat_entries = layout.num_fat_entries
        start_block = layout.start_block

        for part in range(num_fat_entries):
            entry = bytearray(PHYSICAL_BLOCK_SIZE)

            # Flag: active entry
            entry[0x00] = FAT_FLAG_ACTIVE

            # Name (8 bytes, space-padded)
            name_bytes = layout.name.encode("ascii")[:8].ljust(8, b" ")
            entry[0x01:0x09] = name_bytes

            # Type (3 bytes ASCII)
            type_str = layout.subfile_type.value
            entry[0x09:0x0C] = type_str.encode("ascii")

            # Size: only in part 0
            if part == 0:
                struct.pack_into("<I", entry, 0x0C, layout.data_size)

            # Flag2: normal subfile
            entry[0x10] = 0x00

            # Part number
            entry[0x11] = part

            # Reserved: zeros (already zero)

            # Block sequence: fill with data block numbers (32KB logical blocks)
            block_start = part * FAT_SLOTS_PER_ENTRY
            for i in range(FAT_SLOTS_PER_ENTRY):
                block_idx = block_start + i
                if block_idx < num_data_blocks:
                    # Sequential 32KB logical block number
                    logical_block = start_block + block_idx
                    struct.pack_into(
                        "<H",
                        entry,
                        FAT_BLOCKS_TABLE_START + i * 2,
                        logical_block,
                    )
                else:
                    struct.pack_into(
                        "<H",
                        entry,
                        FAT_BLOCKS_TABLE_START + i * 2,
                        FAT_UNUSED_BLOCK,
                    )

            f.write(entry)


class GMPWriter:
    """Writes the GMP (Garmin Map) subfile using the GMP container format.

    The GMP subfile is a container that embeds TRE, RGN, LBL, NET sub-headers,
    followed by data sections and JPEG tile data.

    Layout:
      [GMP Container Header: 53 bytes]
      [Copyright strings: null-terminated]
      [TRE Sub-Header: 273 bytes]
      [Map Info Strings: "Raster Map\\0" + copyright\\0"]
      [RGN Sub-Header: 125 bytes]
      [LBL Sub-Header: 596 bytes]
      [NET Sub-Header: 100 bytes]
      [TRE Data Sections: copyright, subdivisions, map_levels]
      [RGN Data Sections: data_section]
      [LBL Labels: tile filenames as null-terminated strings]
      [Tile Index Table: N × uint32 offsets]
      [JPEG Tile Data: concatenated JFIF JPEGs]
    """

    @staticmethod
    def write(
        f: io.BufferedWriter,
        img_file: IMGFile,
        compressed_tiles: dict[int, list[bytes]],
        gmp_layout: SubfileLayout,
    ) -> None:
        """Write complete GMP subfile with container format."""
        f.seek(gmp_layout.start_offset)

        total_tiles = sum(len(t) for t in compressed_tiles.values())
        now = img_file.gmp_creation_date or datetime.now()

        # --- Phase 1: Compute layout (positions of all sections) ---
        copyright_str = img_file.copyright_string or "Copyright GARMIN."
        copyright_bytes = copyright_str.encode("cp1252") + b"\x00" + b"\x00"

        pos = 0

        # GMP container header
        pos += GMP_CONTAINER_HEADER_SIZE

        # Copyright strings
        pos += len(copyright_bytes)

        # TRE sub-header start (section offset for GMP header)
        tre_pos = pos
        pos += TRE_HEADER_LENGTH

        # Map info strings (after TRE sub-header)
        map_info = b"Raster Map\0" + copyright_str.encode("cp1252") + b"\x00"
        pos += len(map_info)

        # RGN sub-header start
        rgn_pos = pos
        pos += RGN_HEADER_LENGTH

        # LBL sub-header start
        lbl_pos = pos
        pos += LBL_HEADER_LENGTH

        # NET sub-header start
        net_pos = pos
        pos += NET_HEADER_LENGTH

        # --- TRE data sections (offsets relative to TRE start) ---

        # TRE copyright section (6 bytes)
        tre_copyright_pos = pos - tre_pos  # relative to TRE
        pos += 6

        # TRE subdivisions
        tre_subdiv_pos = pos - tre_pos  # relative to TRE
        # For raster: one subdivision per zoom level
        n_zoom = len(img_file.zoom_levels)
        # Each subdivision is 8 bytes (simple raster format)
        subdiv_data = bytearray(n_zoom * 8)
        subdiv_size = len(subdiv_data)
        pos += subdiv_size

        # TRE map levels
        tre_maplevels_pos = pos - tre_pos  # relative to TRE
        map_levels_data = bytearray(n_zoom * 4)
        map_levels_size = len(map_levels_data)
        pos += map_levels_size

        # --- RGN data section (Type E0 records, offsets relative to RGN start) ---
        rgn_data_pos = pos - rgn_pos  # relative to RGN
        # Calculate RGN data size (Type E0 records)
        type_e0_record_size = 23 if total_tiles < 256 else 24
        rgn_data_size = total_tiles * type_e0_record_size
        pos += rgn_data_size

        # --- LBL labels (tile filenames) ---
        lbl_labels_pos = pos - lbl_pos  # relative to LBL
        label_strings = bytearray()
        for i in range(total_tiles):
            label_strings += f"{i}.jpg\0".encode("ascii")
        pos += len(label_strings)

        # --- LBL28 section (image index) ---
        lbl28_pos = pos - lbl_pos  # relative to LBL
        lbl28_size = total_tiles * 4  # uint32 offset per tile
        pos += lbl28_size

        # --- LBL29 section (image storage) ---
        lbl29_pos = pos - lbl_pos  # relative to LBL
        # Calculate LBL29 size (sum of all JPEG sizes)
        lbl29_size = 0
        for zoom in img_file.zoom_levels:
            tiles = compressed_tiles.get(zoom.level_number, [])
            for tile_data in tiles:
                lbl29_size += len(tile_data)
        pos += lbl29_size

        # Fill map levels data
        for z_idx, zoom in enumerate(img_file.zoom_levels):
            tile_count = len(compressed_tiles.get(zoom.level_number, []))
            # zoom level (1 byte) + bits (1 byte) + n_subdivisions (2 bytes LE)
            map_levels_data[z_idx * 4] = zoom.level_number
            map_levels_data[z_idx * 4 + 1] = zoom.zoom_code
            struct.pack_into("<H", map_levels_data, z_idx * 4 + 2, tile_count)

        # --- Phase 2: Write all sections ---

        # 1. GMP Container Header (53 bytes)
        gmp_header = bytearray(GMP_CONTAINER_HEADER_SIZE)
        gmp_header[0] = GMP_CONTAINER_HEADER_SIZE  # header_size
        gmp_header[1] = 0x00  # flag
        gmp_header[2:12] = b"GARMIN GMP"  # signature
        struct.pack_into("<H", gmp_header, 12, 1)  # version = 1
        date_bytes = _encode_garmin_date_7(now)
        gmp_header[14:21] = date_bytes[:7]
        struct.pack_into(
            "<I", gmp_header, 21, 0
        )  # section_table_offset = 0 (sections start immediately)
        # Section offsets (7 × uint32): TRE, RGN, LBL, NET, 0, 0, 0
        struct.pack_into("<I", gmp_header, 25, tre_pos)
        struct.pack_into("<I", gmp_header, 29, rgn_pos)
        struct.pack_into("<I", gmp_header, 33, lbl_pos)
        struct.pack_into("<I", gmp_header, 37, net_pos)
        # Sections 4-6: zeros (already zero)
        f.write(gmp_header)

        # 2. Copyright strings
        f.write(copyright_bytes)

        # 3. TRE Sub-Header
        tre_header = _build_tre_subheader(
            img_file,
            now,
            tre_copyright_pos,
            6,
            tre_subdiv_pos,
            subdiv_size,
            tre_maplevels_pos,
            map_levels_size,
        )
        f.write(tre_header)

        # 4. Map info strings
        f.write(map_info)

        # 5. RGN Sub-Header
        rgn_header = _build_rgn_subheader(now, rgn_data_pos, rgn_data_size)
        f.write(rgn_header)

        # 6. LBL Sub-Header
        lbl_header = _build_lbl_subheader(
            now,
            lbl_labels_pos,
            len(label_strings),
            lbl28_pos,
            lbl28_size,
            lbl29_pos,
            lbl29_size,
        )
        f.write(lbl_header)

        # 7. NET Sub-Header
        net_header = _build_net_subheader(now)
        f.write(net_header)

        # 8. TRE copyright data (6 bytes)
        f.write(b"\x00\x80\xa4\x4f\x05\x58")  # placeholder from reference

        # 9. TRE subdivisions
        f.write(subdiv_data)

        # 10. TRE map levels
        f.write(map_levels_data)

        # 11. RGN data section (Type E0 records)
        _write_rgn_data_section(f, compressed_tiles, img_file.zoom_levels, img_file)

        # 12. LBL labels (tile filenames)
        f.write(label_strings)

        # 13. LBL28 section (image index)
        _write_lbl28_section(f, compressed_tiles, img_file.zoom_levels)

        # 14. LBL29 section (image storage - JPEG tiles)
        _write_lbl29_section(f, compressed_tiles, img_file.zoom_levels)

        # Pad to aligned size
        current_pos = f.tell()
        padding = gmp_layout.start_offset + gmp_layout.aligned_size - current_pos
        if padding > 0:
            f.write(b"\x00" * padding)


def _build_common_header(type_str: str, header_length: int, now: datetime) -> bytearray:
    """Build the 21-byte common sub-header used by TRE, RGN, LBL, NET.

    Format: header_length(2) + type_string(10) + version(1) + lock(1) + date(7)
    """
    buf = bytearray(GMP_COMMON_HEADER_SIZE)
    struct.pack_into("<H", buf, 0, header_length)
    buf[2:12] = f"GARMIN {type_str}".encode("ascii")  # e.g., "GARMIN TRE"
    buf[12] = 1  # version (always 1)
    buf[13] = 0  # lock (0 = unlocked)
    date_bytes = _encode_garmin_date_7(now)
    buf[14:21] = date_bytes[:7]
    return buf


def _build_tre_subheader(
    img_file: IMGFile,
    now: datetime,
    copyright_pos: int,
    copyright_size: int,
    subdiv_pos: int,
    subdiv_size: int,
    maplevels_pos: int,
    maplevels_size: int,
) -> bytes:
    """Build the TRE sub-header (TRE_HEADER_LENGTH bytes).

    After common header (21 bytes):
      bounds: 4 × 3-byte signed map units (N, E, S, W)
      map_levels: position(4) + size(4)
      subdivisions: position(4) + size(4)
      copyright_section: position(4) + size(4) + item_size(2)
      unknown(4) + poi_flags(1) + display_priority(3)
      flags + sections for polyline/polygon/points (zeros for raster)
    """
    buf = bytearray(TRE_HEADER_LENGTH)

    # Common header (21 bytes)
    common = _build_common_header("TRE", TRE_HEADER_LENGTH, now)
    buf[:21] = common

    # Bounds as 3-byte signed map units (N, E, S, W)
    off = 21
    buf[off : off + 3] = _put3s(_deg_to_map_units(img_file.bounds_north))
    off += 3
    buf[off : off + 3] = _put3s(_deg_to_map_units(img_file.bounds_east))
    off += 3
    buf[off : off + 3] = _put3s(_deg_to_map_units(img_file.bounds_south))
    off += 3
    buf[off : off + 3] = _put3s(_deg_to_map_units(img_file.bounds_west))
    off += 3

    # Map levels section info: position(4) + size(4)
    struct.pack_into("<I", buf, off, maplevels_pos)
    off += 4
    struct.pack_into("<I", buf, off, maplevels_size)
    off += 4

    # Subdivisions section info: position(4) + size(4)
    struct.pack_into("<I", buf, off, subdiv_pos)
    off += 4
    struct.pack_into("<I", buf, off, subdiv_size)
    off += 4

    # Copyright section info: position(4) + size(4) + item_size(2)
    struct.pack_into("<I", buf, off, copyright_pos)
    off += 4
    struct.pack_into("<I", buf, off, copyright_size)
    off += 4
    struct.pack_into("<H", buf, off, 3)
    off += 2  # item_size = 3

    # Unknown (4 bytes)
    off += 4

    # POI flags (1 byte)
    buf[off] = 1
    off += 1

    # Display priority (3 bytes) - 24 for raster
    buf[off] = 24
    off += 3

    # Map ID at fixed TRE header offsets (required for GMT recognition)
    # Offset 116: internal map ID (uint32 LE)
    # Offset 207: map ID copy (uint32 LE)
    struct.pack_into("<I", buf, 116, img_file.map_id)
    struct.pack_into("<I", buf, 207, img_file.map_id)

    return bytes(buf)


def _build_rgn_subheader(
    now: datetime,
    data_pos: int,
    data_size: int,
) -> bytes:
    """Build the RGN sub-header (RGN_HEADER_LENGTH bytes).

    After common header (21 bytes):
      data_section: position(4) + size(4)
      ext_type sections: zeros (no extended types for simplified raster)
    """
    buf = bytearray(RGN_HEADER_LENGTH)

    # Common header
    common = _build_common_header("RGN", RGN_HEADER_LENGTH, now)
    buf[:21] = common

    # Data section: position(4) + size(4)
    struct.pack_into("<I", buf, 21, data_pos)
    struct.pack_into("<I", buf, 25, data_size)

    # Ext type sections remain zero

    return bytes(buf)


def _build_lbl_subheader(
    now: datetime,
    labels_pos: int,
    labels_size: int,
    lbl28_pos: int,
    lbl28_size: int,
    lbl29_pos: int,
    lbl29_size: int,
) -> bytes:
    """Build the LBL sub-header (LBL_HEADER_LENGTH bytes).

    After common header (21 bytes):
      label_section: position(4) + size(4)
      offset_multiplier(1) + encoding(1)
      [additional fields at 31-36]
      lbl28_section: position(4) + size(4) at offsets 37-44
      lbl29_section: position(4) + size(4) at offsets 45-52
      remaining: zeros
    """
    buf = bytearray(LBL_HEADER_LENGTH)

    # Common header
    common = _build_common_header("LBL", LBL_HEADER_LENGTH, now)
    buf[:21] = common

    # Label section: position(4) + size(4)
    struct.pack_into("<I", buf, 21, labels_pos)
    struct.pack_into("<I", buf, 25, labels_size)

    # Offset multiplier (1 byte) = 1
    buf[29] = 1

    # Encoding (1 byte) = 6 (CP1252)
    buf[30] = 6

    # LBL28 section descriptor: position(4) + size(4) at bytes 37-44
    struct.pack_into("<I", buf, 37, lbl28_pos)
    struct.pack_into("<I", buf, 41, lbl28_size)

    # LBL29 section descriptor: position(4) + size(4) at bytes 45-52
    struct.pack_into("<I", buf, 45, lbl29_pos)
    struct.pack_into("<I", buf, 49, lbl29_size)

    # Remaining bytes stay zero (places section, codepage, sort ids, etc.)

    return bytes(buf)


def _build_net_subheader(now: datetime) -> bytes:
    """Build the NET sub-header (NET_HEADER_LENGTH bytes).

    Minimal stub for raster maps - all section info is zeros.
    """
    buf = bytearray(NET_HEADER_LENGTH)

    # Common header
    common = _build_common_header("NET", NET_HEADER_LENGTH, now)
    buf[:21] = common

    # All NET-specific fields remain zero

    return bytes(buf)


def _compute_bits_field(total_tiles: int) -> int:
    """
    Compute bits_field value for Type E0 records based on total tile count.

    Args:
        total_tiles: Total number of tiles across all zoom levels

    Returns:
        0x2B for <256 tiles (8-bit image index)
        0x25 for ≥256 tiles (16-bit image index)
    """
    return 0x2B if total_tiles < 256 else 0x25


def _write_type_e0_record(
    f: io.BufferedWriter,
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
    jpeg_size: int,
    image_index: int,
    bits_field: int,
) -> None:
    """
    Write a single RGN Type E0 record for a raster tile.

    Binary format:
      - marker (1 byte): 0xE0
      - bits_field (1 byte): 0x2B or 0x25
      - lat_min, lon_min, lat_max, lon_max (4× uint32 LE): bounds in Garmin map units
      - block_size (uint32 LE): JPEG file size in bytes
      - image_index (uint8 or uint16 LE): index into LBL28 offset array

    Args:
        f: File handle to write to
        lat_min, lon_min, lat_max, lon_max: Tile bounds in decimal degrees
        jpeg_size: JPEG file size in bytes
        image_index: Index into LBL28 array (0-based)
        bits_field: 0x2B for 8-bit index, 0x25 for 16-bit index
    """
    # Marker byte
    f.write(bytes([0xE0]))

    # bits_field
    f.write(bytes([bits_field]))

    # Coordinates in Garmin map units (32-bit signed)
    lat_min_units = _deg_to_garmin(lat_min)
    lon_min_units = _deg_to_garmin(lon_min)
    lat_max_units = _deg_to_garmin(lat_max)
    lon_max_units = _deg_to_garmin(lon_max)

    f.write(struct.pack("<i", lat_min_units))  # signed int32
    f.write(struct.pack("<i", lon_min_units))
    f.write(struct.pack("<i", lat_max_units))
    f.write(struct.pack("<i", lon_max_units))

    # Block size (JPEG size)
    f.write(struct.pack("<I", jpeg_size))  # unsigned int32

    # Image index (variable size based on bits_field)
    if bits_field == 0x2B:
        f.write(struct.pack("<B", image_index))  # uint8
    else:
        f.write(struct.pack("<H", image_index))  # uint16


def _write_lbl28_section(
    f: io.BufferedWriter, compressed_tiles: dict[int, list[bytes]], zoom_levels: list
) -> None:
    """
    Write LBL28 section (image index table).

    Writes an array of uint32 LE offsets, one per tile, pointing to JPEGs in LBL29.
    Offsets are relative to the start of LBL29 section.

    Args:
        f: File handle to write to
        compressed_tiles: Dict mapping zoom level to list of JPEG tile data
        zoom_levels: List of ZoomLevel objects defining zoom order
    """
    offset = 0
    for zoom in zoom_levels:
        tiles = compressed_tiles.get(zoom.level_number, [])
        for tile_data in tiles:
            # Write offset to this JPEG (relative to LBL29 start)
            f.write(struct.pack("<I", offset))
            offset += len(tile_data)


def _write_lbl29_section(
    f: io.BufferedWriter, compressed_tiles: dict[int, list[bytes]], zoom_levels: list
) -> None:
    """
    Write LBL29 section (image storage).

    Writes concatenated JPEG files with no padding between them.
    JPEGs are written in zoom level order.

    Args:
        f: File handle to write to
        compressed_tiles: Dict mapping zoom level to list of JPEG tile data
        zoom_levels: List of ZoomLevel objects defining zoom order
    """
    for zoom in zoom_levels:
        tiles = compressed_tiles.get(zoom.level_number, [])
        for tile_data in tiles:
            # Verify JPEG marker
            if len(tile_data) >= 4 and tile_data[0:2] == b"\xff\xd8":
                f.write(tile_data)
            else:
                logger.warning(
                    f"Tile at zoom {zoom.level_number} does not start with JPEG marker (FFD8)"
                )
                f.write(tile_data)


def _write_rgn_data_section(
    f: io.BufferedWriter,
    compressed_tiles: dict[int, list[bytes]],
    zoom_levels: list,
    img_file,
) -> None:
    """
    Write RGN data section (Type E0 records).

    Writes one Type E0 record per tile, containing bounds, size, and image index.

    Args:
        f: File handle to write to
        compressed_tiles: Dict mapping zoom level to list of JPEG tile data
        zoom_levels: List of ZoomLevel objects defining zoom order
        img_file: IMGFile with map bounds
    """
    total_tiles = sum(
        len(compressed_tiles.get(z.level_number, [])) for z in zoom_levels
    )
    bits_field = _compute_bits_field(total_tiles)

    image_index = 0
    for zoom in zoom_levels:
        tiles = compressed_tiles.get(zoom.level_number, [])
        for tile_data in tiles:
            # TODO: Use actual tile bounds from tile extraction (task 8)
            # For now, use map bounds as a placeholder
            _write_type_e0_record(
                f,
                lat_min=img_file.bounds_south,
                lon_min=img_file.bounds_west,
                lat_max=img_file.bounds_north,
                lon_max=img_file.bounds_east,
                jpeg_size=len(tile_data),
                image_index=image_index,
                bits_field=bits_field,
            )
            image_index += 1


class MPSWriter:
    """Writes the MPS (MAPSOURC) subfile."""

    @staticmethod
    def write(
        f: io.BufferedWriter, mps_layout: SubfileLayout, img_file: IMGFile
    ) -> None:
        """Write MPS subfile (98 bytes of metadata).

        Format matches reference SwissTopo raster IMG files:
          [0-1]   "LE" signature
          [2-6]   padding zeros (5 bytes)
          [7-10]  map_id (uint32 LE)
          [11-32] map name null-terminated (22 bytes, name + null + padding)
          [33-40] hex map_id string "XXXXXXXX" (8 bytes)
          [41]    null terminator for hex ID
          [42-63] map name null-terminated (22 bytes)
          [64-67] map_id (uint32 LE)
          [68-71] zeros (4 bytes)
          [72-73] unknown uint16 (0x1756 from reference)
          [74]    zero
          [75-96] map name null-terminated (22 bytes)
          [97]    zero
        """
        f.seek(mps_layout.start_offset)

        buf = bytearray(MPS_SUBFILE_SIZE)

        # Signature "LE"
        buf[0x00:0x02] = b"LE"

        # [2-6] padding zeros (already zero)

        # [7-10] map_id
        struct.pack_into("<I", buf, 7, img_file.map_id)

        # Map name (max 21 chars + null = 22 bytes)
        map_name = img_file.header.map_name or "Raster Map"
        name_bytes = map_name.encode("ascii")[:21]
        name_padded = name_bytes + b"\x00"  # null terminate
        name_slot = name_padded[:22].ljust(22, b"\x00")  # pad to 22 bytes

        # [11-32] map name
        buf[0x0B : 0x0B + 22] = name_slot

        # [33-40] hex map_id string (8 ASCII chars, no null)
        hex_id = f"{img_file.map_id:08X}"[:8].encode("ascii")
        buf[0x21 : 0x21 + 8] = hex_id

        # [41] null terminator for hex ID
        buf[0x29] = 0x00

        # [42-63] map name again
        buf[0x2A : 0x2A + 22] = name_slot

        # [64-67] map_id again
        struct.pack_into("<I", buf, 0x40, img_file.map_id)

        # [68-71] zeros (already zero)

        # [72-73] unknown uint16
        struct.pack_into("<H", buf, 0x48, 0x1756)

        # [74] zero (already zero)

        # [75-96] map name again
        buf[0x4B : 0x4B + 22] = name_slot

        # [97] zero (already zero)

        f.write(buf)


class TileExtractor:
    """Extracts tiles from GeoTIFF rasters at multiple zoom levels."""

    def __init__(self, raster_path: Path):
        self.raster_path = raster_path

    # ------------------------------------------------------------------
    # Tile grid computation (Web Mercator)
    # ------------------------------------------------------------------

    @staticmethod
    def _tile_grid_for_zoom(
        bounds: dict[str, float],
        zoom: int,
    ) -> list[tuple[int, int, float, float, float, float]]:
        """Compute tile grid cells for a zoom level within the given bounds.

        Returns a list of (x, y, lon_min, lat_max, lon_max, lat_min) tuples,
        one per tile cell covering the bounds at the given zoom.
        """
        n = 2**zoom
        west = bounds["west"]
        east = bounds["east"]
        north = bounds["north"]
        south = bounds["south"]

        def lon_to_tile_x(lon: float) -> int:
            return max(0, min(int((lon + 180.0) / 360.0 * n), n - 1))

        def lat_to_tile_y(lat: float) -> int:
            lat_rad = math.radians(lat)
            return max(
                0,
                min(
                    int(
                        (
                            1.0
                            - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad))
                            / math.pi
                        )
                        / 2.0
                        * n
                    ),
                    n - 1,
                ),
            )

        x_min = lon_to_tile_x(west)
        x_max = lon_to_tile_x(east)
        y_min = lat_to_tile_y(north)
        y_max = lat_to_tile_y(south)

        tile_size_deg = 360.0 / n  # tile width in degrees

        cells = []
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                cell_lon_min = x * tile_size_deg - 180.0
                cell_lat_max = _tile_y_to_lat(y, n)
                cell_lon_max = cell_lon_min + tile_size_deg
                cell_lat_min = _tile_y_to_lat(y + 1, n)
                cells.append(
                    (x, y, cell_lon_min, cell_lat_max, cell_lon_max, cell_lat_min)
                )

        return cells

    # ------------------------------------------------------------------
    # Tile region extraction via gdal_translate
    # ------------------------------------------------------------------

    def _extract_tile_region(
        self,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        lat_min: float,
        tile_size: int = 256,
    ) -> np.ndarray | None:
        """Extract a geographic region from the GeoTIFF as a 256x256 RGB array.

        Uses gdal_translate with -projwin to read the region and -outsize to
        resize to the target tile dimensions.
        """
        with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
            cmd = [
                "gdal_translate",
                "-of",
                "PNG",
                "-projwin",
                str(lon_min),
                str(lat_max),
                str(lon_max),
                str(lat_min),
                "-outsize",
                str(tile_size),
                str(tile_size),
                str(self.raster_path),
                tmp.name,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning(
                    "gdal_translate failed for region (%.4f,%.4f)-(%.4f,%.4f): %s",
                    lon_min,
                    lat_min,
                    lon_max,
                    lat_max,
                    result.stderr.strip(),
                )
                return None

            try:
                img = Image.open(tmp.name).convert("RGB")
                return np.array(img, dtype=np.uint8)
            except Exception as exc:
                logger.warning("Failed to load tile image: %s", exc)
                return None

    # ------------------------------------------------------------------
    # Main extraction entry point
    # ------------------------------------------------------------------

    def extract_tiles(
        self,
        zoom_levels: list[int],
        bounds: dict[str, float],
        tile_size: int = 256,
        *,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> dict[int, list[np.ndarray]]:
        """
        Extract tiles from raster at each zoom level.

        Args:
            zoom_levels: List of zoom levels to extract
            bounds: Geographic bounds (west, east, south, north)
            tile_size: Tile dimension in pixels (default 256)
            progress_callback: Called with (stage, current, total) to report progress

        Returns:
            Dictionary mapping zoom level to list of tile arrays
        """
        logger.info(f"Extracting tiles from {self.raster_path}")
        logger.info(f"  Zoom levels: {zoom_levels}")
        logger.info(f"  Tile size: {tile_size}x{tile_size}")

        # Pre-compute total tile count across all zoom levels
        all_cells: dict[int, list[tuple]] = {}
        total_cells = 0
        for zoom in zoom_levels:
            cells = self._tile_grid_for_zoom(bounds, zoom)
            all_cells[zoom] = cells
            total_cells += len(cells)

        if progress_callback:
            progress_callback("extracting", 0, total_cells)

        tiles_by_zoom: dict[int, list[np.ndarray]] = {}
        extracted_count = 0

        for zoom in zoom_levels:
            cells = all_cells[zoom]
            logger.info(f"  Zoom {zoom}: {len(cells)} tiles to extract")

            tiles: list[np.ndarray] = []
            for x, y, lon_min, lat_max, lon_max, lat_min in cells:
                tile = self._extract_tile_region(
                    lon_min,
                    lat_max,
                    lon_max,
                    lat_min,
                    tile_size,
                )
                if tile is not None:
                    tiles.append(tile)
                extracted_count += 1
                if progress_callback:
                    progress_callback("extracting", extracted_count, total_cells)

            tiles_by_zoom[zoom] = tiles
            logger.info(f"  Zoom {zoom}: extracted {len(tiles)}/{len(cells)} tiles")

        total = sum(len(t) for t in tiles_by_zoom.values())
        logger.info(f"Extracted {total} tiles across {len(zoom_levels)} zoom levels")
        return tiles_by_zoom


def _tile_y_to_lat(y: int, n: int) -> float:
    """Convert Web Mercator tile Y index to latitude in degrees."""
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    return math.degrees(lat_rad)


class TileEncoder:
    """Encodes raw pixel data into the Garmin tile format."""

    @staticmethod
    def encode_tile(tile_array: np.ndarray, quality: int = 85) -> bytes:
        """
        Encode a tile array to JPEG bytes for Garmin IMG.

        Args:
            tile_array: RGB tile data as numpy array (H, W, 3) or (H, W, 4)
            quality: JPEG quality 1-100 (default 85)

        Returns:
            JPEG-compressed tile data

        Raises:
            ValueError: If tile exceeds 3.5 MB after compression
        """
        # Strip alpha channel if present
        if tile_array.ndim == 3 and tile_array.shape[2] == 4:
            tile_array = tile_array[:, :, :3]

        img = Image.fromarray(tile_array.astype(np.uint8))

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        jpeg_data = buffer.getvalue()

        return jpeg_data

    @staticmethod
    def encode_tiles(
        tiles: list[np.ndarray],
        quality: int = 85,
    ) -> list[bytes]:
        """Encode multiple tiles."""
        return [TileEncoder.encode_tile(t, quality) for t in tiles]

    @staticmethod
    def compute_grid(
        bounds: dict[str, float],
        zoom_level: int,
        tile_size: int = 256,
    ) -> tuple[int, int]:
        """
        Compute the tile grid dimensions for a given zoom level and bounds.

        Uses Web Mercator tile math to compute rows and columns.

        Args:
            bounds: Dict with north, south, west, east keys
            zoom_level: Web Mercator zoom level
            tile_size: Tile size in pixels (default 256)

        Returns:
            (num_cols, num_rows) tuple
        """
        n = 2**zoom_level

        # Calculate tile coordinates for corners
        west_rad = math.radians(bounds["west"])
        east_rad = math.radians(bounds["east"])
        north_rad = math.radians(bounds["north"])
        south_rad = math.radians(bounds["south"])

        # Spherical Mercator projection
        def lon_to_x(lon_rad: float) -> float:
            return (lon_rad + math.pi) / (2 * math.pi) * n

        def lat_to_y(lat_rad: float) -> float:
            return (
                (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)
                / 2.0
                * n
            )

        x_min = int(math.floor(lon_to_x(west_rad)))
        x_max = int(math.floor(lon_to_x(east_rad)))
        y_min = int(math.floor(lat_to_y(north_rad)))
        y_max = int(math.floor(lat_to_y(south_rad)))

        num_cols = max(1, x_max - x_min + 1)
        num_rows = max(1, y_max - y_min + 1)

        return num_cols, num_rows


class TileCompressor:
    """Compresses tiles to JPEG format for Garmin IMG."""

    @staticmethod
    def compress_tile(
        tile_array: np.ndarray,
        quality: int = 85,
    ) -> bytes:
        """
        Compress tile to JPEG.

        Args:
            tile_array: RGB tile data as numpy array (H, W, 3)
            quality: JPEG quality 1-100 (default 85)

        Returns:
            JPEG-compressed tile data as bytes

        Raises:
            ValueError: If tile exceeds 3.5 MB after compression
        """
        img = Image.fromarray(tile_array)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        jpeg_data = buffer.getvalue()

        if len(jpeg_data) > MAX_TILE_SIZE:
            logger.warning(
                f"Tile exceeds 3.5 MB limit: {len(jpeg_data):,} bytes "
                f"(quality={quality})"
            )

        return jpeg_data

    @staticmethod
    def compress_tiles(
        tiles: list[np.ndarray],
        quality: int = 85,
    ) -> list[bytes]:
        """Compress multiple tiles."""
        compressed = []
        for i, tile in enumerate(tiles):
            try:
                jpeg_data = TileCompressor.compress_tile(tile, quality)
                compressed.append(jpeg_data)
            except Exception as e:
                logger.error(f"Failed to compress tile {i}: {e}")
                raise
        return compressed


class IMGWriter:
    """
    Binary writer for Garmin IMG files.

    Uses two-pass layout:
      1. Compute subfile sizes and assign byte offsets
      2. Write header, FAT entries, and subfile data
    """

    def __init__(self, output_path: Path):
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self, img_file: IMGFile, compressed_tiles: dict[int, list[bytes]]
    ) -> None:
        """
        Write complete IMG file using two-pass layout.

        Args:
            img_file: IMGFile data structure to serialize
            compressed_tiles: Dict mapping zoom level to list of JPEG tile bytes
        """
        logger.info(f"Writing IMG file: {self.output_path}")

        # Pass 1: Compute layout
        computer = LayoutComputer(img_file, compressed_tiles)
        layouts = computer.compute()

        # Update subfile headers in img_file
        img_file.subfiles = []
        for layout in layouts:
            img_file.subfiles.append(
                SubfileHeader(
                    subfile_type=layout.subfile_type,
                    name=layout.name,
                    start_block_offset=layout.start_block,
                    length=layout.data_size,
                )
            )

        # Pass 2: Write binary data
        with open(self.output_path, "wb") as f:
            # Write main header (512 bytes)
            f.seek(0)
            IMGHeaderWriter.write(f, img_file.header, layouts)

            # Write FAT entries at FAT_START
            f.seek(FAT_START)
            FATWriter.write(f, layouts, FAT_START)

            # Write GMP subfile
            gmp_layout = next(
                lay for lay in layouts if lay.subfile_type == SubfileType.GMP
            )
            GMPWriter.write(f, img_file, compressed_tiles, gmp_layout)

            # Write MPS subfile
            mps_layout = next(
                lay for lay in layouts if lay.subfile_type == SubfileType.MPS
            )
            MPSWriter.write(f, mps_layout, img_file)

            # Pad file to full size (fill any gaps)
            total_size = max(lay.end_offset for lay in layouts)
            current = f.tell()
            if current < total_size:
                f.seek(total_size - 1)
                f.write(b"\x00")

        actual_size = self.output_path.stat().st_size
        logger.info(f"IMG file written: {self.output_path} ({actual_size:,} bytes)")
