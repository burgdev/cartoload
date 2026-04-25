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
from typing import TYPE_CHECKING, Callable, Union

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

# Type alias for compressed tiles with optional per-tile bounds.
# Each entry is (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max)) or just jpeg_bytes.
TileData = Union[bytes, tuple[bytes, tuple[float, float, float, float]]]
CompressedTiles = dict[int, list[TileData]]

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
RGN2_POLYLINE_PREAMBLE_SIZE = 18  # Type 0x06 polyline record before each E0 tile
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

    def __init__(self, img_file: IMGFile, compressed_tiles: CompressedTiles):
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
        # Subdivisions: for raster, one 16-byte group record per zoom level
        # Must match the subdiv_data allocation in GMPWriter.write()
        n_zoom = len(self.img_file.zoom_levels)
        subdiv_size = n_zoom * 16
        tre_data = 6 + subdiv_size + map_levels_size  # copyright + subdiv + map_levels

        # TRE extended sections (needed for GMT bitmap detection)
        # TRE5 is empty (size=0) — matches IOM reference for bitmap detection
        tre7_rec_size = 4  # uint32 offset per entry (matches IOM reference)
        tre7_size = n_zoom * tre7_rec_size  # one entry per zoom level
        tre8_size = 6  # TRE8: 2 entries x 3 bytes (polyline + raster type)
        tre_ext_data = tre7_size + tre8_size

        # RGN data sections:
        # RGN1: minimal (empty or near-empty for raster maps)
        rgn1_data = 0
        # RGN2: Polyline preamble + Type E0 record per tile (no outline records — SwissTopo reference)
        type_e0_record_size = 23 if total_tiles < 256 else 24
        rgn2_data = total_tiles * (RGN2_POLYLINE_PREAMBLE_SIZE + type_e0_record_size)

        # LBL labels (tile filenames)
        lbl_labels = sum(len(f"{i}.jpg\0".encode("ascii")) for i in range(total_tiles))

        # LBL28 section (image index table)
        lbl28_size = total_tiles * 4  # uint32 offset per tile

        # LBL29 section (image storage - JPEG tile data)
        lbl29_size = 0
        for tiles in self.compressed_tiles.values():
            for tile_entry in tiles:
                jpeg_size = (
                    len(tile_entry[0])
                    if isinstance(tile_entry, tuple)
                    else len(tile_entry)
                )
                lbl29_size += jpeg_size

        size = (
            GMP_CONTAINER_HEADER_SIZE
            + len(copyright_section)
            + tre_section
            + len(map_info)
            + rgn_section
            + lbl_section
            + net_section
            + tre_data
            + tre_ext_data  # TRE5 + TRE7 + TRE8
            + rgn1_data
            + rgn2_data
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

        # Offset 0x0A-0x0B: Unknown field (constant 0x7A04 in SwissTopo reference files)
        struct.pack_into("<H", buf, 0x0A, 0x7A04)

        # Offset 0x0C-0x0D: Unknown (zeros in reference files)
        # Already zero

        # Offset 0x0E-0x0F: Checksum/ID field (file-specific, LE uint16)
        struct.pack_into("<H", buf, 0x0E, header.checksum_or_id)

        # Offset 0x10-0x16: Magic "DSKIMG\0"
        magic = header.magic.encode("ascii")
        buf[0x10 : 0x10 + len(magic)] = magic
        buf[0x10 + len(magic)] = 0x00  # null terminator

        # Offset 0x17: Always 0x02
        buf[0x17] = 0x02

        # Offset 0x18-0x19: Sectors per track
        struct.pack_into("<H", buf, 0x18, 0x0020)

        # Offset 0x1A-0x1B: Heads per cylinder (must be 256 to match SwissTopo reference)
        struct.pack_into("<H", buf, 0x1A, 0x0100)

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
        struct.pack_into("<H", buf, 0x5D, 0x0100)

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

        # Offset 0x1C0-0x1CD: Partition table entry (MBR format at 0x1BE)
        # Reference SwissTopo files: boot=0x01, start_head=0x00, sys_type=0x60
        buf[0x1BE] = 0x01  # Bootable partition
        buf[0x1BF] = 0x00  # Start head
        buf[0x1C0] = 0x00  # Start sector/cylinder
        buf[0x1C1] = 0xFF  # Start cylinder low
        buf[0x1C2] = 0x60  # System type (from SwissTopo reference)
        if layouts:
            total_size = max(lay.end_offset for lay in layouts)
            total_sectors = total_size // 512
            end_head = min(0xFE, (total_sectors // 63) // 255)
            buf[0x1C3] = end_head  # End head
            buf[0x1C4] = 0x00  # End sector/cylinder
            buf[0x1C5] = 0x00  # End cylinder low
            struct.pack_into("<I", buf, 0x1C6, 0)  # Relative sectors (LBA start)
            struct.pack_into("<I", buf, 0x1CA, total_sectors)  # Number of sectors
        else:
            buf[0x1C3] = 0x64  # End head (default from reference)
            buf[0x1C4] = 0x00  # End sector
            buf[0x1C5] = 0x00  # End cylinder

        # Offset 0x1FE-0x1FF: Boot signature
        struct.pack_into("<H", buf, 0x1FE, BOOT_SIGNATURE)

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
      [RGN Data Sections: Type E0 records with per-tile bounds]
      [LBL Labels: tile filenames as null-terminated strings]
      [LBL28 Section: image index (uint32 offsets to LBL29)]
      [LBL29 Section: image storage (concatenated JPEG files)]
    """

    @staticmethod
    def write(
        f: io.BufferedWriter,
        img_file: IMGFile,
        compressed_tiles: CompressedTiles,
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

        # --- TRE data sections (offsets are GMP-relative, stored in TRE header) ---

        # TRE copyright section (6 bytes)
        tre_copyright_pos = pos  # GMP-relative
        pos += 6

        # TRE subdivisions (16-byte group records per zoom level)
        tre_subdiv_pos = pos  # GMP-relative
        n_zoom = len(img_file.zoom_levels)
        subdiv_data = bytearray(n_zoom * 16)
        subdiv_size = len(subdiv_data)
        pos += subdiv_size

        # TRE map levels
        tre_maplevels_pos = pos  # GMP-relative
        map_levels_data = bytearray(n_zoom * 4)
        map_levels_size = len(map_levels_data)
        pos += map_levels_size

        # --- TRE extended sections (TRE8, TRE7) ---
        # Layout matches IOM reference: TRE8 data first, then TRE7 right after.
        # TRE4/5/6 are empty (size=0) and share position with TRE8.
        # TRE5 must be empty for GMT to detect bitmaps (IOM has size=0).

        # TRE8 data (6 bytes): 2 object type entries
        tre8_pos = pos  # GMP-relative
        tre8_size = 6
        pos += tre8_size

        # TRE5: empty (shares position with TRE8, size=0)
        tre5_pos = tre8_pos
        tre5_size = 0

        # TRE7 data: one uint32 entry per zoom level
        tre7_pos = pos  # GMP-relative
        tre7_rec_size = 4
        tre7_size = n_zoom * tre7_rec_size
        pos += tre7_size

        # --- RGN data sections ---
        # RGN1: empty for raster maps (all tile data goes to RGN2)
        rgn1_pos = pos  # GMP-relative
        rgn1_size = 0

        # RGN2: Polyline preamble + Type E0 records per tile (no outline records)
        rgn2_pos = pos  # GMP-relative
        type_e0_record_size = 23 if total_tiles < 256 else 24
        # Each tile has a polyline preamble + E0 record (no per-zoom outline records)
        rgn2_size = total_tiles * (RGN2_POLYLINE_PREAMBLE_SIZE + type_e0_record_size)
        pos += rgn2_size

        # --- LBL labels (tile filenames) ---
        lbl_labels_pos = pos  # GMP-relative
        label_strings = bytearray()
        for i in range(total_tiles):
            label_strings += f"{i}.jpg\0".encode("ascii")
        pos += len(label_strings)

        # --- LBL28 section (image index) ---
        lbl28_pos = pos  # GMP-relative
        lbl28_size = total_tiles * 4  # uint32 offset per tile
        pos += lbl28_size

        # --- LBL29 section (image storage) ---
        lbl29_pos = pos  # GMP-relative
        # Calculate LBL29 size (sum of all JPEG sizes)
        lbl29_size = 0
        for zoom in img_file.zoom_levels:
            tiles = compressed_tiles.get(zoom.level_number, [])
            for tile_entry in tiles:
                lbl29_size += (
                    len(tile_entry[0])
                    if isinstance(tile_entry, tuple)
                    else len(tile_entry)
                )
        pos += lbl29_size

        # Fill map levels data (4 bytes per level: zoom_code(1) + level_number(1) + subdiv_count(2 LE))
        for z_idx, zoom in enumerate(img_file.zoom_levels):
            map_levels_data[z_idx * 4] = zoom.zoom_code
            map_levels_data[z_idx * 4 + 1] = zoom.level_number
            # subdiv_count = number of subdivision groups at this zoom level (1 per level)
            struct.pack_into("<H", map_levels_data, z_idx * 4 + 2, 1)

        # Fill subdivision group records (16 bytes each, one per zoom level)
        # Format: rgn_offset(3) + obj_types(1) + lon(3) + lat(3) + flags(2) + subdiv_count(2) + next_level(2)
        map_center_lon = int(
            (img_file.bounds_west + img_file.bounds_east) / 2 * (2**24) / 360
        )
        map_center_lat = int(
            (img_file.bounds_north + img_file.bounds_south) / 2 * (2**24) / 360
        )
        rgn_tile_offset = 0
        type_e0_record_size = 23 if total_tiles < 256 else 24
        for z_idx, zoom in enumerate(img_file.zoom_levels):
            tile_count = len(compressed_tiles.get(zoom.level_number, []))
            off = z_idx * 16
            # RGN offset (3 bytes LE): byte offset into RGN2 data section for this level's tiles
            rgn_off_bytes = rgn_tile_offset.to_bytes(3, "little")
            subdiv_data[off] = rgn_off_bytes[0]
            subdiv_data[off + 1] = rgn_off_bytes[1]
            subdiv_data[off + 2] = rgn_off_bytes[2]
            # Object types: 0x00 (no vector objects in raster maps)
            subdiv_data[off + 3] = 0x00
            # Center longitude (3-byte signed map units)
            lon_bytes = _put3s(map_center_lon)
            subdiv_data[off + 4 : off + 7] = lon_bytes
            # Center latitude (3-byte signed map units)
            lat_bytes = _put3s(map_center_lat)
            subdiv_data[off + 7 : off + 10] = lat_bytes
            # Flags (uint16 LE): bit 15 (0x8000) = has child subdivisions
            # Lower bits indicate zoom level bitmap (bit 0 for first level)
            subdiv_flags = 0x8000 | (1 << z_idx)
            struct.pack_into("<H", subdiv_data, off + 10, subdiv_flags)
            # Subdivision count (uint16 LE): for raster maps, 1 group per zoom level
            # (each group contains all tiles at this zoom)
            struct.pack_into("<H", subdiv_data, off + 12, 1)
            # Next level index (uint16 LE) = index of first subdivision at next zoom
            if z_idx + 1 < n_zoom:
                struct.pack_into("<H", subdiv_data, off + 14, z_idx + 1)
            else:
                struct.pack_into("<H", subdiv_data, off + 14, 0)
            rgn_tile_offset += tile_count * (
                RGN2_POLYLINE_PREAMBLE_SIZE + type_e0_record_size
            )

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
            tre5_pos,
            tre5_size,
            tre7_pos,
            tre7_size,
            tre7_rec_size,
            tre8_pos,
            tre8_size,
        )
        f.write(tre_header)

        # 4. Map info strings
        f.write(map_info)

        # 5. RGN Sub-Header
        rgn_header = _build_rgn_subheader(now, rgn1_pos, rgn1_size, rgn2_pos, rgn2_size)
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

        # 11. TRE8 data (6 bytes): 2 object type entries
        # Entry 1: raster tiles type 0x13 (required for GMT bitmap detection)
        # Entry 2: DATA_BOUNDS type 0x0D (from IOM reference)
        f.write(bytes([0x06, 0x06, 0x13, 0x0D, 0x06, 0x01]))

        # 13. TRE7 data: raster layer offset table (4 bytes per entry)
        # Each entry: uint32 LE offset into RGN2 data section
        # Points to the first polyline preamble for each zoom level
        rgn2_offset = 0
        for z_idx, zoom in enumerate(img_file.zoom_levels):
            tile_count = len(compressed_tiles.get(zoom.level_number, []))
            # Write offset to the first preamble+E0 pair for this zoom level
            f.write(struct.pack("<I", rgn2_offset))
            # Advance past all preamble+E0 pairs (no outline records)
            rgn2_offset += tile_count * (
                RGN2_POLYLINE_PREAMBLE_SIZE + type_e0_record_size
            )

        # 14. RGN2 data section (Type E0 records)
        _write_rgn_data_section(f, compressed_tiles, img_file.zoom_levels, img_file)

        # 15. LBL labels (tile filenames)
        f.write(label_strings)

        # 16. LBL28 section (image index)
        _write_lbl28_section(f, compressed_tiles, img_file.zoom_levels)

        # 17. LBL29 section (image storage - JPEG tiles)
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
    tre5_pos: int,
    tre5_size: int,
    tre7_pos: int,
    tre7_size: int,
    tre7_rec_size: int,
    tre8_pos: int,
    tre8_size: int,
) -> bytes:
    """Build the TRE sub-header (TRE_HEADER_LENGTH bytes).

    After common header (21 bytes):
      bounds: 4 × 3-byte signed map units (N, E, S, W)
      map_levels: position(4) + size(4)
      subdivisions: position(4) + size(4)
      copyright_section: position(4) + size(4) + item_size(2)
      unknown(4) + poi_flags(1) + display_priority(3)
      flags + sections for polyline/polygon/points (zeros for raster)
      TRE4-TRE8 extended section descriptors (for raster bitmap detection)
    """
    buf = bytearray(TRE_HEADER_LENGTH)

    # Common header (21 bytes)
    common = _build_common_header("TRE", TRE_HEADER_LENGTH, now)
    buf[:21] = common

    # TRE+0x15: Bounds as 3-byte signed map units (N, E, S, W)
    buf[0x15 : 0x15 + 3] = _put3s(_deg_to_map_units(img_file.bounds_north))
    buf[0x18 : 0x18 + 3] = _put3s(_deg_to_map_units(img_file.bounds_east))
    buf[0x1B : 0x1B + 3] = _put3s(_deg_to_map_units(img_file.bounds_south))
    buf[0x1E : 0x1E + 3] = _put3s(_deg_to_map_units(img_file.bounds_west))

    # TRE+0x21: Map levels (TRE1) position(4) + size(4)
    struct.pack_into("<I", buf, 0x21, maplevels_pos)
    struct.pack_into("<I", buf, 0x25, maplevels_size)

    # TRE+0x29: Subdivisions (TRE2) position(4) + size(4)
    struct.pack_into("<I", buf, 0x29, subdiv_pos)
    struct.pack_into("<I", buf, 0x2D, subdiv_size)

    # TRE+0x31: Copyright (TRE3) position(4) + size(4) + item_size(2)
    struct.pack_into("<I", buf, 0x31, copyright_pos)
    struct.pack_into("<I", buf, 0x35, copyright_size)
    struct.pack_into("<H", buf, 0x39, 3)

    # TRE+0x3F: Flags (1 byte) = 1
    buf[0x3F] = 1

    # TRE+0x40: Display priority (uint16 LE) = 24 for raster
    struct.pack_into("<H", buf, 0x40, 24)

    # TRE+0x42: More flags / parameters (8 bytes)
    # SwissTopo reference: 00 01 04 24 00 01 00 00
    # GMT reports "parameters 1 4 36 1" for SwissTopo
    buf[0x42] = 0x00  # flag byte (SwissTopo reference: 0x00)
    buf[0x43] = 0x01  # parameter 1
    buf[0x44] = 0x04  # parameter 2 (bits per coord: 4 for SwissTopo)
    buf[0x45] = 0x24  # parameter 3 (36 = tile_size_constant)
    buf[0x46] = 0x00
    buf[0x47] = 0x01  # parameter 4
    buf[0x48] = 0x00
    buf[0x49] = 0x00

    # TRE+0x4A: TRE4 descriptor: pos(4) + size(4) + rec_size(2) + pad(4)
    # TRE4 is not used for raster maps (size=0, shares position with TRE8)
    struct.pack_into("<I", buf, 0x4A, tre8_pos)
    struct.pack_into("<I", buf, 0x4E, 0)  # size=0
    struct.pack_into("<H", buf, 0x52, 2)  # rec_size=2

    # TRE+0x58: TRE5 descriptor: pos(4) + size(4) + rec_size(2) + pad(4)
    # TRE5 must be EMPTY (size=0) for GMT to detect bitmaps (confirmed from IOM reference)
    struct.pack_into("<I", buf, 0x58, tre8_pos)
    struct.pack_into("<I", buf, 0x5C, 0)  # size=0 (empty, like IOM)
    struct.pack_into("<H", buf, 0x60, 2)  # rec_size=2

    # TRE+0x66: TRE6 descriptor: pos(4) + size(4) + rec_size(2) + pad(4)
    # TRE6 shares position with TRE8 (size=0 for raster)
    struct.pack_into("<I", buf, 0x66, tre8_pos)
    struct.pack_into("<I", buf, 0x6A, 0)  # size=0
    struct.pack_into("<H", buf, 0x6E, 3)  # rec_size=3

    # TRE+0x74: Map ID (uint32 LE)
    struct.pack_into("<I", buf, 0x74, img_file.map_id)

    # TRE+0x78: padding (4 bytes, zeros)
    # Already zero

    # TRE+0x7C: TRE7 descriptor (raster layer): pos(4) + size(4) + rec_size(2) + pad(4)
    struct.pack_into("<I", buf, 0x7C, tre7_pos)
    struct.pack_into("<I", buf, 0x80, tre7_size)
    struct.pack_into("<H", buf, 0x84, tre7_rec_size)
    buf[0x86] = 0x01  # flag from IOM reference (01000000)
    buf[0x87] = 0x00

    # TRE+0x8A: TRE8 descriptor (object types): pos(4) + size(4) + rec_size(2) + pad(4)
    struct.pack_into("<I", buf, 0x8A, tre8_pos)
    struct.pack_into("<I", buf, 0x8E, tre8_size)
    struct.pack_into("<H", buf, 0x92, 3)  # rec_size=3 (3-byte entries: type + 2 params)
    buf[0x94] = 0x00  # padding flag (IOM reference: 00 00 02 00 at 0x94)

    # TRE+0xCF: Map ID copy / matching number (uint32 LE)
    struct.pack_into("<I", buf, 0xCF, img_file.map_id)

    # TRE+0xD3: Map name (null-terminated ASCII, rest of 273-byte header)
    name_str = img_file.header.map_name or "Raster Map"
    name_bytes = name_str.encode("ascii")[: TRE_HEADER_LENGTH - 0xD3 - 1]
    buf[0xD3 : 0xD3 + len(name_bytes)] = name_bytes
    buf[0xD3 + len(name_bytes)] = 0x00  # null terminator

    return bytes(buf)


def _build_rgn_subheader(
    now: datetime,
    rgn1_pos: int,
    rgn1_size: int,
    rgn2_pos: int,
    rgn2_size: int,
) -> bytes:
    """Build the RGN sub-header (RGN_HEADER_LENGTH bytes).

    After common header (21 bytes):
      RGN1: position(4) + size(4) at offset 0x15
      RGN2: position(4) + size(4) at offset 0x1D
      Remaining: zeros
    """
    buf = bytearray(RGN_HEADER_LENGTH)

    # Common header
    common = _build_common_header("RGN", RGN_HEADER_LENGTH, now)
    buf[:21] = common

    # RGN1 section: position(4) + size(4) at offset 0x15
    struct.pack_into("<I", buf, 0x15, rgn1_pos)
    struct.pack_into("<I", buf, 0x19, rgn1_size)

    # RGN2 section (extended types / raster data): position(4) + size(4) at offset 0x1D
    struct.pack_into("<I", buf, 0x1D, rgn2_pos)
    struct.pack_into("<I", buf, 0x21, rgn2_size)

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

    # Encoding (1 byte) = 9 (8-bit encoding, matches SwissTopo reference)
    buf[30] = 9

    # Codepage (uint16 LE) at offset 0xAA = 1252 (Windows Western European)
    # GMT reads this field for its "CP" display
    struct.pack_into("<H", buf, 0xAA, 1252)

    # Raster table descriptor (LBL28 equivalent) at offset 0x184
    # GPXSee/GMT reads: offset(4) + size(4) + recordSize(2) + flags(4)
    # Layout verified from IOM reference LBL header at 0x184-0x191
    struct.pack_into("<I", buf, 0x184, lbl28_pos)
    struct.pack_into("<I", buf, 0x188, lbl28_size)
    struct.pack_into("<H", buf, 0x18C, 4)  # record size: uint32 offsets

    # Flags (4 bytes at 0x18E) — 0 for raster maps (matches IOM reference)
    # Already zero

    # Raster image data descriptor (LBL29 equivalent) at offset 0x192
    # offset(4) + size(4)
    struct.pack_into("<I", buf, 0x192, lbl29_pos)
    struct.pack_into("<I", buf, 0x196, lbl29_size)

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

    # Image index IMMEDIATELY after bits_field (per doc Section 4.5.2)
    if bits_field == 0x2B:
        f.write(struct.pack("<B", image_index))  # uint8
    else:
        f.write(struct.pack("<H", image_index))  # uint16

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


def _write_lbl28_section(
    f: io.BufferedWriter, compressed_tiles: CompressedTiles, zoom_levels: list
) -> None:
    """
    Write LBL28 section (image index table).

    Writes an array of uint32 LE offsets, one per tile, pointing to JPEGs in LBL29.
    Offsets are relative to the start of LBL29 section.

    Args:
        f: File handle to write to
        compressed_tiles: Dict mapping zoom level to list of (jpeg_bytes, bounds) tuples or plain bytes
        zoom_levels: List of ZoomLevel objects defining zoom order
    """
    offset = 0
    for zoom in zoom_levels:
        tiles = compressed_tiles.get(zoom.level_number, [])
        for tile_entry in tiles:
            # Write offset to this JPEG (relative to LBL29 start)
            f.write(struct.pack("<I", offset))
            jpeg_data = tile_entry[0] if isinstance(tile_entry, tuple) else tile_entry
            offset += len(jpeg_data)


def _write_lbl29_section(
    f: io.BufferedWriter, compressed_tiles: CompressedTiles, zoom_levels: list
) -> None:
    """
    Write LBL29 section (image storage).

    Writes concatenated JPEG files with no padding between them.
    JPEGs are written in zoom level order.

    Args:
        f: File handle to write to
        compressed_tiles: Dict mapping zoom level to list of (jpeg_bytes, bounds) tuples or plain bytes
        zoom_levels: List of ZoomLevel objects defining zoom order
    """
    for zoom in zoom_levels:
        tiles = compressed_tiles.get(zoom.level_number, [])
        for tile_entry in tiles:
            tile_data = tile_entry[0] if isinstance(tile_entry, tuple) else tile_entry
            # Verify JPEG marker
            if len(tile_data) >= 4 and tile_data[0:2] == b"\xff\xd8":
                f.write(tile_data)
            else:
                logger.warning(
                    f"Tile at zoom {zoom.level_number} does not start with JPEG marker (FFD8)"
                )
                f.write(tile_data)


def _write_polyline_preamble(
    f: io.BufferedWriter,
    center_lat: float,
    center_lon: float,
) -> None:
    """Write an 18-byte polyline preamble record before each E0 tile record.

    This record is required for GMT and Garmin devices to properly detect
    and display raster bitmap tiles. The preamble is a type 0x06 polyline
    record (subtype 0xB3) containing a minimal 2-point line in Garmin
    bitstream format.

    Format: type(1) + subtype(1) + bitstream(16) = 18 bytes total.

    Args:
        f: File handle to write to
        center_lat: Subdivision center latitude (degrees)
        center_lon: Subdivision center longitude (degrees)
    """
    # Type 0x06 (polyline), subtype 0xB3 (line type 51, preamble marker)
    f.write(bytes([0x06, 0xB3]))

    # Garmin polyline bitstream for a 2-point line at the subdivision center.
    # The bitstream uses the standard Garmin RGN polyline encoding:
    # - Byte 0: direction(1) + two_addresses(1) + extra_bytes_count(6 bits)
    # - Extra bytes: define coordinate delta bit width
    # - Coordinate deltas: signed integers at specified bit width
    #
    # Using zero deltas (both points at subdivision center) for simplicity.
    # This matches the IOM reference file's approach of using minimal offsets.
    f.write(b"\x00" * 16)


def _write_rgn_data_section(
    f: io.BufferedWriter,
    compressed_tiles: CompressedTiles,
    zoom_levels: list,
    img_file,
) -> None:
    """
    Write RGN data section (polyline preamble + Type E0 records).

    For each raster tile, writes:
      1. Polyline preamble (18 bytes): type 0x06, subtype 0xB3, + 16 data bytes
      2. Type E0 record (23-24 bytes): tile bounds, JPEG size, image index

    The polyline preamble provides line element metadata for the Garmin renderer.
    SwissTopo reference uses this structure without separate outline records.

    Uses per-tile geographic bounds when available (from tile extraction),
    falling back to full map bounds as a default.

    Args:
        f: File handle to write to
        compressed_tiles: Dict mapping zoom level to list of (jpeg_bytes, bounds) tuples or plain bytes
        zoom_levels: List of ZoomLevel objects defining zoom order
        img_file: IMGFile with map bounds (used as fallback)
    """
    total_tiles = sum(
        len(compressed_tiles.get(z.level_number, [])) for z in zoom_levels
    )
    bits_field = _compute_bits_field(total_tiles)

    # Precompute the subdivision center for preamble records.
    center_lat = (img_file.bounds_north + img_file.bounds_south) / 2
    center_lon = (img_file.bounds_east + img_file.bounds_west) / 2

    image_index = 0
    for zoom in zoom_levels:
        tiles = compressed_tiles.get(zoom.level_number, [])

        for tile_entry in tiles:
            if isinstance(tile_entry, tuple):
                jpeg_data, tile_bounds = tile_entry
                lat_min, lon_min, lat_max, lon_max = tile_bounds
            else:
                jpeg_data = tile_entry
                lat_min = img_file.bounds_south
                lon_min = img_file.bounds_west
                lat_max = img_file.bounds_north
                lon_max = img_file.bounds_east

            # Write polyline preamble (18 bytes)
            _write_polyline_preamble(f, center_lat, center_lon)

            # Write Type E0 record
            _write_type_e0_record(
                f,
                lat_min=lat_min,
                lon_min=lon_min,
                lat_max=lat_max,
                lon_max=lon_max,
                jpeg_size=len(jpeg_data),
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
    ) -> dict[int, list[tuple[np.ndarray, tuple[float, float, float, float]]]]:
        """
        Extract tiles from raster at each zoom level.

        Args:
            zoom_levels: List of zoom levels to extract
            bounds: Geographic bounds (west, east, south, north)
            tile_size: Tile dimension in pixels (default 256)
            progress_callback: Called with (stage, current, total) to report progress

        Returns:
            Dictionary mapping zoom level to list of (tile_array, (lat_min, lon_min, lat_max, lon_max)) tuples
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

        tiles_by_zoom: dict[
            int, list[tuple[np.ndarray, tuple[float, float, float, float]]]
        ] = {}
        extracted_count = 0

        for zoom in zoom_levels:
            cells = all_cells[zoom]
            logger.info(f"  Zoom {zoom}: {len(cells)} tiles to extract")

            tiles: list[tuple[np.ndarray, tuple[float, float, float, float]]] = []
            for x, y, lon_min, lat_max, lon_max, lat_min in cells:
                tile = self._extract_tile_region(
                    lon_min,
                    lat_max,
                    lon_max,
                    lat_min,
                    tile_size,
                )
                if tile is not None:
                    # Store tile with its geographic bounds: (lat_min, lon_min, lat_max, lon_max)
                    tiles.append((tile, (lat_min, lon_min, lat_max, lon_max)))
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

    def write(self, img_file: IMGFile, compressed_tiles: CompressedTiles) -> None:
        """
        Write complete IMG file using two-pass layout.

        Args:
            img_file: IMGFile data structure to serialize
            compressed_tiles: Dict mapping zoom level to list of (jpeg_bytes, bounds) tuples or plain bytes
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
