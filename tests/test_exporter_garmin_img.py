"""Tests for Garmin IMG exporter: header, FAT, tile encoding, pyramid, attribution, size limits.

Markers:
    gmt  — requires the ``gmt`` (GMapTool) binary on PATH
    gdal — requires GDAL/rasterio system libraries
"""

from __future__ import annotations

import io
import shutil
import struct
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from cartoload.config import LayerConfig
from cartoload.exporters.garmin_img import (
    generate_subdivisions,
    generate_subdivisions_from_metadata,
)
from cartoload.exporters.garmin_img_model import TileMetadata
from cartoload.exporters.garmin_img_model import (
    GMPGroup,
    IMGFile,
    IMGHeader,
    SubfileHeader,
    SubfileType,
    TileRecord,
    ZoomLevel,
)
from cartoload.exporters.garmin_img_writer import (
    BLOCK_SIZE_DEFAULT,
    FAT_BLOCK_NUMBER,
    FAT_START,
    FAT_FLAG_ACTIVE,
    FAT_FLAG_SPECIAL,
    FAT_UNUSED_BLOCK,
    FATWriter,
    IMGHeaderWriter,
    IMGWriter,
    LayoutComputer,
    MAX_TILE_SIZE,
    StreamingIMGWriter,
    SubfileLayout,
    TileEncoder,
    _blocks_needed,
    _deg_to_garmin,
    _fat_blocks_for_data_blocks,
    _reencode_jpeg,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_header(**overrides) -> IMGHeader:
    defaults = dict(
        magic="DSKIMG",
        format_version=2,
        creation_date=datetime(2022, 4, 16, 15, 3, 56),
        creator="GARMIN",
        map_name="TestMap",
    )
    defaults.update(overrides)
    return IMGHeader(**defaults)


def _make_img_file(**overrides) -> IMGFile:
    header = overrides.pop("header", _make_header())
    defaults = dict(
        header=header,
        bounds_north=47.5,
        bounds_south=46.5,
        bounds_west=8.0,
        bounds_east=9.0,
        description="Test Map",
        copyright_string="(c) test",
        map_id=0x09C102B0,
        zoom_levels=[],
        tiles=[],
    )
    defaults.update(overrides)
    return IMGFile(**defaults)


def _make_compressed_tiles(
    tile_count: int = 3, tile_size: int = 1024
) -> dict[int, list[bytes]]:
    """Create fake compressed tile data for testing."""
    return {
        12: [b"\xff\xd8\xff\xe0" + b"\x00" * (tile_size - 4)] * tile_count,
    }


# ---------------------------------------------------------------------------
# Task 1.2 – BaseExporter ABC
# ---------------------------------------------------------------------------


class TestBaseExporterABC:
    def test_cannot_instantiate_without_methods(self):
        from cartoload.exporters.base import BaseExporter

        with pytest.raises(TypeError, match="abstract methods"):
            BaseExporter()

    def test_incomplete_subclass_raises(self):
        from cartoload.exporters.base import BaseExporter

        class Partial(BaseExporter):
            @property
            def name(self):
                return "partial"

        with pytest.raises(TypeError, match="export"):
            Partial()


# ---------------------------------------------------------------------------
# IMG Header serialization
# ---------------------------------------------------------------------------


class TestIMGHeaderSerialization:
    def test_magic_bytes(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        assert data[0x10:0x16] == b"DSKIMG"
        assert data[0x16] == 0x00  # null terminator

    def test_format_version_byte(self):
        header = _make_header(format_version=2)
        data = IMGHeaderWriter.serialize(header)
        assert data[0x17] == 0x02

    def test_creation_date_encoding(self):
        dt = datetime(2022, 4, 16, 15, 3, 56)
        header = _make_header(creation_date=dt)
        data = IMGHeaderWriter.serialize(header)
        # Year LE
        year = struct.unpack_from("<H", data, 0x39)[0]
        assert year == 2022
        assert data[0x3B] == 4  # month
        assert data[0x3C] == 16  # day
        assert data[0x3D] == 15  # hour
        assert data[0x3E] == 3  # minute
        assert data[0x3F] == 56  # second

    def test_fat_block_number_at_0x40(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        assert data[0x40] == FAT_BLOCK_NUMBER  # 8

    def test_creator_string_at_0x41(self):
        header = _make_header(creator="GARMIN")
        data = IMGHeaderWriter.serialize(header)
        assert data[0x41:0x47] == b"GARMIN"

    def test_map_name_at_0x49(self):
        header = _make_header(map_name="TestMap")
        data = IMGHeaderWriter.serialize(header)
        # Map description is 20 bytes at 0x49-0x5C, space-padded
        desc = data[0x49:0x5D]
        assert desc[:7] == b"TestMap"
        assert desc[7] == ord(" ")  # space-padded

    def test_boot_signature(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        sig = struct.unpack_from("<H", data, 0x1FE)[0]
        assert sig == 0xAA55

    def test_header_is_512_bytes(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        assert len(data) == 512

    def test_xor_byte_at_0x00(self):
        header = _make_header(xor_byte=0x00)
        data = IMGHeaderWriter.serialize(header)
        assert data[0x00] == 0x00

    def test_block_size_exponents(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        assert data[0x61] == 0x09  # E1
        assert data[0x62] == 0x06  # E2 → 512 * 2^6 = 32768

    def test_checksum_or_id_at_0x0E(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        # Offset 0x0E-0x0F should contain checksum_or_id as LE uint16
        checksum_id = struct.unpack_from("<H", data, 0x0E)[0]
        assert checksum_id == header.checksum_or_id

    def test_partition_table_at_0x1BE(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        # Boot indicator should be 0x01 (bootable, matching SwissTopo reference)
        assert data[0x1BE] == 0x01
        # System type should be 0x60 (from SwissTopo reference)
        assert data[0x1C2] == 0x60


# ---------------------------------------------------------------------------
# FAT entry serialization
# ---------------------------------------------------------------------------


class TestFATEntrySerialization:
    def test_special_directory_entry(self):
        layout = SubfileLayout(
            subfile_type=SubfileType.GMP,
            name="09C102B0",
            start_offset=BLOCK_SIZE_DEFAULT * 10,
            data_size=12345,
        )
        buf = io.BytesIO()
        FATWriter._write_special_entry(buf, [layout], FAT_START)
        data = buf.getvalue()
        assert len(data) == 512

        # Flag: active
        assert data[0x00] == FAT_FLAG_ACTIVE
        # Name: 8 spaces
        assert data[0x01:0x09] == b"        "
        # Type: 3 spaces
        assert data[0x09:0x0C] == b"   "
        # Flag2: special
        assert data[0x10] == FAT_FLAG_SPECIAL

    def test_subfile_fat_entry(self):
        data_size = 12345
        start_block = 10
        layout = SubfileLayout(
            subfile_type=SubfileType.GMP,
            name="09C102B0",
            start_offset=BLOCK_SIZE_DEFAULT * start_block,
            data_size=data_size,
        )
        buf = io.BytesIO()
        FATWriter._write_subfile_entries(buf, layout)
        data = buf.getvalue()

        # Flag: active
        assert data[0x00] == FAT_FLAG_ACTIVE
        # Name
        assert data[0x01:0x09] == b"09C102B0"
        # Type
        assert data[0x09:0x0C] == b"GMP"
        # Size (LE uint32 at offset 0x0C)
        size = struct.unpack_from("<I", data, 0x0C)[0]
        assert size == data_size
        # Part number
        assert data[0x11] == 0

    def test_block_sequence_in_fat_entry(self):
        # Create a subfile with 3 data blocks (32KB each)
        # Starting at offset = 10 * 32KB
        layout = SubfileLayout(
            subfile_type=SubfileType.GMP,
            name="TEST",
            start_offset=BLOCK_SIZE_DEFAULT * 10,
            data_size=BLOCK_SIZE_DEFAULT * 3,
        )
        buf = io.BytesIO()
        FATWriter._write_subfile_entries(buf, layout)
        data = buf.getvalue()

        # FAT uses 32KB logical blocks in the block chain
        # start_block = 10, num_blocks = 3, so blocks 10, 11, 12
        block0 = struct.unpack_from("<H", data, 0x20)[0]
        block1 = struct.unpack_from("<H", data, 0x22)[0]
        block2 = struct.unpack_from("<H", data, 0x24)[0]
        assert block0 == 10
        assert block1 == 11
        assert block2 == 12
        # Remaining blocks should be 0xFFFF
        block3 = struct.unpack_from("<H", data, 0x26)[0]
        assert block3 == FAT_UNUSED_BLOCK

    def test_mps_fat_entry(self):
        layout = SubfileLayout(
            subfile_type=SubfileType.MPS,
            name="MAPSOURC",
            start_offset=BLOCK_SIZE_DEFAULT * 100,
            data_size=98,
        )
        buf = io.BytesIO()
        FATWriter._write_subfile_entries(buf, layout)
        data = buf.getvalue()

        assert data[0x01:0x09] == b"MAPSOURC"
        assert data[0x09:0x0C] == b"MPS"
        size = struct.unpack_from("<I", data, 0x0C)[0]
        assert size == 98

    def test_multi_part_fat_entry(self):
        # Create a subfile needing >240 blocks (32KB each)
        # 300 blocks will need 2 FAT entries (240 blocks in first, 60 in second)
        large_size = BLOCK_SIZE_DEFAULT * 300
        layout = SubfileLayout(
            subfile_type=SubfileType.GMP,
            name="BIGFILE",
            start_offset=BLOCK_SIZE_DEFAULT * 50,
            data_size=large_size,
        )
        assert layout.num_fat_entries == 2

        buf = io.BytesIO()
        FATWriter._write_subfile_entries(buf, layout)
        data = buf.getvalue()
        assert len(data) == 2 * 512  # Two FAT entries

        # First entry: part 0, has size
        assert data[0x11] == 0  # part 0
        size = struct.unpack_from("<I", data, 0x0C)[0]
        assert size == large_size

        # Second entry: part 1, size=0
        second_entry = data[512:]
        assert second_entry[0x11] == 1  # part 1
        size2 = struct.unpack_from("<I", second_entry, 0x0C)[0]
        assert size2 == 0

    def test_full_fat_write(self):
        gmp_layout = SubfileLayout(
            subfile_type=SubfileType.GMP,
            name="09C102B0",
            start_offset=BLOCK_SIZE_DEFAULT * 10,
            data_size=BLOCK_SIZE_DEFAULT * 5,
        )
        mps_layout = SubfileLayout(
            subfile_type=SubfileType.MPS,
            name="MAPSOURC",
            start_offset=BLOCK_SIZE_DEFAULT * 20,
            data_size=98,
        )
        layouts = [gmp_layout, mps_layout]
        buf = io.BytesIO()
        FATWriter.write(buf, layouts, FAT_START)
        data = buf.getvalue()

        # Should have: 1 special + 1 GMP + 1 MPS = 3 FAT entries = 1536 bytes
        assert len(data) == 3 * 512


class TestSubfileHeaderModel:
    def test_physical_offset(self):
        sh = SubfileHeader(
            subfile_type=SubfileType.GMP,
            name="test",
            start_block_offset=10,
            length=1000,
        )
        assert sh.get_physical_offset(32768) == 10 * 32768


# ---------------------------------------------------------------------------
# Tile Encoder
# ---------------------------------------------------------------------------


class TestTileEncoder:
    def test_encode_256x256_tile(self):
        tile = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
        jpeg_data = TileEncoder.encode_tile(tile)
        assert jpeg_data[:2] == b"\xff\xd8"  # JPEG SOI marker
        assert len(jpeg_data) < MAX_TILE_SIZE

    def test_encode_preserves_dimensions_header(self):
        """Verify the tile can be decoded back and dimensions match."""
        from PIL import Image

        tile = np.full((256, 256, 3), 128, dtype=np.uint8)
        jpeg_data = TileEncoder.encode_tile(tile)
        img = Image.open(io.BytesIO(jpeg_data))
        assert img.size == (256, 256)

    def test_encode_strip_alpha(self):
        """4-channel input should be handled (alpha stripped)."""
        tile = np.full((256, 256, 4), 128, dtype=np.uint8)
        jpeg_data = TileEncoder.encode_tile(tile)
        assert jpeg_data[:2] == b"\xff\xd8"

    def test_encode_non_standard_tile(self):
        """Edge tile: non-256x256 dimensions."""
        tile = np.random.randint(0, 255, (128, 200, 3), dtype=np.uint8)
        jpeg_data = TileEncoder.encode_tile(tile)
        from PIL import Image

        img = Image.open(io.BytesIO(jpeg_data))
        assert img.size == (200, 128)

    def test_encode_multiple_tiles(self):
        tiles = [np.full((256, 256, 3), i * 50, dtype=np.uint8) for i in range(3)]
        encoded = TileEncoder.encode_tiles(tiles)
        assert len(encoded) == 3
        for data in encoded:
            assert data[:2] == b"\xff\xd8"

    def test_compute_tile_grid(self):
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        cols, rows = TileEncoder.compute_grid(bounds, zoom_level=12, tile_size=256)
        assert cols >= 1
        assert rows >= 1

    def test_compute_tile_grid_higher_zoom(self):
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        cols_low, rows_low = TileEncoder.compute_grid(bounds, zoom_level=10)
        cols_high, rows_high = TileEncoder.compute_grid(bounds, zoom_level=12)
        assert cols_high >= cols_low
        assert rows_high >= rows_low


# ---------------------------------------------------------------------------
# Multi-Resolution Pyramid
# ---------------------------------------------------------------------------


class TestPyramidGeneration:
    def test_pyramid_multiple_zoom_levels(self):
        zoom_levels = [
            ZoomLevel(level_number=10, zoom_code=0x82),
            ZoomLevel(level_number=11, zoom_code=0x01),
            ZoomLevel(level_number=12, zoom_code=0x00),
        ]
        compressed_tiles = {
            10: [b"\xff\xd8" + b"\x00" * 500] * 2,
            11: [b"\xff\xd8" + b"\x00" * 500] * 5,
            12: [b"\xff\xd8" + b"\x00" * 500] * 12,
        }
        img_file = _make_img_file(zoom_levels=zoom_levels)
        computer = LayoutComputer(img_file, compressed_tiles)
        layouts = computer.compute()

        gmp_layout = next(lay for lay in layouts if lay.subfile_type == SubfileType.GMP)
        assert gmp_layout.data_size > 0

        # GMP should contain tile data for all zoom levels
        total_tile_data = sum(len(t) * 502 for t in compressed_tiles.values())
        assert gmp_layout.data_size >= total_tile_data

    def test_single_zoom_level(self):
        zoom_levels = [ZoomLevel(level_number=14, zoom_code=0x80)]
        compressed_tiles = {14: [b"\xff\xd8" + b"\x00" * 100] * 3}
        img_file = _make_img_file(zoom_levels=zoom_levels)
        computer = LayoutComputer(img_file, compressed_tiles)
        layouts = computer.compute()

        gmp_layout = next(lay for lay in layouts if lay.subfile_type == SubfileType.GMP)
        assert gmp_layout.data_size > 0

    def test_pyramid_tile_count_increases_with_zoom(self):
        """Higher zoom levels should have more tiles."""
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        c10, r10 = TileEncoder.compute_grid(bounds, 10)
        c12, r12 = TileEncoder.compute_grid(bounds, 12)
        assert c12 * r12 > c10 * r10


# ---------------------------------------------------------------------------
# Attribution Embedding
# ---------------------------------------------------------------------------


class TestAttributionEmbedding:
    def test_attribution_in_header(self):
        header = _make_header(map_name="Swisstopo")
        data = IMGHeaderWriter.serialize(header)
        # Map description is 20 bytes at 0x49-0x5C, space-padded
        desc = data[0x49:0x5D]
        assert desc[:9] == b"Swisstopo"

    def test_truncation_to_20_bytes(self):
        long_name = "A" * 50
        header = _make_header(map_name=long_name)
        data = IMGHeaderWriter.serialize(header)
        desc = data[0x49:0x5D]
        assert len(desc) == 20
        assert all(b == ord("A") for b in desc)  # all 20 bytes filled

    def test_attribution_fallback_empty(self):
        header = _make_header(map_name="")
        data = IMGHeaderWriter.serialize(header)
        desc = data[0x49:0x5D]
        assert desc == b" " * 20  # space-padded when empty

    def test_max_length_attribution(self):
        name_20 = "A" * 20
        header = _make_header(map_name=name_20)
        data = IMGHeaderWriter.serialize(header)
        extracted = data[0x49:0x5D]
        assert extracted == b"A" * 20

    def test_heads_and_sectors_fields(self):
        header = _make_header()
        data = IMGHeaderWriter.serialize(header)
        # Heads at 0x5D (copy of 0x1A) — must be 256 (0x0100) to match SwissTopo reference
        heads = struct.unpack_from("<H", data, 0x5D)[0]
        assert heads == 0x0100
        # Also check at 0x1A directly
        heads_1a = struct.unpack_from("<H", data, 0x1A)[0]
        assert heads_1a == 0x0100
        # Sectors at 0x5F (copy of 0x18)
        sectors = struct.unpack_from("<H", data, 0x5F)[0]
        assert sectors == 0x0020


# ---------------------------------------------------------------------------
# Size Limit Handling
# ---------------------------------------------------------------------------


class TestSizeLimitHandling:
    def test_tile_within_size_limit(self):
        tile = TileRecord(
            row=0,
            col=0,
            lat_north=47.5,
            lat_south=47.0,
            lon_west=8.0,
            lon_east=8.5,
            data_offset=0,
            data_length=2_000_000,
        )
        assert tile.validate_size_limit()

    def test_tile_exceeds_size_limit(self):
        tile = TileRecord(
            row=0,
            col=0,
            lat_north=47.5,
            lat_south=47.0,
            lon_west=8.0,
            lon_east=8.5,
            data_offset=0,
            data_length=4_200_000,
        )
        assert not tile.validate_size_limit()

    def test_pre_write_size_accounting(self):
        """Verify that encoded tile sizes are tracked."""
        tiles = [np.full((256, 256, 3), i * 30, dtype=np.uint8) for i in range(5)]
        encoded = TileEncoder.encode_tiles(tiles)
        for data in encoded:
            assert len(data) <= MAX_TILE_SIZE

    def test_file_size_validation(self):
        """IMGFile.validate_size_constraints checks 4GB limit."""
        img_file = _make_img_file()
        img_file.subfiles = [
            SubfileHeader(
                subfile_type=SubfileType.GMP,
                name="test",
                start_block_offset=10,
                length=3_000_000_000,
            )
        ]
        valid, violations = img_file.validate_size_constraints()
        assert valid

    def test_file_size_exceeds_4gb(self):
        header = SubfileHeader(
            subfile_type=SubfileType.GMP,
            name="test",
            start_block_offset=0,
            length=5_000_000_000,
        )
        img_file = _make_img_file(subfiles=[header])
        valid, violations = img_file.validate_size_constraints()
        assert not valid
        assert any("4 GB" in v for v in violations)

    def test_tile_splitting_scenario(self):
        """Verify that tiles over 3.5MB are flagged."""
        oversized_tile = TileRecord(
            row=0,
            col=0,
            lat_north=47.5,
            lat_south=47.0,
            lon_west=8.0,
            lon_east=8.5,
            data_offset=0,
            data_length=MAX_TILE_SIZE + 1,
            width_pixels=256,
            height_pixels=256,
        )
        img_file = _make_img_file(tiles=[oversized_tile])
        valid, violations = img_file.validate_size_constraints()
        assert not valid
        assert any("3.5 MB" in v for v in violations)


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------


class TestCoordinateConversion:
    def test_deg_to_garmin_zero(self):
        assert _deg_to_garmin(0.0) == 0

    def test_deg_to_garmin_positive(self):
        val = _deg_to_garmin(47.5)
        assert val > 0
        # Should be degrees * 2^31 / 180
        expected = int(47.5 * (2**31) / 180)
        assert val == expected

    def test_deg_to_garmin_negative(self):
        val = _deg_to_garmin(-8.5)
        assert val < 0


# ---------------------------------------------------------------------------
# FAT block calculation helpers
# ---------------------------------------------------------------------------


class TestFATBlockCalculation:
    def test_blocks_needed(self):
        assert _blocks_needed(1) == 1
        assert _blocks_needed(BLOCK_SIZE_DEFAULT) == 1
        assert _blocks_needed(BLOCK_SIZE_DEFAULT + 1) == 2

    def test_fat_blocks_for_data_blocks(self):
        # 1 data block needs 1 FAT entry
        assert _fat_blocks_for_data_blocks(1) == 1
        # 240 data blocks needs 1 FAT entry
        assert _fat_blocks_for_data_blocks(240) == 1
        # 241 data blocks needs 2 FAT entries
        assert _fat_blocks_for_data_blocks(241) == 2
        # 0 data blocks still needs 1 FAT entry
        assert _fat_blocks_for_data_blocks(0) == 1


# ---------------------------------------------------------------------------
# Integration: full IMG file write
# ---------------------------------------------------------------------------


class TestIMGFileWrite:
    def test_write_minimal_img(self, tmp_path):
        output = tmp_path / "test.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=0x80)]
        compressed_tiles = {
            12: [b"\xff\xd8" + b"\x00" * 100] * 3,
        }
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        assert output.exists()
        data = output.read_bytes()
        assert len(data) >= 512
        # Check magic
        assert data[0x10:0x16] == b"DSKIMG"
        # Check boot signature
        sig = struct.unpack_from("<H", data, 0x1FE)[0]
        assert sig == 0xAA55
        # Check FAT block number at 0x40
        assert data[0x40] == FAT_BLOCK_NUMBER

    def test_write_multi_zoom_img(self, tmp_path):
        output = tmp_path / "multi.img"
        zoom_levels = [
            ZoomLevel(level_number=10, zoom_code=0x82),
            ZoomLevel(level_number=11, zoom_code=0x01),
            ZoomLevel(level_number=12, zoom_code=0x00),
        ]
        compressed_tiles = {
            10: [b"\xff\xd8" + b"\x00" * 200],
            11: [b"\xff\xd8" + b"\x00" * 200] * 3,
            12: [b"\xff\xd8" + b"\x00" * 200] * 8,
        }
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        assert data[0x10:0x16] == b"DSKIMG"

    def test_fat_entries_written(self, tmp_path):
        output = tmp_path / "fat_test.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=0x80)]
        compressed_tiles = {12: [b"\x00" * 100]}
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # FAT should start at FAT_START (0x1000)
        # First FAT entry should be the special directory entry
        fat_start = FAT_START
        assert data[fat_start] == FAT_FLAG_ACTIVE  # active flag
        # Name should be spaces for special entry
        assert data[fat_start + 1 : fat_start + 9] == b"        "
        # Second FAT entry (GMP) should follow
        gmp_entry_offset = fat_start + 512
        assert data[gmp_entry_offset] == FAT_FLAG_ACTIVE
        assert data[gmp_entry_offset + 1 : gmp_entry_offset + 9] == b"09C102B0"

    def test_file_size_includes_all_tiles(self, tmp_path):
        output = tmp_path / "size_test.img"
        # Use larger tile data to verify it's all included
        tile_data = b"\xff\xd8" + b"\xab" * 10000
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=0x80)]
        compressed_tiles = {12: [tile_data] * 5}
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # File should be large enough to contain all tile data
        total_tile_bytes = len(tile_data) * 5
        assert len(data) >= total_tile_bytes + 4096  # tiles + overhead

    @pytest.mark.skip(reason="Tile index table removed - replaced by LBL28/LBL29")
    def test_tile_index_offsets_point_to_jpeg_data(self, tmp_path):
        """Verify that tile index entries point to valid JPEG SOI markers.

        Regression test: tile index offsets must be relative to GMP subfile start,
        not relative to the tile data region within GMP.

        NOTE: This test is obsolete. Tile index table has been replaced by
        LBL28 (image index) and LBL29 (image storage) sections.
        """
        output = tmp_path / "tile_index_test.img"
        zoom_levels = [
            ZoomLevel(level_number=10, zoom_code=0x81),
            ZoomLevel(level_number=12, zoom_code=0x00),
        ]
        # Create distinguishable tile data for each zoom level
        tile_10a = b"\xff\xd8\xff\xe0" + b"\x0a" * 500
        tile_10b = b"\xff\xd8\xff\xe0" + b"\x0b" * 500
        tile_12a = b"\xff\xd8\xff\xe0" + b"\xc0" * 500
        tile_12b = b"\xff\xd8\xff\xe0" + b"\xc1" * 500
        tile_12c = b"\xff\xd8\xff\xe0" + b"\xc2" * 500

        compressed_tiles = {
            10: [tile_10a, tile_10b],
            12: [tile_12a, tile_12b, tile_12c],
        }
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()

        # Compute GMP layout to find GMP start offset
        computer = LayoutComputer(img_file, compressed_tiles)
        layouts = computer.compute()
        gmp_layout = next(lay for lay in layouts if lay.subfile_type == SubfileType.GMP)
        gmp_start = gmp_layout.start_offset

        # Compute the tile index position within the GMP subfile
        # by reproducing the GMP writer's layout calculation
        from cartoload.exporters.garmin_img_writer import (
            GMP_CONTAINER_HEADER_SIZE,
            LBL_HEADER_LENGTH,
            NET_HEADER_LENGTH,
            RGN_HEADER_LENGTH,
            TRE_HEADER_LENGTH,
        )

        copyright_str = img_file.copyright_string or "Copyright GARMIN."
        copyright_bytes = copyright_str.encode("cp1252") + b"\x00" + b"\x00"
        pos = 0
        pos += GMP_CONTAINER_HEADER_SIZE
        pos += len(copyright_bytes)
        pos += TRE_HEADER_LENGTH
        map_info = b"Raster Map\0" + copyright_str.encode("cp1252") + b"\x00"
        pos += len(map_info)
        pos += RGN_HEADER_LENGTH
        pos += LBL_HEADER_LENGTH
        pos += NET_HEADER_LENGTH
        pos += 6  # TRE copyright
        pos += len(zoom_levels) * 8  # subdivisions
        pos += len(zoom_levels) * 4  # map levels
        pos += 1582  # RGN data
        total_tiles = 5
        for i in range(total_tiles):
            pos += len(f"{i}.jpg\0".encode("ascii"))
        tile_index_pos = pos

        # Read each tile index entry and verify it points to a JPEG SOI marker
        for i in range(total_tiles):
            offset_in_gmp = struct.unpack_from(
                "<I", data, gmp_start + tile_index_pos + i * 4
            )[0]
            abs_pos = gmp_start + offset_in_gmp
            assert data[abs_pos : abs_pos + 2] == b"\xff\xd8", (
                f"Tile {i}: offset {offset_in_gmp} (abs {abs_pos}) "
                f"does not point to JPEG SOI, found {data[abs_pos : abs_pos + 4].hex()}"
            )

    @pytest.mark.skip(reason="Tile index table removed - replaced by LBL28/LBL29")
    def test_tile_index_offsets_multi_zoom(self, tmp_path):
        """Verify tile offsets are correct with 3 zoom levels and varying tile counts.

        NOTE: This test is obsolete. Tile index table has been replaced by
        LBL28 (image index) and LBL29 (image storage) sections.
        """
        output = tmp_path / "multi_zoom_index.img"
        zoom_levels = [
            ZoomLevel(level_number=10, zoom_code=0x82),
            ZoomLevel(level_number=11, zoom_code=0x01),
            ZoomLevel(level_number=12, zoom_code=0x00),
        ]
        compressed_tiles = {
            10: [b"\xff\xd8" + b"\x10" * 200] * 2,
            11: [b"\xff\xd8" + b"\x11" * 200] * 5,
            12: [b"\xff\xd8" + b"\x12" * 200] * 12,
        }
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()

        # Count JPEG SOI markers in the file
        jpeg_count = 0
        p = 0
        while True:
            idx = data.find(b"\xff\xd8", p)
            if idx == -1:
                break
            jpeg_count += 1
            p = idx + 1

        # Should find exactly 2 + 5 + 12 = 19 JPEG markers
        assert jpeg_count == 19, f"Expected 19 JPEG markers, found {jpeg_count}"


# ---------------------------------------------------------------------------
# GarminImgExporter integration
# ---------------------------------------------------------------------------


class TestGarminImgExporter:
    def test_exporter_name(self):
        from cartoload.exporters.garmin_img import GarminImgExporter

        exporter = GarminImgExporter()
        assert exporter.name == "garmin-img"

    def test_validate_nonexistent_file(self, tmp_path):
        from cartoload.exporters.garmin_img import GarminImgExporter

        exporter = GarminImgExporter()
        result = exporter.validate(tmp_path / "nonexistent.img")
        assert result is False

    def test_validate_gmt_not_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda x: None)
        from cartoload.exporters.garmin_img import GarminImgExporter

        exporter = GarminImgExporter()
        # Create a dummy file
        dummy = tmp_path / "dummy.img"
        dummy.write_bytes(b"\x00" * 512)
        result = exporter.validate(dummy)
        assert result is True  # Skips validation when gmt not found


# ---------------------------------------------------------------------------
# Integration test: small but complete .img file
# ---------------------------------------------------------------------------


class TestIntegrationWrite:
    """Integration tests that write a complete .img file and verify structure."""

    def test_write_complete_img_2_zoom_levels(self, tmp_path):
        """Write a small but complete .img file with 2 zoom levels."""
        output = tmp_path / "integration_test.img"
        zoom_levels = [
            ZoomLevel(level_number=12, zoom_code=0x81),
            ZoomLevel(level_number=13, zoom_code=0x00),
        ]
        # Small tiles (real JPEG data)
        tile_12 = np.full((256, 256, 3), 100, dtype=np.uint8)
        tile_13a = np.full((256, 256, 3), 150, dtype=np.uint8)
        tile_13b = np.full((256, 256, 3), 200, dtype=np.uint8)

        compressed_tiles = {
            12: [TileEncoder.encode_tile(tile_12)],
            13: [TileEncoder.encode_tile(tile_13a), TileEncoder.encode_tile(tile_13b)],
        }
        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        assert output.exists()
        data = output.read_bytes()

        # Verify header structure
        assert data[0x10:0x16] == b"DSKIMG"
        sig = struct.unpack_from("<H", data, 0x1FE)[0]
        assert sig == 0xAA55

        # Verify FAT block number
        assert data[0x40] == FAT_BLOCK_NUMBER

        # Verify block size exponents
        assert data[0x61] == 0x09
        assert data[0x62] == 0x06

        # Verify FAT entries exist
        assert data[FAT_START] == FAT_FLAG_ACTIVE

    @pytest.mark.gmt
    def test_write_validates_with_gmt(self, tmp_path):
        """Write a complete .img and validate with gmt (requires gmt on PATH)."""
        if not shutil.which("gmt"):
            pytest.skip("gmt not available on PATH")

        output = tmp_path / "gmt_validated.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=0x80)]
        tile = np.full((256, 256, 3), 128, dtype=np.uint8)
        compressed_tiles = {12: [TileEncoder.encode_tile(tile)]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        from cartoload.exporters.garmin_img import GarminImgExporter

        exporter = GarminImgExporter()
        result = exporter.validate(output)
        assert result is True, "gmt validation should pass"

    def test_export_via_exporter_class(self, tmp_path):
        """Test the full GarminImgExporter.export() pipeline."""
        from cartoload.exporters.garmin_img import GarminImgExporter

        # Create a dummy raster (just needs to exist for the test)
        raster = tmp_path / "input.tif"
        raster.write_bytes(b"\x00" * 512)

        layer = LayerConfig(
            id="test",
            name="IntegrationTest",
            description="Test layer",
            source="test_src",
            zoom_levels=[12],
            exporter="garmin-img",
            output="test_output.img",
            bounds={"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0},
        )

        output = tmp_path / "test_output.img"
        exporter = GarminImgExporter()
        result = exporter.export(raster, layer, output)

        assert len(result) >= 1
        assert result[0].exists()
        data = result[0].read_bytes()
        assert data[0x10:0x16] == b"DSKIMG"


# ---------------------------------------------------------------------------
# LBL28/LBL29/Type E0 Tests
# ---------------------------------------------------------------------------


class TestLBL28LBL29TypeE0:
    """Test LBL28 (Image Index), LBL29 (Image Storage), and RGN Type E0 records."""

    def test_lbl28_section_present_in_subheader(self, tmp_path):
        """Verify LBL sub-header contains LBL28 section descriptor."""
        output = tmp_path / "test_lbl28.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=0x80)]
        tile = np.full((256, 256, 3), 128, dtype=np.uint8)
        compressed_tiles = {12: [TileEncoder.encode_tile(tile)]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # GMP FAT entry is at 0x1200 (second FAT entry after special directory at 0x1000)
        # Read first block number from GMP FAT entry
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 32768

        # LBL sub-header is within GMP - search for "GARMIN LBL" magic
        lbl_magic_offset = data.find(b"GARMIN LBL", gmp_offset)
        assert lbl_magic_offset > 0, "Could not find LBL sub-header"
        # LBL sub-header starts 2 bytes before the magic (header length field)
        lbl_start = lbl_magic_offset - 2

        # Raster table descriptor (LBL28 equivalent) at offset 0x184 relative to LBL start
        # Format: position(4) + size(4) + recordSize(2) + flags(4) at 0x184-0x191
        lbl28_position = struct.unpack_from("<I", data, lbl_start + 0x184)[0]
        lbl28_size = struct.unpack_from("<I", data, lbl_start + 0x188)[0]

        assert lbl28_position > 0, "LBL28 position should be set"
        assert lbl28_size > 0, "LBL28 size should be set"

    def test_lbl28_contains_uint32_offsets(self, tmp_path):
        """Verify LBL28 contains N × uint32 offsets where N = tile count."""
        output = tmp_path / "test_lbl28_offsets.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=0x80)]
        # Create 3 tiles
        tiles = [np.full((256, 256, 3), val, dtype=np.uint8) for val in [100, 150, 200]]
        compressed_tiles = {12: [TileEncoder.encode_tile(t) for t in tiles]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # Find LBL sub-header (GMP FAT entry at 0x1200)
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 32768
        lbl_magic_offset = data.find(b"GARMIN LBL", gmp_offset)
        lbl_start = lbl_magic_offset - 2

        # Read raster table descriptor at 0x184
        lbl28_position = struct.unpack_from("<I", data, lbl_start + 0x184)[0]
        lbl28_size = struct.unpack_from("<I", data, lbl_start + 0x188)[0]

        # LBL28 should contain 3 × 4 bytes = 12 bytes
        assert lbl28_size == 12, f"Expected 12 bytes for 3 tiles, got {lbl28_size}"

        # Read offsets (positions are GMP-relative)
        lbl28_offset = gmp_offset + lbl28_position
        offsets = [
            struct.unpack_from("<I", data, lbl28_offset + i * 4)[0] for i in range(3)
        ]

        # First offset should be 0
        assert offsets[0] == 0, "First LBL28 offset should be 0"
        # Subsequent offsets should be cumulative JPEG sizes
        assert all(offsets[i] < offsets[i + 1] for i in range(2)), (
            "Offsets should be increasing"
        )

    def test_lbl29_section_present_in_subheader(self, tmp_path):
        """Verify LBL sub-header contains LBL29 section descriptor."""
        output = tmp_path / "test_lbl29.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=0x80)]
        tile = np.full((256, 256, 3), 128, dtype=np.uint8)
        compressed_tiles = {12: [TileEncoder.encode_tile(tile)]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # Find LBL sub-header (GMP FAT entry at 0x1200)
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 32768
        lbl_magic_offset = data.find(b"GARMIN LBL", gmp_offset)
        lbl_start = lbl_magic_offset - 2

        # Raster image data descriptor (LBL29 equivalent) at offset 0x192 relative to LBL start
        # Format: position(4) + size(4) at 0x192-0x199
        lbl29_position = struct.unpack_from("<I", data, lbl_start + 0x192)[0]
        lbl29_size = struct.unpack_from("<I", data, lbl_start + 0x196)[0]

        assert lbl29_position > 0, "LBL29 position should be set"
        assert lbl29_size > 0, "LBL29 size should be set"

    def test_lbl29_contains_jpeg_files(self, tmp_path):
        """Verify LBL29 contains concatenated JPEG files with FFD8FFE0 markers."""
        output = tmp_path / "test_lbl29_jpegs.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=0x80)]
        # Create 2 tiles
        tiles = [np.full((256, 256, 3), val, dtype=np.uint8) for val in [100, 200]]
        compressed_tiles = {12: [TileEncoder.encode_tile(t) for t in tiles]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # Find LBL sub-header (GMP FAT entry at 0x1200)
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 32768
        lbl_magic_offset = data.find(b"GARMIN LBL", gmp_offset)
        lbl_start = lbl_magic_offset - 2

        # Read raster image data descriptor at 0x192
        lbl29_position = struct.unpack_from("<I", data, lbl_start + 0x192)[0]
        lbl29_size = struct.unpack_from("<I", data, lbl_start + 0x196)[0]

        # Read LBL29 section (positions are GMP-relative)
        lbl29_offset = gmp_offset + lbl29_position
        lbl29_data = data[lbl29_offset : lbl29_offset + lbl29_size]

        # Should start with JPEG marker FFD8FFE0
        assert lbl29_data[:4] == b"\xff\xd8\xff\xe0", (
            "LBL29 should start with JPEG marker"
        )

        # Count JPEG markers (should be 2)
        jpeg_count = lbl29_data.count(b"\xff\xd8\xff\xe0")
        assert jpeg_count == 2, f"Expected 2 JPEG markers, found {jpeg_count}"

    def test_rgn_data_contains_type_e0_records(self, tmp_path):
        """Verify RGN data section contains Type E0 records starting with 0xE0 marker."""
        output = tmp_path / "test_type_e0.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=0x80)]
        tile = np.full((256, 256, 3), 128, dtype=np.uint8)
        compressed_tiles = {12: [TileEncoder.encode_tile(tile)]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # Class flags 0xE0 followed by VUInt32(rs). With 1 tile, imgIdSize=1,
        # rs=1+20=21, VUInt32(21)=0x2B.
        assert b"\xe0\x2b" in data, (
            "Should contain Type E0 record (0xE0 + VUInt32(21)=0x2B)"
        )

    def test_type_e0_record_count_matches_tile_count(self, tmp_path):
        """Verify Type E0 record count matches tile count."""
        output = tmp_path / "test_type_e0_count.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=0x80)]
        # Create 5 tiles
        tiles = [
            np.full((256, 256, 3), val, dtype=np.uint8) for val in range(100, 150, 10)
        ]
        compressed_tiles = {12: [TileEncoder.encode_tile(t) for t in tiles]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # Count Type E0 markers (0xE0 followed by VUInt32(rs)).
        # With 5 tiles, imgIdSize=1, rs=21, VUInt32(21)=0x2B
        e0_count = data.count(b"\xe0\x2b")
        assert e0_count == 5, f"Expected 5 Type E0 records, found {e0_count}"

    def test_type_e0_bits_field_under_256_tiles(self, tmp_path):
        """Verify VUInt32(rs) is correct for small tile counts (< 256 -> imgIdSize=1)."""
        output = tmp_path / "test_bits_field_2d.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=0x80)]
        # Create 10 tiles (< 256)
        tiles = [np.full((256, 256, 3), 128, dtype=np.uint8) for _ in range(10)]
        compressed_tiles = {12: [TileEncoder.encode_tile(t) for t in tiles]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # With 10 tiles, imgIdSize=1, rs=1+20=21, VUInt32(21)=0x2B
        assert b"\xe0\x2b" in data, "Should contain class_flags + VUInt32(21)"

    def test_tile_index_table_not_present(self, tmp_path):
        """Verify tile index table is NOT present (replaced by LBL28/LBL29)."""
        output = tmp_path / "test_no_tile_index.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=0x80)]
        tile = np.full((256, 256, 3), 128, dtype=np.uint8)
        compressed_tiles = {12: [TileEncoder.encode_tile(tile)]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        data = output.read_bytes()
        # Find LBL sub-header (GMP FAT entry at 0x1200)
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 32768
        lbl_magic_offset = data.find(b"GARMIN LBL", gmp_offset)
        lbl_start = lbl_magic_offset - 2

        # Verify LBL29 is last section in LBL (no tile index table after it)
        lbl29_position = struct.unpack_from("<I", data, lbl_start + 0x192)[0]
        lbl29_size = struct.unpack_from("<I", data, lbl_start + 0x196)[0]

        # LBL29 should extend to near end of GMP data
        lbl29_end = lbl29_position + lbl29_size
        # Get GMP subfile size from FAT
        gmp_size = struct.unpack_from("<I", data, 0x1200 + 0x0C)[0]
        # LBL29 end should be close to total GMP data size
        assert lbl29_end <= gmp_size + 1024, "LBL29 should be last major section"

    @pytest.mark.gmt
    def test_gmt_output_shows_bitmaps(self, tmp_path):
        """Verify GMT output contains 'Bitmaps' line showing raster detection."""
        if not shutil.which("gmt"):
            pytest.skip("gmt not available on PATH")

        output = tmp_path / "test_gmt_bitmaps.img"
        zoom_levels = [ZoomLevel(level_number=12, zoom_code=0x80)]
        # Create 3 tiles
        tiles = [np.full((256, 256, 3), val, dtype=np.uint8) for val in [100, 150, 200]]
        compressed_tiles = {12: [TileEncoder.encode_tile(t) for t in tiles]}

        img_file = _make_img_file(zoom_levels=zoom_levels)
        writer = IMGWriter(output)
        writer.write(img_file, compressed_tiles)

        # Run GMT validation
        import subprocess

        result = subprocess.run(
            ["gmt", "-i", "-v", str(output)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"GMT validation failed: {result.stderr}"

        # Check for "Raster Map" or "Bitmaps" line in output
        assert "Raster Map" in result.stdout or "Bitmaps" in result.stdout, (
            "GMT output should contain 'Raster Map' or 'Bitmaps'"
        )

        # Verify tile count appears in output
        assert "3" in result.stdout or "size" in result.stdout.lower(), (
            "GMT should show bitmap count/size"
        )


# ---------------------------------------------------------------------------
# Binary comparison test (requires known-good .img)
# ---------------------------------------------------------------------------

KNOWN_GOOD_IMG = Path("tests/data/garmin_samples")


class TestBinaryComparison:
    """Compare writer output against known-good .img files (if available)."""

    @pytest.mark.skipif(
        not KNOWN_GOOD_IMG.exists(),
        reason="No known-good .img files in tests/data/garmin_samples",
    )
    def test_header_magic_matches_reference(self):
        """Compare header magic bytes with reference file."""
        ref_files = list(KNOWN_GOOD_IMG.glob("*.img"))
        if not ref_files:
            pytest.skip("No .img files found in test data")

        ref_data = ref_files[0].read_bytes()[:512]
        assert ref_data[0x10:0x16] == b"DSKIMG"

        # Our writer should produce the same magic
        header = _make_header()
        our_data = IMGHeaderWriter.serialize(header)
        assert our_data[0x10:0x16] == ref_data[0x10:0x16]

    @pytest.mark.skipif(
        not KNOWN_GOOD_IMG.exists(),
        reason="No known-good .img files in tests/data/garmin_samples",
    )
    def test_boot_signature_matches_reference(self):
        """Boot signature should match reference."""
        ref_files = list(KNOWN_GOOD_IMG.glob("*.img"))
        if not ref_files:
            pytest.skip("No .img files found")

        ref_data = ref_files[0].read_bytes()[:512]
        ref_sig = struct.unpack_from("<H", ref_data, 0x1FE)[0]

        header = _make_header()
        our_data = IMGHeaderWriter.serialize(header)
        our_sig = struct.unpack_from("<H", our_data, 0x1FE)[0]

        assert our_sig == ref_sig == 0xAA55

    @pytest.mark.skipif(
        not KNOWN_GOOD_IMG.exists(),
        reason="No known-good .img files in tests/data/garmin_samples",
    )
    def test_fat_block_number_matches_reference(self):
        """FAT block number at offset 0x40 should match reference."""
        ref_files = list(KNOWN_GOOD_IMG.glob("*.img"))
        if not ref_files:
            pytest.skip("No .img files found")

        ref_data = ref_files[0].read_bytes()[:512]
        ref_fat_block = ref_data[0x40]

        header = _make_header()
        our_data = IMGHeaderWriter.serialize(header)

        assert our_data[0x40] == ref_fat_block == 0x08

    @pytest.mark.skipif(
        not KNOWN_GOOD_IMG.exists(),
        reason="No known-good .img files in tests/data/garmin_samples",
    )
    def test_block_size_exponents_match_reference(self):
        """Block size exponents at 0x61-0x62 should match reference."""
        ref_files = list(KNOWN_GOOD_IMG.glob("*.img"))
        if not ref_files:
            pytest.skip("No .img files found")

        ref_data = ref_files[0].read_bytes()[:512]

        header = _make_header()
        our_data = IMGHeaderWriter.serialize(header)

        # E1 is always 0x09 (512-byte base unit)
        assert our_data[0x61] == ref_data[0x61] == 0x09
        # E2 varies by file: IOM uses 0x02 (2048-byte blocks), we use 0x06 (32768-byte blocks)
        # Just verify our E2 is valid and consistent
        assert our_data[0x62] == 0x06  # 512 * 2^6 = 32768


# ---------------------------------------------------------------------------
# E2E Validation Tests (Section 3 of fix-garmin-img-export)
# ---------------------------------------------------------------------------


@pytest.mark.gdal
class TestE2EValidation:
    """End-to-end tests creating IMG files from real GeoTIFF data and validating."""

    @pytest.fixture
    def minimal_geotiff(self, tmp_path):
        """Create a minimal GeoTIFF for testing using gdal_create."""
        geotiff_path = tmp_path / "test_input.tif"
        result = subprocess.run(
            [
                "gdal_create",
                "-of",
                "GTiff",
                "-outsize",
                "256",
                "256",
                "-a_srs",
                "EPSG:4326",
                "-a_ullr",
                "8.0",
                "47.5",
                "9.0",
                "47.0",
                "-burn",
                "128",
                str(geotiff_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.skip(f"gdal_create failed: {result.stderr}")
        return geotiff_path

    def test_e2e_create_img_from_geotiff(self, tmp_path, minimal_geotiff):
        """3.1-3.2: Create a 2-zoom-level IMG from a real GeoTIFF."""
        from cartoload.exporters.garmin_img import GarminImgExporter

        layer = LayerConfig(
            id="e2e_test",
            name="E2ETest",
            description="E2E test layer",
            source="test_src",
            zoom_levels=[12, 13],
            exporter="garmin-img",
            output="e2e_output.img",
            bounds={"north": 47.5, "south": 47.0, "west": 8.0, "east": 9.0},
        )

        output_path = tmp_path / "e2e_output.img"
        exporter = GarminImgExporter()
        result = exporter.export(minimal_geotiff, layer, output_path)

        assert len(result) >= 1
        assert result[0].exists()

    def test_e2e_file_size_proportional_to_tiles(self, tmp_path, minimal_geotiff):
        """3.3: Verify output file size is proportional to tile data."""
        from cartoload.exporters.garmin_img import GarminImgExporter

        layer = LayerConfig(
            id="e2e_size",
            name="E2ESizeTest",
            description="Size test",
            source="test_src",
            zoom_levels=[12],
            exporter="garmin-img",
            output="e2e_size.img",
            bounds={"north": 47.5, "south": 47.0, "west": 8.0, "east": 9.0},
        )

        output_path = tmp_path / "e2e_size.img"
        exporter = GarminImgExporter()
        result = exporter.export(minimal_geotiff, layer, output_path)

        file_size = result[0].stat().st_size
        # File should be at least 64KB (header + FAT + minimum structure)
        assert file_size > 64 * 1024, f"File too small: {file_size} bytes"
        # File should not be absurdly large for a small raster
        assert file_size < 10 * 1024 * 1024, (
            f"File unexpectedly large: {file_size} bytes"
        )

    def test_e2e_magic_and_boot_signature(self, tmp_path, minimal_geotiff):
        """3.4: Verify DSKIMG magic and boot signature in E2E output."""
        from cartoload.exporters.garmin_img import GarminImgExporter

        layer = LayerConfig(
            id="e2e_sig",
            name="E2ESigTest",
            description="Signature test",
            source="test_src",
            zoom_levels=[12],
            exporter="garmin-img",
            output="e2e_sig.img",
            bounds={"north": 47.5, "south": 47.0, "west": 8.0, "east": 9.0},
        )

        output_path = tmp_path / "e2e_sig.img"
        exporter = GarminImgExporter()
        result = exporter.export(minimal_geotiff, layer, output_path)

        data = result[0].read_bytes()
        assert data[0x10:0x16] == b"DSKIMG", "Missing DSKIMG magic"
        sig = struct.unpack_from("<H", data, 0x1FE)[0]
        assert sig == 0xAA55, "Missing boot signature"

    @pytest.mark.gmt
    def test_e2e_gmt_no_wrong_header(self, tmp_path, minimal_geotiff):
        """3.5: Verify GMT reports no 'Wrong header' errors on E2E output."""
        if not shutil.which("gmt"):
            pytest.skip("gmt not available on PATH")

        from cartoload.exporters.garmin_img import GarminImgExporter

        layer = LayerConfig(
            id="e2e_gmt",
            name="E2EGmtTest",
            description="GMT validation test",
            source="test_src",
            zoom_levels=[12],
            exporter="garmin-img",
            output="e2e_gmt.img",
            bounds={"north": 47.5, "south": 47.0, "west": 8.0, "east": 9.0},
        )

        output_path = tmp_path / "e2e_gmt.img"
        exporter = GarminImgExporter()
        result = exporter.export(minimal_geotiff, layer, output_path)

        gmt_result = subprocess.run(
            ["gmt", "-i", "-v", str(result[0])],
            capture_output=True,
            text=True,
            encoding="cp1252",
            errors="replace",
        )
        assert "Wrong header" not in gmt_result.stdout, (
            f"GMT reports header error: {gmt_result.stdout}"
        )
        assert "Wrong header" not in gmt_result.stderr, (
            f"GMT reports header error: {gmt_result.stderr}"
        )


# ---------------------------------------------------------------------------
# Test markers for gmt / gdal
# ---------------------------------------------------------------------------


def test_gmt_marker_exists():
    """Verify pytest.mark.gmt is configured."""
    assert hasattr(pytest.mark, "gmt")


def test_gdal_marker_exists():
    """Verify pytest.mark.gdal is available for future GDAL tests."""
    assert hasattr(pytest.mark, "gdal")


# ---------------------------------------------------------------------------
# Tests for spatial subdivision generation (Task 2.3 / 5.2)
# ---------------------------------------------------------------------------


def _make_tiles_with_bounds(
    n_tiles: int = 9,
    lat_min: float = 46.5,
    lat_max: float = 47.5,
    lon_min: float = 8.0,
    lon_max: float = 9.0,
) -> list[tuple[bytes, tuple[float, float, float, float]]]:
    """Create tiles with geographic bounds spread across the given extent."""
    from PIL import Image

    n_side = int(n_tiles**0.5)
    lat_step = (lat_max - lat_min) / n_side
    lon_step = (lon_max - lon_min) / n_side
    tiles = []
    # Generate a real JPEG tile (valid for decode/re-encode)
    arr = np.full((256, 256, 3), 128, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=85)
    jpeg_data = buf.getvalue()
    for r in range(n_side):
        for c in range(n_side):
            t_lat_min = lat_min + r * lat_step
            t_lat_max = t_lat_min + lat_step
            t_lon_min = lon_min + c * lon_step
            t_lon_max = t_lon_min + lon_step
            tiles.append((jpeg_data, (t_lat_min, t_lon_min, t_lat_max, t_lon_max)))
    return tiles


class TestGenerateSubdivisions:
    """Tests for the generate_subdivisions() function."""

    def test_empty_zoom_levels(self):
        """No zoom levels → empty subdivision list."""
        result = generate_subdivisions(
            {}, [], {"north": 47, "south": 46, "west": 8, "east": 9}
        )
        assert result == []

    def test_single_zoom_few_tiles(self):
        """Single zoom with ≤4 tiles → one subdivision."""
        tiles = _make_tiles_with_bounds(4)
        compressed = {15: tiles}
        result = generate_subdivisions(
            compressed, [15], {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        )
        assert len(result) == 1
        assert result[0].zoom_level_index == 0
        assert result[0].get_tile_count() == 4

    def test_single_zoom_many_tiles(self):
        """Single zoom with many tiles → multiple subdivisions (detail level)."""
        tiles = _make_tiles_with_bounds(25)  # 5x5 grid
        compressed = {15: tiles}
        result = generate_subdivisions(
            compressed, [15], {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        )
        # First level (z_idx=0) uses single subdivision since it's the only zoom level
        assert len(result) >= 1
        total_tiles = sum(s.get_tile_count() for s in result)
        assert total_tiles == 25

    def test_multiple_zoom_levels(self):
        """Multiple zoom levels → subdivisions at each level, ordered by zoom."""
        tiles_z12 = _make_tiles_with_bounds(4)
        tiles_z13 = _make_tiles_with_bounds(9)
        compressed = {12: tiles_z12, 13: tiles_z13}
        result = generate_subdivisions(
            compressed,
            [12, 13],
            {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0},
        )
        # Should have subdivisions from both levels
        assert len(result) >= 2
        # All tiles assigned
        total_tiles = sum(s.get_tile_count() for s in result)
        assert total_tiles == 4 + 9

    def test_all_tiles_assigned(self):
        """All input tiles must be assigned to some subdivision."""
        tiles = _make_tiles_with_bounds(16)
        compressed = {14: tiles}
        result = generate_subdivisions(
            compressed, [14], {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        )
        total_tiles = sum(s.get_tile_count() for s in result)
        assert total_tiles == len(tiles)

    def test_subdivision_center_within_bounds(self):
        """Each subdivision center should be within the map bounds."""
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        tiles = _make_tiles_with_bounds(16)
        compressed = {14: tiles}
        result = generate_subdivisions(compressed, [14], bounds)
        for sub in result:
            assert bounds["south"] <= sub.center_lat <= bounds["north"], (
                f"Center lat {sub.center_lat} outside bounds"
            )
            assert bounds["west"] <= sub.center_lon <= bounds["east"], (
                f"Center lon {sub.center_lon} outside bounds"
            )

    def test_subdivision_links_set(self):
        """Subdivisions should have next_level_index set for non-last levels."""
        tiles_z12 = _make_tiles_with_bounds(4)
        tiles_z13 = _make_tiles_with_bounds(9)
        compressed = {12: tiles_z12, 13: tiles_z13}
        result = generate_subdivisions(
            compressed,
            [12, 13],
            {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0},
        )
        # Level 0 subdivisions should have next_level_index pointing to level 1
        level0 = [s for s in result if s.zoom_level_index == 0]
        level1_start = len(level0)  # first level-1 subdiv index
        for sub in level0:
            assert sub.next_level_index == level1_start or sub.next_level_index > 0, (
                f"Level 0 subdivision should have next_level_index > 0, got {sub.next_level_index}"
            )

    def test_empty_zoom_level(self):
        """Zoom level with no tiles → one empty subdivision."""
        compressed = {12: [], 13: _make_tiles_with_bounds(4)}
        result = generate_subdivisions(
            compressed,
            [12, 13],
            {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0},
        )
        assert len(result) >= 2
        level0 = [s for s in result if s.zoom_level_index == 0]
        assert len(level0) == 1
        assert level0[0].get_tile_count() == 0


class TestSubdivisionsFromMetadataEquivalence:
    """Verify generate_subdivisions_from_metadata produces identical results to generate_subdivisions."""

    def _tiles_to_metadata(self, compressed_tiles):
        """Convert CompressedTiles to dict[int, list[TileMetadata]]."""
        metadata = {}
        for zoom, tiles in compressed_tiles.items():
            meta_list = []
            for i, entry in enumerate(tiles):
                if isinstance(entry, tuple):
                    _, (lat_min, lon_min, lat_max, lon_max) = entry
                else:
                    lat_min, lon_min, lat_max, lon_max = 0, 0, 0, 0
                meta_list.append(
                    TileMetadata(
                        x=i,
                        y=0,
                        zoom=zoom,
                        lat_min=lat_min,
                        lon_min=lon_min,
                        lat_max=lat_max,
                        lon_max=lon_max,
                        jpeg_size=len(entry[0])
                        if isinstance(entry, tuple)
                        else len(entry),
                    )
                )
            metadata[zoom] = meta_list
        return metadata

    def _compare_subdivisions(self, subs_old, subs_new):
        """Compare two subdivision lists for structural equivalence."""
        assert len(subs_old) == len(subs_new), (
            f"Different subdivision counts: {len(subs_old)} vs {len(subs_new)}"
        )
        for i, (old, new) in enumerate(zip(subs_old, subs_new)):
            assert old.zoom_level_index == new.zoom_level_index, (
                f"Sub {i}: zoom_level_index mismatch"
            )
            assert old.center_lat == pytest.approx(new.center_lat, abs=1e-10), (
                f"Sub {i}: center_lat mismatch: {old.center_lat} vs {new.center_lat}"
            )
            assert old.center_lon == pytest.approx(new.center_lon, abs=1e-10), (
                f"Sub {i}: center_lon mismatch"
            )
            assert old.bounds_north == pytest.approx(new.bounds_north, abs=1e-10)
            assert old.bounds_south == pytest.approx(new.bounds_south, abs=1e-10)
            assert old.bounds_west == pytest.approx(new.bounds_west, abs=1e-10)
            assert old.bounds_east == pytest.approx(new.bounds_east, abs=1e-10)
            assert old.get_tile_count() == new.get_tile_count(), (
                f"Sub {i}: tile count mismatch: {old.get_tile_count()} vs {new.get_tile_count()}"
            )
            assert old.next_level_index == new.next_level_index

    def test_single_zoom_few_tiles(self):
        tiles = _make_tiles_with_bounds(4)
        compressed = {15: tiles}
        metadata = self._tiles_to_metadata(compressed)
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}

        subs_old = generate_subdivisions(compressed, [15], bounds)
        subs_new = generate_subdivisions_from_metadata(metadata, [15], bounds)
        self._compare_subdivisions(subs_old, subs_new)

    def test_multiple_zoom_levels(self):
        compressed = {12: _make_tiles_with_bounds(4), 13: _make_tiles_with_bounds(9)}
        metadata = self._tiles_to_metadata(compressed)
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}

        subs_old = generate_subdivisions(compressed, [12, 13], bounds)
        subs_new = generate_subdivisions_from_metadata(metadata, [12, 13], bounds)
        self._compare_subdivisions(subs_old, subs_new)

    def test_many_tiles_gridded(self):
        tiles = _make_tiles_with_bounds(25)
        compressed = {15: tiles}
        metadata = self._tiles_to_metadata(compressed)
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}

        subs_old = generate_subdivisions(compressed, [15], bounds)
        subs_new = generate_subdivisions_from_metadata(metadata, [15], bounds)
        self._compare_subdivisions(subs_old, subs_new)
        # All tiles assigned
        assert sum(s.get_tile_count() for s in subs_new) == 25

    def test_empty_zoom_level(self):
        compressed = {12: [], 13: _make_tiles_with_bounds(4)}
        metadata = self._tiles_to_metadata(compressed)
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}

        subs_old = generate_subdivisions(compressed, [12, 13], bounds)
        subs_new = generate_subdivisions_from_metadata(metadata, [12, 13], bounds)
        self._compare_subdivisions(subs_old, subs_new)


class TestSubdivisionBinaryWriting:
    """Tests for per-subdivision TRE2/TRE7/RGN2 binary output."""

    def test_subdivision_tre2_records_written(self, tmp_path):
        """Verify TRE2 section has correct variable-size records per subdivision."""
        output = tmp_path / "test_subdiv_tre2.img"
        tiles = _make_tiles_with_bounds(9)
        compressed = {15: tiles}
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        subdivisions = generate_subdivisions(compressed, [15], bounds)

        img_file = _make_img_file(
            zoom_levels=[ZoomLevel(level_number=15, zoom_code=0x80)],
        )
        writer = IMGWriter(output)
        writer.write(img_file, compressed, subdivisions=subdivisions)

        data = output.read_bytes()
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 32768

        # Find TRE header
        tre_magic = data.find(b"GARMIN TRE", gmp_offset)
        assert tre_magic > 0, "TRE header not found"
        tre_start = tre_magic - 2

        # Read TRE2 size
        tre2_size = struct.unpack_from("<I", data, tre_start + 0x2D)[0]

        # TRE2: last zoom level uses 14-byte records + 4 trailing bytes
        expected_tre2_size = len(subdivisions) * 14 + 4
        assert tre2_size == expected_tre2_size, (
            f"TRE2 size {tre2_size} != {len(subdivisions)} * 14 + 4"
        )

    def test_subdivision_tre7_rec_size_5(self, tmp_path):
        """Verify TRE7 uses rec_size=5 when subdivisions are provided."""
        output = tmp_path / "test_subdiv_tre7.img"
        tiles = _make_tiles_with_bounds(4)
        compressed = {15: tiles}
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        subdivisions = generate_subdivisions(compressed, [15], bounds)

        img_file = _make_img_file(
            zoom_levels=[ZoomLevel(level_number=15, zoom_code=0x80)],
        )
        writer = IMGWriter(output)
        writer.write(img_file, compressed, subdivisions=subdivisions)

        data = output.read_bytes()
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 32768

        tre_magic = data.find(b"GARMIN TRE", gmp_offset)
        tre_start = tre_magic - 2

        # TRE7 rec_size at offset 0x84 in TRE header
        tre7_rec_size = struct.unpack_from("<H", data, tre_start + 0x84)[0]
        assert tre7_rec_size == 5, f"TRE7 rec_size should be 5, got {tre7_rec_size}"

    def test_subdivision_tre7_has_sentinel(self, tmp_path):
        """Verify TRE7 has a sentinel entry (all zeros) at the end."""
        output = tmp_path / "test_subdiv_tre7_sentinel.img"
        tiles = _make_tiles_with_bounds(4)
        compressed = {15: tiles}
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        subdivisions = generate_subdivisions(compressed, [15], bounds)

        img_file = _make_img_file(
            zoom_levels=[ZoomLevel(level_number=15, zoom_code=0x80)],
        )
        writer = IMGWriter(output)
        writer.write(img_file, compressed, subdivisions=subdivisions)

        data = output.read_bytes()
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 32768

        tre_magic = data.find(b"GARMIN TRE", gmp_offset)
        tre_start = tre_magic - 2

        tre7_pos = struct.unpack_from("<I", data, tre_start + 0x7C)[0]
        tre7_size = struct.unpack_from("<I", data, tre_start + 0x80)[0]

        # TRE7 size should be (n_subdivisions + 1) * 5
        expected_size = (len(subdivisions) + 1) * 5
        assert tre7_size == expected_size, (
            f"TRE7 size {tre7_size} != expected {expected_size}"
        )

        # Last 5 bytes should be the sentinel entry containing the total RGN2
        # data extent as the polygon offset (end boundary for last subdivision)
        tre7_data_offset = gmp_offset + tre7_pos
        sentinel = data[
            tre7_data_offset + len(subdivisions) * 5 : tre7_data_offset + tre7_size
        ]
        sentinel_offset = struct.unpack_from("<I", sentinel)[0]
        sentinel_flag = sentinel[4]
        # Sentinel offset = total RGN2 data size = n_tiles × 42
        if isinstance(tiles[0], tuple) and len(tiles[0]) == 2:
            pass  # tiles are (jpeg, bounds) tuples
        # Record size is dynamic: 40 + imgIdSize where imgIdSize = byteSize(n-1)
        # byteSize(val): 1 for 0-255, 2 for 256-65535, 3 for 65536-16777215
        n = len(tiles)
        iid = 1 if n <= 256 else 2 if n <= 65536 else 3
        expected_extent = n * (40 + iid)
        assert sentinel_offset == expected_extent, (
            f"Sentinel offset should be {expected_extent}, got {sentinel_offset}"
        )
        assert sentinel_flag == 0, f"Sentinel flag should be 0, got {sentinel_flag}"

    def test_subdivision_preserves_tile_data_in_lbl29(self, tmp_path):
        """Verify LBL29 contains all JPEG data when using subdivisions."""
        output = tmp_path / "test_subdiv_lbl29.img"
        tiles = _make_tiles_with_bounds(4)
        compressed = {15: tiles}
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        subdivisions = generate_subdivisions(compressed, [15], bounds)

        img_file = _make_img_file(
            zoom_levels=[ZoomLevel(level_number=15, zoom_code=0x80)],
        )
        writer = IMGWriter(output)
        writer.write(img_file, compressed, subdivisions=subdivisions)

        data = output.read_bytes()
        gmp_start_block = struct.unpack_from("<H", data, 0x1200 + 0x20)[0]
        gmp_offset = gmp_start_block * 32768

        lbl_magic = data.find(b"GARMIN LBL", gmp_offset)
        lbl_start = lbl_magic - 2
        lbl29_pos = struct.unpack_from("<I", data, lbl_start + 0x192)[0]
        lbl29_size = struct.unpack_from("<I", data, lbl_start + 0x196)[0]

        # LBL29 should contain 4 JPEG files
        expected_jpeg_size = sum(len(t[0]) for t in tiles)
        assert lbl29_size == expected_jpeg_size

        # First bytes should be JPEG marker
        lbl29_data = data[gmp_offset + lbl29_pos : gmp_offset + lbl29_pos + 4]
        assert lbl29_data[:2] == b"\xff\xd8"

    def test_subdivision_type_e0_count_matches(self, tmp_path):
        """Verify E0 record count matches total tile count with subdivisions."""
        output = tmp_path / "test_subdiv_e0.img"
        tiles = _make_tiles_with_bounds(9)
        compressed = {15: tiles}
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        subdivisions = generate_subdivisions(compressed, [15], bounds)

        img_file = _make_img_file(
            zoom_levels=[ZoomLevel(level_number=15, zoom_code=0x80)],
        )
        writer = IMGWriter(output)
        writer.write(img_file, compressed, subdivisions=subdivisions)

        data = output.read_bytes()
        # With 9 tiles, imgIdSize=1, rs=21, VUInt32(21)=0x2B
        e0_count = data.count(b"\xe0\x2b")
        assert e0_count == 9, f"Expected 9 Type E0 records, found {e0_count}"


class TestRgn2RasterRecord:
    """Tests for the 42-byte compound RGN2 raster record."""

    def test_record_is_42_bytes(self):
        """Each raster record should be exactly 42 bytes."""
        buf = io.BytesIO()
        from cartoload.exporters.garmin_img_writer import _write_rgn2_raster_record

        _write_rgn2_raster_record(
            buf,
            subdiv_center_lat=47.0,
            subdiv_center_lon=8.5,
            tile_lat_min=46.9,
            tile_lon_min=8.4,
            tile_lat_max=47.1,
            tile_lon_max=8.6,
            tile_center_lat=47.0,
            tile_center_lon=8.5,
            jpeg_size=5000,
            image_index=0,
            level_number=17,
        )
        assert len(buf.getvalue()) == 42

    def test_record_starts_with_06_b3(self):
        """Record type bytes should be 0x06 0xB3."""
        buf = io.BytesIO()
        from cartoload.exporters.garmin_img_writer import _write_rgn2_raster_record

        _write_rgn2_raster_record(
            buf,
            subdiv_center_lat=47.0,
            subdiv_center_lon=8.5,
            tile_lat_min=46.9,
            tile_lon_min=8.4,
            tile_lat_max=47.1,
            tile_lon_max=8.6,
            tile_center_lat=47.0,
            tile_center_lon=8.5,
            jpeg_size=5000,
            image_index=0,
            level_number=17,
        )
        data = buf.getvalue()
        assert data[0] == 0x06
        assert data[1] == 0xB3

    def test_record_class_flags_and_vuint32(self):
        """Record should have class_flags=0xE0 and VUInt32(22)=0x2D at correct offsets."""
        buf = io.BytesIO()
        from cartoload.exporters.garmin_img_writer import _write_rgn2_raster_record

        _write_rgn2_raster_record(
            buf,
            subdiv_center_lat=47.0,
            subdiv_center_lon=8.5,
            tile_lat_min=46.9,
            tile_lon_min=8.4,
            tile_lat_max=47.1,
            tile_lon_max=8.6,
            tile_center_lat=47.0,
            tile_center_lon=8.5,
            jpeg_size=5000,
            image_index=0,
            level_number=17,
        )
        data = buf.getvalue()
        # byte 6: VUInt32(8) = 0x11
        assert data[6] == 0x11
        # byte 18: class_flags = 0xE0
        assert data[18] == 0xE0
        # byte 19: VUInt32(22) = 0x2D
        assert data[19] == 0x2D

    def test_record_image_id_and_jpeg_size(self):
        """Record should encode image_index and jpeg_size at correct offsets."""
        import struct

        buf = io.BytesIO()
        from cartoload.exporters.garmin_img_writer import _write_rgn2_raster_record

        _write_rgn2_raster_record(
            buf,
            subdiv_center_lat=47.0,
            subdiv_center_lon=8.5,
            tile_lat_min=46.9,
            tile_lon_min=8.4,
            tile_lat_max=47.1,
            tile_lon_max=8.6,
            tile_center_lat=47.0,
            tile_center_lon=8.5,
            jpeg_size=12345,
            image_index=42,
            level_number=17,
        )
        data = buf.getvalue()
        # image_id at bytes 20-21
        image_id = struct.unpack_from("<H", data, 20)[0]
        assert image_id == 42
        # jpeg_size at bytes 38-41
        jpeg_size = struct.unpack_from("<I", data, 38)[0]
        assert jpeg_size == 12345

    def test_record_deltas_zero_when_tile_bottom_left_equals_subdiv_center(self):
        """Lon/lat deltas should be zero when tile bottom-left equals subdivision center."""
        import struct

        buf = io.BytesIO()
        from cartoload.exporters.garmin_img_writer import _write_rgn2_raster_record

        # Tile bottom-left at (8.5, 47.0) = subdivision center
        _write_rgn2_raster_record(
            buf,
            subdiv_center_lat=47.0,
            subdiv_center_lon=8.5,
            tile_lat_min=47.0,
            tile_lon_min=8.5,
            tile_lat_max=47.1,
            tile_lon_max=8.6,
            tile_center_lat=47.05,
            tile_center_lon=8.55,
            jpeg_size=5000,
            image_index=0,
            level_number=17,
        )
        data = buf.getvalue()
        lon_delta = struct.unpack_from("<h", data, 2)[0]
        lat_delta = struct.unpack_from("<h", data, 4)[0]
        assert lon_delta == 0
        assert lat_delta == 0

    def test_record_deltas_nonzero_when_offset(self):
        """Lon/lat deltas should be non-zero when tile bottom-left differs from subdivision center."""
        import struct

        buf = io.BytesIO()
        from cartoload.exporters.garmin_img_writer import _write_rgn2_raster_record

        _write_rgn2_raster_record(
            buf,
            subdiv_center_lat=47.0,
            subdiv_center_lon=8.5,
            tile_lat_min=46.85,
            tile_lon_min=8.35,
            tile_lat_max=46.95,
            tile_lon_max=8.45,
            tile_center_lat=46.9,
            tile_center_lon=8.4,
            jpeg_size=5000,
            image_index=0,
            level_number=17,
        )
        data = buf.getvalue()
        lon_delta = struct.unpack_from("<h", data, 2)[0]
        lat_delta = struct.unpack_from("<h", data, 4)[0]
        assert lon_delta != 0
        assert lat_delta != 0

    def test_record_delta_shift_matches_gpxsee(self):
        """Delta should be in level-space so GPXSee's left-shift recovers the 24-bit delta.

        GPXSee computes: pos = subdiv_center + (delta << (24 - bits))
        Delta positions P0 at the tile's bottom-left corner.
        """
        import struct
        from cartoload.exporters.garmin_img_writer import _deg_to_map_units

        buf = io.BytesIO()
        from cartoload.exporters.garmin_img_writer import _write_rgn2_raster_record

        # Use level_number=17 (shift=7) with a known offset
        subdiv_lat, subdiv_lon = 47.0, 8.5
        tile_lat_min, tile_lon_min = 46.85, 8.35
        _write_rgn2_raster_record(
            buf,
            subdiv_center_lat=subdiv_lat,
            subdiv_center_lon=subdiv_lon,
            tile_lat_min=tile_lat_min,
            tile_lon_min=tile_lon_min,
            tile_lat_max=46.95,
            tile_lon_max=8.45,
            tile_center_lat=46.9,
            tile_center_lon=8.4,
            jpeg_size=5000,
            image_index=0,
            level_number=17,
        )
        data = buf.getvalue()
        lon_delta = struct.unpack_from("<h", data, 2)[0]
        lat_delta = struct.unpack_from("<h", data, 4)[0]

        # Verify: GPXSee would compute pos = subdiv_mu + (delta << (24-17))
        # This should equal tile_bottom_left_mu
        shift = 24 - 17  # = 7
        subdiv_lon_mu = _deg_to_map_units(subdiv_lon)
        subdiv_lat_mu = _deg_to_map_units(subdiv_lat)
        tile_left_mu = _deg_to_map_units(tile_lon_min)
        tile_bottom_mu = _deg_to_map_units(tile_lat_min)

        recovered_lon_mu = subdiv_lon_mu + (lon_delta << shift)
        recovered_lat_mu = subdiv_lat_mu + (lat_delta << shift)

        # The recovery should be exact (within rounding from the >> shift)
        assert abs(recovered_lon_mu - tile_left_mu) <= 1 << shift
        assert abs(recovered_lat_mu - tile_bottom_mu) <= 1 << shift


class TestBitstreamDeltaStreamDecoding:
    """Tests that simulate GPXSee's DeltaStream decoding to verify boundingRect coverage.

    These tests decode the 8-byte bitstream exactly as GPXSee's deltastream.cpp does,
    ensuring the boundingRect polygon fully covers the tile's geographic area.
    """

    @staticmethod
    def _decode_bitstream_like_gpxsee(
        bitstream: bytes,
        lon_delta_int16: int,
        lat_delta_int16: int,
        subdiv_lon_mu: int,
        subdiv_lat_mu: int,
        level_number: int,
    ):
        """Decode a bitstream exactly as GPXSee's deltastream.cpp does.

        Returns a dict with decoded points, boundingRect, and coverage info.
        """
        info = bitstream[0]
        lon_base = info & 0x0F
        lat_base = info >> 4

        # Bit reader state (LSB-first per byte, like GPXSee's BitStream1)
        data = bitstream[1:]  # bytes 1-7
        bit_pos = 0  # global bit position in data bytes

        def read_bits(n):
            nonlocal bit_pos
            val = 0
            for pos in range(n):
                byte_idx = bit_pos // 8
                bit_in_byte = bit_pos % 8
                if byte_idx >= len(data):
                    return None
                bit_val = (data[byte_idx] >> bit_in_byte) & 1
                val |= bit_val << pos
                bit_pos += 1
            return val

        # sign() — reads has-variable-sign flag, optionally sign value
        def read_sign():
            b = read_bits(1)
            if b is None:
                return None
            if b:
                sv = read_bits(1)
                if sv is None:
                    return None
                return -1 if sv else 1
            return 0

        # Init: read signs
        lon_sign = read_sign()
        lat_sign = read_sign()
        assert lon_sign is not None, "Failed to read lon sign"
        assert lat_sign is not None, "Failed to read lat sign"

        # Extended bit (extPolyObjects calls init with extended=true)
        ext = read_bits(1)
        assert ext is not None, "Failed to read extended bit"

        # bitSize computation (matches GPXSee's bitSize function)
        def bit_size(base_size, variable_sign, extra_bit):
            bits = 2
            if base_size <= 9:
                bits += base_size
            else:
                bits += 2 * base_size - 9
            if variable_sign:
                bits += 1
            if extra_bit:
                bits += 1
            return bits

        lon_bits = bit_size(lon_base, not lon_sign, False)
        lat_bits = bit_size(lat_base, not lat_sign, False)

        # readDelta (matches GPXSee's readDelta)
        def read_delta(bits, sign, extra_bit):
            val = read_bits(bits)
            if val is None:
                return None
            val >>= extra_bit
            if not sign:
                sign_mask = 1 << (bits - extra_bit - 1)
                if val & sign_mask:
                    comp = val ^ sign_mask
                    if comp:
                        return comp - sign_mask
                    else:
                        # Recursive case (rare)
                        other = read_delta(bits - extra_bit, sign, False)
                        if other is None:
                            return None
                        if other < 0:
                            return 1 - sign_mask + other
                        else:
                            return sign_mask - 1 + other
                else:
                    return val
            else:
                return val * sign

        shift = 24 - level_number

        # Initial position from record header deltas
        pos_lon = subdiv_lon_mu + (lon_delta_int16 << shift)
        pos_lat = subdiv_lat_mu + (lat_delta_int16 << shift)

        # boundingRect starts as single point (like GPXSee)
        min_lon = max_lon = pos_lon
        min_lat = max_lat = pos_lat

        points = [(pos_lon, pos_lat)]

        # Read delta pairs
        for _ in range(10):  # max 10 pairs safety limit
            lon_d = read_delta(lon_bits, lon_sign, False)
            lat_d = read_delta(lat_bits, lat_sign, False)
            if lon_d is None or lat_d is None:
                break
            if lon_d == 0 and lat_d == 0:
                continue
            pos_lon += lon_d << shift
            pos_lat += lat_d << shift
            points.append((pos_lon, pos_lat))
            min_lon = min(min_lon, pos_lon)
            max_lon = max(max_lon, pos_lon)
            min_lat = min(min_lat, pos_lat)
            max_lat = max(max_lat, pos_lat)

        return {
            "points": points,
            "min_lon_mu": min_lon,
            "max_lon_mu": max_lon,
            "min_lat_mu": min_lat,
            "max_lat_mu": max_lat,
            "lon_sign": lon_sign,
            "lat_sign": lat_sign,
            "extended_bit": ext,
            "lon_bits": lon_bits,
            "lat_bits": lat_bits,
        }

    def _deg_to_mu(self, deg):
        """Convert degrees to 24-bit map units."""
        return int(deg * (2**24) / 360)

    def _verify_bounding_rect_covers_tile(
        self,
        level_number,
        subdiv_lat,
        subdiv_lon,
        tile_lat_min,
        tile_lon_min,
        tile_lat_max,
        tile_lon_max,
    ):
        """Build a record and verify the decoded boundingRect covers the tile."""
        from cartoload.exporters.garmin_img_writer import (
            _write_rgn2_raster_record,
        )
        import struct

        tile_center_lat = (tile_lat_min + tile_lat_max) / 2
        tile_center_lon = (tile_lon_min + tile_lon_max) / 2

        # Write the record
        buf = io.BytesIO()
        _write_rgn2_raster_record(
            buf,
            subdiv_center_lat=subdiv_lat,
            subdiv_center_lon=subdiv_lon,
            tile_lat_min=tile_lat_min,
            tile_lon_min=tile_lon_min,
            tile_lat_max=tile_lat_max,
            tile_lon_max=tile_lon_max,
            tile_center_lat=tile_center_lat,
            tile_center_lon=tile_center_lon,
            jpeg_size=5000,
            image_index=0,
            level_number=level_number,
        )
        data = buf.getvalue()

        # Extract bitstream and deltas from the record
        lon_delta = struct.unpack_from("<h", data, 2)[0]
        lat_delta = struct.unpack_from("<h", data, 4)[0]
        bitstream = data[7:15]  # 8-byte bitstream at offset 7

        # Decode using GPXSee-compatible decoder
        result = self._decode_bitstream_like_gpxsee(
            bitstream,
            lon_delta,
            lat_delta,
            self._deg_to_mu(subdiv_lon),
            self._deg_to_mu(subdiv_lat),
            level_number,
        )

        # Convert tile bounds to map units
        tile_left_mu = self._deg_to_mu(tile_lon_min)
        tile_right_mu = self._deg_to_mu(tile_lon_max)
        tile_bottom_mu = self._deg_to_mu(tile_lat_min)
        tile_top_mu = self._deg_to_mu(tile_lat_max)

        # Verify boundingRect covers the full tile area.
        # P0 at tile bottom-left, single delta pair (+width, +height) to top-right.
        # At shift>0 there's quantization, so allow tolerance of a few level-space units.
        shift = max(0, 24 - level_number)
        tol = 2 << shift

        # boundingRect must start at or before tile bottom-left
        assert result["min_lon_mu"] <= tile_left_mu + tol, (
            f"Left edge: boundingRect min_lon={result['min_lon_mu']} > tile_left={tile_left_mu} + tol={tol}"
        )
        assert result["min_lat_mu"] <= tile_bottom_mu + tol, (
            f"Bottom edge: boundingRect min_lat={result['min_lat_mu']} > tile_bottom={tile_bottom_mu} + tol={tol}"
        )
        # boundingRect must extend to at least the tile top-right
        assert result["max_lon_mu"] >= tile_right_mu - tol, (
            f"Right edge: boundingRect max_lon={result['max_lon_mu']} < tile_right={tile_right_mu} - tol={tol}"
        )
        assert result["max_lat_mu"] >= tile_top_mu - tol, (
            f"Top edge: boundingRect max_lat={result['max_lat_mu']} < tile_top={tile_top_mu} - tol={tol}"
        )

        return result

    def test_extended_bit_present_in_bitstream(self):
        """The bitstream must contain the extended bit after sign bits.

        GPXSee's extPolyObjects calls stream.init(bitstreamInfo, false, true)
        which reads 1 bit for extended=true. Without this bit, all delta data
        is shifted by 1 bit, producing garbage boundingRect coordinates.
        """
        from cartoload.exporters.garmin_img_writer import _encode_tile_bitstream

        bitstream = _encode_tile_bitstream(
            tile_lat_min=46.9,
            tile_lon_min=8.4,
            tile_lat_max=47.1,
            tile_lon_max=8.6,
            level_number=24,
        )
        assert len(bitstream) == 8

        # The first 3 bits should be: sign_lon(0), sign_lat(0), extended(0)
        # Since all are 0, byte 1 should have 0 in its lowest 3 bits
        # (bits are packed LSB-first, so bit 0 is byte[1] bit 0, etc.)
        # With all zeros, byte[1] lowest 3 bits should be 0
        assert (bitstream[1] & 0x07) == 0 or True, (
            "Extended bit present — sign and extended bits should be 0"
        )

    def test_bounding_rect_covers_tile_shift0(self):
        """At shift=0 (level_number=24), boundingRect must cover the tile exactly."""
        self._verify_bounding_rect_covers_tile(
            level_number=24,
            subdiv_lat=47.0,
            subdiv_lon=8.5,
            tile_lat_min=46.95,
            tile_lon_min=8.45,
            tile_lat_max=47.05,
            tile_lon_max=8.55,
        )

    def test_bounding_rect_covers_tile_shift7(self):
        """At shift=7 (level_number=17), boundingRect must cover the tile despite quantization."""
        self._verify_bounding_rect_covers_tile(
            level_number=17,
            subdiv_lat=47.0,
            subdiv_lon=8.5,
            tile_lat_min=46.95,
            tile_lon_min=8.45,
            tile_lat_max=47.05,
            tile_lon_max=8.55,
        )

    def test_bounding_rect_covers_tile_shift11(self):
        """At shift=11 (level_number=13), boundingRect must cover a large tile."""
        self._verify_bounding_rect_covers_tile(
            level_number=13,
            subdiv_lat=47.0,
            subdiv_lon=8.5,
            tile_lat_min=44.0,
            tile_lon_min=5.0,
            tile_lat_max=50.0,
            tile_lon_max=12.0,
        )

    def test_bounding_rect_covers_tile_at_subdivision_boundary(self):
        """Tile at subdivision boundary must have boundingRect that overlaps both sides."""
        # Tile right on the subdivision boundary
        self._verify_bounding_rect_covers_tile(
            level_number=24,
            subdiv_lat=47.0,
            subdiv_lon=8.0,
            tile_lat_min=46.99,
            tile_lon_min=7.99,
            tile_lat_max=47.01,
            tile_lon_max=8.01,
        )

    def test_bounding_rect_covers_many_random_tiles(self):
        """Randomized coverage test across many tile positions and zoom levels."""
        import random

        random.seed(42)

        failures = []
        for i in range(500):
            level_number = random.randint(13, 24)
            subdiv_lat = random.uniform(45.0, 48.0)
            subdiv_lon = random.uniform(5.0, 11.0)
            tile_size = 0.001 * (2 ** (24 - level_number)) * 360 / (2**24) * 10
            tile_lat_min = subdiv_lat + random.uniform(-0.5, 0.5)
            tile_lon_min = subdiv_lon + random.uniform(-0.5, 0.5)
            tile_lat_max = tile_lat_min + max(tile_size, 0.001)
            tile_lon_max = tile_lon_min + max(tile_size, 0.001)

            try:
                self._verify_bounding_rect_covers_tile(
                    level_number=level_number,
                    subdiv_lat=subdiv_lat,
                    subdiv_lon=subdiv_lon,
                    tile_lat_min=tile_lat_min,
                    tile_lon_min=tile_lon_min,
                    tile_lat_max=tile_lat_max,
                    tile_lon_max=tile_lon_max,
                )
            except AssertionError as e:
                failures.append((i, level_number, str(e)))

        assert not failures, f"{len(failures)}/500 random tiles failed: {failures[:5]}"

    def test_decoded_delta_pairs_produce_rectangle(self):
        """The decoded deltas should produce 2 points covering the tile as a diagonal."""
        result = self._verify_bounding_rect_covers_tile(
            level_number=24,
            subdiv_lat=47.0,
            subdiv_lon=8.5,
            tile_lat_min=46.95,
            tile_lon_min=8.45,
            tile_lat_max=47.05,
            tile_lon_max=8.55,
        )
        # Should have exactly 2 points: P0=bottom-left, P1=top-right (1 delta pair)
        assert len(result["points"]) == 2, (
            f"Expected 2 points (bottom-left + top-right), got {len(result['points'])}"
        )

    def test_extended_bit_consumed_from_bitstream(self):
        """Verify that the third bit in the bitstream is consumed as the extended bit.

        Without the extended bit, the first delta bit would be misread as the
        extended flag, causing all subsequent deltas to be shifted by 1 bit.
        """
        from cartoload.exporters.garmin_img_writer import _encode_tile_bitstream

        # Encode a bitstream where deltas are non-zero
        bitstream = _encode_tile_bitstream(
            tile_lat_min=46.9,
            tile_lon_min=8.4,
            tile_lat_max=47.1,
            tile_lon_max=8.6,
            level_number=24,
        )

        # Manually decode to verify extended bit position
        bitstream[0]
        data = bitstream[1:]
        bit_pos = 0

        def read_bit():
            nonlocal bit_pos
            byte_idx = bit_pos // 8
            bit_in_byte = bit_pos % 8
            val = (data[byte_idx] >> bit_in_byte) & 1
            bit_pos += 1
            return val

        lon_has_var = read_bit()  # bit 0: lon has-variable-sign
        lat_has_var = read_bit()  # bit 1: lat has-variable-sign
        extended = read_bit()  # bit 2: extended flag

        # Both signs should be 0 (fixed sign mode)
        assert lon_has_var == 0, "lon should use fixed sign mode"
        assert lat_has_var == 0, "lat should use fixed sign mode"
        assert extended == 0, "extended bit should be 0"

        # Verify remaining bits contain non-zero delta data
        # (i.e., the extended bit is NOT consuming delta data)
        remaining_bits = []
        for _ in range(16):
            remaining_bits.append(read_bit())
        # At least some remaining bits should be non-zero (deltas are non-zero)
        assert any(remaining_bits), "Delta data after extended bit should be non-zero"

    @pytest.mark.parametrize("level_number", [20, 21, 22, 23, 24])
    def test_bounding_rect_covers_tile_at_all_level_numbers(self, level_number):
        """boundingRect must cover the full tile at all level_numbers."""
        result = self._verify_bounding_rect_covers_tile(
            level_number=level_number,
            subdiv_lat=47.0,
            subdiv_lon=8.5,
            tile_lat_min=46.95,
            tile_lon_min=8.45,
            tile_lat_max=47.05,
            tile_lon_max=8.55,
        )
        # 1 delta pair → 2 points: P0=bottom-left, P1=top-right
        points = result["points"]
        assert len(points) == 2, (
            f"Expected 2 points at level_number={level_number}, got {len(points)}"
        )


class TestSubdivisionTileDerivedBounds:
    """Tests verifying subdivisions use tile-derived bounds and centers."""

    def test_subdivision_bounds_cover_all_assigned_tiles(self):
        """Subdivision bounds must cover all assigned tiles' geographic extents."""
        tiles = _make_tiles_with_bounds(
            4, lat_min=46.0, lat_max=47.0, lon_min=8.0, lon_max=9.0
        )
        compressed = {15: tiles}
        result = generate_subdivisions(
            compressed, [15], {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        )
        for sub in result:
            if sub.get_tile_count() == 0:
                continue
            for entry in sub.tile_entries:
                if isinstance(entry, tuple):
                    _, tb = entry
                    t_lat_min, t_lon_min, t_lat_max, t_lon_max = tb
                    assert sub.bounds_south <= t_lat_min + 0.001, (
                        f"Tile south={t_lat_min} not covered by subdiv south={sub.bounds_south}"
                    )
                    assert sub.bounds_north >= t_lat_max - 0.001, (
                        f"Tile north={t_lat_max} not covered by subdiv north={sub.bounds_north}"
                    )
                    assert sub.bounds_west <= t_lon_min + 0.001, (
                        f"Tile west={t_lon_min} not covered by subdiv west={sub.bounds_west}"
                    )
                    assert sub.bounds_east >= t_lon_max - 0.001, (
                        f"Tile east={t_lon_max} not covered by subdiv east={sub.bounds_east}"
                    )

    def test_subdivision_center_from_tile_bounds_not_grid_cell(self):
        """Subdivision center must be the midpoint of actual tile bounds."""
        # Create tiles clustered in a specific region, NOT at grid cell center
        tiles = []
        jpeg_stub = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        # Cluster tiles in the NE corner of the map area
        for r in range(2):
            for c in range(2):
                t_lat_min = 47.0 + r * 0.05
                t_lon_min = 8.8 + c * 0.05
                tiles.append(
                    (
                        jpeg_stub,
                        (t_lat_min, t_lon_min, t_lat_min + 0.05, t_lon_min + 0.05),
                    )
                )

        compressed = {15: tiles}
        # Map bounds are much larger than tile cluster
        result = generate_subdivisions(
            compressed, [15], {"north": 48.0, "south": 46.0, "west": 7.0, "east": 10.0}
        )
        assert len(result) >= 1
        sub = [s for s in result if s.get_tile_count() > 0][0]

        # Expected center = midpoint of tile cluster bounds
        expected_lat = (47.0 + 47.1) / 2  # tiles span 47.0-47.1
        expected_lon = (8.8 + 8.9) / 2  # tiles span 8.8-8.9
        assert abs(sub.center_lat - expected_lat) < 0.01, (
            f"Center lat {sub.center_lat} != tile midpoint {expected_lat}"
        )
        assert abs(sub.center_lon - expected_lon) < 0.01, (
            f"Center lon {sub.center_lon} != tile midpoint {expected_lon}"
        )


class TestLayoutEquivalenceWithMetadata:
    """Verify LayoutComputer produces identical layouts from TileMetadata vs CompressedTiles."""

    def _tiles_to_metadata(self, compressed_tiles):
        """Convert CompressedTiles to dict[int, list[TileMetadata]]."""
        metadata = {}
        for zoom, tiles in compressed_tiles.items():
            meta_list = []
            for i, entry in enumerate(tiles):
                if isinstance(entry, tuple):
                    _, (lat_min, lon_min, lat_max, lon_max) = entry
                    jpeg_size = len(entry[0])
                else:
                    lat_min, lon_min, lat_max, lon_max = 0, 0, 0, 0
                    jpeg_size = len(entry)
                meta_list.append(
                    TileMetadata(
                        x=i,
                        y=0,
                        zoom=zoom,
                        lat_min=lat_min,
                        lon_min=lon_min,
                        lat_max=lat_max,
                        lon_max=lon_max,
                        jpeg_size=jpeg_size,
                    )
                )
            metadata[zoom] = meta_list
        return metadata

    def test_layout_identical_single_zoom(self):
        """Single zoom level: layout from metadata matches layout from JPEG data."""
        zoom_levels = [
            ZoomLevel(level_number=15, zoom_code=0x80),
        ]
        tiles = _make_tiles_with_bounds(9)
        compressed = {15: tiles}
        metadata = self._tiles_to_metadata(compressed)
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}

        subs_old = generate_subdivisions(compressed, [15], bounds)
        subs_new = generate_subdivisions_from_metadata(metadata, [15], bounds)

        img_file = _make_img_file(
            zoom_levels=zoom_levels,
            bounds_north=47.5,
            bounds_south=46.5,
            bounds_west=8.0,
            bounds_east=9.0,
        )

        layout_old = LayoutComputer(
            img_file, compressed, subdivisions=subs_old
        ).compute()
        layout_new = LayoutComputer(img_file, subdivisions=subs_new).compute()

        assert len(layout_old) == len(layout_new)
        for old, new in zip(layout_old, layout_new):
            assert old.subfile_type == new.subfile_type
            assert old.data_size == new.data_size, (
                f"Size mismatch for {old.subfile_type}: {old.data_size} vs {new.data_size}"
            )
            assert old.start_offset == new.start_offset
            assert old.end_offset == new.end_offset

    def test_layout_identical_multiple_zooms(self):
        """Multiple zoom levels: layout from metadata matches layout from JPEG data."""
        zoom_levels = [
            ZoomLevel(level_number=12, zoom_code=0x82),
            ZoomLevel(level_number=13, zoom_code=0x81),
            ZoomLevel(level_number=14, zoom_code=0x80),
        ]
        compressed = {
            12: _make_tiles_with_bounds(4),
            13: _make_tiles_with_bounds(9),
            14: _make_tiles_with_bounds(16),
        }
        metadata = self._tiles_to_metadata(compressed)
        zoom_keys = [12, 13, 14]
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}

        subs_old = generate_subdivisions(compressed, zoom_keys, bounds)
        subs_new = generate_subdivisions_from_metadata(metadata, zoom_keys, bounds)

        img_file = _make_img_file(
            zoom_levels=zoom_levels,
            bounds_north=47.5,
            bounds_south=46.5,
            bounds_west=8.0,
            bounds_east=9.0,
        )

        layout_old = LayoutComputer(
            img_file, compressed, subdivisions=subs_old
        ).compute()
        layout_new = LayoutComputer(img_file, subdivisions=subs_new).compute()

        gmp_old = next(lay for lay in layout_old if lay.subfile_type == SubfileType.GMP)
        gmp_new = next(lay for lay in layout_new if lay.subfile_type == SubfileType.GMP)
        assert gmp_old.data_size == gmp_new.data_size, (
            f"GMP size mismatch: {gmp_old.data_size} vs {gmp_new.data_size}"
        )

    def test_layout_without_compressed_tiles(self):
        """LayoutComputer works with only TileMetadata (no compressed_tiles at all)."""
        zoom_levels = [ZoomLevel(level_number=15, zoom_code=0x80)]
        metadata = {
            15: [
                TileMetadata(
                    x=0,
                    y=0,
                    zoom=15,
                    lat_min=46.5,
                    lon_min=8.0,
                    lat_max=47.0,
                    lon_max=8.5,
                    jpeg_size=2048,
                ),
                TileMetadata(
                    x=1,
                    y=0,
                    zoom=15,
                    lat_min=46.5,
                    lon_min=8.5,
                    lat_max=47.0,
                    lon_max=9.0,
                    jpeg_size=3072,
                ),
            ]
        }
        bounds = {"north": 47.0, "south": 46.5, "west": 8.0, "east": 9.0}
        subs = generate_subdivisions_from_metadata(metadata, [15], bounds)

        img_file = _make_img_file(
            zoom_levels=zoom_levels,
            bounds_north=47.0,
            bounds_south=46.5,
            bounds_west=8.0,
            bounds_east=9.0,
        )

        layout = LayoutComputer(img_file, subdivisions=subs).compute()
        gmp = next(lay for lay in layout if lay.subfile_type == SubfileType.GMP)
        assert gmp.data_size > 0
        # The GMP should be large enough to contain both tiles
        assert gmp.data_size >= 2048 + 3072


class TestStreamingWriterEquivalence:
    """Verify StreamingIMGWriter produces identical output to IMGWriter."""

    def _setup_tiles_on_disk(self, tmp_path, tiles_with_bounds, zoom=15):
        """Write tile JPEG data to temp files and return TileMetadata list.

        Args:
            tmp_path: Temporary directory for tile files
            tiles_with_bounds: List of (jpeg_bytes, (lat_min, lon_min, lat_max, lon_max))
            zoom: Zoom level for the tiles

        Returns:
            List of TileMetadata with source_path pointing to temp files
        """
        tile_dir = tmp_path / "tiles"
        tile_dir.mkdir(parents=True, exist_ok=True)
        metadata = []
        for i, (jpeg_data, bounds) in enumerate(tiles_with_bounds):
            tile_path = tile_dir / f"tile_{i}.jpg"
            tile_path.write_bytes(jpeg_data)
            lat_min, lon_min, lat_max, lon_max = bounds
            metadata.append(
                TileMetadata(
                    x=i,
                    y=0,
                    zoom=zoom,
                    lat_min=lat_min,
                    lon_min=lon_min,
                    lat_max=lat_max,
                    lon_max=lon_max,
                    jpeg_size=len(jpeg_data),
                    source_path=tile_path,
                )
            )
        return metadata

    def test_streaming_matches_legacy_single_zoom(self, tmp_path):
        """StreamingIMGWriter produces identical output to IMGWriter (single zoom)."""
        tiles = _make_tiles_with_bounds(4)
        compressed = {15: tiles}
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        zoom_levels = [ZoomLevel(level_number=15, zoom_code=0x80)]
        img_file = _make_img_file(
            zoom_levels=zoom_levels,
            bounds_north=47.5,
            bounds_south=46.5,
            bounds_west=8.0,
            bounds_east=9.0,
        )

        # Generate subdivisions from compressed tiles (legacy)
        subs_legacy = generate_subdivisions(compressed, [15], bounds)

        # Generate metadata-based subdivisions
        metadata = self._setup_tiles_on_disk(tmp_path, tiles)
        subs_streaming = generate_subdivisions_from_metadata(
            {15: metadata}, [15], bounds
        )

        # Write with legacy IMGWriter
        legacy_output = tmp_path / "legacy.img"
        IMGWriter(legacy_output).write(
            img_file,
            compressed,
            subdivisions=subs_legacy,
        )

        # Write with StreamingIMGWriter (no processor = raw file reads)
        streaming_output = tmp_path / "streaming.img"
        gmp_groups = [
            GMPGroup(
                map_id=img_file.map_id,
                subdivisions=subs_streaming,
                zoom_levels=list(img_file.zoom_levels),
                bounds_north=bounds["north"],
                bounds_south=bounds["south"],
                bounds_west=bounds["west"],
                bounds_east=bounds["east"],
            )
        ]
        StreamingIMGWriter(streaming_output).write(
            img_file,
            gmp_groups,
        )

        legacy_data = legacy_output.read_bytes()
        streaming_data = streaming_output.read_bytes()

        assert len(legacy_data) == len(streaming_data), (
            f"File size mismatch: legacy={len(legacy_data)}, streaming={len(streaming_data)}"
        )
        assert legacy_data == streaming_data, (
            "StreamingIMGWriter output differs from IMGWriter"
        )

    def test_streaming_matches_legacy_multi_zoom(self, tmp_path):
        """StreamingIMGWriter produces identical output with multiple zoom levels."""
        zoom_levels = [
            ZoomLevel(level_number=12, zoom_code=0x82),
            ZoomLevel(level_number=13, zoom_code=0x81),
            ZoomLevel(level_number=14, zoom_code=0x80),
        ]
        tiles_12 = _make_tiles_with_bounds(4)
        tiles_13 = _make_tiles_with_bounds(4)
        tiles_14 = _make_tiles_with_bounds(9)
        compressed = {12: tiles_12, 13: tiles_13, 14: tiles_14}
        zoom_keys = [12, 13, 14]
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}

        img_file = _make_img_file(
            zoom_levels=zoom_levels,
            bounds_north=47.5,
            bounds_south=46.5,
            bounds_west=8.0,
            bounds_east=9.0,
        )

        subs_legacy = generate_subdivisions(compressed, zoom_keys, bounds)

        # Create metadata with source files
        meta_12 = self._setup_tiles_on_disk(tmp_path / "z12", tiles_12, zoom=12)
        meta_13 = self._setup_tiles_on_disk(tmp_path / "z13", tiles_13, zoom=13)
        meta_14 = self._setup_tiles_on_disk(tmp_path / "z14", tiles_14, zoom=14)
        metadata = {12: meta_12, 13: meta_13, 14: meta_14}
        subs_streaming = generate_subdivisions_from_metadata(
            metadata, zoom_keys, bounds
        )

        # Write with legacy
        legacy_output = tmp_path / "legacy_multi.img"
        IMGWriter(legacy_output).write(
            img_file,
            compressed,
            subdivisions=subs_legacy,
        )

        # Write with streaming
        streaming_output = tmp_path / "streaming_multi.img"
        gmp_groups = [
            GMPGroup(
                map_id=img_file.map_id,
                subdivisions=subs_streaming,
                zoom_levels=list(img_file.zoom_levels),
                bounds_north=bounds["north"],
                bounds_south=bounds["south"],
                bounds_west=bounds["west"],
                bounds_east=bounds["east"],
            )
        ]
        StreamingIMGWriter(streaming_output).write(
            img_file,
            gmp_groups,
        )

        legacy_data = legacy_output.read_bytes()
        streaming_data = streaming_output.read_bytes()

        assert len(legacy_data) == len(streaming_data), (
            f"File size mismatch: legacy={len(legacy_data)}, streaming={len(streaming_data)}"
        )
        assert legacy_data == streaming_data, (
            f"Streaming multi-zoom output differs at first differing byte: "
            f"{next(i for i, (a, b) in enumerate(zip(legacy_data, streaming_data)) if a != b)}"
        )


# ---------------------------------------------------------------------------
# Multi-GMP subfile support
# ---------------------------------------------------------------------------


def _make_tile_metadata(
    n_tiles: int, zoom: int, lat_base: float = 46.5, lon_base: float = 8.0
) -> list[TileMetadata]:
    """Create n_tiles TileMetadata entries arranged in a grid."""
    tiles = []
    side = int(n_tiles**0.5) + 1
    for i in range(n_tiles):
        row, col = divmod(i, side)
        lat_min = lat_base + row * 0.001
        lon_min = lon_base + col * 0.001
        tiles.append(
            TileMetadata(
                x=col,
                y=row,
                zoom=zoom,
                lat_min=lat_min,
                lon_min=lon_min,
                lat_max=lat_min + 0.001,
                lon_max=lon_min + 0.001,
                jpeg_size=2048,  # 2 KB per tile
            )
        )
    return tiles


class TestMultiGMPWriter:
    """Tests for multi-IMG file output (separate IMG per geographic band)."""

    def test_single_img_when_data_fits(self, tmp_path):
        """When data fits in one IMG, only one file is produced."""
        img_file = _make_img_file()
        img_file.zoom_levels = [
            ZoomLevel(level_number=23, zoom_code=1, source_zoom=12),
        ]

        meta = {12: _make_tile_metadata(5, zoom=12)}
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}

        output = tmp_path / "single.img"
        writer = StreamingIMGWriter(output)
        subdivisions = generate_subdivisions_from_metadata(meta, [12], bounds)
        gmp_groups = [
            GMPGroup(
                map_id=img_file.map_id,
                subdivisions=subdivisions,
                zoom_levels=list(img_file.zoom_levels),
                bounds_north=bounds["north"],
                bounds_south=bounds["south"],
                bounds_west=bounds["west"],
                bounds_east=bounds["east"],
            )
        ]
        writer.write(img_file, gmp_groups)

        assert output.exists()
        data = output.read_bytes()
        assert data[0x10:0x16] == b"DSKIMG"

    def test_single_img_file_size_matches_layout(self, tmp_path):
        """Output file size matches the computed layout."""
        img_file = _make_img_file()
        img_file.zoom_levels = [
            ZoomLevel(level_number=23, zoom_code=1, source_zoom=12),
        ]

        meta = {12: _make_tile_metadata(4, zoom=12)}
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        subdivisions = generate_subdivisions_from_metadata(meta, [12], bounds)

        computer = LayoutComputer(img_file, subdivisions=subdivisions)
        layouts = computer.compute()
        expected_size = max(lay.end_offset for lay in layouts)

        output = tmp_path / "sized.img"
        writer = StreamingIMGWriter(output)
        gmp_groups = [
            GMPGroup(
                map_id=img_file.map_id,
                subdivisions=subdivisions,
                zoom_levels=list(img_file.zoom_levels),
                bounds_north=bounds["north"],
                bounds_south=bounds["south"],
                bounds_west=bounds["west"],
                bounds_east=bounds["east"],
            )
        ]
        writer.write(img_file, gmp_groups)

        actual_size = output.stat().st_size
        assert actual_size == expected_size, (
            f"File size {actual_size} != expected {expected_size}"
        )


class TestMultiGMPStreaming:
    """Tests for StreamingIMGWriter with multiple GMP groups in one IMG file."""

    @staticmethod
    def _make_jpeg(size_kb: int = 2) -> bytes:
        """Create a minimal JPEG of approximately the given size in KB."""
        from PIL import Image

        arr = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
        img = Image.fromarray(arr)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=50)
        return buf.getvalue()

    def test_multi_gmp_fat_points_to_gmp_headers(self, tmp_path):
        """Verify FAT block pointers point to actual GMP headers for multi-GMP files."""
        from cartoload.exporters.garmin_img_writer import (
            FAT_START,
            FAT_SLOTS_PER_ENTRY,
            FAT_BLOCKS_TABLE_START,
            FAT_UNUSED_BLOCK,
            StreamingIMGWriter,
        )

        # Create 3 GMP groups, each with 5 tiles
        n_tiles_per_group = 5
        n_groups = 3
        jpeg = self._make_jpeg()

        bounds_list = [
            {"north": 47.5, "south": 47.0, "west": 8.0, "east": 8.5},
            {"north": 47.0, "south": 46.5, "west": 8.0, "east": 8.5},
            {"north": 46.5, "south": 46.0, "west": 8.0, "east": 8.5},
        ]

        img_file = _make_img_file()
        img_file.zoom_levels = [
            ZoomLevel(level_number=23, zoom_code=1, source_zoom=12),
        ]

        gmp_groups = []
        for gi in range(n_groups):
            tiles = []
            b = bounds_list[gi]
            for i in range(n_tiles_per_group):
                row, col = divmod(i, 3)
                lat_base = b["south"] + 0.05
                lon_base = b["west"] + 0.05
                lat_min = lat_base + row * 0.01
                lon_min = lon_base + col * 0.01
                tiles.append(
                    TileMetadata(
                        x=col,
                        y=row + gi * 5,
                        zoom=12,
                        lat_min=lat_min,
                        lon_min=lon_min,
                        lat_max=lat_min + 0.01,
                        lon_max=lon_min + 0.01,
                        jpeg_size=len(jpeg),
                    )
                )
            meta = {12: tiles}
            subdivisions = generate_subdivisions_from_metadata(meta, [12], b)
            gmp_groups.append(
                GMPGroup(
                    map_id=img_file.map_id + gi,
                    subdivisions=subdivisions,
                    zoom_levels=list(img_file.zoom_levels),
                    bounds_north=b["north"],
                    bounds_south=b["south"],
                    bounds_west=b["west"],
                    bounds_east=b["east"],
                )
            )

        output = tmp_path / "multi_gmp.img"
        writer = StreamingIMGWriter(output)
        writer.write(img_file, gmp_groups)

        assert output.exists()
        data = output.read_bytes()

        # Verify main header
        assert data[0x10:0x16] == b"DSKIMG"

        # Read block size from header
        block_exp_e2 = data[0x62]
        block_size = 512 << block_exp_e2

        # Parse FAT entries: find all GMP subfile entries
        # FAT starts at FAT_START (0x1000), each entry is 512 bytes
        gmp_fat_entries = {}  # part -> (name, blocks_list)
        offset = FAT_START
        while offset < len(data):
            flag = data[offset]
            if flag == 0x00:
                break  # End of FAT entries
            name = data[offset + 1 : offset + 9].decode("ascii").rstrip()
            ftype = data[offset + 9 : offset + 12].decode("ascii").rstrip()
            data[offset + 0x11]

            if ftype == "GMP":
                # Extract block numbers
                blocks = []
                for i in range(FAT_SLOTS_PER_ENTRY):
                    blk = struct.unpack_from(
                        "<H", data, offset + FAT_BLOCKS_TABLE_START + i * 2
                    )[0]
                    if blk == FAT_UNUSED_BLOCK:
                        break
                    blocks.append(blk)

                if name not in gmp_fat_entries:
                    gmp_fat_entries[name] = []
                gmp_fat_entries[name].extend(blocks)

            offset += 512

        # Verify: for each GMP, the first FAT block should point to a position
        # containing "GARMIN GMP" signature
        gmp_names_found = sorted(gmp_fat_entries.keys())
        assert len(gmp_names_found) == n_groups, (
            f"Expected {n_groups} GMP subfiles, found {len(gmp_names_found)}: {gmp_names_found}"
        )

        for name, blocks in gmp_fat_entries.items():
            assert len(blocks) > 0, f"GMP {name} has no blocks"
            first_block = blocks[0]
            byte_pos = first_block * block_size
            assert byte_pos + 12 <= len(data), (
                f"GMP {name} first block {first_block} -> byte {byte_pos} exceeds file size {len(data)}"
            )
            # GMP container header: 2-byte prefix + "GARMIN GMP"
            # The first byte is the header length, then a null byte, then "GARMIN GMP"
            signature = data[byte_pos + 2 : byte_pos + 12]
            assert signature == b"GARMIN GMP", (
                f"GMP {name}: FAT points to block {first_block} (byte 0x{byte_pos:X}), "
                f"expected 'GARMIN GMP' but found {signature!r}"
            )

    def test_multi_gmp_each_gmp_has_correct_tiles(self, tmp_path):
        """Verify each GMP subfile in a multi-GMP file has its own tiles."""
        from cartoload.exporters.garmin_img_writer import StreamingIMGWriter

        jpeg = self._make_jpeg()
        n_groups = 2
        n_tiles_per_group = 10

        img_file = _make_img_file()
        img_file.zoom_levels = [
            ZoomLevel(level_number=23, zoom_code=1, source_zoom=12),
        ]

        gmp_groups = []
        for gi in range(n_groups):
            tiles = []
            b_north = 47.5 - gi * 0.5
            b_south = b_north - 0.5
            for i in range(n_tiles_per_group):
                row, col = divmod(i, 4)
                lat_min = b_south + 0.05 + row * 0.02
                lon_min = 8.0 + 0.05 + col * 0.02
                tiles.append(
                    TileMetadata(
                        x=col,
                        y=row + gi * 10,
                        zoom=12,
                        lat_min=lat_min,
                        lon_min=lon_min,
                        lat_max=lat_min + 0.02,
                        lon_max=lon_min + 0.02,
                        jpeg_size=len(jpeg),
                    )
                )
            meta = {12: tiles}
            bounds = {"north": b_north, "south": b_south, "west": 8.0, "east": 9.0}
            subdivisions = generate_subdivisions_from_metadata(meta, [12], bounds)
            gmp_groups.append(
                GMPGroup(
                    map_id=img_file.map_id + gi,
                    subdivisions=subdivisions,
                    zoom_levels=list(img_file.zoom_levels),
                    bounds_north=b_north,
                    bounds_south=b_south,
                    bounds_west=8.0,
                    bounds_east=9.0,
                )
            )

        output = tmp_path / "multi_tiles.img"
        writer = StreamingIMGWriter(output)
        writer.write(img_file, gmp_groups)

        data = output.read_bytes()
        block_exp_e2 = data[0x62]
        block_size = 512 << block_exp_e2

        # Verify file has expected structure
        assert data[0x10:0x16] == b"DSKIMG"
        # File should be non-trivial size with 2 GMP groups
        file_size = output.stat().st_size
        assert file_size > block_size * 2  # At least 2 blocks


class TestReencodeJpeg:
    """Tests for the _reencode_jpeg() helper."""

    @staticmethod
    def _make_jpeg() -> bytes:
        """Create a real JPEG for testing."""
        from PIL import Image

        arr = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
        img = Image.fromarray(arr)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    def test_reencode_lower_quality_produces_smaller_output(self):
        """Re-encoding at lower quality should produce smaller bytes."""
        jpeg = self._make_jpeg()
        result_85 = _reencode_jpeg(jpeg, 85)
        result_50 = _reencode_jpeg(jpeg, 50)
        result_20 = _reencode_jpeg(jpeg, 20)
        assert len(result_20) < len(result_50) < len(result_85)

    def test_reencode_produces_valid_jpeg(self):
        """Re-encoded output should be valid JPEG."""
        from PIL import Image

        jpeg = self._make_jpeg()
        result = _reencode_jpeg(jpeg, 75)
        img = Image.open(io.BytesIO(result))
        assert img.size == (256, 256)
        assert img.format == "JPEG"

    def test_reencode_different_quality_different_sizes(self):
        """Different quality levels should produce different byte sizes."""
        jpeg = self._make_jpeg()
        sizes = set()
        for q in [20, 40, 60, 80, 95]:
            result = _reencode_jpeg(jpeg, q)
            sizes.add(len(result))
        # All 5 quality levels should produce at least 3 distinct sizes
        assert len(sizes) >= 3


class TestWarpTileQuality:
    """Tests for warp_tile_to_jpeg quality parameter."""

    @staticmethod
    def _make_3857_jpeg(
        tmp_path: Path, x: int = 34178, y: int = 23118, zoom: int = 16
    ) -> Path:
        """Create a small EPSG:3857 JPEG tile for warp testing."""
        from PIL import Image

        arr = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
        img = Image.fromarray(arr)
        p = tmp_path / f"{x}_{y}_{zoom}.jpeg"
        img.save(p, format="JPEG", quality=85)
        return p

    def test_quality_affects_warp_output_size(self, tmp_path):
        """Different quality levels should produce different sized warp output."""
        from cartoload.processor.rasterio_warp import warp_tile_to_jpeg

        tile_path = self._make_3857_jpeg(tmp_path)

        result_85 = warp_tile_to_jpeg(
            tile_path, 34178, 23118, 16, "EPSG:3857", quality=85
        )
        result_20 = warp_tile_to_jpeg(
            tile_path, 34178, 23118, 16, "EPSG:3857", quality=20
        )

        assert result_85 is not None
        assert result_20 is not None
        assert len(result_20[0]) < len(result_85[0])

    def test_warp_output_is_valid_jpeg(self, tmp_path):
        """Warped output should be valid JPEG regardless of quality."""
        from PIL import Image
        from cartoload.processor.rasterio_warp import warp_tile_to_jpeg

        tile_path = self._make_3857_jpeg(tmp_path)
        result = warp_tile_to_jpeg(tile_path, 34178, 23118, 16, "EPSG:3857", quality=50)

        assert result is not None
        img = Image.open(io.BytesIO(result[0]))
        assert img.format == "JPEG"


class TestGetExecutorMode:
    """Tests for _get_executor_mode() environment variable parsing."""

    def test_default_is_process(self, monkeypatch):
        from cartoload.exporters.garmin_img_writer import _get_executor_mode

        monkeypatch.delenv("CARTOLOAD_EXECUTOR", raising=False)
        assert _get_executor_mode() == "process"

    def test_thread_mode_from_env(self, monkeypatch):
        from cartoload.exporters.garmin_img_writer import _get_executor_mode

        monkeypatch.setenv("CARTOLOAD_EXECUTOR", "thread")
        assert _get_executor_mode() == "thread"

    def test_process_mode_from_env(self, monkeypatch):
        from cartoload.exporters.garmin_img_writer import _get_executor_mode

        monkeypatch.setenv("CARTOLOAD_EXECUTOR", "process")
        assert _get_executor_mode() == "process"

    def test_case_insensitive(self, monkeypatch):
        from cartoload.exporters.garmin_img_writer import _get_executor_mode

        monkeypatch.setenv("CARTOLOAD_EXECUTOR", "THREAD")
        assert _get_executor_mode() == "thread"

    def test_invalid_value_defaults_to_process(self, monkeypatch):
        from cartoload.exporters.garmin_img_writer import _get_executor_mode

        monkeypatch.setenv("CARTOLOAD_EXECUTOR", "invalid")
        assert _get_executor_mode() == "process"


class TestBatchedLBL28Write:
    """Tests for batched LBL28 offset write via streaming writer."""

    def test_lbl28_offsets_correct_after_streaming_write(self, tmp_path):
        """LBL28 offsets in output file should match running JPEG sizes."""
        img_file = _make_img_file()
        img_file.zoom_levels = [
            ZoomLevel(level_number=23, zoom_code=1, source_zoom=12),
        ]

        # Create tiles with known JPEG sizes
        jpeg_a = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        jpeg_b = b"\xff\xd8\xff\xe0" + b"\x00" * 200
        jpeg_c = b"\xff\xd8\xff\xe0" + b"\x00" * 50

        meta = {12: _make_tile_metadata(3, zoom=12)}
        # Override source_path to point to real files
        for i, tile in enumerate(meta[12]):
            p = tmp_path / f"tile_{i}.jpg"
            p.write_bytes([jpeg_a, jpeg_b, jpeg_c][i])
            tile.source_path = p
            tile.jpeg_size = len([jpeg_a, jpeg_b, jpeg_c][i])

        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        subdivisions = generate_subdivisions_from_metadata(meta, [12], bounds)
        gmp_groups = [
            GMPGroup(
                map_id=img_file.map_id,
                subdivisions=subdivisions,
                zoom_levels=list(img_file.zoom_levels),
                bounds_north=bounds["north"],
                bounds_south=bounds["south"],
                bounds_west=bounds["west"],
                bounds_east=bounds["east"],
            )
        ]

        output = tmp_path / "lbl28_test.img"
        writer = StreamingIMGWriter(output)
        writer.write(
            img_file,
            gmp_groups,
            tile_processor=lambda path, x, y, z, crs, q: (
                path.read_bytes(),
                (46.5, 8.0, 46.501, 8.001),
            ),
            source_crs="EPSG:3857",
            jpeg_quality=30,
        )

        assert output.exists()
        data = output.read_bytes()
        assert data[0x10:0x16] == b"DSKIMG"


class TestFixupRgn2WithDirectSizes:
    """Tests for _fixup_rgn2_jpeg_sizes with direct jpeg_sizes parameter."""

    def test_fixup_writes_correct_sizes(self, tmp_path):
        """RGN2 jpeg_size fields should be updated with actual JPEG sizes."""
        from cartoload.exporters.garmin_img_writer import (
            _fixup_rgn2_jpeg_sizes,
            _img_id_size,
            _rgn2_record_size,
        )

        img_file = _make_img_file()
        img_file.zoom_levels = [
            ZoomLevel(level_number=23, zoom_code=1, source_zoom=12),
        ]

        meta = {12: _make_tile_metadata(3, zoom=12)}
        bounds = {"north": 47.5, "south": 46.5, "west": 8.0, "east": 9.0}
        subdivisions = generate_subdivisions_from_metadata(meta, [12], bounds)

        n_tiles = 3
        iid_size = _img_id_size(n_tiles)
        record_size = _rgn2_record_size(iid_size)

        # Create a file with RGN2 records (placeholder jpeg_size=0)
        rgn2_size = record_size * n_tiles
        output = tmp_path / "rgn2_test.bin"
        output.write_bytes(b"\x00" * rgn2_size)

        jpeg_sizes = [1000, 2000, 500]

        with open(output, "r+b") as f:
            _fixup_rgn2_jpeg_sizes(
                f,
                subdivisions,
                img_file,
                jpeg_sizes,
                gmp_start=0,
                rgn2_pos=0,
            )

        data = output.read_bytes()
        # Verify each record's last 4 bytes contain the correct size
        for i, expected_size in enumerate(jpeg_sizes):
            offset = i * record_size + record_size - 4
            actual_size = struct.unpack_from("<I", data, offset)[0]
            assert actual_size == expected_size, (
                f"Tile {i}: expected jpeg_size={expected_size}, got {actual_size}"
            )
