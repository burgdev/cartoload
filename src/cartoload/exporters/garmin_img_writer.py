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
import os
import struct
import subprocess
import tempfile
from concurrent.futures import (
    Executor,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
)
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Union

import numpy as np
from PIL import Image

from .garmin_img_model import (
    GMPGroup,
    IMGFile,
    IMGHeader,
    Subdivision,
    SubfileHeader,
    SubfileType,
    TileMetadata,
)

# Type alias for processed tile result from warp operations
ProcessedTile = tuple[bytes, tuple[float, float, float, float]]

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Type alias for compressed tiles with optional per-tile bounds.
# Each entry is (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max)) or just jpeg_bytes.
TileData = Union[bytes, tuple[bytes, tuple[float, float, float, float]]]
CompressedTiles = dict[int, list[TileData]]

# Garmin IMG constants
BLOCK_SIZE_DEFAULT = 32768  # 32 KB data blocks (e2=6)
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
BLOCK_SIZE_EXP_E2_DEFAULT = 0x06  # 512 * 2^6 = 32768 (default, for maps under ~2 GB)

# Subfile header sizes
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

# Maximum size of a single GMP subfile in bytes.
# Limited by uint32 section size fields (RGN2, LBL28, LBL29 offsets/sizes).
# Keep conservative to leave room for headers and metadata.
MAX_GMP_SIZE = 3_500_000_000  # ~3.5 GB per GMP


def _compute_block_exp_e2(total_data_size: int) -> int:
    """Compute the minimum block size exponent e2 for the total data size.

    Block numbers in the FAT are uint16, so max addressable bytes =
    65535 * (512 << e2). We need e2 large enough that the total file size
    fits within this range.

    Returns the minimum e2 value (0-12) that can address the given size.
    """
    # 65535 blocks * block_size must >= total_data_size
    # block_size = 512 << e2
    # So: 65535 * 512 * 2^e2 >= total_data_size
    # => 2^e2 >= total_data_size / (65535 * 512)
    # => e2 >= ceil(log2(total_data_size / (65535 * 512)))
    base_addressable = 65535 * 512  # = 33,553,920 bytes per e2 increment
    if total_data_size <= base_addressable:
        return BLOCK_SIZE_EXP_E2_DEFAULT  # Use default for small maps

    import math

    ratio = total_data_size / base_addressable
    e2 = max(BLOCK_SIZE_EXP_E2_DEFAULT, math.ceil(math.log2(ratio)))
    # Cap at e2=12 (2MB blocks) — should handle maps up to ~128 GB
    return min(e2, 12)


def _get_worker_count() -> int:
    """Get parallel worker count from environment or default.

    Default: max(1, ceil(cpu_count / 2)).
    Override: CARTOLOAD_WORKERS environment variable.
    """
    env_val = os.environ.get("CARTOLOAD_WORKERS")
    if env_val is not None:
        try:
            return max(1, int(env_val))
        except ValueError:
            pass
    cpu_count = os.cpu_count() or 4
    return max(1, math.ceil(cpu_count / 2))


def _get_executor_mode() -> str:
    """Get executor mode from environment or default.

    Default: "process" (ProcessPoolExecutor, fastest).
    Override: CARTOLOAD_EXECUTOR environment variable ("process" or "thread").
    """
    env_val = os.environ.get("CARTOLOAD_EXECUTOR", "process").lower().strip()
    if env_val not in ("process", "thread"):
        logger.warning(
            "Invalid CARTOLOAD_EXECUTOR value '%s', using 'process'", env_val
        )
        return "process"
    return env_val


# Module-level global for pre-loaded warp function in worker processes
_warp_func: Callable | None = None


def _init_worker() -> None:
    """Pre-load heavy libraries (rasterio, numpy) once per worker process."""
    global _warp_func
    from cartoload.processor.rasterio_warp import warp_tile_to_jpeg

    _warp_func = warp_tile_to_jpeg


def _warp_tile_worker(
    source_path: Path,
    x: int,
    y: int,
    zoom: int,
    source_crs: str,
    target_crs: str,
    quality: int | None,
) -> tuple[int, int, int, bytes | None]:
    """Top-level worker for parallel tile warping via ProcessPoolExecutor.

    Returns (x, y, zoom, jpeg_bytes_or_none) for result mapping.
    Must be top-level (not a method) for pickling.
    Uses pre-loaded _warp_func if available (set by _init_worker).
    """
    if not source_path.exists():
        return (x, y, zoom, None)

    if quality is None:
        # Passthrough: read raw file bytes without re-encoding
        return (x, y, zoom, source_path.read_bytes())

    warp_fn = _warp_func
    if warp_fn is None:
        # Fallback: import on first call if initializer wasn't used
        from ..processor.rasterio_warp import warp_tile_to_jpeg

        warp_fn = warp_tile_to_jpeg

    result = warp_fn(source_path, x, y, zoom, source_crs, target_crs, quality)
    if result is not None:
        return (x, y, zoom, result[0])
    return (x, y, zoom, None)


def _img_id_size(total_tiles: int) -> int:
    """Compute the byte size needed for image IDs (matches GPXSee's byteSize).

    GPXSee computes _imgIdSize = byteSize(imgCount - 1) where byteSize
    returns the minimum number of bytes needed to represent the value.
    """
    if total_tiles <= 1:
        return 1
    val = total_tiles - 1
    size = 0
    while val > 0:
        size += 1
        val >>= 8
    return size


def _rgn2_record_size(img_id_bytes: int) -> int:
    """Compute RGN2 compound raster record size based on image ID byte width.

    Fixed fields: type(1)+subtype(1)+lon(2)+lat(2)+len(1)+bitstream(8)+label(3)+class(1)+rs(1)+bounds(16)+jpgSz(4) = 40
    Variable: image ID (img_id_bytes)
    """
    return 40 + img_id_bytes


def _deg_to_garmin(deg: float) -> int:
    """Convert decimal degrees to Garmin coordinate units (degrees * 2^31 / 180)."""
    return int(deg * (2**31) / 180)


def _deg_to_map_units(deg: float) -> int:
    """Convert decimal degrees to Garmin 3-byte map units (degrees * 2^24 / 360).

    Used in TRE sub-header bounds fields.
    """
    return int(deg * (2**24) / 360)


def _encode_vuint32(value: int) -> bytes:
    """Encode a value using Garmin's variable-length unsigned int format.

    Matches GPXSee's SubFile::readVUInt32 (subfile_img.cpp:43).

    The encoding uses the low bits of the first byte to indicate size:
    - bit[0]=1: single byte, value = byte >> 1  (0-127)
    - bit[1:0]=10: two bytes, value uses 13 bits
    - bit[2:0]=000: three bytes, value uses 20 bits
    - bit[2:0]=001: four bytes, value uses 28 bits

    For raster records, values are small (bitstream_len=8 → 0x11, rs=22 → 0x2D).
    """
    if value < 0:
        raise ValueError(f"VUInt32 cannot encode negative value {value}")
    if value < (1 << 7):
        # Single byte: bit[0]=1, value in bits[7:1]
        return bytes([(value << 1) | 1])
    elif value < (1 << 13):
        # Two bytes: bit[1:0]=10, 6 bits in byte0, 8 bits in byte1
        b0 = ((value & 0x3F) << 2) | 0x02
        b1 = (value >> 6) & 0xFF
        return bytes([b0, b1])
    elif value < (1 << 20):
        raise NotImplementedError("3-byte VUInt32 not needed for raster records")
    else:
        raise ValueError(f"Value {value} too large for VUInt32 encoding")


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


def _blocks_needed(byte_count: int, block_size: int = BLOCK_SIZE_DEFAULT) -> int:
    """Calculate number of blocks needed for given byte count."""
    return math.ceil(byte_count / block_size)


def _align_to_block(size: int, block_size: int = BLOCK_SIZE_DEFAULT) -> int:
    """Align a byte count up to the next block boundary."""
    return _blocks_needed(size, block_size) * block_size


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
        block_size: int = BLOCK_SIZE_DEFAULT,
    ):
        self.subfile_type = subfile_type
        self.name = name
        self.start_offset = start_offset
        self.data_size = data_size
        self.block_size = block_size
        self.aligned_size = _align_to_block(data_size, block_size)
        self.num_data_blocks = _blocks_needed(data_size, block_size)
        self.num_fat_entries = _fat_blocks_for_data_blocks(self.num_data_blocks)
        self.start_block = start_offset // block_size

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

    def __init__(
        self,
        img_file: IMGFile,
        compressed_tiles: CompressedTiles | None = None,
        subdivisions: list[Subdivision] | None = None,
        jpeg_quality: int | None = None,
    ):
        self.img_file = img_file
        self.compressed_tiles: CompressedTiles = compressed_tiles or {}
        self.subdivisions = subdivisions
        self.jpeg_quality = jpeg_quality
        self.layouts: list[SubfileLayout] = []
        self.block_size = BLOCK_SIZE_DEFAULT
        self.block_exp_e2 = BLOCK_SIZE_EXP_E2_DEFAULT

    def compute(self) -> list[SubfileLayout]:
        """Compute layout for all subfiles and return ordered list."""
        self.layouts = []

        # Compute GMP data size first (before knowing block size)
        gmp_size = self._compute_gmp_size_for(
            subdivisions=self.subdivisions,
            compressed_tiles=self.compressed_tiles,
            img_file=self.img_file,
            jpeg_quality=self.jpeg_quality,
        )

        # Estimate total file size to determine block size exponent
        # Rough estimate: GMP + MPS + FAT overhead + header
        estimated_total = gmp_size + MPS_SUBFILE_SIZE + FAT_START + 1024 * 1024
        self.block_exp_e2 = _compute_block_exp_e2(estimated_total)
        self.block_size = 512 << self.block_exp_e2
        logger.info(
            f"Block size: {self.block_size:,} bytes (e2={self.block_exp_e2}), "
            f"estimated total: {estimated_total:,} bytes"
        )

        # Calculate FAT entries needed (using dynamic block size)
        gmp_data_blocks = _blocks_needed(gmp_size, self.block_size)
        mps_data_blocks = _blocks_needed(MPS_SUBFILE_SIZE, self.block_size)

        total_fat_entries = (
            1
            + _fat_blocks_for_data_blocks(gmp_data_blocks)
            + _fat_blocks_for_data_blocks(mps_data_blocks)
        )
        fat_region_size = total_fat_entries * PHYSICAL_BLOCK_SIZE
        data_start = _align_to_block(FAT_START + fat_region_size, self.block_size)

        current_offset = data_start

        gmp_name = f"{self.img_file.map_id:08X}"[:8]
        gmp_layout = SubfileLayout(
            SubfileType.GMP, gmp_name, current_offset, gmp_size, self.block_size
        )
        self.layouts.append(gmp_layout)
        current_offset = gmp_layout.end_offset

        mps_layout = SubfileLayout(
            SubfileType.MPS,
            "MAPSOURC",
            current_offset,
            MPS_SUBFILE_SIZE,
            self.block_size,
        )
        self.layouts.append(mps_layout)
        current_offset = mps_layout.end_offset

        return self.layouts

    def compute_multi_gmp(
        self,
        gmp_groups: list[GMPGroup],
    ) -> list[SubfileLayout]:
        """Compute layout for multiple GMP subfiles + one MPS within a single IMG.

        Each GMPGroup gets its own GMP subfile with a unique FAT name derived
        from the group's map_id. All GMPs share the same block size and IMG header.

        Args:
            gmp_groups: List of GMPGroup objects, each with subdivisions and zoom_levels.

        Returns:
            Ordered list of SubfileLayout objects (multiple GMPs + one MPS).
        """

        self.layouts = []

        # Compute size of each GMP subfile
        gmp_sizes: list[int] = []
        for group in gmp_groups:
            # Create a temporary IMGFile for this group to compute its GMP size
            group_img = IMGFile(
                header=self.img_file.header,
                map_id=group.map_id,
                copyright_string=self.img_file.copyright_string,
                zoom_levels=group.zoom_levels,
                bounds_north=group.bounds_north,
                bounds_south=group.bounds_south,
                bounds_west=group.bounds_west,
                bounds_east=group.bounds_east,
            )
            gmp_size = self._compute_gmp_size_for(
                subdivisions=group.subdivisions,
                compressed_tiles={},
                img_file=group_img,
                jpeg_quality=self.jpeg_quality,
            )
            gmp_sizes.append(gmp_size)

        # Estimate total file size for block size exponent
        total_data = sum(gmp_sizes) + MPS_SUBFILE_SIZE + FAT_START + 1024 * 1024
        self.block_exp_e2 = _compute_block_exp_e2(total_data)
        self.block_size = 512 << self.block_exp_e2
        logger.info(
            f"Block size: {self.block_size:,} bytes (e2={self.block_exp_e2}), "
            f"estimated total: {total_data:,} bytes ({total_data / 1e9:.1f} GB)"
        )

        # Calculate total FAT entries (1 special + N GMPs + 1 MPS)
        total_fat_entries = 1  # special directory entry
        for gmp_size in gmp_sizes:
            total_fat_entries += _fat_blocks_for_data_blocks(
                _blocks_needed(gmp_size, self.block_size)
            )
        total_fat_entries += _fat_blocks_for_data_blocks(
            _blocks_needed(MPS_SUBFILE_SIZE, self.block_size)
        )

        fat_region_size = total_fat_entries * PHYSICAL_BLOCK_SIZE
        data_start = _align_to_block(FAT_START + fat_region_size, self.block_size)

        current_offset = data_start

        # Create layout for each GMP subfile
        for group_idx, (group, gmp_size) in enumerate(zip(gmp_groups, gmp_sizes)):
            gmp_name = f"{group.map_id:08X}"[:8]
            gmp_layout = SubfileLayout(
                SubfileType.GMP, gmp_name, current_offset, gmp_size, self.block_size
            )
            self.layouts.append(gmp_layout)
            current_offset = gmp_layout.end_offset
            logger.info(
                f"  GMP layout {group_idx}: name={gmp_name}, "
                f"size={gmp_size:,} bytes ({gmp_size / 1e9:.1f} GB), "
                f"FAT entries={gmp_layout.num_fat_entries}"
            )

        # MPS subfile (one shared MPS at the end)
        mps_layout = SubfileLayout(
            SubfileType.MPS,
            "MAPSOURC",
            current_offset,
            MPS_SUBFILE_SIZE,
            self.block_size,
        )
        self.layouts.append(mps_layout)

        return self.layouts

    @staticmethod
    def _compute_gmp_size_for(
        subdivisions: list[Subdivision] | None,
        compressed_tiles: CompressedTiles,
        img_file: IMGFile,
        jpeg_quality: int | None = None,
    ) -> int:
        """Compute the total size of a single GMP subfile.

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
        # Compute total tiles from subdivisions (if available) or compressed_tiles
        if subdivisions is not None and len(subdivisions) > 0:
            total_tiles = sum(len(sub.tile_entries) for sub in subdivisions)
            ct_count = sum(len(tiles) for tiles in compressed_tiles.values())
            if ct_count > 0 and total_tiles != ct_count:
                raise ValueError(
                    f"Subdivision tile count ({total_tiles}) != "
                    f"compressed_tiles count ({ct_count})"
                )
        else:
            total_tiles = sum(len(tiles) for tiles in compressed_tiles.values())

        # Container header + copyright strings
        copyright_str = img_file.copyright_string or "Copyright GARMIN."
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
        n_zoom_levels = len(img_file.zoom_levels)
        map_levels_size = n_zoom_levels * 4  # 4 bytes per zoom level

        # Subdivisions: non-last levels use 16-byte records, last level uses 14-byte
        # Plus 4 trailing bytes (total RGN2 extent marker)
        n_subdivisions = len(subdivisions) if subdivisions else n_zoom_levels
        if subdivisions:
            by_level: dict[int, int] = {}
            for sub in subdivisions:
                by_level[sub.zoom_level_index] = (
                    by_level.get(sub.zoom_level_index, 0) + 1
                )
            n_last_level = by_level.get(n_zoom_levels - 1, 0)
            n_non_last = n_subdivisions - n_last_level
            subdiv_size = n_non_last * 16 + n_last_level * 14 + 4  # +4 trailing extent
        else:
            subdiv_size = (
                (n_subdivisions - 1) * 16 + 1 * 14 + 4
            )  # legacy: last is 14-byte
        tre_data = 6 + subdiv_size + map_levels_size  # copyright + subdiv + map_levels

        # TRE extended sections (needed for GMT bitmap detection)
        # rec_size=4 (uint32 offset only, no flag byte)
        # +1 sentinel entry for GPXSee compatibility (setExtEnds on last subdiv)
        tre7_rec_size = 4
        tre7_size = (n_subdivisions + 1) * tre7_rec_size
        # TRE extended sections (TRE5, TRE7, TRE8)
        tre5_size = 0  # IOM reference: no TRE5 data
        tre8_size = 6  # TRE8: two 3-byte entries (06 06 13, 0D 06 01)
        tre_ext_data = tre5_size + tre8_size + tre7_size

        # RGN data sections:
        # RGN1: minimal (empty or near-empty for raster maps)
        rgn1_data = 0
        # RGN2: Compound raster record per tile (size varies with imgIdSize)
        rgn2_data = total_tiles * _rgn2_record_size(_img_id_size(total_tiles))

        # LBL labels (tile filenames)
        lbl_labels = sum(len(f"{i}.jpg\0".encode("ascii")) for i in range(total_tiles))

        # LBL28 section (image index table)
        lbl28_size = total_tiles * 4  # uint32 offset per tile

        # LBL29 section (image storage - JPEG tile data)
        # When jpeg_quality is set, estimate the re-encoded size
        quality_ratio = 1.0
        if subdivisions and jpeg_quality is not None:
            quality_ratio = _estimate_quality_ratio(subdivisions, jpeg_quality)

        lbl29_size = 0
        if subdivisions:
            # When using subdivisions, tiles are stored in subdivision objects
            for sub in subdivisions:
                for tile_entry in sub.tile_entries:
                    if isinstance(tile_entry, TileMetadata):
                        lbl29_size += int(tile_entry.jpeg_size * quality_ratio)
                    else:
                        jpeg_data = (
                            tile_entry[0]
                            if isinstance(tile_entry, tuple)
                            else tile_entry
                        )
                        lbl29_size += len(jpeg_data)
        else:
            # Legacy: tiles are in compressed_tiles dict
            for tiles in compressed_tiles.values():
                for tile_entry in tiles:
                    if isinstance(tile_entry, TileMetadata):
                        lbl29_size += int(tile_entry.jpeg_size * quality_ratio)
                    else:
                        jpeg_size = (
                            len(tile_entry[0])
                            if isinstance(tile_entry, tuple)
                            else len(tile_entry)
                        )
                        lbl29_size += jpeg_size

        # Clamp to uint32 max — LBL header stores this as uint32
        lbl29_size = min(lbl29_size, 0xFFFFFFFF)

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
        block_exp_e2: int = BLOCK_SIZE_EXP_E2_DEFAULT,
    ) -> None:
        """Write the 512-byte IMG header at current file position."""
        block_size = 512 << block_exp_e2
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
        buf[0x62] = block_exp_e2

        # Offset 0x63-0x64: Total block count (or 0xFFFF if overflow)
        if layouts:
            total_blocks = max(lay.end_offset for lay in layouts) // block_size
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
            block_size = layouts[0].block_size
        else:
            block_size = BLOCK_SIZE_DEFAULT
            data_start = block_size  # minimum
        struct.pack_into("<I", entry, 0x0C, data_start)

        # Flag2: special directory
        entry[0x10] = FAT_FLAG_SPECIAL

        # Part: 0
        entry[0x11] = 0x00

        # Reserved: zeros (0x12-0x1F already zero)

        # Block sequence: cover blocks 0 through (data_start/block_size - 1)
        # These are the logical blocks occupied by header + FAT region
        header_blocks = data_start // block_size
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

        if num_fat_entries > 256:
            raise ValueError(
                f"GMP subfile '{layout.name}' needs {num_fat_entries} FAT entries "
                f"(max 256). Data size {layout.data_size:,} bytes exceeds the "
                f"FAT part number limit. Split into multiple GMP subfiles."
            )

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

            # Size: only in part 0 (clamp to uint32 max for large subfiles;
            # GPXSee uses block chain for actual data access, not this field)
            if part == 0:
                struct.pack_into("<I", entry, 0x0C, min(layout.data_size, 0xFFFFFFFF))

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
        subdivisions: list[Subdivision] | None = None,
    ) -> None:
        """Write complete GMP subfile with container format.

        Args:
            f: File handle positioned at GMP start
            img_file: IMGFile data structure
            compressed_tiles: Dict mapping zoom level to tile data
            gmp_layout: Computed layout for the GMP subfile
            subdivisions: Optional list of Subdivision objects for spatial indexing.
                When provided, writes per-subdivision TRE2/TRE7/RGN2 data.
                When None, writes one subdivision per zoom level (legacy mode).
        """
        f.seek(gmp_layout.start_offset)

        total_tiles = sum(len(t) for t in compressed_tiles.values())
        n_zoom = len(img_file.zoom_levels)
        now = img_file.gmp_creation_date or datetime.now()

        # Determine subdivision mode
        use_subdivisions = subdivisions is not None and len(subdivisions) > 0
        if use_subdivisions:
            n_subdivisions = len(subdivisions)
        else:
            n_subdivisions = n_zoom
        # IOM reference: rec_size=4 (uint32 offset only, no flag byte)
        tre7_rec_size = 4

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

        # TRE subdivisions: non-last levels use 16-byte records, last level uses 14-byte
        # Plus 4 trailing bytes (total RGN2 extent marker)
        tre_subdiv_pos = pos  # GMP-relative
        if use_subdivisions:
            n_last = sum(1 for s in subdivisions if s.zoom_level_index == n_zoom - 1)
            n_non_last = len(subdivisions) - n_last
        else:
            n_last = 1  # legacy: last zoom level has 1 subdivision
            n_non_last = n_zoom - 1
        subdiv_binary_size = n_non_last * 16 + n_last * 14 + 4  # +4 trailing extent
        subdiv_data = bytearray(subdiv_binary_size)
        subdiv_size = len(subdiv_data)
        pos += subdiv_size

        # TRE map levels
        tre_maplevels_pos = pos  # GMP-relative
        map_levels_data = bytearray(n_zoom * 4)
        map_levels_size = len(map_levels_data)
        pos += map_levels_size

        # --- TRE extended sections (TRE5, TRE8, TRE7) ---
        tre5_pos = pos  # GMP-relative (separate from TRE8)
        tre5_size = 0  # IOM reference: no TRE5 data
        pos += tre5_size

        tre8_pos = pos  # GMP-relative
        tre8_size = 6  # Two entries: 06 06 13, 0D 06 01 (IOM reference)
        pos += tre8_size

        # TRE7 data: one entry per subdivision + sentinel (uint32 offset only)
        tre7_pos = pos  # GMP-relative
        tre7_size = (n_subdivisions + 1) * tre7_rec_size
        pos += tre7_size

        # --- RGN data sections ---
        rgn1_pos = pos  # GMP-relative
        rgn1_size = 0

        # RGN2: Compound raster records per tile (size varies with imgIdSize)
        rgn2_pos = pos  # GMP-relative
        rgn2_size = total_tiles * _rgn2_record_size(_img_id_size(total_tiles))
        pos += rgn2_size

        # --- LBL labels (tile filenames) ---
        lbl_labels_pos = pos  # GMP-relative
        label_strings = bytearray()
        for i in range(total_tiles):
            label_strings += f"{i}.jpg\0".encode("ascii")
        pos += len(label_strings)

        # --- LBL28 section (image index) ---
        lbl28_pos = pos  # GMP-relative
        lbl28_size = total_tiles * 4
        pos += lbl28_size

        # --- LBL29 section (image storage) ---
        lbl29_pos = pos  # GMP-relative
        lbl29_size = 0
        if use_subdivisions:
            # When using subdivisions, tiles are stored in subdivision objects
            for sub in subdivisions:
                for tile_entry in sub.tile_entries:
                    if isinstance(tile_entry, TileMetadata):
                        lbl29_size += tile_entry.jpeg_size
                    else:
                        jpeg_data = (
                            tile_entry[0]
                            if isinstance(tile_entry, tuple)
                            else tile_entry
                        )
                        lbl29_size += len(jpeg_data)
        else:
            # Legacy: tiles are in compressed_tiles dict
            for zoom in img_file.zoom_levels:
                tiles = compressed_tiles.get(zoom.source_zoom or zoom.level_number, [])
                for tile_entry in tiles:
                    lbl29_size += (
                        len(tile_entry[0])
                        if isinstance(tile_entry, tuple)
                        else len(tile_entry)
                    )
        # Clamp to uint32 max — LBL header stores this as uint32
        lbl29_size = min(lbl29_size, 0xFFFFFFFF)
        pos += lbl29_size

        # --- Fill TRE1 map levels data ---
        if use_subdivisions:
            # Count subdivisions per zoom level
            subdiv_count_per_level: dict[int, int] = {}
            for sub in subdivisions:
                subdiv_count_per_level[sub.zoom_level_index] = (
                    subdiv_count_per_level.get(sub.zoom_level_index, 0) + 1
                )
            for z_idx in range(n_zoom):
                map_levels_data[z_idx * 4] = img_file.zoom_levels[z_idx].zoom_code
                map_levels_data[z_idx * 4 + 1] = img_file.zoom_levels[
                    z_idx
                ].level_number
                struct.pack_into(
                    "<H",
                    map_levels_data,
                    z_idx * 4 + 2,
                    subdiv_count_per_level.get(z_idx, 1),
                )
        else:
            for z_idx, zoom in enumerate(img_file.zoom_levels):
                map_levels_data[z_idx * 4] = zoom.zoom_code
                map_levels_data[z_idx * 4 + 1] = zoom.level_number
                struct.pack_into("<H", map_levels_data, z_idx * 4 + 2, 1)

        # --- Fill TRE2 subdivision records ---
        # Non-last levels: 16 bytes (rgn_off(3) + obj(1) + lon(3) + lat(3) + width(2) + height(2) + nextLevel(2))
        # Last level: 14 bytes (no nextLevel field)
        # Plus 4 trailing bytes (total RGN2 data extent)
        if use_subdivisions:
            # Assign RGN2 offsets to subdivisions (sequential per-subdivision)
            rgn2_running_offset = 0
            rgn2_total_extent = 0
            record_size = _rgn2_record_size(_img_id_size(total_tiles))
            for sub in subdivisions:
                tile_count = sub.get_tile_count()
                if tile_count == 0:
                    # Empty subdivision (overview zoom): no RGN2 data
                    sub.rgn2_offset = 0
                else:
                    sub.rgn2_offset = rgn2_running_offset
                    chunk_size = tile_count * record_size
                    rgn2_running_offset += chunk_size
                    rgn2_total_extent = rgn2_running_offset

            # Compute shift per zoom level for width/height encoding
            # shift = 24 - bits_per_coord, where bits_per_coord = level_number
            zoom_shifts = {}
            for z_idx, zoom in enumerate(img_file.zoom_levels):
                zoom_shifts[z_idx] = max(0, 24 - zoom.level_number)

            # Determine the last subdivision index at each zoom level
            # (for setting the "end of chain" bit 15 on width).
            # With the simple chain model (all parents point to first child at
            # next level), EOC goes on the last sub at each non-last level.
            last_sub_at_level: dict[int, int] = {}
            for i, sub in enumerate(subdivisions):
                last_sub_at_level[sub.zoom_level_index] = i

            # Write per-subdivision TRE2 records with variable size
            off = 0
            for i, sub in enumerate(subdivisions):
                is_last_level = sub.zoom_level_index == n_zoom - 1
                rec_size = 14 if is_last_level else 16
                shift = zoom_shifts.get(sub.zoom_level_index, 0)

                # RGN offset (4 bytes LE uint32, lower 28 bits = offset)
                rgn2_offset_u32 = sub.rgn2_offset & 0x0FFFFFFF
                struct.pack_into("<I", subdiv_data, off, rgn2_offset_u32)
                # Center longitude (3-byte signed map units)
                lon_mu = int(sub.center_lon * (2**24) / 360)
                subdiv_data[off + 4 : off + 7] = _put3s(lon_mu)
                # Center latitude (3-byte signed map units)
                lat_mu = int(sub.center_lat * (2**24) / 360)
                subdiv_data[off + 7 : off + 10] = _put3s(lat_mu)
                # Width: encoded horizontal extent with bit 15 = end of chain
                w = sub.encode_tre2_width(shift)
                if (
                    not is_last_level
                    and last_sub_at_level.get(sub.zoom_level_index) == i
                ):
                    w |= 0x8000  # bit 15 = end of chain
                struct.pack_into("<H", subdiv_data, off + 10, w)
                # Height: encoded vertical extent
                h = sub.encode_tre2_height(shift)
                struct.pack_into("<H", subdiv_data, off + 12, h)
                # Next level index (only for non-last levels, 1-based per
                # mkgmap and PDF spec: "1-based index of the first subdivision
                # in chain for the next zoom level")
                if not is_last_level:
                    nl = sub.next_level_index + 1 if sub.next_level_index > 0 else 0
                    struct.pack_into("<H", subdiv_data, off + 14, nl)

                off += rec_size

            # Trailing 4 bytes: total RGN2 data extent
            struct.pack_into("<I", subdiv_data, off, rgn2_total_extent)
        else:
            # Legacy: one subdivision per zoom level
            map_center_lon = int(
                (img_file.bounds_west + img_file.bounds_east) / 2 * (2**24) / 360
            )
            map_center_lat = int(
                (img_file.bounds_north + img_file.bounds_south) / 2 * (2**24) / 360
            )
            # Compute map extent in map units for width/height encoding
            map_w_mu = int(
                (img_file.bounds_east - img_file.bounds_west) * (2**24) / 360
            )
            map_h_mu = int(
                (img_file.bounds_north - img_file.bounds_south) * (2**24) / 360
            )
            rgn_tile_offset = 0
            off = 0
            legacy_record_size = _rgn2_record_size(_img_id_size(total_tiles))
            for z_idx, zoom in enumerate(img_file.zoom_levels):
                tile_count = len(
                    compressed_tiles.get(zoom.source_zoom or zoom.level_number, [])
                )
                is_last_level = z_idx == n_zoom - 1
                rec_size = 14 if is_last_level else 16
                shift = max(0, 24 - zoom.level_number)
                mask = (1 << shift) - 1

                # RGN offset (4 bytes LE uint32, lower 28 bits = offset)
                rgn2_offset_u32 = rgn_tile_offset & 0x0FFFFFFF
                struct.pack_into("<I", subdiv_data, off, rgn2_offset_u32)
                subdiv_data[off + 4 : off + 7] = _put3s(map_center_lon)
                subdiv_data[off + 7 : off + 10] = _put3s(map_center_lat)
                # Width: encoded extent with bit 15 = end of chain
                # (only subdivision at this level, so it IS the last in chain)
                w = ((map_w_mu + 1) // 2 + mask) >> shift
                if not is_last_level:
                    w |= 0x8000
                struct.pack_into("<H", subdiv_data, off + 10, w)
                # Height: encoded extent
                h = ((map_h_mu + 1) // 2 + mask) >> shift
                struct.pack_into("<H", subdiv_data, off + 12, h)
                # Next level: 1-based global subdivision number.
                # Each legacy level has 1 subdiv; level Z+1's first subdiv
                # is at 0-based index Z+1, so 1-based = Z+2.
                if not is_last_level:
                    struct.pack_into("<H", subdiv_data, off + 14, z_idx + 2)
                rgn_tile_offset += tile_count * legacy_record_size
                off += rec_size

            # Trailing 4 bytes: total RGN2 data extent
            struct.pack_into("<I", subdiv_data, off, rgn_tile_offset)

        # --- Phase 2: Write all sections ---

        # 1. GMP Container Header (53 bytes)
        gmp_header = bytearray(GMP_CONTAINER_HEADER_SIZE)
        gmp_header[0] = GMP_CONTAINER_HEADER_SIZE
        gmp_header[1] = 0x00
        gmp_header[2:12] = b"GARMIN GMP"
        struct.pack_into("<H", gmp_header, 12, 1)
        date_bytes = _encode_garmin_date_7(now)
        gmp_header[14:21] = date_bytes[:7]
        struct.pack_into("<I", gmp_header, 21, 0)
        struct.pack_into("<I", gmp_header, 25, tre_pos)
        struct.pack_into("<I", gmp_header, 29, rgn_pos)
        struct.pack_into("<I", gmp_header, 33, lbl_pos)
        struct.pack_into("<I", gmp_header, 37, net_pos)
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
            rgn1_pos,
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

        # 8. TRE copyright data (6 bytes) — label offset indices matching SwissTopo
        f.write(bytes([0x0C, 0x00, 0x00, 0x32, 0x00, 0x00]))

        # 9. TRE subdivisions
        f.write(subdiv_data)

        # 10. TRE map levels
        f.write(map_levels_data)

        # 11. TRE5 data — IOM reference: no TRE5 data (size=0)
        # (no data written)

        # 12. TRE8 data (6 bytes) — two entries matching IOM reference
        f.write(bytes([0x06, 0x06, 0x13, 0x0D, 0x06, 0x01]))

        # 12. TRE7 data: raster layer offset table (uint32 per subdivision + sentinel)
        if use_subdivisions:
            # uint32 offset per subdivision, then sentinel with total RGN2 extent
            for sub in subdivisions:
                f.write(struct.pack("<I", sub.rgn2_offset))
            # Sentinel: total RGN2 data extent (used by GPXSee for setExtEnds)
            f.write(
                struct.pack(
                    "<I",
                    total_tiles * _rgn2_record_size(_img_id_size(total_tiles)),
                )
            )
        else:
            # Legacy: one uint32 per zoom level + sentinel
            rgn2_offset = 0
            legacy_rs = _rgn2_record_size(_img_id_size(total_tiles))
            for z_idx, zoom in enumerate(img_file.zoom_levels):
                tile_count = len(
                    compressed_tiles.get(zoom.source_zoom or zoom.level_number, [])
                )
                f.write(struct.pack("<I", rgn2_offset))
                rgn2_offset += tile_count * legacy_rs
            # Sentinel: total RGN2 data extent
            f.write(struct.pack("<I", rgn2_offset))

        # 13. RGN2 data section (Type E0 records)
        if use_subdivisions:
            _write_rgn_data_section_subdivisions(f, subdivisions, total_tiles, img_file)
        else:
            _write_rgn_data_section(f, compressed_tiles, img_file.zoom_levels, img_file)

        # 14. LBL labels (tile filenames)
        f.write(label_strings)

        # 15. LBL28 section (image index)
        if use_subdivisions:
            _write_lbl28_section_subdivisions(f, subdivisions)
        else:
            _write_lbl28_section(f, compressed_tiles, img_file.zoom_levels)

        # 16. LBL29 section (image storage - JPEG tiles)
        if use_subdivisions:
            _write_lbl29_section_subdivisions(f, subdivisions)
        else:
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
    rgn1_pos: int = 0,
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

    # TRE+0x40: Display priority (uint16 LE) = 20 for raster (IOM reference)
    struct.pack_into("<H", buf, 0x40, 20)

    # TRE+0x42: More flags / parameters (8 bytes)
    # IOM reference: 10 01 08 24 00 01 00 00
    buf[0x42] = 0x10  # flag byte (IOM reference: 0x10)
    buf[0x43] = 0x01  # parameter 1
    buf[0x44] = 0x08  # parameter 2 (IOM reference: 0x08)
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
    # IOM reference: no TRE5 data (size=0, rec_size=2, pad=00 00 00 00)
    struct.pack_into("<I", buf, 0x58, tre5_pos)
    struct.pack_into("<I", buf, 0x5C, 0)  # size=0
    struct.pack_into("<H", buf, 0x60, 2)  # rec_size=2
    buf[0x62] = 0x00  # pad (IOM reference: 00 00 00 00)
    buf[0x63] = 0x00
    buf[0x64] = 0x00
    buf[0x65] = 0x00

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
    buf[0x86] = 0x01  # pad flag (IOM reference: 01 00 00 00)
    buf[0x87] = 0x00
    buf[0x88] = 0x00
    buf[0x89] = 0x00

    # TRE+0x8A: TRE8 descriptor (object types): pos(4) + size(4) + rec_size(2) + pad(4)
    struct.pack_into("<I", buf, 0x8A, tre8_pos)
    struct.pack_into("<I", buf, 0x8E, tre8_size)
    struct.pack_into("<H", buf, 0x92, 3)  # rec_size=3 (3-byte entries: type + 2 params)
    buf[0x94] = 0x00  # pad flag (IOM reference: 00 00 02 00 — 2 entries)
    buf[0x95] = 0x00
    buf[0x96] = 0x02
    buf[0x97] = 0x00

    # TRE+0x9A-0xAD: Map ID hash area (already zeros)

    # TRE+0xAE: TRE9 descriptor: pos(4) + size(4) + rec_size(2) + pad(4)
    # Points to RGN1 section (SwissTopo reference)
    struct.pack_into("<I", buf, 0xAE, rgn1_pos)
    struct.pack_into("<I", buf, 0xB2, 0)  # size=0
    struct.pack_into("<H", buf, 0xB6, 0)  # rec_size=0

    # TRE+0xBC: TRE10 descriptor: pos(4) + size(4) + rec_size(2) + pad(4)
    # Points to RGN1 section with rec_size=1 (SwissTopo reference)
    struct.pack_into("<I", buf, 0xBC, rgn1_pos)
    struct.pack_into("<I", buf, 0xC0, 0)  # size=0
    struct.pack_into("<H", buf, 0xC4, 1)  # rec_size=1

    # TRE+0xCF: Map ID copy / matching number (uint32 LE)
    struct.pack_into("<I", buf, 0xCF, img_file.map_id)

    # TRE+0xD3: Extended map info area with section references
    # SwissTopo reference has two 16-byte entries referencing TRE9/TRE10 positions.
    # Structure: {uint16(0), uint16(section_pos), zeros(12)} repeated twice.
    # Writing rgn1_pos (same as TRE9/TRE10 position) as the section reference.
    struct.pack_into("<H", buf, 0xD3, 0)  # label index = 0
    struct.pack_into(
        "<H", buf, 0xD5, rgn1_pos & 0xFFFF
    )  # section reference (low 16 bits)
    struct.pack_into("<H", buf, 0xE3, rgn1_pos & 0xFFFF)  # second entry, same reference

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
      Extended fields at 0x25-0x7C: local flag bitmasks for each section,
      critical for Garmin device rendering. Values taken from SwissTopo
      reference files (SwissTopo_West.img, SwissTopo_Est.img).
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

    # RGN2 extended polygon descriptor (0x25-0x38)
    # 0x25: uint32 = 2 (known values: 0, 2; 2 = extended polygon encoding)
    struct.pack_into("<I", buf, 0x25, 2)
    # 0x29: uint32 = 0 (global flags)
    # 0x2D: uint32 = 0x200000FF (polygon local flags[0])
    struct.pack_into("<I", buf, 0x2D, 0x200000FF)
    # 0x31: uint32 = 0x0003FCFD (polygon local flags[1])
    struct.pack_into("<I", buf, 0x31, 0x0003FCFD)

    # RGN3 (polylines) — empty for raster maps
    rgn2_end = rgn2_pos + rgn2_size
    struct.pack_into("<I", buf, 0x39, rgn2_end)  # position = end of RGN2
    # 0x3D: size = 0 (already zero)
    # 0x49: uint32 = 0x2000003F (lines local flags[1])
    struct.pack_into("<I", buf, 0x49, 0x2000003F)
    # 0x4D: uint32 = 0x00000FFD (lines local flags[2])
    struct.pack_into("<I", buf, 0x4D, 0x00000FFD)

    # RGN4 (POIs) — empty for raster maps
    struct.pack_into("<I", buf, 0x55, rgn2_end)  # position = end of RGN2
    # 0x59: size = 0 (already zero)
    # 0x65: uint32 = 0x20003FFF (points local flags[1], SwissTopo reference)
    struct.pack_into("<I", buf, 0x65, 0x20003FFF)
    # 0x69: uint32 = 0x0FFFF73F (points local flags[2], SwissTopo reference)
    struct.pack_into("<I", buf, 0x69, 0x0FFFF73F)

    # RGN5 (dictionary) — empty for raster maps
    struct.pack_into("<I", buf, 0x71, rgn2_end)  # position = end of RGN2
    # 0x75: size = 0 (already zero)
    # 0x79: uint32 = 1 (dict info, SwissTopo reference)
    struct.pack_into("<I", buf, 0x79, 1)

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
    # GPXSee reads at _gmpOffset + 0x184 (when hdrLen >= 0x19A):
    #   offset(4) + size(4) + recordSize(2) + flags(4) + img_offset(4) + img_size(4)
    struct.pack_into("<I", buf, 0x184, lbl28_pos)
    struct.pack_into("<I", buf, 0x188, lbl28_size)
    struct.pack_into("<H", buf, 0x18C, 4)  # record size: uint32 offsets

    # Flags (4 bytes at 0x18E) — 0 for raster maps
    # Already zero

    # Raster image data descriptor (LBL29 equivalent) at offset 0x192
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


def _encode_tile_bitstream(
    tile_lat_min: float,
    tile_lon_min: float,
    tile_lat_max: float,
    tile_lon_max: float,
    level_number: int,
) -> bytes:
    """Encode 8-byte bitstream with tile extent delta for boundingRect coverage.

    Generates a DeltaStream that GPXSee decodes as polygon points expanding
    the boundingRect to cover the full tile area. P0 is at the tile's bottom-left
    (set by record header delta). One delta pair (+width, +height) extends the
    boundingRect to the tile's top-right corner.

    Format (matches GPXSee DeltaStream in deltastream.cpp):
      byte 0: info byte — low nibble = lon baseSize, high nibble = lat baseSize
      bytes 1-7: sign bits + extended bit + delta-encoded coordinate pair (LSB-first)

    The encoding uses fixed-sign mode for both axes. GPXSee's extPolyObjects calls
    stream.init(info, false, true) with extended=true, so an extended bit is included.

    Bit budget for 8 bytes (56 data bits in bytes 1-7):
      3 bits: lon sign + lat sign + extended
      1 delta pair at (3+baseSize) bits each axis
      Total: 3 + 2*(3+baseSize) = 9 + 2*baseSize → baseSize up to 23

    Args:
        tile_lat_min/max, tile_lon_min/max: Tile geographic bounds in degrees
        level_number: TRE1 bits value (determines coordinate shift)

    Returns:
        8 bytes of bitstream data
    """
    shift = max(0, 24 - level_number)
    mask = (1 << shift) - 1 if shift > 0 else 0

    left_mu = _deg_to_map_units(tile_lon_min)
    right_mu = _deg_to_map_units(tile_lon_max)
    bottom_mu = _deg_to_map_units(tile_lat_min)
    top_mu = _deg_to_map_units(tile_lat_max)

    # Tile width and height in level-space, ceiling division + 1 for quantization
    width_ls = ((right_mu - left_mu + mask) >> shift) + 1
    height_ls = ((top_mu - bottom_mu + mask) >> shift) + 1

    # Determine info byte based on max delta magnitude (width or height)
    max_delta = max(width_ls, height_ls)
    base_size = min(_bitstream_base_size(max_delta), 15)
    info = (base_size << 4) | base_size

    # Bit sizes for each axis — must match GPXSee's bitSize() exactly:
    #   baseSize <= 9: bits = 2 + baseSize
    #   baseSize >  9: bits = 2 + 2*baseSize - 9
    # Plus +1 for fixed-sign mode (sign bit embedded in each delta value)
    def _gpxsee_bit_size(bs: int) -> int:
        base = 2 + (bs if bs <= 9 else 2 * bs - 9)
        return base + 1  # +1 for fixed sign (variableSign=true in bitSize)

    lon_bits = _gpxsee_bit_size(base_size)
    lat_bits = _gpxsee_bit_size(base_size)
    max_pos = (1 << (lon_bits - 1)) - 1

    bits: list[int] = []

    # Sign bits: 0 = fixed sign for both axes (sign bit embedded in each delta)
    bits.append(0)  # lon: has-variable-sign = 0
    bits.append(0)  # lat: has-variable-sign = 0
    # Extended bit required by extPolyObjects (stream.init with extended=true)
    bits.append(0)  # extended = 0

    # Single delta pair: (+width, +height) — P0 is tile bottom-left, P1 is top-right
    bits.extend(_encode_delta(min(max_pos, width_ls), lon_bits))
    bits.extend(_encode_delta(min(max_pos, height_ls), lat_bits))

    # Pack into 8 bytes: byte 0 = info, bytes 1-7 = bit-packed data
    data = bytearray(8)
    data[0] = info
    for i, bit in enumerate(bits):
        if bit:
            data[1 + i // 8] |= 1 << (i % 8)

    return bytes(data)


def _bitstream_base_size(max_val: int) -> int:
    """Determine the DeltaStream baseSize for a given max delta magnitude.

    GPXSee's bitSize(baseSize, variableSign=True, extraBit=False):
      baseSize <= 9: bits = 2 + baseSize + 1 = baseSize + 3
      baseSize >  9: bits = 2 + 2*baseSize - 9 + 1 = 2*baseSize - 6

    We need max positive (1 << (bits-1)) - 1 >= max_val.
    Iterates from baseSize=1 to find the smallest valid baseSize.
    """
    import math as _math

    if max_val <= 0:
        return 1
    # For baseSize <= 9: bits = baseSize + 3, max_pos = (1 << (bits-1)) - 1
    needed_bits = _math.ceil(_math.log2(max_val + 1)) + 1
    base = max(1, needed_bits - 3)
    if base <= 9:
        return min(base, 15)
    # For baseSize > 9: bits = 2*baseSize - 6, so baseSize = (bits + 6) / 2
    base = max(10, _math.ceil((needed_bits + 6) / 2))
    return min(base, 15)


def _encode_delta(val: int, bits: int) -> list[int]:
    """Encode a signed delta value as a list of bits (LSB-first) for DeltaStream.

    Variable-sign encoding (sign=0 mode in GPXSee):
      - Positive v (v >= 0): raw value v, sign bit (MSB) = 0
      - Negative v (v < 0): value = (-v) | signMask, where signMask = 1 << (bits-1)
    """
    sign_mask = 1 << (bits - 1)
    if val >= 0:
        raw = val
    else:
        raw = (sign_mask + val) | sign_mask

    # Convert to LSB-first bit list
    result = []
    for i in range(bits):
        result.append((raw >> i) & 1)
    return result


def _write_rgn2_raster_record(
    f: io.BufferedWriter,
    subdiv_center_lat: float,
    subdiv_center_lon: float,
    tile_lat_min: float,
    tile_lon_min: float,
    tile_lat_max: float,
    tile_lon_max: float,
    tile_center_lat: float,
    tile_center_lon: float,
    jpeg_size: int,
    image_index: int,
    level_number: int,
    img_id_size: int = 2,
) -> None:
    """Write a single RGN2 compound raster record.

    Record size is dynamic: 40 + img_id_size bytes.
    img_id_size is determined by total tile count via _img_id_size().

    This is a single extended polyline object parsed by GPXSee's extPolyObjects().
    The record combines what was previously a separate preamble + E0 record into
    one compound record that Garmin devices parse as a unit.

    Record layout (42 bytes total, matching SwissTopo reference):
      [0x00] type = 0x06 (polyline)
      [0x01] subtype = 0xB3 (bit7=1→has class fields, bit5=1→has label, bits[4:0]=0x13)
             subtype & 0x1F = 0x13, type | (0x13<<8) | 0x10000 = 0x10613 = isRaster()
      [0x02-03] lon_delta (int16 LE) — tile left edge minus subdiv center, in level-space
      [0x04-05] lat_delta (int16 LE) — tile bottom edge minus subdiv center, in level-space
      [0x06] VUInt32(bitstream_len) = 0x11 (value=8, single-byte encoding)
      [0x07-0E] bitstream (8 bytes) — 1 delta pair (+width, +height) from bottom-left
                to top-right, producing a boundingRect covering the full tile area
      [0x0F-11] label_ptr (uint24 LE) = 0x000000 (no label needed for raster)
      [0x12] class_flags = 0xE0 (flags>>5 = 7 → triggers readRasterInfo)
      [0x13] VUInt32(remaining_size) = 0x2D (value=22, single-byte encoding)
      [0x14-15] image_id (uint16 LE) — index into LBL28 offset array
      [0x16-19] top (int32 LE) — max latitude in Garmin 32-bit map units
      [0x1A-1D] right (int32 LE) — max longitude in Garmin 32-bit map units
      [0x1E-21] bottom (int32 LE) — min latitude in Garmin 32-bit map units
      [0x22-25] left (int32 LE) — min longitude in Garmin 32-bit map units
      [0x26-29] JPEG block_size (uint32 LE) — JPEG file size in bytes

    GPXSee parsing flow (rgnfile.cpp extPolyObjects):
      read type(1) + subtype(1) → type = 0x10000 | (type<<8) | (subtype & 0x1F)
      → type = 0x10613 → isRaster()
      read lon_delta(int16) + lat_delta(int16)
      read VUInt32(len) → bitstream_len
      read bitstream (bitstream_len bytes)
      if subtype & 0x20: read label_ptr (uint24)
      if subtype & 0x80: readClassFields() → read flags byte
        → flags>>5 == 7 → read VUInt32(rs) → readRasterInfo()
        → readRasterInfo: read imgId(imgIdSize) + top(u32) + right(u32) + bottom(u32) + left(u32)

    Args:
        f: File handle to write to
        subdiv_center_lat: Subdivision center latitude (degrees)
        subdiv_center_lon: Subdivision center longitude (degrees)
        tile_lat_min: Tile south bound (degrees)
        tile_lon_min: Tile west bound (degrees)
        tile_lat_max: Tile north bound (degrees)
        tile_lon_max: Tile east bound (degrees)
        tile_center_lat: Tile center latitude (degrees)
        tile_center_lon: Tile center longitude (degrees)
        jpeg_size: JPEG file size in bytes
        image_index: Index into LBL28 array (0-based)
        level_number: The TRE1 level_number (bits) for this tile's zoom level.
    """
    # Type 0x06 + subtype 0xB3
    f.write(bytes([0x06, 0xB3]))

    # Lon/lat deltas from subdivision center (int16 LE, in level-space)
    # GPXSee computes: pos = subdiv_center_24bit + (delta_int16 << (24 - bits))
    # P0 is positioned at the tile's bottom-left corner so the single bitstream
    # delta pair (+width, +height) produces a boundingRect covering the full tile.
    center_lat_mu = _deg_to_map_units(subdiv_center_lat)
    center_lon_mu = _deg_to_map_units(subdiv_center_lon)
    tile_left_mu = _deg_to_map_units(tile_lon_min)
    tile_bottom_mu = _deg_to_map_units(tile_lat_min)

    shift = max(0, 24 - level_number)
    lon_delta = (tile_left_mu - center_lon_mu) >> shift
    lat_delta = (tile_bottom_mu - center_lat_mu) >> shift

    # Clamp to int16 range
    lon_delta = max(-32768, min(32767, lon_delta))
    lat_delta = max(-32768, min(32767, lat_delta))

    f.write(struct.pack("<h", lon_delta))
    f.write(struct.pack("<h", lat_delta))

    # VUInt32(bitstream_len=8) → 0x11
    f.write(_encode_vuint32(8))

    # Bitstream (8 bytes): 1 delta pair (+width, +height) from tile bottom-left
    # Produces a boundingRect covering [bottom-left, top-right] of the tile.
    bitstream = _encode_tile_bitstream(
        tile_lat_min,
        tile_lon_min,
        tile_lat_max,
        tile_lon_max,
        level_number,
    )
    assert len(bitstream) == 8
    f.write(bitstream)

    # Label pointer (uint24 LE) — 0 for raster tiles (no label)
    f.write(b"\x00\x00\x00")

    # Class flags byte: 0xE0 → flags>>5 = 7, triggers readRasterInfo
    f.write(bytes([0xE0]))

    # VUInt32(remaining_size) — rs = imgIdSize + 20 (image ID + 4 bounds + jpeg_size)
    rs = img_id_size + 20
    f.write(_encode_vuint32(rs))

    # Image ID (raw little-endian, img_id_size bytes) — index into LBL28 offset array
    if img_id_size == 1:
        f.write(struct.pack("<B", image_index))
    elif img_id_size == 2:
        f.write(struct.pack("<H", image_index))
    elif img_id_size == 3:
        f.write(struct.pack("<I", image_index)[:3])
    else:
        f.write(struct.pack("<I", image_index))

    # Tile bounds in Garmin 32-bit map units (int32 LE)
    # Order: top(max_lat), right(max_lon), bottom(min_lat), left(min_lon)
    f.write(struct.pack("<i", _deg_to_garmin(tile_lat_max)))  # top
    f.write(struct.pack("<i", _deg_to_garmin(tile_lon_max)))  # right
    f.write(struct.pack("<i", _deg_to_garmin(tile_lat_min)))  # bottom
    f.write(struct.pack("<i", _deg_to_garmin(tile_lon_min)))  # left

    # JPEG block size (uint32 LE)
    f.write(struct.pack("<I", jpeg_size))


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
        tiles = compressed_tiles.get(zoom.source_zoom or zoom.level_number, [])
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
        tiles = compressed_tiles.get(zoom.source_zoom or zoom.level_number, [])
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


def _write_rgn_data_section(
    f: io.BufferedWriter,
    compressed_tiles: CompressedTiles,
    zoom_levels: list,
    img_file,
) -> None:
    """Write RGN2 data section (compound raster records).

    For each raster tile, writes a single compound record combining
    the polyline header and raster info into one record parsed by extPolyObjects().

    Uses per-tile geographic bounds when available (from tile extraction),
    falling back to full map bounds as a default.

    Args:
        f: File handle to write to
        compressed_tiles: Dict mapping zoom level to list of (jpeg_bytes, bounds) tuples or plain bytes
        zoom_levels: List of ZoomLevel objects defining zoom order
        img_file: IMGFile with map bounds (used as fallback)
    """
    # Use map center as subdivision center (for non-subdivision path)
    center_lat = (img_file.bounds_north + img_file.bounds_south) / 2
    center_lon = (img_file.bounds_east + img_file.bounds_west) / 2

    total_tiles = sum(
        len(compressed_tiles.get(zoom.source_zoom or zoom.level_number, []))
        for zoom in zoom_levels
    )
    iid_size = _img_id_size(total_tiles)

    image_index = 0
    for zoom in zoom_levels:
        tiles = compressed_tiles.get(zoom.source_zoom or zoom.level_number, [])

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

            tile_center_lat = (lat_min + lat_max) / 2
            tile_center_lon = (lon_min + lon_max) / 2

            _write_rgn2_raster_record(
                f,
                subdiv_center_lat=center_lat,
                subdiv_center_lon=center_lon,
                tile_lat_min=lat_min,
                tile_lon_min=lon_min,
                tile_lat_max=lat_max,
                tile_lon_max=lon_max,
                tile_center_lat=tile_center_lat,
                tile_center_lon=tile_center_lon,
                jpeg_size=len(jpeg_data),
                image_index=image_index,
                level_number=zoom.level_number,
                img_id_size=iid_size,
            )
            image_index += 1


def _write_rgn_data_section_subdivisions(
    f: io.BufferedWriter,
    subdivisions: list[Subdivision],
    total_tiles: int,
    img_file: IMGFile,
) -> None:
    """Write RGN2 data section grouped by subdivision.

    For each subdivision, writes compound raster records for all its tiles.
    Each record encodes the tile's position relative to the subdivision center.
    Supports TileMetadata entries (bounds from fields) and legacy tuple/bytes entries.
    """
    iid_size = _img_id_size(total_tiles)
    image_index = 0
    for sub in subdivisions:
        level_number = img_file.zoom_levels[sub.zoom_level_index].level_number
        for tile_entry in sub.tile_entries:
            if isinstance(tile_entry, TileMetadata):
                lat_min = tile_entry.lat_min
                lon_min = tile_entry.lon_min
                lat_max = tile_entry.lat_max
                lon_max = tile_entry.lon_max
                jpeg_size = tile_entry.jpeg_size
            elif isinstance(tile_entry, tuple):
                jpeg_data, tile_bounds = tile_entry
                lat_min, lon_min, lat_max, lon_max = tile_bounds
                jpeg_size = len(jpeg_data)
            else:
                jpeg_data = tile_entry
                lat_min = img_file.bounds_south
                lon_min = img_file.bounds_west
                lat_max = img_file.bounds_north
                lon_max = img_file.bounds_east
                jpeg_size = len(jpeg_data)

            tile_center_lat = (lat_min + lat_max) / 2
            tile_center_lon = (lon_min + lon_max) / 2

            _write_rgn2_raster_record(
                f,
                subdiv_center_lat=sub.center_lat,
                subdiv_center_lon=sub.center_lon,
                tile_lat_min=lat_min,
                tile_lon_min=lon_min,
                tile_lat_max=lat_max,
                tile_lon_max=lon_max,
                tile_center_lat=tile_center_lat,
                tile_center_lon=tile_center_lon,
                jpeg_size=jpeg_size,
                image_index=image_index,
                level_number=level_number,
                img_id_size=iid_size,
            )
            image_index += 1


def _write_lbl28_section_subdivisions(
    f: io.BufferedWriter, subdivisions: list[Subdivision]
) -> None:
    """Write LBL28 section (image index table) for subdivision-ordered tiles.

    Supports TileMetadata entries (uses jpeg_size field) and legacy tuple/bytes entries.
    """
    offset = 0
    for sub in subdivisions:
        for tile_entry in sub.tile_entries:
            f.write(struct.pack("<I", offset))
            if isinstance(tile_entry, TileMetadata):
                offset += tile_entry.jpeg_size
            else:
                jpeg_data = (
                    tile_entry[0] if isinstance(tile_entry, tuple) else tile_entry
                )
                offset += len(jpeg_data)


def _write_lbl29_section_subdivisions(
    f: io.BufferedWriter, subdivisions: list[Subdivision]
) -> None:
    """Write LBL29 section (image storage) for subdivision-ordered tiles.

    Supports TileMetadata entries (raises error — use StreamingIMGWriter for
    metadata-only workflows) and legacy tuple/bytes entries.
    """
    for sub in subdivisions:
        for tile_entry in sub.tile_entries:
            if isinstance(tile_entry, TileMetadata):
                raise TypeError(
                    "TileMetadata entries cannot be written directly to LBL29. "
                    "Use StreamingIMGWriter which processes JPEG data on demand."
                )
            tile_data = tile_entry[0] if isinstance(tile_entry, tuple) else tile_entry
            if len(tile_data) >= 4 and tile_data[0:2] == b"\xff\xd8":
                f.write(tile_data)
            else:
                logger.warning(
                    "Tile in subdivision does not start with JPEG marker (FFD8)"
                )
                f.write(tile_data)


class StreamingIMGWriter:
    """Writes Garmin IMG files using a streaming two-pass approach.

    Pass 1 (layout): Compute all section positions from TileMetadata only.
    Pass 2 (write): Write the IMG file, streaming JPEG data in batches.

    Memory is bounded to ~60 MB per batch of tiles regardless of total tile count.
    """

    # Number of tiles to process in one batch during the LBL29 streaming write
    BATCH_SIZE = 5000

    def __init__(self, output_path: Path):
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        img_file: IMGFile,
        gmp_groups: list[GMPGroup],
        tile_processor: Callable[[Path, int, int, int, str, int], ProcessedTile | None]
        | None = None,
        source_crs: str = "EPSG:3857",
        jpeg_quality: int | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
        sequential_only: bool = False,
    ) -> None:
        """Write complete IMG file streaming JPEG data from source files.

        Uses a write-data-first approach: writes all GMP data sequentially
        without pre-computing JPEG sizes, then fixes up IMG header and FAT
        with actual sizes. This eliminates file size bloat from estimation
        inaccuracies.

        Memory usage is bounded to ~12 MB per batch of tiles.

        Args:
            img_file: IMGFile data structure (provides header, map_name, etc.)
            gmp_groups: List of GMPGroup objects, each with subdivisions and zoom_levels.
            tile_processor: Optional callable to process source tiles.
            source_crs: Source CRS for tile processing (default EPSG:3857)
            jpeg_quality: JPEG quality for warping (1-100), or None for passthrough
            progress_callback: Called with (stage, current, total) for progress.
        """
        logger.info(f"Streaming write IMG file: {self.output_path}")

        # Compute a conservative block size from original JPEG sizes (upper bound).
        # Actual data will be <= original (quality reduces or passes through),
        # so this block size is always sufficient.
        total_original_jpeg = 0
        for group in gmp_groups:
            for sub in group.subdivisions:
                for tile_entry in sub.tile_entries:
                    if isinstance(tile_entry, TileMetadata):
                        total_original_jpeg += tile_entry.jpeg_size
                    elif isinstance(tile_entry, tuple):
                        total_original_jpeg += len(tile_entry[0])
                    else:
                        total_original_jpeg += len(tile_entry)

        # Estimate conservative total to determine block size.
        # This MUST be an upper bound on the actual file size so that the block
        # size computed from it is always sufficient. Per-tile overhead includes:
        # RGN2 record (~42 bytes), LBL28 entry (4 bytes), LBL label (~12 bytes).
        total_tiles = sum(
            len(s.tile_entries) for g in gmp_groups for s in g.subdivisions
        )
        per_tile_overhead = 60  # RGN2 + LBL28 + label (upper bound)
        fixed_headers = (
            GMP_CONTAINER_HEADER_SIZE
            + TRE_HEADER_LENGTH
            + RGN_HEADER_LENGTH
            + LBL_HEADER_LENGTH
            + NET_HEADER_LENGTH
            + 100  # copyright, map info, TRE data sections
        )
        overhead_per_group = (
            fixed_headers + total_tiles * per_tile_overhead + 4096
        )  # +padding
        estimated_overhead = overhead_per_group * len(gmp_groups) + MPS_SUBFILE_SIZE
        conservative_total = total_original_jpeg + estimated_overhead
        block_exp_e2 = _compute_block_exp_e2(conservative_total)
        block_size = 512 << block_exp_e2

        # Compute dynamic FAT reservation: FAT needs 1 special entry + per-subfile
        # entries. Each FAT entry = 512 bytes, holds 240 block pointers.
        num_subfiles = len(gmp_groups) + 1  # GMP groups + MPS
        estimated_blocks = math.ceil(conservative_total / block_size)
        fat_entries_per_subfile = max(
            1, math.ceil(estimated_blocks / FAT_SLOTS_PER_ENTRY)
        )
        total_fat_entries = 1 + fat_entries_per_subfile * num_subfiles
        fat_reserved = total_fat_entries * PHYSICAL_BLOCK_SIZE

        logger.info(
            f"Conservative block size: {block_size:,} bytes (e2={block_exp_e2}), "
            f"original JPEG total: {total_original_jpeg:,} bytes, "
            f"FAT reserved: {fat_reserved:,} bytes"
        )

        # Compute data start: aligned after FAT region
        # FAT region starts at FAT_START (0x1000), occupies fat_reserved bytes
        data_start = _align_to_block(FAT_START + fat_reserved, block_size)

        # --- Phase 1: Write data sections (GMP groups + MPS) sequentially ---
        gmp_actual: list[tuple[str, int, int]] = []  # (name, start_offset, data_size)

        with open(self.output_path, "wb") as f:
            current_offset = data_start
            tiles_offset = 0

            for group_idx, group in enumerate(gmp_groups):
                gmp_name = f"{group.map_id:08X}"[:8]
                start_offset = current_offset

                group_img = IMGFile(
                    header=img_file.header,
                    map_id=group.map_id,
                    copyright_string=img_file.copyright_string,
                    zoom_levels=group.zoom_levels,
                    bounds_north=group.bounds_north,
                    bounds_south=group.bounds_south,
                    bounds_west=group.bounds_west,
                    bounds_east=group.bounds_east,
                )
                logger.info(
                    f"Writing GMP {group_idx}/{len(gmp_groups)}: "
                    f"{len(group.subdivisions)} subdivisions"
                )
                actual_size = self._write_gmp_data(
                    f,
                    start_offset,
                    group_img,
                    group.subdivisions,
                    tile_processor,
                    source_crs,
                    jpeg_quality,
                    progress_callback,
                    tiles_offset=tiles_offset,
                    sequential_only=sequential_only,
                )

                tiles_offset += sum(len(sub.tile_entries) for sub in group.subdivisions)
                gmp_actual.append((gmp_name, start_offset, actual_size))
                # Next GMP starts at block-aligned end of this one
                aligned_end = _align_to_block(start_offset + actual_size, block_size)
                logger.info(
                    f"  Phase1 GMP {group_idx}: start=0x{start_offset:X}, "
                    f"actual_size={actual_size:,}, aligned_end=0x{aligned_end:X}, "
                    f"f.tell()=0x{f.tell():X}"
                )
                current_offset = aligned_end

            # Write MPS subfile
            mps_start = current_offset
            f.seek(mps_start)
            _write_mps_data(f, img_file)
            current_offset = mps_start + MPS_SUBFILE_SIZE

            actual_total = current_offset
            logger.info(
                f"Actual data size: {actual_total:,} bytes ({actual_total / 1e9:.1f} GB)"
            )

            # --- Phase 2: Compute actual layout and write IMG header + FAT ---
            # CRITICAL: We MUST use the same block_size that Phase 1 used for data
            # positioning. Phase 1 wrote data aligned to `block_size`, so Phase 2's
            # FAT must point to those exact positions. Changing block_size here would
            # cause all FAT block pointers to be wrong → GPXSee "Invalid map tile".
            #
            # If the actual total exceeds what our conservative block_size can address
            # (65535 * block_size), that's a fatal error — we can't retroactively
            # change the alignment of already-written data.
            max_addressable = 65535 * block_size
            if actual_total > max_addressable:
                raise ValueError(
                    f"Actual data ({actual_total:,} bytes) exceeds what block_size "
                    f"{block_size:,} (e2={block_exp_e2}) can address "
                    f"({max_addressable:,} bytes). Conservative estimate was too low."
                )

            # Build layouts using actual start_offset positions from Phase 1.
            # This guarantees FAT block pointers match where data was actually written.
            layouts: list[SubfileLayout] = []

            for gmp_name, start_offset, data_size in gmp_actual:
                layout = SubfileLayout(
                    SubfileType.GMP, gmp_name, start_offset, data_size, block_size
                )
                layouts.append(layout)

            # MPS follows after the last GMP's aligned end
            last_end = layouts[-1].end_offset if layouts else data_start
            mps_layout = SubfileLayout(
                SubfileType.MPS, "MAPSOURC", last_end, MPS_SUBFILE_SIZE, block_size
            )
            layouts.append(mps_layout)

            # Verify FAT fits within reserved space
            fat_needed_entries = 1  # special directory
            for layout in layouts:
                fat_needed_entries += layout.num_fat_entries
            fat_needed_bytes = fat_needed_entries * PHYSICAL_BLOCK_SIZE
            if fat_needed_bytes > fat_reserved:
                raise ValueError(
                    f"FAT region overflow: need {fat_needed_bytes:,} bytes, "
                    f"reserved {fat_reserved:,} bytes"
                )

            # Update subfile headers
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

            # Write main header at offset 0
            f.seek(0)
            IMGHeaderWriter.write(f, img_file.header, layouts, block_exp_e2)

            # Write FAT entries at FAT_START
            f.seek(FAT_START)
            FATWriter.write(f, layouts, FAT_START)

            # Truncate file to actual end
            total_end = max(lay.end_offset for lay in layouts)
            f.seek(total_end - 1)
            f.write(b"\x00")
            f.truncate()

        actual_size = self.output_path.stat().st_size
        logger.info(f"IMG file written: {self.output_path} ({actual_size:,} bytes)")

    @staticmethod
    def _write_gmp_data(
        f: io.BufferedWriter,
        start_offset: int,
        img_file: IMGFile,
        subdivisions: list[Subdivision],
        tile_processor: Callable[[Path, int, int, int, str, int], ProcessedTile | None]
        | None,
        source_crs: str,
        jpeg_quality: int | None,
        progress_callback: Callable[[str, int, int], None] | None = None,
        tiles_offset: int = 0,
        sequential_only: bool = False,
    ) -> int:
        """Write GMP subfile with streaming LBL29 section.

        Returns the actual data size in bytes.
        """
        f.seek(start_offset)

        total_tiles = sum(len(sub.tile_entries) for sub in subdivisions)
        n_zoom = len(img_file.zoom_levels)
        now = img_file.gmp_creation_date or datetime.now()
        tre7_rec_size = 4  # IOM reference: uint32 offset only, no flag byte

        # --- Compute section layout (positions within GMP) ---
        copyright_str = img_file.copyright_string or "Copyright GARMIN."
        copyright_bytes = copyright_str.encode("cp1252") + b"\x00" + b"\x00"

        pos = 0
        pos += GMP_CONTAINER_HEADER_SIZE
        pos += len(copyright_bytes)

        tre_pos = pos
        pos += TRE_HEADER_LENGTH

        map_info = b"Raster Map\0" + copyright_str.encode("cp1252") + b"\x00"
        pos += len(map_info)

        rgn_pos = pos
        pos += RGN_HEADER_LENGTH

        lbl_pos = pos
        pos += LBL_HEADER_LENGTH

        net_pos = pos
        pos += NET_HEADER_LENGTH

        tre_copyright_pos = pos
        pos += 6

        tre_subdiv_pos = pos
        n_last = sum(1 for s in subdivisions if s.zoom_level_index == n_zoom - 1)
        n_non_last = len(subdivisions) - n_last
        subdiv_binary_size = n_non_last * 16 + n_last * 14 + 4
        pos += subdiv_binary_size

        tre_maplevels_pos = pos
        map_levels_size = n_zoom * 4
        pos += map_levels_size

        tre5_pos = pos
        tre5_size = 0  # IOM reference: no TRE5 data
        pos += tre5_size

        tre8_pos = pos
        tre8_size = 6  # Two entries: 06 06 13, 0D 06 01 (IOM reference)
        pos += tre8_size

        tre7_pos = pos
        tre7_size = (len(subdivisions) + 1) * tre7_rec_size  # +1 sentinel
        pos += tre7_size

        rgn1_pos = pos
        rgn1_size = 0

        rgn2_pos = pos
        rgn2_size = total_tiles * _rgn2_record_size(_img_id_size(total_tiles))
        pos += rgn2_size

        lbl_labels_pos = pos
        label_strings = bytearray()
        for i in range(total_tiles):
            label_strings += f"{i}.jpg\0".encode("ascii")
        pos += len(label_strings)

        lbl28_pos = pos
        lbl28_size = total_tiles * 4
        pos += lbl28_size

        lbl29_pos = pos
        # LBL29 size is unknown until streaming — use 0 as placeholder.
        # The actual value is fixed up after LBL29 data is written.
        estimated_lbl29_size = 0

        # --- Build subdivision binary data ---
        map_levels_data = bytearray(map_levels_size)
        subdiv_data = bytearray(subdiv_binary_size)

        # Fill TRE1 map levels
        subdiv_count_per_level: dict[int, int] = {}
        for sub in subdivisions:
            subdiv_count_per_level[sub.zoom_level_index] = (
                subdiv_count_per_level.get(sub.zoom_level_index, 0) + 1
            )
        for z_idx in range(n_zoom):
            map_levels_data[z_idx * 4] = img_file.zoom_levels[z_idx].zoom_code
            map_levels_data[z_idx * 4 + 1] = img_file.zoom_levels[z_idx].level_number
            struct.pack_into(
                "<H",
                map_levels_data,
                z_idx * 4 + 2,
                subdiv_count_per_level.get(z_idx, 1),
            )

        # Assign RGN2 offsets and fill TRE2 subdivision records
        rgn2_running_offset = 0
        rgn2_total_extent = 0
        record_size = _rgn2_record_size(_img_id_size(total_tiles))
        for sub in subdivisions:
            tile_count = sub.get_tile_count()
            if tile_count == 0:
                sub.rgn2_offset = 0
            else:
                sub.rgn2_offset = rgn2_running_offset
                chunk_size = tile_count * record_size
                rgn2_running_offset += chunk_size
                rgn2_total_extent = rgn2_running_offset

        zoom_shifts = {}
        for z_idx, zoom in enumerate(img_file.zoom_levels):
            zoom_shifts[z_idx] = max(0, 24 - zoom.level_number)

        # Determine the last subdivision index at each zoom level
        # (for setting the "end of chain" bit 15 on width)
        last_sub_at_level: dict[int, int] = {}
        for i, sub in enumerate(subdivisions):
            last_sub_at_level[sub.zoom_level_index] = i

        off = 0
        for i, sub in enumerate(subdivisions):
            is_last_level = sub.zoom_level_index == n_zoom - 1
            rec_size = 14 if is_last_level else 16
            shift = zoom_shifts.get(sub.zoom_level_index, 0)

            # RGN2 offset: lower 28 bits of uint32 (GPXSee reads readUInt32,
            # extracts offset as oo & 0xfffffff, upper 4 bits → objects)
            rgn2_offset_u32 = sub.rgn2_offset & 0x0FFFFFFF
            struct.pack_into("<I", subdiv_data, off, rgn2_offset_u32)
            lon_mu = int(sub.center_lon * (2**24) / 360)
            subdiv_data[off + 4 : off + 7] = _put3s(lon_mu)
            lat_mu = int(sub.center_lat * (2**24) / 360)
            subdiv_data[off + 7 : off + 10] = _put3s(lat_mu)
            # Width: encoded horizontal extent with bit 15 = end of chain
            w = sub.encode_tre2_width(shift)
            if not is_last_level and last_sub_at_level.get(sub.zoom_level_index) == i:
                w |= 0x8000  # bit 15 = end of chain
            struct.pack_into("<H", subdiv_data, off + 10, w)
            h = sub.encode_tre2_height(shift)
            struct.pack_into("<H", subdiv_data, off + 12, h)
            # Next level index (1-based, per mkgmap and PDF spec)
            # 0 = no children (SwissTopo reference uses next_level=0 for
            # childless subdivisions)
            if not is_last_level:
                nl = sub.next_level_index + 1 if sub.next_level_index > 0 else 0
                struct.pack_into("<H", subdiv_data, off + 14, nl)
            off += rec_size
        struct.pack_into("<I", subdiv_data, off, rgn2_total_extent)

        # --- Write all sections up to LBL28 ---

        # GMP Container Header
        gmp_header = bytearray(GMP_CONTAINER_HEADER_SIZE)
        gmp_header[0] = GMP_CONTAINER_HEADER_SIZE
        gmp_header[1] = 0x00
        gmp_header[2:12] = b"GARMIN GMP"
        struct.pack_into("<H", gmp_header, 12, 1)
        date_bytes = _encode_garmin_date_7(now)
        gmp_header[14:21] = date_bytes[:7]
        struct.pack_into("<I", gmp_header, 21, 0)
        struct.pack_into("<I", gmp_header, 25, tre_pos)
        struct.pack_into("<I", gmp_header, 29, rgn_pos)
        struct.pack_into("<I", gmp_header, 33, lbl_pos)
        struct.pack_into("<I", gmp_header, 37, net_pos)
        f.write(gmp_header)

        # Copyright strings
        f.write(copyright_bytes)

        # TRE Sub-Header
        tre_header = _build_tre_subheader(
            img_file,
            now,
            tre_copyright_pos,
            6,
            tre_subdiv_pos,
            subdiv_binary_size,
            tre_maplevels_pos,
            map_levels_size,
            tre5_pos,
            tre5_size,
            tre7_pos,
            tre7_size,
            tre7_rec_size,
            tre8_pos,
            tre8_size,
            rgn1_pos,
        )
        f.write(tre_header)

        # Map info strings
        f.write(map_info)

        # RGN Sub-Header
        rgn_header = _build_rgn_subheader(now, rgn1_pos, rgn1_size, rgn2_pos, rgn2_size)
        f.write(rgn_header)

        # LBL Sub-Header (with estimated lbl29_size — will fix up later)
        lbl_header = _build_lbl_subheader(
            now,
            lbl_labels_pos,
            len(label_strings),
            lbl28_pos,
            lbl28_size,
            lbl29_pos,
            estimated_lbl29_size,
        )
        # Remember the absolute file position of the LBL header for later fixup
        lbl_header_file_pos = f.tell()
        f.write(lbl_header)

        # NET Sub-Header
        net_header = _build_net_subheader(now)
        f.write(net_header)

        # TRE copyright data
        f.write(bytes([0x0C, 0x00, 0x00, 0x32, 0x00, 0x00]))

        # TRE subdivisions
        f.write(subdiv_data)

        # TRE map levels
        f.write(map_levels_data)

        # TRE5 data — IOM reference: no TRE5 data (size=0)
        # (no data written)

        # TRE8 data (6 bytes) — two entries matching IOM reference
        f.write(bytes([0x06, 0x06, 0x13, 0x0D, 0x06, 0x01]))

        # TRE7 data (uint32 per subdivision + sentinel with total RGN2 extent)
        for sub in subdivisions:
            f.write(struct.pack("<I", sub.rgn2_offset))
        # Sentinel: total RGN2 data extent (used by GPXSee for setExtEnds)
        f.write(
            struct.pack(
                "<I",
                total_tiles * _rgn2_record_size(_img_id_size(total_tiles)),
            )
        )

        # RGN2 data section (bounds from TileMetadata, no JPEG data needed)
        _write_rgn_data_section_subdivisions(f, subdivisions, total_tiles, img_file)

        # LBL labels
        f.write(label_strings)

        # --- LBL28: write placeholder (zeros) — will fix up after LBL29 ---
        lbl28_file_pos = f.tell()
        f.write(b"\x00" * lbl28_size)

        # --- LBL29: stream JPEG data from source files ---
        # Flatten tiles into an ordered list for batch processing
        all_tiles: list = []
        for sub in subdivisions:
            all_tiles.extend(sub.tile_entries)

        # Per-zoom progress tracking
        zoom_tile_counts: dict[int, int] = {}
        for tile_entry in all_tiles:
            if isinstance(tile_entry, TileMetadata):
                z = tile_entry.zoom
                zoom_tile_counts[z] = zoom_tile_counts.get(z, 0) + 1
        zoom_progress: dict[int, int] = {}

        # Determine parallelism: the standard parallel path uses _warp_tile_worker
        # which calls warp_tile_to_jpeg directly. For custom tile processors
        # (sequential_only), use ThreadPoolExecutor since they can't be pickled
        # for ProcessPoolExecutor but do release the GIL during warp/composite.
        use_parallel = tile_processor is not None and _get_worker_count() > 1
        max_workers = _get_worker_count() if use_parallel else 1
        # Smaller batches for custom processors to allow more frequent progress updates
        batch_size = 500 if sequential_only else StreamingIMGWriter.BATCH_SIZE

        # Create persistent executor (reused across all batches, not recreated)
        executor: Executor | None = None
        if use_parallel:
            # Custom tile processors must use threads (not picklable for processes)
            executor_mode = "thread" if sequential_only else _get_executor_mode()
            executor_cls = (
                ProcessPoolExecutor
                if executor_mode == "process"
                else ThreadPoolExecutor
            )
            init_fn = None if sequential_only else _init_worker
            executor = executor_cls(max_workers=max_workers, initializer=init_fn)
            logger.info(
                "LBL29 streaming: %d tiles, batch_size=%d, workers=%d (%s, persistent)",
                len(all_tiles),
                batch_size,
                max_workers,
                executor_mode,
            )
        else:
            logger.info(
                "LBL29 streaming: %d tiles, batch_size=%d (sequential)",
                len(all_tiles),
                batch_size,
            )

        actual_lbl29_size = 0
        lbl28_offsets: list[int] = []  # Accumulate offsets for fixup
        jpeg_sizes: list[int] = []  # Track actual JPEG sizes for RGN2 fixup
        running_offset = 0
        tiles_processed = 0

        try:
            for batch_start in range(0, len(all_tiles), batch_size):
                batch = all_tiles[batch_start : batch_start + batch_size]
                batch_jpegs: list[bytes] = [b""] * len(batch)

                if executor is not None:
                    # Parallel processing
                    future_to_idx: dict = {}
                    for i, tile_entry in enumerate(batch):
                        if isinstance(tile_entry, TileMetadata):
                            has_source = (
                                tile_entry.source_path is not None
                                and tile_entry.source_path.exists()
                            )
                            if sequential_only and tile_processor is not None:
                                # Custom processor: use _process_tile_jpeg
                                # which respects the tile_processor override.
                                # Submit even if source_path is missing — the
                                # custom processor may read from elsewhere
                                # (e.g. a GeoTIFF mosaic).
                                if has_source or tile_processor is not None:
                                    future = executor.submit(
                                        _process_tile_jpeg,
                                        tile_entry,
                                        tile_processor,
                                        source_crs,
                                        jpeg_quality,
                                    )
                                    future_to_idx[future] = i
                            elif has_source:
                                # Standard warp path
                                future = executor.submit(
                                    _warp_tile_worker,
                                    tile_entry.source_path,
                                    tile_entry.x,
                                    tile_entry.y,
                                    tile_entry.zoom,
                                    source_crs,
                                    "EPSG:4326",
                                    jpeg_quality,
                                )
                                future_to_idx[future] = i
                        elif isinstance(tile_entry, tuple):
                            batch_jpegs[i] = tile_entry[0]
                        else:
                            batch_jpegs[i] = tile_entry

                    batch_done = 0
                    for future in as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        try:
                            result = future.result()
                            if sequential_only:
                                # _process_tile_jpeg returns bytes | None
                                jpeg_data = result
                            else:
                                # _warp_tile_worker returns (x, y, zoom, bytes|None)
                                jpeg_data = result[3]
                            if jpeg_data is not None:
                                batch_jpegs[idx] = jpeg_data
                        except Exception as e:
                            logger.warning("Parallel tile warp failed: %s", e)
                        # Report progress as tiles complete
                        batch_done += 1
                        if progress_callback is not None and batch_done % 100 == 0:
                            progress_callback(
                                "writing",
                                tiles_offset + tiles_processed + batch_done,
                                total_tiles,
                            )
                else:
                    # Sequential processing
                    for i, tile_entry in enumerate(batch):
                        if isinstance(tile_entry, TileMetadata):
                            jpeg_data = _process_tile_jpeg(
                                tile_entry,
                                tile_processor,
                                source_crs,
                                jpeg_quality,
                            )
                            if jpeg_data is None:
                                logger.warning(
                                    "Failed to process tile (%d, %d, z=%d), skipping",
                                    tile_entry.x,
                                    tile_entry.y,
                                    tile_entry.zoom,
                                )
                                jpeg_data = b""
                            batch_jpegs[i] = jpeg_data
                        elif isinstance(tile_entry, tuple):
                            batch_jpegs[i] = tile_entry[0]
                        else:
                            batch_jpegs[i] = tile_entry

                # Write batch results sequentially (preserving order)
                for i, jpeg_data in enumerate(batch_jpegs):
                    lbl28_offsets.append(running_offset)
                    jpeg_sizes.append(len(jpeg_data))
                    actual_lbl29_size += len(jpeg_data)
                    running_offset += len(jpeg_data)
                    f.write(jpeg_data)
                    tiles_processed += 1

                    # Per-zoom progress reporting
                    tile_entry = batch[i]
                    if isinstance(tile_entry, TileMetadata):
                        z = tile_entry.zoom
                        zoom_progress[z] = zoom_progress.get(z, 0) + 1
                        if progress_callback is not None:
                            progress_callback(
                                f"writing:{z}",
                                zoom_progress[z],
                                zoom_tile_counts.get(z, 0),
                            )

                # Overall progress after each batch
                if progress_callback is not None:
                    progress_callback(
                        "writing", tiles_offset + tiles_processed, total_tiles
                    )

                if tiles_processed % 5000 == 0 or batch_start + batch_size >= len(
                    all_tiles
                ):
                    logger.info(
                        f"  LBL29: {tiles_processed}/{total_tiles} tiles streamed"
                    )
        finally:
            if executor is not None:
                executor.shutdown(wait=True)

        logger.info(
            f"  LBL29 complete: {tiles_processed} tiles, {actual_lbl29_size:,} bytes"
        )

        # --- Fix up LBL28 offsets (batched single write) ---
        f.seek(lbl28_file_pos)
        buf = bytearray(len(lbl28_offsets) * 4)
        for i, offset in enumerate(lbl28_offsets):
            if offset < 0 or offset > 0xFFFFFFFF:
                raise ValueError(
                    f"LBL28 offset out of range: {offset} (tile index {i})"
                )
            struct.pack_into("<I", buf, i * 4, offset)
        f.write(buf)

        # --- Fix up LBL header's lbl29_size ---
        # LBL header offset 0x196 (relative to LBL start) contains lbl29_size
        if actual_lbl29_size < 0 or actual_lbl29_size > 0xFFFFFFFF:
            raise ValueError(
                f"LBL29 size out of uint32 range: {actual_lbl29_size:,} bytes"
            )
        f.seek(lbl_header_file_pos + 0x196)
        f.write(struct.pack("<I", actual_lbl29_size))

        # Also update RGN2 records if jpeg_size changed (due to warping)
        # Only needed when a tile_processor is provided (actual warping may change sizes).
        # When no processor is used (raw file reads), sizes match TileMetadata.jpeg_size exactly.
        if tile_processor is not None:
            # Sizes may have changed — update RGN2 jpeg_size fields
            _fixup_rgn2_jpeg_sizes(
                f,
                subdivisions,
                img_file,
                jpeg_sizes,
                start_offset,
                rgn2_pos,
            )

        # Seek to end of actual data
        current_pos = lbl28_file_pos + lbl28_size + actual_lbl29_size
        logger.debug(
            f"  _write_gmp_data done: start=0x{start_offset:X}, "
            f"lbl28_file_pos=0x{lbl28_file_pos:X}, lbl28_size={lbl28_size}, "
            f"actual_lbl29_size={actual_lbl29_size:,}, "
            f"current_pos=0x{current_pos:X}, f.tell()=0x{f.tell():X}, "
            f"return_size={current_pos - start_offset:,}"
        )
        f.seek(current_pos)

        return current_pos - start_offset


def _reencode_jpeg(jpeg_bytes: bytes, quality: int) -> bytes:
    """Re-encode JPEG bytes at the specified quality level.

    Uses PIL (backed by libjpeg-turbo) for fast in-memory re-encoding.
    """
    img = Image.open(io.BytesIO(jpeg_bytes))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _estimate_quality_ratio(
    subdivisions: list[Subdivision],
    jpeg_quality: int | None,
    max_samples: int = 5,
    tile_processor: Callable[[Path, int, int, int, str, int], ProcessedTile | None]
    | None = None,
    source_crs: str = "EPSG:3857",
) -> float:
    """Estimate the JPEG size ratio when re-encoding at the target quality.

    When a tile_processor is provided (e.g. warp_tile_to_jpeg), samples are
    processed through the full pipeline (warp + re-encode) for an accurate
    ratio. Otherwise, a simple re-encode is used.

    Returns 1.0 if no samples can be taken or quality is None (passthrough).
    """
    if jpeg_quality is None:
        return 1.0

    samples: list[float] = []
    for sub in subdivisions:
        for tile_entry in sub.tile_entries:
            if len(samples) >= max_samples:
                break
            if (
                isinstance(tile_entry, TileMetadata)
                and tile_entry.source_path
                and tile_entry.source_path.exists()
            ):
                raw_size = tile_entry.source_path.stat().st_size
                if raw_size == 0:
                    continue
                if tile_processor is not None:
                    # Full pipeline: warp + re-encode
                    result = tile_processor(
                        tile_entry.source_path,
                        tile_entry.x,
                        tile_entry.y,
                        tile_entry.zoom,
                        source_crs,
                        jpeg_quality,
                    )
                    if result is not None:
                        samples.append(len(result[0]) / raw_size)
                else:
                    # Simple re-encode (no warp)
                    raw = tile_entry.source_path.read_bytes()
                    reencoded = _reencode_jpeg(raw, jpeg_quality)
                    if len(raw) > 0:
                        samples.append(len(reencoded) / len(raw))
        if len(samples) >= max_samples:
            break

    if not samples:
        logger.warning("No sample tiles found for quality ratio estimation, using 1.0")
        return 1.0

    samples.sort()
    ratio = samples[len(samples) // 2]  # median
    logger.info("Quality ratio estimate: %.3f (from %d samples)", ratio, len(samples))
    return ratio


def _process_tile_jpeg(
    tile: TileMetadata,
    tile_processor: Callable[[Path, int, int, int, str, int], ProcessedTile | None]
    | None,
    source_crs: str,
    jpeg_quality: int | None,
) -> bytes | None:
    """Get JPEG bytes for a tile from its source path.

    Args:
        tile: TileMetadata with source_path, x, y, zoom
        tile_processor: Optional processing callable
        source_crs: Source CRS string
        jpeg_quality: JPEG quality, or None for passthrough

    Returns:
        JPEG bytes, or None if processing failed
    """
    if tile_processor is not None:
        # Custom processor (e.g. composite blending): always call it,
        # regardless of jpeg_quality and source_path. The processor
        # reads from its own data sources (e.g. sub-layer caches).
        result = tile_processor(
            tile.source_path,
            tile.x,
            tile.y,
            tile.zoom,
            source_crs,
            jpeg_quality,
        )
        if result is not None:
            return result[0]  # (jpeg_bytes, bounds)
        return None

    if tile.source_path is None or not tile.source_path.exists():
        return None

    # No processor: read raw bytes
    if jpeg_quality is None:
        # Passthrough: return raw bytes without re-encoding
        return tile.source_path.read_bytes()

    # Re-encode at target quality
    raw = tile.source_path.read_bytes()
    return _reencode_jpeg(raw, jpeg_quality)


def _fixup_rgn2_jpeg_sizes(
    f: io.BufferedWriter,
    subdivisions: list[Subdivision],
    img_file: IMGFile,
    jpeg_sizes: list[int],
    gmp_start: int,
    rgn2_pos: int,
) -> None:
    """Update RGN2 record jpeg_size fields after actual JPEG sizes are known.

    Called only when a tile_processor is provided (warping may change sizes).
    Receives actual JPEG sizes tracked inline during LBL29 streaming.
    """
    iid_size = _img_id_size(sum(len(sub.tile_entries) for sub in subdivisions))
    record_size = _rgn2_record_size(iid_size)
    idx = 0
    offset = gmp_start + rgn2_pos

    for sub in subdivisions:
        for _tile_entry in sub.tile_entries:
            actual_size = jpeg_sizes[idx]

            if actual_size < 0 or actual_size > 0xFFFFFFFF:
                raise ValueError(
                    f"RGN2 jpeg_size out of range: {actual_size} (tile {idx})"
                )

            # jpeg_size is the last 4 bytes of the RGN2 record
            jpeg_size_offset = offset + record_size - 4
            f.seek(jpeg_size_offset)
            f.write(struct.pack("<I", actual_size))

            offset += record_size
            idx += 1


def _write_mps_data(f: io.BufferedWriter, img_file: IMGFile) -> None:
    """Write MPS subfile data at current file position.

    Standalone helper that writes the 98-byte MPS data without needing a layout.
    Used by the write-data-first approach.
    """
    buf = bytearray(MPS_SUBFILE_SIZE)
    buf[0x00:0x02] = b"LE"
    struct.pack_into("<I", buf, 7, img_file.map_id)
    map_name = img_file.header.map_name or "Raster Map"
    name_bytes = map_name.encode("ascii")[:21]
    name_slot = (name_bytes + b"\x00")[:22].ljust(22, b"\x00")
    buf[0x0B : 0x0B + 22] = name_slot
    hex_id = f"{img_file.map_id:08X}"[:8].encode("ascii")
    buf[0x21 : 0x21 + 8] = hex_id
    buf[0x29] = 0x00
    buf[0x2A : 0x2A + 22] = name_slot
    struct.pack_into("<I", buf, 0x40, img_file.map_id)
    struct.pack_into("<H", buf, 0x48, 0x1756)
    buf[0x4B : 0x4B + 22] = name_slot
    f.write(buf)


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

    def write(
        self,
        img_file: IMGFile,
        compressed_tiles: CompressedTiles,
        subdivisions: list[Subdivision] | None = None,
    ) -> None:
        """
        Write complete IMG file using two-pass layout.

        Args:
            img_file: IMGFile data structure to serialize
            compressed_tiles: Dict mapping zoom level to list of (jpeg_bytes, bounds) tuples or plain bytes
            subdivisions: Optional pre-computed subdivisions. If None, writes one per zoom level.
        """
        logger.info(f"Writing IMG file: {self.output_path}")

        # Pass 1: Compute layout
        computer = LayoutComputer(img_file, compressed_tiles, subdivisions=subdivisions)
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
            IMGHeaderWriter.write(f, img_file.header, layouts, computer.block_exp_e2)

            # Write FAT entries at FAT_START
            f.seek(FAT_START)
            FATWriter.write(f, layouts, FAT_START)

            # Write GMP subfile
            gmp_layout = next(
                lay for lay in layouts if lay.subfile_type == SubfileType.GMP
            )
            GMPWriter.write(
                f, img_file, compressed_tiles, gmp_layout, subdivisions=subdivisions
            )

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
